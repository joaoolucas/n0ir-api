"""Simple Bearer token authentication for API protection."""
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings
from app.core.logger import logger
from typing import Optional
from datetime import datetime, timedelta
import jwt

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


def create_session_token(wallet: str, expiry_hours: int = 24) -> str:
    """
    Create a JWT session token for a wallet address.

    Args:
        wallet: Ethereum wallet address
        expiry_hours: Hours until token expires (default 24)

    Returns:
        JWT token string
    """
    if not settings.jwt_secret:
        raise ValueError("JWT_SECRET not configured")

    payload = {
        "wallet": wallet.lower(),
        "exp": datetime.utcnow() + timedelta(hours=expiry_hours)
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    logger.info(f"Created session token for wallet {wallet[:10]}... (expires in {expiry_hours}h)")

    return token


async def get_authenticated_wallet(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> str:
    """
    Verify JWT session token or API Bearer token and return authenticated wallet address.

    Supports two authentication methods:
    1. JWT session token - Returns the wallet address from the token
    2. API_BEARER_TOKEN - Returns the user_id from the request path (for admin/service access)

    Args:
        request: FastAPI request object (to extract user_id from path for Bearer token auth)
        credentials: Bearer token credentials from request

    Returns:
        Lowercase wallet address from token or path

    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if it's the API Bearer token (for admin/service access)
    if settings.api_bearer_token and credentials.credentials == settings.api_bearer_token:
        # Extract user_id from path (e.g., /api/v1/users/{user_id}/transactions)
        path_params = request.path_params
        user_id = path_params.get("user_id")

        if user_id:
            logger.debug(f"API Bearer token authenticated for user: {user_id[:10]}...")
            return user_id.lower()
        else:
            # If no user_id in path, this is an admin endpoint, return empty string
            # The endpoint will need to handle this case
            logger.debug("API Bearer token authenticated (no user_id in path)")
            return ""

    # Try JWT authentication
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=500,
            detail="JWT authentication not configured"
        )

    try:
        # Decode and verify JWT
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"]
        )

        wallet = payload.get("wallet")
        if not wallet:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        logger.debug(f"JWT authenticated wallet: {wallet[:10]}...")
        return wallet

    except jwt.ExpiredSignatureError:
        logger.warning("Expired session token")
        raise HTTPException(
            status_code=401,
            detail="Session expired, please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )