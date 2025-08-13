# app/credential_utils.py
import os
import json
import tempfile
from typing import Optional, Dict, Any, Tuple
from google.oauth2 import service_account
from google.auth import default
from google import generativeai as genai
from google.cloud import storage
from elevenlabs.client import ElevenLabs
from openai import OpenAI
from app.mcp_models import UserCredentials, VideoGenerationParameters

# Supported video generation models
SUPPORTED_VIDEO_MODELS = [
    "veo-3.0-generate-preview",
    "veo-2.0-generate-preview", 
    "veo-1.0-generate-preview",
    "imagen-3.0-generate-001",
    "imagen-3.0-fast-generate-001"
]

def validate_video_parameters(parameters: Optional[VideoGenerationParameters]) -> Tuple[bool, Optional[str]]:
    """
    Validate video generation parameters including model selection.
    Returns (is_valid, error_message) tuple.
    """
    if not parameters:
        return True, None
    
    # Validate model selection
    if parameters.model and parameters.model not in SUPPORTED_VIDEO_MODELS:
        return False, f"Unsupported video model '{parameters.model}'. Supported models: {', '.join(SUPPORTED_VIDEO_MODELS)}"
    
    # Validate duration
    if parameters.durationSeconds:
        if parameters.durationSeconds < 1 or parameters.durationSeconds > 60:
            return False, "Duration must be between 1 and 60 seconds"
    
    # Validate aspect ratio
    if parameters.aspectRatio:
        valid_ratios = ["16:9", "9:16", "1:1", "4:3", "3:4"]
        if parameters.aspectRatio not in valid_ratios:
            return False, f"Unsupported aspect ratio '{parameters.aspectRatio}'. Supported ratios: {', '.join(valid_ratios)}"
    
    # Validate sample count
    if parameters.sampleCount:
        if parameters.sampleCount < 1 or parameters.sampleCount > 4:
            return False, "Sample count must be between 1 and 4"
    
    return True, None


def get_credentials_or_default(user_creds: Optional[UserCredentials]) -> Dict[str, Any]:
    """
    Extract credentials from user request or fall back to environment variables.
    Returns a dictionary with all necessary credential information.
    """
    return {
        'gemini_api_key': user_creds.gemini_api_key if user_creds else None or os.getenv("GEMINI_API_KEY"),
        'openai_api_key': os.getenv("OPENAI_API_KEY"),  # Always use internal OpenAI key
        'google_cloud_credentials': user_creds.google_cloud_credentials if user_creds else None,
        'google_cloud_project': user_creds.google_cloud_project if user_creds else None or os.getenv("GOOGLE_CLOUD_PROJECT", "mcp-summer-school"),
        'vertex_ai_region': user_creds.vertex_ai_region if user_creds else None or os.getenv("VERTEX_AI_REGION", "us-central1"),
        'gcs_bucket': user_creds.gcs_bucket if user_creds else None or os.getenv("GCS_BUCKET"),
        'elevenlabs_api_key': user_creds.elevenlabs_api_key if user_creds else None or os.getenv("XI_KEY"),
        'vertex_model_id': os.getenv("VEO_MODEL_ID", "veo-3.0-generate-preview")  # Not user-configurable for now
    }


def create_google_cloud_credentials(creds_dict: Dict[str, Any], google_cloud_credentials: Optional[Dict[str, Any]]):
    """
    Create Google Cloud credentials object from user-provided JSON dict or environment.
    Returns (credentials, credentials_path) tuple.
    """
    if google_cloud_credentials:
        # User provided credentials as JSON dict
        credentials = service_account.Credentials.from_service_account_info(
            google_cloud_credentials,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        return credentials, None
    else:
        # Fall back to environment credentials
        vertex_credentials_path = os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH")
        if vertex_credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                vertex_credentials_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            return credentials, vertex_credentials_path
        else:
            # Use default credentials
            credentials, _ = default()
            return credentials, None


def create_storage_client(creds_dict: Dict[str, Any]) -> storage.Client:
    """Create Google Cloud Storage client with appropriate credentials."""
    if creds_dict['google_cloud_credentials']:
        return storage.Client.from_service_account_info(creds_dict['google_cloud_credentials'])
    else:
        gcs_credentials_path = os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH")
        if gcs_credentials_path:
            return storage.Client.from_service_account_json(gcs_credentials_path)
        else:
            return storage.Client()


def validate_credentials(creds_dict: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate that all required credentials are present and functional.
    Returns (is_valid, error_message) tuple.
    """
    try:
        # OpenAI is always available via internal key, check if Gemini is also available
        has_gemini = bool(creds_dict.get('gemini_api_key'))
        has_openai = bool(creds_dict.get('openai_api_key'))  # Internal key
        
        # At least OpenAI should be available (internal), but validate it exists
        if not has_openai:
            return False, "Internal OpenAI API key not configured on server"
        
        # Check Google Cloud credentials
        if not creds_dict['google_cloud_project']:
            return False, "Google Cloud project is required"
        
        if not creds_dict['gcs_bucket']:
            return False, "GCS bucket is required"
        
        # Test Google Cloud credentials by creating credentials object
        try:
            create_google_cloud_credentials(creds_dict, creds_dict['google_cloud_credentials'])
        except Exception as e:
            return False, f"Invalid Google Cloud credentials: {str(e)}"
        
        # Test storage client creation (lighter validation)
        try:
            storage_client = create_storage_client(creds_dict)
            # Just ensure we can create a bucket reference (doesn't make API call)
            bucket = storage_client.bucket(creds_dict['gcs_bucket'])
        except Exception as e:
            return False, f"Cannot create storage client: {str(e)}"
        
        # Basic validation for API keys
        # OpenAI key is internal - validate it exists and has reasonable length
        if creds_dict.get('openai_api_key') and len(creds_dict['openai_api_key']) < 20:
            return False, "Internal OpenAI API key appears to be invalid (too short)"
        
        # Gemini key is optional and user-provided
        if creds_dict.get('gemini_api_key') and len(creds_dict['gemini_api_key']) < 20:
            return False, "Gemini API key appears to be invalid (too short)"
        
        # Basic validation for ElevenLabs (only if provided)
        if creds_dict.get('elevenlabs_api_key'):
            if len(creds_dict['elevenlabs_api_key']) < 20:
                return False, "ElevenLabs API key appears to be invalid (too short)"
        
        return True, None
        
    except Exception as e:
        return False, f"Credential validation error: {str(e)}"


def clear_sensitive_data(job_meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove sensitive credential data from job metadata.
    Returns cleaned metadata dict.
    """
    cleaned_meta = job_meta.copy()
    
    # Remove sensitive keys (OpenAI key is internal so still needs to be cleared from job metadata)
    sensitive_keys = [
        'gemini_api_key',
        'openai_api_key',
        'google_cloud_credentials', 
        'elevenlabs_api_key',
        'credentials'
    ]
    
    for key in sensitive_keys:
        if key in cleaned_meta:
            del cleaned_meta[key]
    
    return cleaned_meta