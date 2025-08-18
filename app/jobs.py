# app/jobs.py
import uuid, os, tempfile, subprocess, json, time, requests, sys, logging
from google.cloud import storage
from google import generativeai as genai
from google.auth import default
from google.auth.transport.requests import Request
from google.cloud import aiplatform
from elevenlabs.client import ElevenLabs
from rq import Queue
import redis
from app.credential_utils import get_credentials_or_default, create_google_cloud_credentials, create_storage_client, clear_sensitive_data
from google.cloud.storage import Blob

# Note: Gemini API is configured per-request to use appropriate credentials
# Global configuration removed to prevent interference with user-provided credentials

# Configure Google Cloud Storage with separate credentials
BUCKET = os.getenv("GCS_BUCKET")
# Use explicit credentials for Cloud Storage if provided
gcs_credentials_path = os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH")
if gcs_credentials_path:
    client = storage.Client.from_service_account_json(gcs_credentials_path)
else:
    # Fall back to default credentials
    client = storage.Client()
bucket = client.bucket(BUCKET)

def make_blob_public_safe(blob: Blob) -> str:
    """
    Make a blob publicly accessible, handling both uniform and legacy bucket access.
    Returns the public URL.
    """
    try:
        # Try legacy ACL method first
        blob.make_public()
        return blob.public_url
    except Exception as e:
        if "uniform bucket-level access" in str(e).lower():
            # For uniform bucket-level access, we need to ensure the bucket allows public access
            # The blob is already publicly accessible if the bucket allows it
            # Return the public URL format
            return f"https://storage.googleapis.com/{blob.bucket.name}/{blob.name}"
        else:
            # Re-raise other exceptions
            raise e

# Setup logging for debug output
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Redis connection and queue setup
redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
q = Queue(connection=redis_conn)

def convert_audio_format(audio_bytes: bytes, source_format: str, target_format: str) -> tuple[bytes, str]:
    """
    Convert audio from one format to another using PyDub.
    Returns (converted_audio_bytes, mime_type)
    """
    from pydub import AudioSegment
    from io import BytesIO
    
    # Load audio from bytes
    if source_format == "pcm":
        # For raw PCM data from ElevenLabs, specify the audio parameters
        audio = AudioSegment.from_file(
            BytesIO(audio_bytes), 
            format="raw", 
            frame_rate=44100, 
            channels=1, 
            sample_width=2
        )
    else:
        audio = AudioSegment.from_file(BytesIO(audio_bytes), format=source_format)
    
    # Convert to target format
    output = BytesIO()
    
    if target_format == "m4a":
        # Export as M4A (AAC in MP4 container)
        audio.export(output, format="mp4", codec="aac")
        mime_type = "audio/mp4"
    elif target_format == "mp3":
        audio.export(output, format="mp3")
        mime_type = "audio/mpeg"
    elif target_format == "wav":
        audio.export(output, format="wav")
        mime_type = "audio/wav"
    else:
        raise ValueError(f"Unsupported target format: {target_format}")
    
    output.seek(0)
    return output.read(), mime_type

def estimate_script_duration(text: str, words_per_minute: int = 150) -> float:
    """
    Estimate the duration of a script in seconds based on word count.
    Uses a more accurate word counting method that accounts for natural speech patterns.
    """
    import re
    
    # Remove extra whitespace and normalize
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Count words more accurately by splitting on whitespace
    words = text.split()
    word_count = len(words)
    
    # Estimate duration in seconds
    duration_minutes = word_count / words_per_minute
    duration_seconds = duration_minutes * 60
    
    logger.debug(f"Script analysis: {word_count} words, estimated {duration_seconds:.1f} seconds at {words_per_minute} WPM")
    
    return duration_seconds

def truncate_script_to_duration(text: str, max_duration_seconds: int, words_per_minute: int = 150) -> str:
    """
    Truncate script to fit within the maximum duration while preserving sentence boundaries.
    """
    import re
    
    # Calculate maximum allowed words
    max_words = int((max_duration_seconds / 60) * words_per_minute)
    
    # Split into sentences (look for sentence endings)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    truncated_sentences = []
    word_count = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        
        # If adding this sentence would exceed the limit, stop
        if word_count + sentence_words > max_words:
            logger.debug(f"Truncating at {word_count} words to stay within {max_words} word limit")
            break
            
        truncated_sentences.append(sentence)
        word_count += sentence_words
    
    truncated_text = ' '.join(truncated_sentences)
    
    # Ensure it ends properly (add period if needed)
    if truncated_text and not truncated_text.rstrip().endswith(('.', '!', '?')):
        truncated_text = truncated_text.rstrip() + '.'
    
    logger.debug(f"Script truncated from {len(text)} to {len(truncated_text)} characters, {word_count} words")
    
    return truncated_text

def sanitize_script_text(text: str) -> str:
    """
    Sanitize script text to remove markdown formatting and ensure natural speech.
    Removes asterisks and other formatting while preserving natural punctuation.
    Also validates and cleans emotional tags for ElevenLabs.
    """
    import re
    
    # Remove all asterisks (markdown bold/italic)
    text = re.sub(r'\*+', '', text)
    
    # Remove markdown headers (# ## ###)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    
    # Remove markdown code blocks and inline code
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)  # Keep content inside inline code
    
    # Remove markdown links [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove markdown list markers (- * +) - do this after code blocks to preserve line structure
    text = re.sub(r'^[ \t]*[-\*\+][ \t]+', '', text, flags=re.MULTILINE)
    
    # Remove all bracketed content (no emotional tags)
    text = re.sub(r'\[([^\]]+)\]', '', text)
    
    # Clean up whitespace - normalize spaces and line breaks
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Max 2 consecutive line breaks
    
    # Fix spacing around periods when followed by code blocks
    text = re.sub(r'\.(\w)', r'. \1', text)
    
    # Ensure proper sentence spacing
    text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)
    
    # Clean up extra spaces where tags were removed
    text = re.sub(r'\s+', ' ', text)  # Normalize multiple spaces
    
    return text.strip()

