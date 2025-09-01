"""Simple Bearer token authentication for API protection."""
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings
from app.core.logger import logger
from typing import Optional

# Create the Bearer scheme
bearer_scheme = HTTPBearer(auto_error=False)


async def verify_bearer_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> bool:
    """
    Verify the Bearer token from the Authorization header.
    
    Returns True if valid, raises HTTPException if invalid.
    """
    # If no token is configured, allow all requests (for development)
    if not settings.api_bearer_token:
        return True
    
    # Log request details for debugging mobile issues
    origin = request.headers.get("origin", "no-origin")
    user_agent = request.headers.get("user-agent", "no-user-agent")
    auth_header = request.headers.get("authorization", "no-auth-header")
    
    # Log for debugging
    logger.info(f"Auth check - Method: {request.method}, Origin: {origin}, Auth present: {auth_header != 'no-auth-header'}")
    
    # Check if this is a preflight OPTIONS request
    if request.method == "OPTIONS":
        logger.info(f"Allowing OPTIONS request from origin: {origin}")
        return True
    
    # If no credentials provided
    if not credentials:
        logger.warning(f"Missing auth credentials from origin: {origin}, user-agent: {user_agent[:100]}")
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if the token matches
    if credentials.credentials != settings.api_bearer_token:
        logger.warning(f"Invalid auth token from origin: {origin}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return True