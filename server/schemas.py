"""The shapes of what the website sends and what the server sends back."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator

# Money crosses between server and website as a whole number of kobo written as
# text, e.g. "50000000". Text keeps very large amounts exact; a browser's ordinary
# numbers start losing kobo above about ₦90 trillion.
Kobo = Annotated[int, PlainSerializer(lambda value: str(value), return_type=str)]

ProfileIcon = Literal["male", "female"]


class Request(BaseModel):
    """Anything the website sends. Fields the server did not ask for are refused,
    so nobody can slip in extras such as their own cash balance."""

    model_config = ConfigDict(extra="forbid")


class SignUpRequest(Request):
    email: EmailStr
    display_name: str = Field(min_length=3, max_length=24)
    password: str = Field(min_length=10, max_length=128)
    date_of_birth: date
    profile_icon: ProfileIcon

    @field_validator("display_name")
    @classmethod
    def tidy_display_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Display name must be at least 3 characters.")
        if not all(ch.isalnum() or ch in " _-" for ch in value):
            raise ValueError("Display name may use letters, numbers, spaces, hyphens and underscores.")
        return value


class LoginRequest(Request):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileIconRequest(Request):
    profile_icon: ProfileIcon


class Money(BaseModel):
    amount_kobo: Kobo
    currency: str


class PlayerResponse(BaseModel):
    id: str
    display_name: str
    reputation: int
    profile_icon: ProfileIcon | None
    cash: Money


class MovementResponse(BaseModel):
    """One line of the player's own account history."""
    at: datetime
    kind: str
    memo: str
    counterparty: str
    amount_kobo: Kobo          # positive: money in. Negative: money out.
    currency: str


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


class WorldStatusResponse(BaseModel):
    companies: int
    last_closed_period: int
    last_closed_label: str | None      # e.g. "Year 2 Q4". None until the first quarter closes.


class CompanySummary(BaseModel):
    ticker: str
    name: str
    headquarters: str
    period: int
    period_label: str
    credit_rating: str
    revenue_kobo: Kobo
    net_profit_kobo: Kobo
    total_assets_kobo: Kobo
    revenue_change_bps: int | None     # against the quarter before; None when there is nothing to compare


class SectorCompanies(BaseModel):
    code: str
    name: str
    companies: list[CompanySummary]


class CompaniesResponse(BaseModel):
    sectors: list[SectorCompanies]


class Owner(BaseModel):
    name: str
    shares: Kobo
    share_bps: int                     # 2500 = 25%


class FiledReport(BaseModel):
    period: int
    period_label: str
    version: int
    amended: bool
    filed_by: str
    filed_at: datetime
    credit_rating: str
    rating_reasons: list[str]
    # The statements exactly as filed. Every amount is kobo, written as text.
    figures: dict


class CompanyResponse(BaseModel):
    ticker: str
    name: str
    sector: str
    headquarters: str
    shares_in_issue: Kobo
    owners: list[Owner]
    reports: list[FiledReport]         # oldest first
