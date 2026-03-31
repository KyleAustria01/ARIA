def decode_invite_token(token: str) -> dict:
    """
    Decode a JWT invite token and return its payload.
    Args:
        token (str): JWT invite token.
    Returns:
        dict: Decoded payload.
    Raises:
        jose.JWTError: If token is invalid or expired.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
"""
Invite token system for ARIA AI Interview System.
Handles generation, storage, and validation of applicant invite tokens in Redis.
"""
from typing import Dict, Any
from datetime import datetime, timedelta
from jose import jwt
from config import settings
from redis_client import redis_client
import asyncio

async def generate_invite_token(applicant_name: str, role: str, expires_in_minutes: int = 60) -> str:
    """
    Generate and store a JWT invite token for an applicant in Redis.
    Args:
        applicant_name (str): Name of the applicant.
        role (str): Role for the interview.
        expires_in_minutes (int): Token expiry in minutes.
    Returns:
        str: JWT invite token.
    """
    expire = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
    payload = {
        "sub": applicant_name,
        "role": role,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    key = f"invite:{token}"
    await redis_client.set(key, applicant_name, ex=expires_in_minutes * 60)
    return token

async def validate_invite_token(token: str) -> bool:
    """
    Validate if an invite token exists and is valid in Redis.
    Args:
        token (str): JWT invite token.
    Returns:
        bool: True if valid, False otherwise.
    """
    key = f"invite:{token}"
    value = await redis_client.get(key)
    return value is not None

async def mark_token_used(token: str) -> None:
    """
    Mark an invite token as used by deleting it from Redis.
    Args:
        token (str): JWT invite token.
    """
    key = f"invite:{token}"
    await redis_client.delete(key)