def make_script_openai(prompt: str, api_key: str, model: str = "gpt-4o", max_duration_seconds: int = 60) -> str:
    """Generate script using OpenAI GPT models"""
    from openai import OpenAI
    
    logger.debug("=== OPENAI SCRIPT GENERATION START ===")
    logger.debug(f"Input prompt: {prompt}")
    logger.debug(f"API key provided: {'Yes' if api_key else 'No'}")
    logger.debug(f"Model: {model}")
    
    client = OpenAI(api_key=api_key)
    
    # Calculate estimated word count based on duration (average 150 words per minute)
    max_words = int((max_duration_seconds / 60) * 150)
    
    # Enhanced prompt for natural human monologue
    enhanced_prompt = f"""Create a natural, conversational podcast monologue based on this request: {prompt}

CRITICAL DURATION CONSTRAINT:
- MAXIMUM duration: {max_duration_seconds} seconds ({max_duration_seconds/60:.1f} minutes)
- Target word count: approximately {max_words} words (150 words per minute speaking rate)
- MUST stay close to this limit - do not generate significantly longer content
- If unsure, err on the side of being shorter rather than longer

Requirements:
- Write as if speaking directly to listeners in a natural, human voice
- Use conversational language with natural pauses and flow
- Include verbal connectors like "you know", "well", "so", "now"
- Vary sentence length for natural rhythm
- Avoid any markdown formatting, bullet points, or structured lists
- Sound like spontaneous speech, not written text
- Use only standard punctuation: periods, commas, question marks, exclamation points
- Make it engaging and personal, as if talking to a friend
- Include natural transitions between ideas
- Keep it conversational and authentic
- Be concise - focus on the most important points within the time limit

Generate ONLY the spoken content - no titles, headers, or formatting. Just the natural monologue text that can be spoken in {max_duration_seconds} seconds. 

IMPORTANT: Respect the {max_duration_seconds} second time limit. Do not generate content that would take significantly longer to speak. Do not include any bracketed tags or special formatting."""
    
    logger.debug("Calling OpenAI API for content generation...")
    # GPT-5 models use max_completion_tokens instead of max_tokens and don't support custom temperature
    if model.startswith("gpt-5") or model.startswith("o1"):
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": enhanced_prompt}
            ],
            max_completion_tokens=8000
        )
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": enhanced_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
    
    script = response.choices[0].message.content
    logger.debug(f"Raw script length: {len(script)} characters")
    
    # Sanitize the script to ensure clean, natural text
    sanitized_script = sanitize_script_text(script)
    logger.debug(f"Sanitized script length: {len(sanitized_script)} characters")
    
    # Check for significant duration violations (prevent obvious problems like 3min when 30s requested)
    estimated_duration = estimate_script_duration(sanitized_script)
    logger.debug(f"Estimated duration: {estimated_duration:.1f}s, Max allowed: {max_duration_seconds}s")
    
    # Only enforce if significantly over limit (2x or more, minimum 30s buffer)
    violation_threshold = max(max_duration_seconds * 2, max_duration_seconds + 30)
    
    if estimated_duration > violation_threshold:
        logger.debug(f"Script significantly exceeds duration limit ({estimated_duration:.1f}s > {violation_threshold:.1f}s threshold), truncating...")
        sanitized_script = truncate_script_to_duration(sanitized_script, max_duration_seconds)
        final_duration = estimate_script_duration(sanitized_script)
        logger.debug(f"After truncation: {final_duration:.1f}s")
    elif estimated_duration > max_duration_seconds:
        logger.debug(f"Script slightly exceeds limit ({estimated_duration:.1f}s > {max_duration_seconds}s) but within acceptable range")
    else:
        logger.debug("Script duration is within limits")
    
    logger.debug("=== OPENAI SCRIPT GENERATION END ===")
    
    return sanitized_script

def make_script_gemini(prompt: str, api_key: str, max_duration_seconds: int = 60) -> str:
    """Generate script using Gemini models (legacy support)"""
    logger.debug("=== GEMINI SCRIPT GENERATION START ===")
    logger.debug(f"Input prompt: {prompt}")
    logger.debug(f"API key provided: {'Yes' if api_key else 'No'}")
    logger.debug(f"API key length: {len(api_key) if api_key else 0}")
    
    # Always use provided API key - no fallback to global configuration
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    logger.debug("Gemini model configured: gemini-2.5-flash")
    
    # Calculate estimated word count based on duration (average 150 words per minute)
    max_words = int((max_duration_seconds / 60) * 150)
    
    # Enhanced prompt for natural human monologue
    enhanced_prompt = f"""Create a natural, conversational podcast monologue based on this request: {prompt}

CRITICAL DURATION CONSTRAINT:
- MAXIMUM duration: {max_duration_seconds} seconds ({max_duration_seconds/60:.1f} minutes)
- Target word count: approximately {max_words} words (150 words per minute speaking rate)
- MUST stay close to this limit - do not generate significantly longer content
- If unsure, err on the side of being shorter rather than longer

Requirements:
- Write as if speaking directly to listeners in a natural, human voice
- Use conversational language with natural pauses and flow
- Include verbal connectors like "you know", "well", "so", "now"
- Vary sentence length for natural rhythm
- Avoid any markdown formatting, bullet points, or structured lists
- Sound like spontaneous speech, not written text
- Use only standard punctuation: periods, commas, question marks, exclamation points
- Make it engaging and personal, as if talking to a friend
- Include natural transitions between ideas
- Keep it conversational and authentic
- Be concise - focus on the most important points within the time limit

Generate ONLY the spoken content - no titles, headers, or formatting. Just the natural monologue text that can be spoken in {max_duration_seconds} seconds. 

IMPORTANT: Respect the {max_duration_seconds} second time limit. Do not generate content that would take significantly longer to speak. Do not include any bracketed tags or special formatting."""
    
    logger.debug(f"Enhanced prompt length: {len(enhanced_prompt)} characters")
    logger.debug(f"Enhanced prompt preview: {enhanced_prompt[:200]}...")
    
    logger.debug("Calling Gemini API for content generation...")
    response = model.generate_content(enhanced_prompt)
    logger.debug("Gemini API response received")
    
    # Handle multi-part responses by extracting text from parts
    logger.debug(f"Response has parts attribute: {hasattr(response, 'parts')}")
    logger.debug(f"Response has candidates attribute: {hasattr(response, 'candidates')}")
    
    if hasattr(response, 'parts') and response.parts:
        logger.debug(f"Processing response.parts - found {len(response.parts)} parts")
        script = ''.join(part.text for part in response.parts if hasattr(part, 'text'))
        logger.debug("Used response.parts method for text extraction")
    elif hasattr(response, 'candidates') and response.candidates:
        logger.debug(f"Processing response.candidates - found {len(response.candidates)} candidates")
        # Extract text from the first candidate's content parts
        candidate = response.candidates[0]
        logger.debug(f"Candidate has content: {hasattr(candidate, 'content')}")
        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            parts_count = len(candidate.content.parts)
            logger.debug(f"Candidate content has {parts_count} parts")
            script = ''.join(part.text for part in candidate.content.parts if hasattr(part, 'text'))
            logger.debug("Used candidate.content.parts method for text extraction")
        else:
            script = response.text  # Fallback for simple responses
            logger.debug("Used response.text fallback for simple response")
    else:
        script = response.text  # Fallback for simple responses
        logger.debug("Used response.text fallback - no parts or candidates found")
    
    logger.debug(f"Raw script length: {len(script)} characters")
    logger.debug(f"Raw script preview: {script[:200]}...")
    
    # Sanitize the script to ensure clean, natural text
    logger.debug("Starting script sanitization...")
    sanitized_script = sanitize_script_text(script)
    logger.debug(f"Sanitized script length: {len(sanitized_script)} characters")
    logger.debug(f"Sanitized script preview: {sanitized_script[:200]}...")
    
    # Check for significant duration violations (prevent obvious problems like 3min when 30s requested)
    estimated_duration = estimate_script_duration(sanitized_script)
    logger.debug(f"Estimated duration: {estimated_duration:.1f}s, Max allowed: {max_duration_seconds}s")
    
    # Only enforce if significantly over limit (2x or more, minimum 30s buffer)
    violation_threshold = max(max_duration_seconds * 2, max_duration_seconds + 30)
    
    if estimated_duration > violation_threshold:
        logger.debug(f"Script significantly exceeds duration limit ({estimated_duration:.1f}s > {violation_threshold:.1f}s threshold), truncating...")
        sanitized_script = truncate_script_to_duration(sanitized_script, max_duration_seconds)
        final_duration = estimate_script_duration(sanitized_script)
        logger.debug(f"After truncation: {final_duration:.1f}s")
    elif estimated_duration > max_duration_seconds:
        logger.debug(f"Script slightly exceeds limit ({estimated_duration:.1f}s > {max_duration_seconds}s) but within acceptable range")
    else:
        logger.debug("Script duration is within limits")
    
    logger.debug("=== GEMINI SCRIPT GENERATION END ===")
    
    return sanitized_script

