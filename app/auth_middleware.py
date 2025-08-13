# app/auth_middleware.py
"""
API Key authentication middleware for securing all endpoints.
Validates X-API-Key header against environment variable.
"""

import os
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate API key for all requests.
    Checks X-API-Key header against API_KEY environment variable.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.api_key = os.getenv("API_KEY")
        
        if not self.api_key:
            print("WARNING: API_KEY environment variable is not set - service will reject all requests")
            print("Please set API_KEY environment variable to secure the service")
            self.api_key = None
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and validate API key.
        Returns 401 if API key is missing or invalid.
        Allows OPTIONS requests (CORS preflight) and health endpoint to pass through.
        """
        # Allow OPTIONS requests (CORS preflight) to pass through without authentication
        if request.method == "OPTIONS":
            response = await call_next(request)
            # Add CORS headers to OPTIONS response
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "X-API-Key, Content-Type, Authorization"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            return response
        
        # Allow health and validate endpoints to pass through without authentication
        if request.url.path in ["/health", "/validate"]:
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            return response
        
        # If no API key is configured on the server, reject all requests
        if not self.api_key:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Service Unavailable",
                    "message": "API key not configured on server. Contact administrator."
                },
                headers={
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY"
                }
            )
        
        # Get API key from header
        provided_api_key = request.headers.get("X-API-Key")
        
        # Check if API key is provided
        if not provided_api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "API key required. Please provide X-API-Key header."
                },
                headers={
                    "WWW-Authenticate": "ApiKey",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY"
                }
            )
        
        # Validate API key
        if provided_api_key != self.api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized", 
                    "message": "Invalid API key provided."
                },
                headers={
                    "WWW-Authenticate": "ApiKey",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY"
                }
            )
        
        # API key is valid, proceed with request
        response = await call_next(request)
        
        # Add security headers to response
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        
        return response