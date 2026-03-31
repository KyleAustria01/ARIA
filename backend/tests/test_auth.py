"""
Pytest tests for authentication logic in ARIA AI Interview System.
"""
import pytest
from backend.static_users import verify_password, STATIC_RECRUITERS
from backend.auth import create_access_token, verify_recruiter
from jose import jwt
from backend.config import settings

def test_verify_password():
    password = "supersecret1"
    hashed = STATIC_RECRUITERS["recruiter1"]
    assert verify_password(password, hashed)
    assert not verify_password("wrongpass", hashed)

def test_verify_recruiter():
    assert verify_recruiter("recruiter1", "supersecret1")
    assert not verify_recruiter("recruiter1", "badpass")
    assert not verify_recruiter("unknown", "supersecret1")

def test_create_access_token():
    data = {"sub": "recruiter1"}
    token = create_access_token(data)
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert decoded["sub"] == "recruiter1"