def make_script(prompt: str, gemini_api_key: str = None, provider: str = "openai", max_duration_seconds: int = 60) -> str:
    """
    Generate script using specified provider (OpenAI by default, Gemini as fallback).
    OpenAI key is managed internally via environment variable.
    """
    logger.debug(f"=== SCRIPT GENERATION DISPATCH - Provider: {provider} ===")
    
    if provider == "openai":
        # Use internal OpenAI key from environment
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("Internal OpenAI API key not configured on server")
        return make_script_openai(prompt, openai_api_key, max_duration_seconds=max_duration_seconds)
    elif provider == "gemini":
        if gemini_api_key:
            return make_script_gemini(prompt, gemini_api_key, max_duration_seconds=max_duration_seconds)
        else:
            raise ValueError("Gemini API key is required when using Gemini provider")
    else:
        raise ValueError(f"Unsupported provider: {provider}. Use 'openai' or 'gemini'.")

def analyze_writing_style_openai(content: str, api_key: str, model: str = "gpt-4o") -> dict:
    """
    Analyze dialogue style for podcast generation using OpenAI GPT models.
    """
    from openai import OpenAI
    
    logger.debug("=== OPENAI WRITING STYLE ANALYSIS START ===")
    logger.debug(f"Input content: {content}")
    logger.debug(f"API key provided: {'Yes' if api_key else 'No'}")
    logger.debug(f"Model: {model}")
    
    # Only allow GPT-4o for writing style analysis
    if model != "gpt-4o":
        logger.error(f"Unsupported model for writing style analysis: {model}")
        raise ValueError(f"Writing style analysis only supports 'gpt-4o' model. Requested model: {model}")
    
    client = OpenAI(api_key=api_key)
    
    prompt = f"""You are a dialogue style expert for podcast generation. Analyze this instruction: "{content}"

Provide detailed podcast generation settings for this speaking style. Give specific, actionable descriptions for each field.

Return ONLY a valid JSON object with podcast generation settings:

{{
    "tone": "emotional tone and vocal qualities",
    "pace": "speaking speed and rhythm patterns",
    "vocabulary_level": "word complexity and language style",
    "target_audience": "intended listeners and communication approach",
    "content_structure": "organization and flow patterns",
    "energy_level": "vocal energy and enthusiasm",
    "formality": "professional vs casual language use",
    "humor_style": "comedy approach and timing",
    "empathy_level": "emotional connection and validation",
    "confidence_level": "self-assurance and authority projection",
    "storytelling": "narrative style and anecdote use",
    "keyPhrases": ["signature phrases", "common expressions", "verbal tics"],
    "additionalInstructions": "specific vocal patterns and mannerisms"
}}

Provide detailed, specific descriptions for each field based on the requested style.

Instruction to analyze: {content}

Return only valid JSON:"""

    logger.debug(f"Prompt length: {len(prompt)} characters")
    logger.debug("Calling OpenAI API for writing style analysis...")

    # Use GPT-4o with standard parameters
    try:
        logger.debug(f"Making API call with GPT-4o parameters for model: {model}")
        import time
        start_time = time.time()
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500,
            timeout=60  # 1 minute timeout for faster responses
        )
        
        end_time = time.time()
        logger.debug(f"GPT-4o API call completed successfully in {end_time - start_time:.2f} seconds")
    except Exception as api_error:
        logger.error(f"OpenAI API call failed: {type(api_error).__name__}: {api_error}")
        logger.error("=== OPENAI WRITING STYLE ANALYSIS API ERROR ===")
        raise api_error
    
    logger.debug("OpenAI API response received")
    logger.debug(f"Response type: {type(response)}")
    
    try:
        response_text = response.choices[0].message.content.strip()
        logger.debug(f"Raw response length: {len(response_text)} characters")
        logger.debug(f"Raw response preview: {response_text[:200]}...")
        
        # Remove any markdown code block formatting if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        logger.debug(f"Cleaned response length: {len(response_text)} characters")
        logger.debug("Attempting to parse JSON response...")
        
        parsed_result = json.loads(response_text)
        logger.debug("JSON parsing successful")
        logger.debug(f"Parsed result keys: {list(parsed_result.keys())}")
        logger.debug("=== OPENAI WRITING STYLE ANALYSIS SUCCESS ===")
        
        return parsed_result
    except json.JSONDecodeError as e:
        logger.error("=== OPENAI WRITING STYLE ANALYSIS ERROR ===")
        logger.error(f"JSON parsing error: {e}")
        logger.error(f"Raw response: {response.choices[0].message.content}")
        print(f"JSON parsing error: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
        # Fallback if JSON parsing fails
        logger.debug("Using fallback response due to JSON parsing error")
        logger.debug("=== OPENAI WRITING STYLE ANALYSIS FALLBACK ===")
        return {
            "tone": "conversational",
            "pace": "moderate", 
            "vocabulary_level": "conversational",
            "target_audience": "general public",
            "content_structure": "structured",
            "energy_level": "moderate",
            "formality": "conversational",
            "humor_style": "none",
            "empathy_level": "moderate",
            "confidence_level": "confident",
            "storytelling": "direct",
            "keyPhrases": ["well", "you know", "I think"],
            "additionalInstructions": "Use natural, conversational speech patterns with clear articulation"
        }

def analyze_writing_style_gemini(content: str, api_key: str) -> dict:
    """
    Analyze dialogue style for podcast generation and return structured output using Gemini API.
    Takes a style instruction (e.g., "talk like Trump") and returns podcast generation settings.
    """
    genai.configure(api_key=api_key)
    
    # Use the latest Gemini model for structured output
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # Create a comprehensive prompt for dialogue style analysis
    prompt = f"""You are a dialogue style expert for podcast generation. Given a style instruction, provide podcast generation settings that would make the speaker sound like the requested style/person.

Analyze this instruction: "{content}"

Return ONLY a valid JSON object with podcast generation settings:

{{
    "tone": "emotional tone for speech (e.g., authoritative, casual, dramatic, confident, passionate)",
    "pace": "speaking pace (e.g., fast, slow, moderate, rushed, deliberate)",
    "vocabulary_level": "word complexity (e.g., simple, conversational, sophisticated, technical, colloquial)",
    "target_audience": "intended listeners (e.g., supporters, general public, experts, working class)",
    "content_structure": "speech organization (e.g., rambling, structured, repetitive, stream-of-consciousness)",
    "energy_level": "vocal energy (e.g., high, explosive, moderate, low, dynamic)",
    "formality": "speech formality (e.g., informal, conversational, formal, crude, folksy)",
    "humor_style": "humor approach (e.g., sarcastic, self-deprecating, boastful, witty, none)",
    "empathy_level": "emotional connection (e.g., low, moderate, high, performative)",
    "confidence_level": "self-assurance (e.g., extremely confident, boastful, uncertain, assertive)",
    "storytelling": "narrative style (e.g., anecdotal, repetitive, tangential, direct, exaggerated)",
    "keyPhrases": ["signature phrases", "common expressions", "verbal tics"],
    "additionalInstructions": "specific vocal patterns, mannerisms, and speech characteristics to implement"
}}

Instruction to analyze: {content}

Return only valid JSON:"""
    
    # Generate the content with structured output
    response = model.generate_content(prompt)
    
    # Parse the JSON response
    try:
        response_text = response.text.strip()
        
        # Remove any markdown code block formatting if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print(f"Raw response: {response.text}")
        # Fallback if JSON parsing fails
        return {
            "tone": "conversational",
            "pace": "moderate", 
            "vocabulary_level": "conversational",
            "target_audience": "general public",
            "content_structure": "structured",
            "energy_level": "moderate",
            "formality": "conversational",
            "humor_style": "none",
            "empathy_level": "moderate",
            "confidence_level": "confident",
            "storytelling": "direct",
            "keyPhrases": ["well", "you know", "I think"],
            "additionalInstructions": "Use natural, conversational speech patterns with clear articulation"
        }

def analyze_writing_style(content: str, provider: str = "openai", gemini_api_key: str = None) -> dict:
    """
    Analyze dialogue style using specified provider (OpenAI by default, Gemini as fallback).
    OpenAI key is managed internally via environment variable.
    """
    if provider == "openai":
        # Use internal OpenAI key from environment
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("Internal OpenAI API key not configured on server")
        return analyze_writing_style_openai(content, openai_api_key)
    elif provider == "gemini":
        if gemini_api_key:
            return analyze_writing_style_gemini(content, gemini_api_key)
        else:
            raise ValueError("Gemini API key is required when using Gemini provider")
    else:
        raise ValueError(f"Unsupported provider: {provider}. Use 'openai' or 'gemini'.")

def gen_video(video_request: dict, credentials: dict = None) -> str:
    """
    Video generation using Google's full API structure.
    Supports image inputs, video inputs, and all parameters.
    """
    from rq import get_current_job
    from app.websocket_manager import manager
    
    job = get_current_job()
    job_id = job.get_id()
    total_steps = 3
    
    try:
        # Step 1: Initialize authentication
        job.meta['progress'] = 10
        job.meta['current_step'] = 'Initializing video generation'
        job.meta['step_number'] = 1
        job.meta['total_steps'] = total_steps
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 10, 'Initializing video generation', 1, total_steps)
        
        # Get credentials (user-provided or environment defaults)
        creds_dict = credentials if credentials else {}
        project_id = creds_dict.get('google_cloud_project') or os.getenv("GOOGLE_CLOUD_PROJECT", "mcp-summer-school")
        location_id = creds_dict.get('vertex_ai_region') or os.getenv("VERTEX_AI_REGION", "us-central1")
        bucket_name = creds_dict.get('gcs_bucket') or os.getenv("GCS_BUCKET")
        
        # Get model from video request parameters or use default
        parameters = video_request.get("parameters", {})
        model_id = parameters.get("model") or os.getenv("VEO_MODEL_ID", "veo-3.0-generate-preview")
        
        # Create Google Cloud credentials
        google_credentials, _ = create_google_cloud_credentials(creds_dict, creds_dict.get('google_cloud_credentials'))
        google_credentials.refresh(Request())
        access_token = google_credentials.token
        
        # Create storage client with appropriate credentials
        storage_client = create_storage_client(creds_dict)
        bucket = storage_client.bucket(bucket_name)
        
        # Vertex AI configuration
        api_endpoint = f"{location_id}-aiplatform.googleapis.com"
        
        # Step 2: Submit video generation request
        job.meta['progress'] = 50
        job.meta['current_step'] = 'Submitting video generation request'
        job.meta['step_number'] = 2
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 50, 'Submitting video generation request', 2, total_steps)
        
        # Build instance from video_request
        instance = {
            "prompt": video_request["prompt"]
        }
        
        # Add optional image input
        if video_request.get("image"):
            instance["image"] = video_request["image"]
        
        # Add optional last frame input
        if video_request.get("lastFrame"):
            instance["lastFrame"] = video_request["lastFrame"]
        
        # Add optional video input
        if video_request.get("video"):
            instance["video"] = video_request["video"]
        
        # Get parameters with defaults (already extracted above)
        request_parameters = {
            "aspectRatio": parameters.get("aspectRatio", "16:9"),
            "sampleCount": parameters.get("sampleCount", 1),
            "durationSeconds": parameters.get("durationSeconds", 8),
            "personGeneration": parameters.get("personGeneration", "allow_all"),
            "generateAudio": parameters.get("generateAudio", True),
            "enhancePrompt": parameters.get("enhancePrompt", True)  # Veo 3 requires this to be True
        }
        
        # Add optional parameters if provided
        if parameters.get("negativePrompt"):
            request_parameters["negativePrompt"] = parameters["negativePrompt"]
        if parameters.get("resolution"):
            request_parameters["resolution"] = parameters["resolution"]
        if parameters.get("seed"):
            request_parameters["seed"] = parameters["seed"]
        
        # Always set storageUri to automatically save to our GCS bucket
        # This prevents base64 responses and saves directly to our bucket
        storage_folder = f"gs://{bucket_name}/videos/{job_id}"
        request_parameters["storageUri"] = parameters.get("storageUri", storage_folder)
        
        # Prepare request payload matching Google's exact structure
        request_data = {
            "instances": [instance],
            "parameters": request_parameters
        }
        
        # Submit the long-running operation
        url = f"https://{api_endpoint}/v1/projects/{project_id}/locations/{location_id}/publishers/google/models/{model_id}:predictLongRunning"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        import sys
        print(f"DEBUG: Submitting request to: {url}", file=sys.stderr)
        print(f"DEBUG: Request headers: {headers}", file=sys.stderr)
        print(f"DEBUG: Request data: {json.dumps(request_data, indent=2)}", file=sys.stderr)
        
        response = requests.post(url, headers=headers, json=request_data)
        
        print(f"DEBUG: Response status: {response.status_code}", file=sys.stderr)
        print(f"DEBUG: Response content: {response.text}", file=sys.stderr)
        
        response.raise_for_status()
        
        operation = response.json()
        operation_name = operation.get("name")
        
        if not operation_name:
            raise ValueError(f"No operation name returned from API. Response: {operation}")
        
        print(f"DEBUG: Operation name: {operation_name}", file=sys.stderr)
        
        # Initialize video_url variable
        video_url = None
        
        # Immediate status check to catch early failures
        job.meta['progress'] = 55
        job.meta['current_step'] = 'Checking initial operation status'
        job.save_meta()
        manager.notify_progress(job_id, 55, 'Checking initial operation status', 3, total_steps)
        
        print(f"DEBUG: Performing immediate status check for early failure detection", file=sys.stderr)
        try:
            # Wait a brief moment for operation to be registered, then check immediately
            time.sleep(5)
            immediate_status = fetch_operation_status(operation_name, creds_dict)
            print(f"DEBUG: Immediate status check result: {immediate_status}", file=sys.stderr)
            
            # Check if operation failed immediately
            if immediate_status.get("done") and "error" in immediate_status:
                error = immediate_status["error"]
                error_msg = f"Video generation failed immediately - Code: {error.get('code', 'unknown')}, Message: {error.get('message', 'no message')}"
                print(f"DEBUG: {error_msg}", file=sys.stderr)
                raise ValueError(error_msg)
            
            # If operation completed immediately (unlikely but possible)
            if immediate_status.get("done") and "response" in immediate_status:
                print(f"DEBUG: Operation completed immediately!", file=sys.stderr)
                response_data = immediate_status["response"]
                videos = response_data.get("videos", [])
                if videos and "gcsUri" in videos[0]:
                    video_gcs_uri = videos[0]["gcsUri"]
                    blob_path = video_gcs_uri.replace(f"gs://{bucket_name}/", "")
                    blob = bucket.blob(blob_path)
                    video_url = make_blob_public_safe(blob)
                    
                    # Operation completed immediately, skip polling
                    video_url = make_blob_public_safe(blob)
                    print(f"DEBUG: Video ready immediately at: {video_url}", file=sys.stderr)
                else:
                    print(f"DEBUG: Operation done but no video found, will continue polling", file=sys.stderr)
            
        except Exception as e:
            print(f"DEBUG: Immediate status check failed (operation still initializing): {e}", file=sys.stderr)
        
        # If we got a video URL immediately, we're done
        if video_url:
            # Store operation metadata for immediate completion
            operation_info = {
                "operation_name": operation_name,
                "video_request": video_request,
                "timestamp": time.time(),
                "job_id": job_id,
                "project_id": project_id,
                "location_id": location_id,
                "video_url": video_url,
                "video_filename": video_url.split('/')[-1] if video_url.startswith("https://") else "immediate_completion.mp4",
                "original_video_url": video_url,
                "source_type": "immediate_completion"
            }
            
            metadata_blob = bucket.blob(f"metadata/{operation_info['video_filename'].replace('.mp4', '.json')}")
            metadata_blob.upload_from_string(json.dumps(operation_info, indent=2), content_type="application/json")
            
            # Mark as complete and clear sensitive data
            job.meta['progress'] = 100
            job.meta['current_step'] = 'Complete - Video ready!'
            job.meta = clear_sensitive_data(job.meta)
            job.save_meta()
            
            manager.notify_completion(job_id, video_url)
            return video_url
        
        # Operation is running - store operation info for user to track
        job.meta['progress'] = 60
        job.meta['current_step'] = 'Video generation in progress - check status manually'
        job.meta['operation_name'] = operation_name
        job.meta['status'] = 'running'  # Explicitly mark as running, not failed
        job.meta = clear_sensitive_data(job.meta)
        job.save_meta()
        
        # Send WebSocket notification about ongoing operation
        manager.notify_progress(job_id, 60, 'Video generation in progress - use /mcp/{job_id} or /operation/{operation_name} to check status', 3, total_steps)
        
        print(f"DEBUG: Video generation submitted successfully. Operation: {operation_name}", file=sys.stderr)
        print(f"DEBUG: Use status endpoints to check progress", file=sys.stderr)
        
        # Return a success indicator with operation name
        # This ensures RQ treats the job as successful
        return {
            "status": "submitted",
            "operation_name": operation_name,
            "message": "Video generation started successfully"
        }
    
    except Exception as e:
        # Clear sensitive data even on error
        job = get_current_job()
        if job:
            job.meta = clear_sensitive_data(job.meta)
            job.save_meta()
        manager.notify_error(job_id, str(e))
        raise e


