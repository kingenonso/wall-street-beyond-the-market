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
    test_weeks_ahead: int = 0          # a test world that has been fast-forwarded; always 0 on a live world


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
    location: "LocationEffect | None" = None
    buys_from: list["Supplier"] = []


class LocationEffect(BaseModel):
    """What a company's head-office location does to its running costs."""
    running_cost_bps: int              # 10000 = the national average; 8800 = 12% cheaper
    reasons: list[str]


class Supplier(BaseModel):
    sector: str
    share_bps: int                     # of its own sales, spent with this kind of supplier


class HouseholdGroup(BaseModel):
    location: str
    population_bps: int
    income_kobo: Kobo
    wages_kobo: Kobo
    government_kobo: Kobo
    pensions_kobo: Kobo
    spending_kobo: Kobo
    savings_kobo: Kobo
    claims_kobo: Kobo                  # paid to them by insurers after a severe event
    debt_kobo: Kobo                    # what they owe the banks
    jobs: int
    income_change_bps: int | None
    jobs_change_bps: int | None


class MoneyHolder(BaseModel):
    holder: str
    amount_kobo: Kobo
    share_bps: int


class EconomyQuarter(BaseModel):
    period: int
    period_label: str
    company_sales_kobo: Kobo
    household_income_kobo: Kobo
    household_spending_kobo: Kobo
    jobs: int


class SpendingShare(BaseModel):
    sector: str
    share_bps: int


class CommodityPrice(BaseModel):
    name: str                          # what it is called on screen
    index_bps: int                     # 10000 = its price on the day the world began
    change_bps: int | None             # against the quarter before


class PricesAndRates(BaseModel):
    """Prices and the Central Bank (design document, section 10)."""
    inflation_bps: int                 # how much prices rose over the past year
    inflation_target_bps: int
    inflation_low_bps: int             # the band the Central Bank accepts
    inflation_high_bps: int
    price_index_bps: int               # 10000 = prices on the day the world began
    wage_index_bps: int
    policy_rate_bps: int               # the Central Bank's interest rate for the quarter now running
    previous_rate_bps: int
    rate_reason: str
    household_loan_rate_bps: int       # what households pay on a bank loan this quarter
    confidence_bps: int                # households' readiness to spend (10000 = the usual)
    demand_gap_bps: int                # spending against what the economy can supply (0 = in step)
    household_debt_kobo: Kobo
    central_bank_lending_kobo: Kobo    # what the banks owe the Central Bank
    commodities: list[CommodityPrice]


class MacroQuarter(BaseModel):
    period: int
    period_label: str
    inflation_bps: int
    policy_rate_bps: int
    money_kobo: Kobo


class MoneyWatch(BaseModel):
    """The Money Watch (design document, section 10)."""
    reading: str                       # green, amber or red
    reasons: list[str]
    action: str
    money_growth_bps: int              # over the past year
    output_growth_bps: int


class EconomyResponse(BaseModel):
    period: int
    period_label: str | None
    money_in_existence_kobo: Kobo
    households: list[HouseholdGroup]
    money: list[MoneyHolder]
    history: list[EconomyQuarter]              # oldest first
    household_spending: list[SpendingShare]    # where households' spending went in the latest quarter
    prices: PricesAndRates | None = None       # none before the first quarter has closed
    macro_history: list[MacroQuarter] = []     # oldest first
    money_watch: MoneyWatch | None = None


class NewsItem(BaseModel):
    period: int
    period_label: str
    day: int                           # the day of that quarter, 1 to 90
    outlet: str                        # the newspaper's name
    kind: str
    story: str                         # items about the same affair share a story
    importance: int
    headline: str
    body: str
    tickers: list[str]
    locations: list[str]


class NewsResponse(BaseModel):
    outlets: list[str]
    items: list[NewsItem]              # newest first


# ---------------------------------------------------------------------------
# The Broad Street Exchange
# ---------------------------------------------------------------------------

class OrderRequest(Request):
    """An order to buy or sell shares. Prices are whole kobo per share."""
    ticker: str = Field(pattern=r"^[A-Z]{3}$")
    side: Literal["buy", "sell"]
    kind: Literal["limit", "market"]
    quantity: int = Field(gt=0, le=100_000_000_000, strict=True)
    limit_price_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000, strict=True)


class PriceLevel(BaseModel):
    price_kobo: Kobo
    quantity: int                      # shares waiting at this price, all orders together
    orders: int


class PublicTrade(BaseModel):
    price_kobo: Kobo
    quantity: int
    in_auction: bool
    traded_at: datetime


class QuoteResponse(BaseModel):
    """What everybody may see of one share. Nobody's name is on it."""
    ticker: str
    name: str
    market_state: str
    last_price_kobo: Kobo | None       # none until the first trade
    reference_price_kobo: Kobo         # the last price of the session before
    lowest_today_kobo: Kobo
    highest_today_kobo: Kobo
    fee_bps: int                       # what buyer and seller each pay on a trade, in hundredths of a percent
    bids: list[PriceLevel]             # buyers waiting, best price first
    offers: list[PriceLevel]           # sellers waiting, best price first
    trades: list[PublicTrade]          # newest first


class OrderResponse(BaseModel):
    id: int
    ticker: str
    name: str
    side: str
    kind: str
    limit_price_kobo: Kobo | None
    quantity: int
    remaining: int
    held_kobo: Kobo                    # cash the exchange is holding for this order
    value_traded_kobo: Kobo
    fees_paid_kobo: Kobo
    status: str
    closed_reason: str | None
    placed_at: datetime
    closed_at: datetime | None


class PlacedOrderResponse(BaseModel):
    order: OrderResponse
    trades: list[PublicTrade]          # what this order traded at once


class Holding(BaseModel):
    ticker: str
    name: str
    shares: int                        # owned and free to sell
    held_for_orders: int               # owned, and held by the exchange for sell orders still waiting
    price_kobo: Kobo                   # the last price, or the listing price if it has never traded
    value_kobo: Kobo
