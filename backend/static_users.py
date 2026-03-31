"""
Static recruiter credentials for ARIA AI Interview System.
Passwords are bcrypt-hashed and loaded from environment variables via config.py.
"""
from typing import Dict
import os
import bcrypt

from config import settings



def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def load_static_recruiters() -> Dict[str, str]:
    """
    Load recruiter credentials from settings.recruiter_credentials as 'username:password' string.
    Returns:
        Dict[str, str]: username to bcrypt hash mapping
    """
    creds_str = settings.recruiter_credentials
    if not creds_str:
        raise RuntimeError("recruiter_credentials not set in config")
    pairs = [creds_str] if ',' not in creds_str else creds_str.split(',')
    result = {}
    for pair in pairs:
        if ':' not in pair:
            continue
        user, pw = pair.split(':', 1)
        result[user.strip()] = hash_password(pw.strip())
    return result

STATIC_RECRUITERS: Dict[str, str] = load_static_recruiters()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
