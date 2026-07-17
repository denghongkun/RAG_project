from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=64)


class RegisterRequest(LoginRequest):
    role: str = "user"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class AskRequest(BaseModel):
    session_id: int
    question: str


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]


class EditQuestionRequest(BaseModel):
    message_id: int
    question: str


class EditQuestionResponse(BaseModel):
    answer: str
    sources: list[dict]
    deleted_count: int
