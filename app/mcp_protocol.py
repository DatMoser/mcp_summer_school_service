# app/mcp_protocol.py
"""
Model Context Protocol (MCP) JSON-RPC 2.0 implementation.
Provides MCP-compliant protocol handling with initialization, capabilities, and primitives.
"""

import json
import uuid
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field
from enum import Enum


class JsonRpcVersion(str, Enum):
    """JSON-RPC version specification"""
    V2_0 = "2.0"


class McpProtocolVersion(str, Enum):
    """MCP protocol version specification"""
    V2024_11_05 = "2024-11-05"  # Legacy HTTP+SSE dual endpoint
    V2025_03_26 = "2025-03-26"  # Streamable HTTP single endpoint
    V2025_06_18 = "2025-06-18"  # Latest streamable HTTP


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request structure"""
    jsonrpc: JsonRpcVersion = JsonRpcVersion.V2_0
    id: Union[str, int, None] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response structure"""
    jsonrpc: JsonRpcVersion = JsonRpcVersion.V2_0
    id: Union[str, int, None] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error structure"""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None


class McpError:
    """Standard MCP error codes"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # MCP-specific errors
    INVALID_PROTOCOL_VERSION = -32000
    UNSUPPORTED_CAPABILITY = -32001
    TOOL_EXECUTION_ERROR = -32002
    RESOURCE_NOT_FOUND = -32003


class ServerCapabilities(BaseModel):
    """MCP server capabilities"""
    tools: Optional[Dict[str, Any]] = {"listChanged": True}
    resources: Optional[Dict[str, Any]] = {"subscribe": True, "listChanged": True}
    prompts: Optional[Dict[str, Any]] = {"listChanged": True}
    logging: Optional[Dict[str, Any]] = {}


class ClientCapabilities(BaseModel):
    """MCP client capabilities"""
    sampling: Optional[Dict[str, Any]] = {}
    roots: Optional[Dict[str, Any]] = {"listChanged": True}


class ServerInfo(BaseModel):
    """MCP server information"""
    name: str = "MCP Video/Audio Generator"
    version: str = "1.0.0"


class ClientInfo(BaseModel):
    """MCP client information"""
    name: str
    version: str


class InitializeRequest(BaseModel):
    """MCP initialize request parameters"""
    protocolVersion: McpProtocolVersion
    capabilities: ClientCapabilities
    clientInfo: ClientInfo


class InitializeResponse(BaseModel):
    """MCP initialize response"""
    protocolVersion: McpProtocolVersion = McpProtocolVersion.V2025_06_18  # Latest by default
    capabilities: ServerCapabilities = Field(default_factory=ServerCapabilities)
    serverInfo: ServerInfo = Field(default_factory=ServerInfo)


class McpProtocolHandler:
    """
    MCP Protocol handler implementing JSON-RPC 2.0 and MCP specification.
    Handles protocol initialization, capability negotiation, and message routing.
    """
    
    def __init__(self):
        self.initialized = False
        self.client_capabilities: Optional[ClientCapabilities] = None
        self.client_info: Optional[ClientInfo] = None
        
        # Supported MCP protocol versions
        self.supported_versions = [
            McpProtocolVersion.V2024_11_05,  # Legacy
            McpProtocolVersion.V2025_03_26,  # Streamable HTTP
            McpProtocolVersion.V2025_06_18   # Latest
        ]
        
        # Server capabilities
        self.server_capabilities = ServerCapabilities(
            tools={"listChanged": True},
            resources={"subscribe": True, "listChanged": True}, 
            prompts={"listChanged": True},
            logging={}
        )
    
    def create_error_response(self, request_id: Union[str, int, None], 
                            error_code: int, message: str, 
                            data: Optional[Dict[str, Any]] = None) -> JsonRpcResponse:
        """Create a JSON-RPC error response"""
        error = JsonRpcError(code=error_code, message=message, data=data)
        return JsonRpcResponse(id=request_id, error=error.dict())
    
    def create_success_response(self, request_id: Union[str, int, None], 
                              result: Dict[str, Any]) -> JsonRpcResponse:
        """Create a JSON-RPC success response"""
        return JsonRpcResponse(id=request_id, result=result)
    
    def validate_json_rpc(self, data: Dict[str, Any]) -> Optional[JsonRpcRequest]:
        """Validate and parse JSON-RPC request"""
        try:
            return JsonRpcRequest(**data)
        except Exception as e:
            return None
    
    def handle_initialize(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle MCP initialize method"""
        if not request.params:
            return self.create_error_response(
                request.id, McpError.INVALID_PARAMS, 
                "Initialize requires parameters"
            )
        
        try:
            init_request = InitializeRequest(**request.params)
            
            # Validate protocol version
            if init_request.protocolVersion not in self.supported_versions:
                return self.create_error_response(
                    request.id, McpError.INVALID_PROTOCOL_VERSION,
                    f"Unsupported protocol version: {init_request.protocolVersion}. Supported: {self.supported_versions}"
                )
            
            # Store client info and capabilities
            self.client_capabilities = init_request.capabilities
            self.client_info = init_request.clientInfo
            self.initialized = True

            # Return server capabilities and info with negotiated version
            response = InitializeResponse(protocolVersion=init_request.protocolVersion)
            return self.create_success_response(request.id, response.dict())
            
        except Exception as e:
            return self.create_error_response(
                request.id, McpError.INVALID_PARAMS,
                f"Invalid initialize parameters: {str(e)}"
            )
    
    def handle_notifications_initialized(self, request: JsonRpcRequest) -> Optional[JsonRpcResponse]:
        """Handle notifications/initialized - no response needed"""
        # This is a notification, no response required
        return None
    
    def handle_ping(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle ping method for connection testing"""
        return self.create_success_response(request.id, {})
    
    def is_initialized(self) -> bool:
        """Check if the protocol has been initialized"""
        return self.initialized
    
    def route_request(self, request: JsonRpcRequest) -> Optional[JsonRpcResponse]:
        """Route JSON-RPC request to appropriate handler"""
        # Handle core protocol methods
        if request.method == "initialize":
            return self.handle_initialize(request)
        elif request.method == "notifications/initialized":
            return self.handle_notifications_initialized(request)
        elif request.method == "ping":
            return self.handle_ping(request)
        
        # Check if initialized for other methods
        if not self.is_initialized() and request.method not in ["initialize", "notifications/initialized"]:
            return self.create_error_response(
                request.id, McpError.INVALID_REQUEST,
                "Protocol not initialized. Call 'initialize' first."
            )
        
        # Will be handled by specific endpoint handlers
        return None
    
    def process_message(self, message: str) -> Optional[str]:
        """
        Process incoming JSON-RPC message and return response.
        Returns None for notifications (no response needed).
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            error_response = self.create_error_response(
                None, McpError.PARSE_ERROR, "Invalid JSON"
            )
            return error_response.json()
        
        # Validate JSON-RPC structure
        request = self.validate_json_rpc(data)
        if not request:
            error_response = self.create_error_response(
                data.get("id"), McpError.INVALID_REQUEST, "Invalid JSON-RPC request"
            )
            return error_response.json()
        
        # Route to appropriate handler
        response = self.route_request(request)
        
        # Return JSON response or None for notifications
        return response.json() if response else None


# Global protocol handler instance
mcp_handler = McpProtocolHandler()