def fetch_operation_status(operation_name: str, credentials: dict = None) -> dict:
    """
    Query the status of a video generation operation using Google's fetchPredictOperation endpoint.
    Returns the operation status and result if available.
    """
    try:
        # Get credentials (user-provided or environment defaults)
        creds_dict = credentials if credentials else {}
        project_id = creds_dict.get('google_cloud_project') or os.getenv("GOOGLE_CLOUD_PROJECT", "mcp-summer-school")
        location_id = creds_dict.get('vertex_ai_region') or os.getenv("VERTEX_AI_REGION", "us-central1")
        # For fetch operation, we need to use the default model since we don't have the original request
        model_id = os.getenv("VEO_MODEL_ID", "veo-3.0-generate-preview")
        
        # Create Google Cloud credentials
        google_credentials, _ = create_google_cloud_credentials(creds_dict, creds_dict.get('google_cloud_credentials'))
        google_credentials.refresh(Request())
        
        # Vertex AI configuration
        api_endpoint = f"{location_id}-aiplatform.googleapis.com"
        
        # Prepare request payload for fetchPredictOperation
        request_data = {
            "operationName": operation_name
        }
        
        # Submit fetchPredictOperation request
        url = f"https://{api_endpoint}/v1/projects/{project_id}/locations/{location_id}/publishers/google/models/{model_id}:fetchPredictOperation"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {google_credentials.token}"
        }
        
        import sys
        print(f"DEBUG FETCH: Querying operation status at: {url}", file=sys.stderr)
        print(f"DEBUG FETCH: Request data: {json.dumps(request_data, indent=2)}", file=sys.stderr)
        
        response = requests.post(url, headers=headers, json=request_data)
        
        print(f"DEBUG FETCH: Response status: {response.status_code}", file=sys.stderr)
        print(f"DEBUG FETCH: Response content: {response.text}", file=sys.stderr)
        
        response.raise_for_status()
        
        return response.json()
        
    except Exception as e:
        print(f"DEBUG FETCH: Error fetching operation status: {e}", file=sys.stderr)
        raise e

