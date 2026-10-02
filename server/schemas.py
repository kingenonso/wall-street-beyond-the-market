"""The shapes of what the website sends and what the server sends back."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator

# Money crosses between server and website as a whole number of kobo written as
# text, e.g. "50000000". Text keeps very large amounts exact; a browser's ordinary
# numbers start losing kobo above about ₦90 trillion.
Kobo = Annotated[int, PlainSerializer(lambda value: str(value), return_type=str)]

ProfileIcon = Literal["male", "female"]


# No player may pass themselves off as the game, the state or an institution.
RESERVED_NAME_PARTS = (
    "admin", "moderator", "gamemaster", "officialsupport", "centralbank", "treasury", "federalgovernment",
    "prizepool", "companymanagement", "playeraccount", "smallinvestors",
)


def display_name_key(name: str) -> str:
    """What a display name looks like at a glance: no accents, capitals, spaces or
    punctuation. Two names with the same key would be mistaken for each other, so
    only one player may hold each key."""
    stripped = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in stripped if ch.isalnum()).lower()


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
        value = " ".join(unicodedata.normalize("NFKC", value).split())   # no stray or doubled spaces
        if len(value) < 3:
            raise ValueError("Display name must be at least 3 characters.")
        # Letters of the Latin alphabet (accents and under-dots included) and digits only.
        # This stops names written with lookalike letters from another alphabet.
        for ch in value:
            latin_letter = ch.isalpha() and unicodedata.name(ch, "").startswith("LATIN")
            if not (latin_letter or ch in "0123456789 _-"):
                raise ValueError("Display name may use letters, numbers, spaces, hyphens and underscores.")
        key = display_name_key(value)
        if len(key) < 3:
            raise ValueError("Display name must have at least 3 letters or numbers.")
        if any(word in key for word in RESERVED_NAME_PARTS):
            raise ValueError("That display name is reserved. Please choose another.")
        return value


class ConfirmEmailRequest(Request):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")


class SignUpPendingResponse(BaseModel):
    """Sign-up is not finished until the emailed code is typed in."""
    detail: str
    email: str
    # Only ever filled in while no email service is connected (your own computer).
    code_shown_on_screen: str | None = None


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
    ebitda_kobo: Kobo                  # profit before interest paid, tax and wear on assets
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
