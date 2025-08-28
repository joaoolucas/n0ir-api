"""Simple Bearer token authentication for API protection."""
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings
from typing import Optional

# Create the Bearer scheme
bearer_scheme = HTTPBearer(auto_error=False)


async def verify_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> bool:
    """
    Verify the Bearer token from the Authorization header.
    
    Returns True if valid, raises HTTPException if invalid.
    """
    # If no token is configured, allow all requests (for development)
    if not settings.api_bearer_token:
        return True
    
    # If no credentials provided
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if the token matches
    if credentials.credentials != settings.api_bearer_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return True