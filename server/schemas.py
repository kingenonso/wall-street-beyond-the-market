"""The shapes of what the website sends and what the server sends back."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignUpRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=3, max_length=24)
    password: str = Field(min_length=10, max_length=128)
    date_of_birth: date

    @field_validator("display_name")
    @classmethod
    def tidy_display_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Display name must be at least 3 characters.")
        if not all(ch.isalnum() or ch in " _-" for ch in value):
            raise ValueError("Display name may use letters, numbers, spaces, hyphens and underscores.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Money(BaseModel):
    amount_kobo: int
    currency: str


class PlayerResponse(BaseModel):
    id: str
    display_name: str
    reputation: int
    cash: Money


class GameDateResponse(BaseModel):
    year: int
    quarter: int
    day_of_quarter: int


class ClockResponse(BaseModel):
    lagos_time: datetime
    market_state: str
    next_state: str
    next_change_at: datetime
    world_started: bool
    game_date: GameDateResponse | None