def gen_audio(prompt: str, credentials: dict = None, generate_thumbnail: bool = False, thumbnail_prompt: str = None, provider: str = "openai", audio_format: str = "m4a", max_duration_seconds: int = 60) -> dict:
    from rq import get_current_job
    from app.websocket_manager import manager
    import time
    
    job = get_current_job()
    job_id = job.get_id()
    total_steps = 5 if generate_thumbnail else 4
    
    logger.debug("=== AUDIO GENERATION START ===")
    logger.debug(f"Job ID: {job_id}")
    logger.debug(f"Input prompt: {prompt}")
    logger.debug(f"Generate thumbnail: {generate_thumbnail}")
    logger.debug(f"Thumbnail prompt: {thumbnail_prompt}")
    logger.debug(f"Total steps: {total_steps}")
    
    try:
        # Get credentials (user-provided or environment defaults)
        creds_dict = credentials if credentials else {}
        logger.debug(f"Credentials provided: {'Yes' if credentials else 'No'}")
        
        gemini_api_key = creds_dict.get('gemini_api_key') or os.getenv("GEMINI_API_KEY")
        openai_api_key = creds_dict.get('openai_api_key') or os.getenv("OPENAI_API_KEY")
        elevenlabs_api_key = creds_dict.get('elevenlabs_api_key') or os.getenv("XI_KEY")
        bucket_name = creds_dict.get('gcs_bucket') or os.getenv("GCS_BUCKET")
        
        logger.debug(f"Provider: {provider}")
        logger.debug(f"Gemini API key available: {'Yes' if gemini_api_key else 'No'}")
        logger.debug(f"OpenAI API key available: {'Yes' if openai_api_key else 'No'}")
        logger.debug(f"ElevenLabs API key available: {'Yes' if elevenlabs_api_key else 'No'}")
        logger.debug(f"GCS bucket: {bucket_name}")
        
        # Create storage client with appropriate credentials
        logger.debug("Creating storage client...")
        storage_client = create_storage_client(creds_dict)
        bucket = storage_client.bucket(bucket_name)
        logger.debug("Storage client created successfully")
        
        # Step 1: Generate script
        logger.debug("STEP 1: Starting script generation")
        job.meta['progress'] = 10
        job.meta['current_step'] = 'Generating script with AI'
        job.meta['step_number'] = 1
        job.meta['total_steps'] = total_steps
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 10, 'Generating script with AI', 1, total_steps)
        
        logger.debug(f"Calling make_script function with provider: {provider}, max_duration: {max_duration_seconds}s...")
        script = make_script(prompt, gemini_api_key, provider, max_duration_seconds)
        logger.debug(f"Script generated successfully - length: {len(script)} characters")
        
        # Step 2: Initialize ElevenLabs and get voice
        logger.debug("STEP 2: Initializing ElevenLabs TTS")
        job.meta['progress'] = 30
        job.meta['current_step'] = 'Initializing text-to-speech engine'
        job.meta['step_number'] = 2
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 30, 'Initializing text-to-speech engine', 2, total_steps)
        
        logger.debug("Creating ElevenLabs client...")
        el = ElevenLabs(api_key=elevenlabs_api_key)
        logger.debug("ElevenLabs client created")
        
        # Get available voices and prefer ones that support emotional tags
        try:
            logger.debug("Fetching available voices...")
            voices = el.voices.get_all()
            voice_count = len(voices.voices) if voices.voices else 0
            logger.debug(f"Found {voice_count} available voices")
            
            # Prefer voices known to support emotional tags well
            preferred_voices = ["pNInz6obpgDQGcFmaJgB", "21m00Tcm4TlvDq8ikWAM", "AZnzlk1XvdvUeBnXmlld"]  # Adam, Rachel, Domi
            selected_voice = None
            
            if voices.voices:
                # Try to find a preferred voice
                for voice in voices.voices:
                    if voice.voice_id in preferred_voices:
                        selected_voice = voice
                        break
                
                # If no preferred voice found, use the first available
                if not selected_voice:
                    selected_voice = voices.voices[0]
                
                voice_id = selected_voice.voice_id
                voice_name = selected_voice.name
            else:
                voice_id = "pNInz6obpgDQGcFmaJgB"  # Default Adam voice ID
                voice_name = "Adam (default)"
            
            logger.debug(f"Selected voice: {voice_name} (ID: {voice_id}) - supports emotional tags")
        except Exception as e:
            # Fallback to a known voice ID for Adam (supports emotional tags)
            voice_id = "pNInz6obpgDQGcFmaJgB"
            logger.debug(f"Voice fetch failed, using fallback voice ID: {voice_id}, Error: {e}")
        
        # Step 3: Generate audio
        logger.debug("STEP 3: Converting text to speech")
        job.meta['progress'] = 60
        job.meta['current_step'] = 'Converting text to speech'
        job.meta['step_number'] = 3
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 60, 'Converting text to speech', 3, total_steps)
        
        logger.debug(f"Generating audio with voice {voice_id}...")
        logger.debug(f"Text to convert: {len(script)} characters")
        logger.debug(f"Target audio format: {audio_format}")
        
        # Always generate MP3 first for consistent web playback
        elevenlabs_format = "mp3_44100_128"
        source_format = "mp3"
        
        logger.debug(f"Using ElevenLabs format: {elevenlabs_format} (always MP3 first)")
        
        # Configure ElevenLabs generation settings
        from elevenlabs import VoiceSettings
        voice_settings = VoiceSettings(
            stability=0.7,        # Good stability for clear speech
            similarity_boost=0.8, # High similarity to original voice
            style=0.0,           # No style variation - natural speech only
            use_speaker_boost=True  # Enhance speaker characteristics
        )
        
        logger.debug("Generating MP3 audio with ElevenLabs...")
        
        # Try different models in order of preference
        models_to_try = [
            "eleven_turbo_v2_5",  # Latest turbo model (if available)
            "eleven_turbo_v2",    # Turbo v2 
            "eleven_multilingual_v2",  # Multilingual v2
            "eleven_multilingual_v1",  # Multilingual v1 (most widely available)
            "eleven_monolingual_v1"    # Monolingual v1 (fallback)
        ]
        
        audio_generator = None
        last_error = None
        
        for model_name in models_to_try:
            try:
                logger.debug(f"Trying ElevenLabs model: {model_name}")
                audio_generator = el.generate(
                    text=script, 
                    voice=voice_id, 
                    voice_settings=voice_settings,
                    model=model_name,
                    output_format=elevenlabs_format
                )
                logger.debug(f"Successfully using model: {model_name}")
                break
            except Exception as e:
                logger.debug(f"Model {model_name} failed: {e}")
                last_error = e
                continue
        
        if audio_generator is None:
            logger.error(f"All ElevenLabs models failed. Last error: {last_error}")
            raise Exception(f"Unable to generate audio with any available ElevenLabs model. Last error: {last_error}")
        logger.debug("Audio generation started, converting generator to bytes...")
        mp3_audio_bytes = b"".join(audio_generator)  # Convert generator to bytes
        logger.debug(f"MP3 audio generated successfully - size: {len(mp3_audio_bytes)} bytes")
        
        # Convert to target format if needed (keep MP3 separate)
        converted_audio_bytes = None
        converted_content_type = None
        if audio_format != "mp3":
            logger.debug(f"Converting MP3 to {audio_format}...")
            try:
                converted_audio_bytes, converted_content_type = convert_audio_format(mp3_audio_bytes, "mp3", audio_format)
                logger.debug(f"Conversion to {audio_format} completed - new size: {len(converted_audio_bytes)} bytes")
            except Exception as conversion_error:
                logger.error(f"Audio conversion to {audio_format} failed: {conversion_error}")
                logger.debug("Will use MP3 for both display and download")
                converted_audio_bytes = None
                converted_content_type = None
        
        # Optional Step 4: Generate thumbnail if requested
        thumbnail_url = None
        if generate_thumbnail:
            logger.debug("STEP 4: Starting thumbnail generation")
            job.meta['progress'] = 70
            job.meta['current_step'] = 'Generating podcast thumbnail'
            job.meta['step_number'] = 4
            job.save_meta()
            
            # Send WebSocket notification
            manager.notify_progress(job_id, 70, 'Generating podcast thumbnail', 4, total_steps)
            
            try:
                # Generate thumbnail using Vertex AI Imagen API
                logger.debug("Generating podcast thumbnail using Vertex AI Imagen 3 Fast")
                print(f"Info: Generating podcast thumbnail using Vertex AI Imagen 3 Fast (cheapest model at $0.02/image)", file=sys.stderr)
                
                # Use custom thumbnail prompt if provided, otherwise create one based on the main prompt
                if thumbnail_prompt:
                    final_thumbnail_prompt = f"{thumbnail_prompt}. NO TEXT, NO WORDS, NO LETTERS, NO TYPOGRAPHY - only visual elements and icons."
                    logger.debug(f"Using custom thumbnail prompt: {thumbnail_prompt}")
                    print(f"Info: Using custom thumbnail prompt: {thumbnail_prompt[:50]}...", file=sys.stderr)
                else:
                    final_thumbnail_prompt = f"{prompt}. NO TEXT, NO WORDS, NO LETTERS, NO TYPOGRAPHY - only visual elements and icons."
                    logger.debug("Using auto-generated thumbnail prompt based on main prompt")
                    logger.debug(f"Auto-generated prompt: {final_thumbnail_prompt}")
                    print(f"Info: Using auto-generated thumbnail prompt based on main prompt", file=sys.stderr)
                
                # Get credentials and project info
                project_id = creds_dict.get('google_cloud_project') or os.getenv("GOOGLE_CLOUD_PROJECT", "mcp-summer-school")
                location_id = creds_dict.get('vertex_ai_region') or os.getenv("VERTEX_AI_REGION", "us-central1")
                logger.debug(f"Project ID: {project_id}")
                logger.debug(f"Location ID: {location_id}")
                
                # Create Google Cloud credentials for Imagen API
                logger.debug("Creating Google Cloud credentials for Imagen API...")
                google_credentials, _ = create_google_cloud_credentials(creds_dict, creds_dict.get('google_cloud_credentials'))
                google_credentials.refresh(Request())
                access_token = google_credentials.token
                logger.debug("Google Cloud credentials refreshed successfully")
                
                # Vertex AI Imagen API configuration (using cheapest model)
                api_endpoint = f"{location_id}-aiplatform.googleapis.com"
                # Use cheapest Imagen model by default, configurable via environment
                model_id = os.getenv("IMAGEN_MODEL_ID", "imagen-3.0-fast-generate-001")  # Imagen 3 Fast - cheapest at $0.02/image
                logger.debug(f"API endpoint: {api_endpoint}")
                logger.debug(f"Model ID: {model_id}")
                
                # Prepare request payload for Imagen
                request_data = {
                    "instances": [{
                        "prompt": final_thumbnail_prompt
                    }],
                    "parameters": {
                        "sampleCount": 1,
                        "aspectRatio": "1:1",  # Square thumbnail
                        "safetyFilterLevel": "block_some",
                        "personGeneration": "dont_allow"
                    }
                }
                
                # Submit image generation request
                url = f"https://{api_endpoint}/v1/projects/{project_id}/locations/{location_id}/publishers/google/models/{model_id}:predict"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                }
                
                print(f"DEBUG THUMBNAIL: Submitting request to: {url}", file=sys.stderr)
                
                response = requests.post(url, headers=headers, json=request_data)
                response.raise_for_status()
                
                result = response.json()
                print(f"DEBUG THUMBNAIL: Response received", file=sys.stderr)
                
                # Extract image data from response
                if "predictions" in result and len(result["predictions"]) > 0:
                    prediction = result["predictions"][0]
                    if "bytesBase64Encoded" in prediction:
                        # Decode base64 image data
                        import base64
                        image_data = base64.b64decode(prediction["bytesBase64Encoded"])
                        
                        # Upload thumbnail to storage
                        thumbnail_blob = bucket.blob(f"thumbnails/{uuid.uuid4()}.png")
                        thumbnail_blob.upload_from_string(image_data, content_type="image/png")
                        thumbnail_url = make_blob_public_safe(thumbnail_blob)
                        
                        print(f"DEBUG THUMBNAIL: Thumbnail generated and uploaded: {thumbnail_url}", file=sys.stderr)
                    else:
                        print(f"Warning: No image data in Imagen response", file=sys.stderr)
                else:
                    print(f"Warning: No predictions in Imagen response", file=sys.stderr)
                            
            except Exception as e:
                print(f"Warning: Thumbnail generation failed: {e}", file=sys.stderr)
                # Continue without thumbnail - not critical
        
        # Step 4/5: Upload audio files to storage
        next_step = 5 if generate_thumbnail else 4
        logger.debug(f"STEP {next_step}: Uploading audio files to cloud storage")
        job.meta['progress'] = 90
        job.meta['current_step'] = 'Uploading audio files to cloud storage'
        job.meta['step_number'] = next_step
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 90, 'Uploading audio files to cloud storage', next_step, total_steps)
        
        # Upload MP3 file (always for display)
        file_uuid = str(uuid.uuid4())
        mp3_filename = f"audio/{file_uuid}.mp3"
        logger.debug(f"Creating MP3 blob with filename: {mp3_filename}")
        mp3_blob = bucket.blob(mp3_filename)
        
        logger.debug(f"Uploading MP3 audio bytes to cloud storage...")
        mp3_blob.upload_from_string(mp3_audio_bytes, content_type="audio/mpeg")
        logger.debug("MP3 upload completed")
        
        logger.debug("Making MP3 blob public...")
        display_audio_url = make_blob_public_safe(mp3_blob)
        logger.debug(f"MP3 display URL generated: {display_audio_url}")
        
        # Upload converted file if different format was requested
        download_audio_url = display_audio_url  # Default to MP3
        if converted_audio_bytes is not None and audio_format != "mp3":
            converted_filename = f"audio/{file_uuid}_converted.{audio_format}"
            logger.debug(f"Creating converted blob with filename: {converted_filename}")
            converted_blob = bucket.blob(converted_filename)
            
            logger.debug(f"Uploading converted audio bytes to cloud storage with content-type: {converted_content_type}...")
            converted_blob.upload_from_string(converted_audio_bytes, content_type=converted_content_type)
            logger.debug("Converted audio upload completed")
            
            logger.debug("Making converted blob public...")
            download_audio_url = make_blob_public_safe(converted_blob)
            logger.debug(f"Converted download URL generated: {download_audio_url}")
        else:
            logger.debug(f"Using MP3 for both display and download (requested format: {audio_format})")
        
        # Completion and clear sensitive data
        logger.debug("Finalizing job completion...")
        job.meta['progress'] = 100
        job.meta['current_step'] = 'Complete'
        job.meta = clear_sensitive_data(job.meta)
        job.save_meta()
        
        # Calculate audio duration from MP3 bytes
        try:
            from pydub import AudioSegment
            from io import BytesIO
            audio_segment = AudioSegment.from_file(BytesIO(mp3_audio_bytes), format="mp3")
            audio_duration_seconds = len(audio_segment) / 1000.0  # Convert milliseconds to seconds
            logger.debug(f"Audio duration calculated: {audio_duration_seconds:.2f} seconds")
        except Exception as e:
            logger.warning(f"Could not calculate audio duration: {e}")
            audio_duration_seconds = None
        
        # Send completion notification (use display URL for compatibility)
        manager.notify_completion(job_id, display_audio_url)
        logger.debug("Completion notification sent")
        
        # Return all URLs with duration
        result = {
            "audio_url": display_audio_url,  # Backward compatibility
            "display_audio_url": display_audio_url,  # MP3 for web playback
            "download_audio_url": download_audio_url,  # Requested format for download
            "thumbnail_url": thumbnail_url,
            "audio_duration_seconds": audio_duration_seconds
        }
        logger.debug(f"Final result: {result}")
        logger.debug("=== AUDIO GENERATION END ===")
        return result
    
    except Exception as e:
        logger.error(f"=== AUDIO GENERATION ERROR ===")
        logger.error(f"Error in gen_audio: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        
        # Clear sensitive data even on error
        job = get_current_job()
        if job:
            logger.debug("Clearing sensitive data from job metadata...")
            job.meta = clear_sensitive_data(job.meta)
            job.save_meta()
        
        # Send error notification
        logger.debug("Sending error notification...")
        manager.notify_error(job_id, str(e))
        logger.error("=== AUDIO GENERATION ERROR END ===")
        raise e