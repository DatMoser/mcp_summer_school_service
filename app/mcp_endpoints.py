# app/mcp_endpoints.py
"""
MCP (Model Context Protocol) endpoint implementations.
Provides tools, resources, and prompts according to MCP specification.
"""

import json
import base64
from typing import Dict, Any, List, Optional
from app.mcp_models import (
    McpTool, McpToolInputSchema, McpToolResult, McpToolsListResult, McpToolsCallParams,
    McpResource, McpResourceContents, McpResourcesListResult, McpResourcesReadParams,
    McpPrompt, McpPromptArgument, McpGetPromptResult, McpPromptMessage, McpPromptsListResult, McpPromptsGetParams,
    UserCredentials, MCPRequest, WritingStyleRequest
)
from app.mcp_protocol import JsonRpcRequest, JsonRpcResponse, McpError, mcp_handler
from app.jobs import q, make_script, analyze_writing_style, gen_video, gen_audio
from app.credential_utils import get_credentials_or_default, validate_credentials, validate_video_parameters
import uuid
import os


class McpEndpoints:
    """
    MCP endpoint implementations for video/audio generation service.
    Provides tools, resources, and prompts through MCP protocol.
    """
    
    def __init__(self):
        self.tools = self._define_tools()
        self.prompts = self._define_prompts()
    
    def _define_tools(self) -> List[McpTool]:
        """Define available MCP tools"""
        return [
            McpTool(
                name="generate_video",
                description="Generate a video from text prompt using Google's Veo models",
                inputSchema=McpToolInputSchema(
                    type="object",
                    properties={
                        "prompt": {
                            "type": "string",
                            "description": "Text description of the video to generate"
                        },
                        "duration_seconds": {
                            "type": "integer",
                            "description": "Video duration in seconds (1-60)",
                            "minimum": 1,
                            "maximum": 60,
                            "default": 8
                        },
                        "aspect_ratio": {
                            "type": "string",
                            "description": "Video aspect ratio",
                            "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                            "default": "16:9"
                        },
                        "model": {
                            "type": "string",
                            "description": "Video generation model to use",
                            "enum": ["veo-3.0-generate-preview", "veo-2.0-generate-preview", "veo-1.0-generate-preview"],
                            "default": "veo-3.0-generate-preview"
                        },
                        "generate_audio": {
                            "type": "boolean",
                            "description": "Whether to generate audio for the video",
                            "default": True
                        },
                        "credentials": {
                            "type": "object",
                            "description": "User credentials for API access",
                            "properties": {
                                "gemini_api_key": {"type": "string"},
                                "google_cloud_credentials": {"type": "object"},
                                "google_cloud_project": {"type": "string"},
                                "vertex_ai_region": {"type": "string"},
                                "gcs_bucket": {"type": "string"}
                            }
                        }
                    },
                    required=["prompt"]
                )
            ),
            McpTool(
                name="generate_audio",
                description="Generate audio/podcast from text prompt using AI text-to-speech",
                inputSchema=McpToolInputSchema(
                    type="object",
                    properties={
                        "prompt": {
                            "type": "string",
                            "description": "Text description of the audio content to generate"
                        },
                        "generate_thumbnail": {
                            "type": "boolean",
                            "description": "Whether to generate a podcast thumbnail image",
                            "default": False
                        },
                        "thumbnail_prompt": {
                            "type": "string",
                            "description": "Custom prompt for thumbnail generation"
                        },
                        "credentials": {
                            "type": "object",
                            "description": "User credentials for API access",
                            "properties": {
                                "gemini_api_key": {"type": "string"},
                                "google_cloud_credentials": {"type": "object"},
                                "gcs_bucket": {"type": "string"},
                                "elevenlabs_api_key": {"type": "string"}
                            }
                        }
                    },
                    required=["prompt"]
                )
            ),
            McpTool(
                name="analyze_writing_style",
                description="Analyze dialogue style for podcast generation",
                inputSchema=McpToolInputSchema(
                    type="object",
                    properties={
                        "style_instruction": {
                            "type": "string",
                            "description": "Style instruction like 'Talk like Trump' or 'Speak like a professor'"
                        },
                        "credentials": {
                            "type": "object",
                            "description": "User credentials for API access",
                            "properties": {
                                "gemini_api_key": {"type": "string"}
                            }
                        }
                    },
                    required=["style_instruction"]
                )
            ),
            McpTool(
                name="check_job_status",
                description="Check the status of a video or audio generation job",
                inputSchema=McpToolInputSchema(
                    type="object",
                    properties={
                        "job_id": {
                            "type": "string",
                            "description": "The job ID to check status for"
                        }
                    },
                    required=["job_id"]
                )
            )
        ]
    
    def _define_prompts(self) -> List[McpPrompt]:
        """Define available MCP prompts"""
        return [
            McpPrompt(
                name="video_generation",
                description="Template for video generation with customizable parameters",
                arguments=[
                    McpPromptArgument(name="topic", description="Main topic or subject", required=True),
                    McpPromptArgument(name="style", description="Visual style (e.g., cinematic, cartoon, realistic)", required=False),
                    McpPromptArgument(name="mood", description="Mood or atmosphere", required=False),
                    McpPromptArgument(name="duration", description="Duration preference", required=False)
                ]
            ),
            McpPrompt(
                name="podcast_generation",
                description="Template for podcast/audio generation",
                arguments=[
                    McpPromptArgument(name="topic", description="Podcast topic", required=True),
                    McpPromptArgument(name="audience", description="Target audience", required=False),
                    McpPromptArgument(name="tone", description="Speaking tone", required=False),
                    McpPromptArgument(name="length", description="Desired length", required=False)
                ]
            ),
            McpPrompt(
                name="style_analysis",
                description="Template for analyzing speaking/writing styles",
                arguments=[
                    McpPromptArgument(name="reference", description="Style reference (person, character, or description)", required=True),
                    McpPromptArgument(name="context", description="Context or situation", required=False)
                ]
            )
        ]
    
    def handle_tools_list(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle tools/list method"""
        result = McpToolsListResult(tools=self.tools)
        return mcp_handler.create_success_response(request.id, result.dict())
    
    def handle_tools_call(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle tools/call method"""
        if not request.params:
            return mcp_handler.create_error_response(
                request.id, McpError.INVALID_PARAMS, "Missing parameters"
            )
        
        try:
            params = McpToolsCallParams(**request.params)
            tool_name = params.name
            arguments = params.arguments
            
            if tool_name == "generate_video":
                return self._handle_generate_video(request.id, arguments)
            elif tool_name == "generate_audio":
                return self._handle_generate_audio(request.id, arguments)
            elif tool_name == "analyze_writing_style":
                return self._handle_analyze_writing_style(request.id, arguments)
            elif tool_name == "check_job_status":
                return self._handle_check_job_status(request.id, arguments)
            else:
                return mcp_handler.create_error_response(
                    request.id, McpError.METHOD_NOT_FOUND, f"Unknown tool: {tool_name}"
                )
                
        except Exception as e:
            return mcp_handler.create_error_response(
                request.id, McpError.TOOL_EXECUTION_ERROR, str(e)
            )
    
    def _handle_generate_video(self, request_id, arguments: Dict[str, Any]) -> JsonRpcResponse:
        """Handle video generation tool call"""
        prompt = arguments.get("prompt")
        if not prompt:
            return mcp_handler.create_error_response(
                request_id, McpError.INVALID_PARAMS, "Missing required parameter: prompt"
            )
        
        # Build video request
        video_request = MCPRequest(
            mode="video",
            prompt=prompt,
            parameters={
                "durationSeconds": arguments.get("duration_seconds", 8),
                "aspectRatio": arguments.get("aspect_ratio", "16:9"),
                "model": arguments.get("model", "veo-3.0-generate-preview"),
                "generateAudio": arguments.get("generate_audio", True)
            },
            credentials=arguments.get("credentials")
        )
        
        try:
            # Get credentials
            creds_dict = get_credentials_or_default(video_request.credentials)
            
            # Validate credentials
            is_valid, error_message = validate_credentials(creds_dict)
            if not is_valid:
                return mcp_handler.create_error_response(
                    request_id, McpError.TOOL_EXECUTION_ERROR, f"Invalid credentials: {error_message}"
                )
            
            # Validate parameters
            is_valid, error_message = validate_video_parameters(video_request.parameters)
            if not is_valid:
                return mcp_handler.create_error_response(
                    request_id, McpError.TOOL_EXECUTION_ERROR, f"Invalid parameters: {error_message}"
                )
            
            # Submit job
            job_id = str(uuid.uuid4())
            video_req_dict = {
                "prompt": video_request.prompt,
                "parameters": video_request.parameters.dict() if video_request.parameters else {}
            }
            
            job = q.enqueue_call(func=gen_video, args=(video_req_dict, creds_dict), job_id=job_id)
            
            result = McpToolResult(
                content=[{
                    "type": "text",
                    "text": f"Video generation started successfully. Job ID: {job_id}. Use check_job_status tool to monitor progress."
                }],
                isError=False
            )
            return mcp_handler.create_success_response(request_id, result.dict())
            
        except Exception as e:
            return mcp_handler.create_error_response(
                request_id, McpError.TOOL_EXECUTION_ERROR, str(e)
            )
    
    def _handle_generate_audio(self, request_id, arguments: Dict[str, Any]) -> JsonRpcResponse:
        """Handle audio generation tool call"""
        prompt = arguments.get("prompt")
        if not prompt:
            return mcp_handler.create_error_response(
                request_id, McpError.INVALID_PARAMS, "Missing required parameter: prompt"
            )
        
        try:
            # Get credentials
            creds_dict = get_credentials_or_default(arguments.get("credentials"))
            
            # Validate credentials
            is_valid, error_message = validate_credentials(creds_dict)
            if not is_valid:
                return mcp_handler.create_error_response(
                    request_id, McpError.TOOL_EXECUTION_ERROR, f"Invalid credentials: {error_message}"
                )
            
            # Submit job
            job_id = str(uuid.uuid4())
            generate_thumbnail = arguments.get("generate_thumbnail", False)
            thumbnail_prompt = arguments.get("thumbnail_prompt")
            
            job = q.enqueue_call(
                func=gen_audio, 
                args=(prompt, creds_dict, generate_thumbnail, thumbnail_prompt), 
                job_id=job_id
            )
            
            result = McpToolResult(
                content=[{
                    "type": "text",
                    "text": f"Audio generation started successfully. Job ID: {job_id}. Use check_job_status tool to monitor progress."
                }],
                isError=False
            )
            return mcp_handler.create_success_response(request_id, result.dict())
            
        except Exception as e:
            return mcp_handler.create_error_response(
                request_id, McpError.TOOL_EXECUTION_ERROR, str(e)
            )
    
    def _handle_analyze_writing_style(self, request_id, arguments: Dict[str, Any]) -> JsonRpcResponse:
        """Handle writing style analysis tool call"""
        style_instruction = arguments.get("style_instruction")
        if not style_instruction:
            return mcp_handler.create_error_response(
                request_id, McpError.INVALID_PARAMS, "Missing required parameter: style_instruction"
            )
        
        try:
            # Get credentials
            creds_dict = get_credentials_or_default(arguments.get("credentials"))
            
            # Validate Gemini API key
            if not creds_dict.get('gemini_api_key'):
                return mcp_handler.create_error_response(
                    request_id, McpError.TOOL_EXECUTION_ERROR, "Gemini API key is required for style analysis"
                )
            
            # Analyze style
            analysis_result = analyze_writing_style(style_instruction, creds_dict['gemini_api_key'])
            
            result = McpToolResult(
                content=[{
                    "type": "text",
                    "text": f"Writing style analysis completed for: {style_instruction}"
                }, {
                    "type": "application/json",
                    "data": analysis_result
                }],
                isError=False
            )
            return mcp_handler.create_success_response(request_id, result.dict())
            
        except Exception as e:
            return mcp_handler.create_error_response(
                request_id, McpError.TOOL_EXECUTION_ERROR, str(e)
            )
    
    def _handle_check_job_status(self, request_id, arguments: Dict[str, Any]) -> JsonRpcResponse:
        """Handle job status check tool call"""
        job_id = arguments.get("job_id")
        if not job_id:
            return mcp_handler.create_error_response(
                request_id, McpError.INVALID_PARAMS, "Missing required parameter: job_id"
            )
        
        try:
            job = q.fetch_job(job_id)
            
            if job is None:
                return mcp_handler.create_error_response(
                    request_id, McpError.RESOURCE_NOT_FOUND, f"Job not found: {job_id}"
                )
            
            # Get job status info
            progress = job.meta.get('progress', 0)
            current_step = job.meta.get('current_step', 'Processing...')
            status = job.get_status()
            
            status_info = {
                "job_id": job_id,
                "status": status,
                "progress": progress,
                "current_step": current_step,
                "download_url": job.result if job.is_finished else None
            }
            
            result = McpToolResult(
                content=[{
                    "type": "application/json",
                    "data": status_info
                }],
                isError=False
            )
            return mcp_handler.create_success_response(request_id, result.dict())
            
        except Exception as e:
            return mcp_handler.create_error_response(
                request_id, McpError.TOOL_EXECUTION_ERROR, str(e)
            )
    
    def handle_resources_list(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle resources/list method"""
        # List available job resources
        resources = []
        
        # Add job status resources
        try:
            jobs = q.get_jobs()
            for job in jobs[:10]:  # Limit to recent 10 jobs
                resources.append(McpResource(
                    uri=f"job://{job.get_id()}",
                    name=f"Job {job.get_id()[:8]}",
                    description=f"Status and results for job {job.get_id()}",
                    mimeType="application/json"
                ))
        except Exception:
            pass  # Skip if can't access jobs
        
        result = McpResourcesListResult(resources=resources)
        return mcp_handler.create_success_response(request.id, result.dict())
    
    def handle_resources_read(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle resources/read method"""
        if not request.params:
            return mcp_handler.create_error_response(
                request.id, McpError.INVALID_PARAMS, "Missing parameters"
            )
        
        try:
            params = McpResourcesReadParams(**request.params)
            uri = params.uri
            
            if uri.startswith("job://"):
                job_id = uri[6:]  # Remove "job://" prefix
                return self._read_job_resource(request.id, job_id)
            else:
                return mcp_handler.create_error_response(
                    request.id, McpError.RESOURCE_NOT_FOUND, f"Unknown resource URI: {uri}"
                )
                
        except Exception as e:
            return mcp_handler.create_error_response(
                request.id, McpError.RESOURCE_NOT_FOUND, str(e)
            )
    
    def _read_job_resource(self, request_id, job_id: str) -> JsonRpcResponse:
        """Read job resource"""
        try:
            job = q.fetch_job(job_id)
            
            if job is None:
                return mcp_handler.create_error_response(
                    request_id, McpError.RESOURCE_NOT_FOUND, f"Job not found: {job_id}"
                )
            
            job_data = {
                "job_id": job_id,
                "status": job.get_status(),
                "progress": job.meta.get('progress', 0),
                "current_step": job.meta.get('current_step', 'Processing...'),
                "total_steps": job.meta.get('total_steps', 1),
                "result": job.result if job.is_finished else None,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None
            }
            
            contents = McpResourceContents(
                uri=f"job://{job_id}",
                mimeType="application/json",
                text=json.dumps(job_data, indent=2)
            )
            
            return mcp_handler.create_success_response(request_id, contents.dict())
            
        except Exception as e:
            return mcp_handler.create_error_response(
                request_id, McpError.RESOURCE_NOT_FOUND, str(e)
            )
    
    def handle_prompts_list(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle prompts/list method"""
        result = McpPromptsListResult(prompts=self.prompts)
        return mcp_handler.create_success_response(request.id, result.dict())
    
    def handle_prompts_get(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle prompts/get method"""
        if not request.params:
            return mcp_handler.create_error_response(
                request.id, McpError.INVALID_PARAMS, "Missing parameters"
            )
        
        try:
            params = McpPromptsGetParams(**request.params)
            prompt_name = params.name
            arguments = params.arguments or {}
            
            if prompt_name == "video_generation":
                return self._get_video_prompt(request.id, arguments)
            elif prompt_name == "podcast_generation":
                return self._get_podcast_prompt(request.id, arguments)
            elif prompt_name == "style_analysis":
                return self._get_style_analysis_prompt(request.id, arguments)
            else:
                return mcp_handler.create_error_response(
                    request.id, McpError.RESOURCE_NOT_FOUND, f"Unknown prompt: {prompt_name}"
                )
                
        except Exception as e:
            return mcp_handler.create_error_response(
                request.id, McpError.INVALID_PARAMS, str(e)
            )
    
    def _get_video_prompt(self, request_id, arguments: Dict[str, Any]) -> JsonRpcResponse:
        """Get video generation prompt"""
        topic = arguments.get("topic", "[TOPIC]")
        style = arguments.get("style", "cinematic")
        mood = arguments.get("mood", "engaging")
        duration = arguments.get("duration", "8 seconds")
        
        prompt_text = f"""Create a {style} {duration} video about {topic}.

The video should have a {mood} atmosphere and be visually compelling. Consider:
- Clear visual storytelling
- Smooth camera movements
- Good lighting and composition
- Appropriate pacing for the {duration} duration

Topic: {topic}
Style: {style}
Mood: {mood}
Duration: {duration}"""
        
        result = McpGetPromptResult(
            description=f"Video generation prompt for {topic}",
            messages=[McpPromptMessage(
                role="user",
                content={"type": "text", "text": prompt_text}
            )]
        )
        
        return mcp_handler.create_success_response(request_id, result.dict())
    
    def _get_podcast_prompt(self, request_id, arguments: Dict[str, Any]) -> JsonRpcResponse:
        """Get podcast generation prompt"""
        topic = arguments.get("topic", "[TOPIC]")
        audience = arguments.get("audience", "general audience")
        tone = arguments.get("tone", "conversational")
        length = arguments.get("length", "2-3 minutes")
        
        prompt_text = f"""Create a {tone} {length} podcast about {topic} for {audience}.

The podcast should be:
- Engaging and informative
- Well-structured with clear introduction and conclusion
- Appropriate for {audience}
- Delivered in a {tone} style
- Approximately {length} in length

Topic: {topic}
Audience: {audience}
Tone: {tone}
Length: {length}

Make it conversational and natural, as if speaking directly to listeners."""
        
        result = McpGetPromptResult(
            description=f"Podcast generation prompt for {topic}",
            messages=[McpPromptMessage(
                role="user",
                content={"type": "text", "text": prompt_text}
            )]
        )
        
        return mcp_handler.create_success_response(request_id, result.dict())
    
    def _get_style_analysis_prompt(self, request_id, arguments: Dict[str, Any]) -> JsonRpcResponse:
        """Get style analysis prompt"""
        reference = arguments.get("reference", "[REFERENCE]")
        context = arguments.get("context", "general speaking")
        
        prompt_text = f"""Analyze the speaking/writing style of {reference} in the context of {context}.

Please provide detailed analysis covering:
- Tone and vocal characteristics
- Vocabulary and language patterns
- Speech pace and rhythm
- Typical phrases and expressions
- Communication style and approach
- Target audience considerations

Reference: {reference}
Context: {context}

Focus on extracting specific, actionable style elements that can be used for content generation."""
        
        result = McpGetPromptResult(
            description=f"Style analysis prompt for {reference}",
            messages=[McpPromptMessage(
                role="user",
                content={"type": "text", "text": prompt_text}
            )]
        )
        
        return mcp_handler.create_success_response(request_id, result.dict())


# Global endpoints instance
mcp_endpoints = McpEndpoints()