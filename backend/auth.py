"""
Authentication utilities for ARIA AI Interview System.
Handles JWT creation/validation and FastAPI dependencies for recruiter/applicant auth.
"""
from typing import Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from config import settings
from static_users import STATIC_RECRUITERS, verify_password
from redis_client import redis_client

OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="/api/recruiter/login")

class TokenData:
    """
    Token data structure for JWT payloads.
    """
    def __init__(self, username: str):
        self.username = username

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    Args:
        data (dict): Payload data.
        expires_delta (Optional[timedelta]): Expiry duration.
    Returns:
        str: Encoded JWT token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def verify_recruiter(username: str, password: str) -> bool:
    """
    Verify recruiter credentials against static users.
    Args:
        username (str): Recruiter username.
        password (str): Plain password.
    Returns:
        bool: True if valid, False otherwise.
    """
    hashed = STATIC_RECRUITERS.get(username)
    if not hashed:
        return False
    return verify_password(password, hashed)

def get_current_recruiter(token: str = Depends(OAUTH2_SCHEME)) -> str:
    """
    FastAPI dependency to get current recruiter from JWT.
    Args:
        token (str): JWT token from OAuth2.
    Returns:
        str: Recruiter username.
    Raises:
        HTTPException: If token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception

def get_current_applicant(token: str) -> str:
    """
    Validate applicant invite token (JWT) from Redis.
    Args:
        token (str): JWT invite token.
    Returns:
        str: Applicant name.
    Raises:
        HTTPException: If token is invalid, expired, or not in Redis.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired invite token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        applicant_name: str = payload.get("sub")
        if applicant_name is None:
            raise credentials_exception
        # Check token existence in Redis
        import asyncio
        loop = asyncio.get_event_loop()
        redis_value = loop.run_until_complete(redis_client.get(f"invite:{token}"))
        if not redis_value:
            raise credentials_exception
        return applicant_name
    except JWTError:
        raise credentials_exception
