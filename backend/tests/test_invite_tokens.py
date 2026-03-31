"""
Pytest tests for invite token system in ARIA AI Interview System.
"""
import pytest
import asyncio
from backend.invite_tokens import generate_invite_token, validate_invite_token, mark_token_used
from backend.config import settings

@pytest.mark.asyncio
async def test_generate_and_validate_invite_token():
    applicant_name = "Test Applicant"
    role = "QA Engineer"
    token = await generate_invite_token(applicant_name, role, expires_in_minutes=1)
    assert isinstance(token, str)
    is_valid = await validate_invite_token(token)
    assert is_valid
    await mark_token_used(token)
    is_valid_after = await validate_invite_token(token)
    assert not is_valid_after
