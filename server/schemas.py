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
    closing_rush: bool = False         # the last ten minutes of the trading day: lower fees, large orders shown
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


class WhyResponse(BaseModel):
    """Why a share's price is where it is today, from what is on record."""
    ticker: str
    name: str
    summary: str
    move_bps: int                      # today's move against the last price of the day before
    reference_price_kobo: Kobo
    last_price_kobo: Kobo | None       # none if it has not traded today
    bought_in_a_hurry: int             # shares buyers took from waiting sellers today
    sold_in_a_hurry: int               # shares sellers sold to waiting buyers today
    reasons: list[str]                 # what the investors did today, newest first
    valuation_label: str | None        # the filing the investors' view of its worth is built on
    valuation_reasons: list[str]       # why that view changed with that filing


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


# ---------------------------------------------------------------------------
# The market screens (Stage 4, Part A, slice 3)
# ---------------------------------------------------------------------------

class MarketShare(BaseModel):
    ticker: str
    name: str
    sector: str
    price_kobo: Kobo                   # the last price, or the listing price if it has never traded
    traded: bool                       # whether it has ever traded
    change_bps: int                    # today, against the last price of the day before
    volume: int                        # shares traded today
    market_value_kobo: Kobo            # the whole company at this price
    credit_rating: str | None


class IndexPoint(BaseModel):
    session_date: date
    level: float                       # the BSX 50 at the end of that trading day


class MarketResponse(BaseModel):
    market_state: str
    paused_until: datetime | None      # set while trading is paused after a sharp fall
    index: float                       # the BSX 50: 1,000 when each share was first listed
    index_change_bps: int              # today
    market_value_kobo: Kobo
    volume: int
    trades: int
    shares: list[MarketShare]
    index_history: list[IndexPoint]    # oldest first


class TradingDay(BaseModel):
    session_date: date
    open_kobo: Kobo
    close_kobo: Kobo
    high_kobo: Kobo
    low_kobo: Kobo
    volume: int


class PortfolioHolding(BaseModel):
    ticker: str
    name: str
    shares: int
    held_for_orders: int
    price_kobo: Kobo
    change_bps: int
    value_kobo: Kobo
    cost_kobo: Kobo                    # what the shares still held cost, fees included (average cost)
    gain_kobo: Kobo                    # value less cost; negative for a loss
    dividends_kobo: Kobo               # dividends received from this company so far


class PortfolioResponse(BaseModel):
    cash_kobo: Kobo
    held_for_orders_kobo: Kobo         # cash the exchange is holding for buy orders still waiting
    shares_value_kobo: Kobo
    total_kobo: Kobo
    dividends_kobo: Kobo               # all dividends received so far
    realised_kobo: Kobo                # gains less losses on shares already sold, after fees
    holdings: list[PortfolioHolding]
    advice: list[str] = []             # the personal advisory summary: observations, never tips
    net_worth: list["NetWorthDay"] = []  # the end of each trading day, oldest first, then today so far


class NpvYear(BaseModel):
    label: str
    profit_kobo: Kobo                  # the profit expected
    value_today_kobo: Kobo             # what that profit is worth in today's money


class Shareholder(BaseModel):
    holder: str
    shares: int
    share_bps: int


class AnalysisResponse(BaseModel):
    """The investor's page on one company. Every figure comes from what the company filed,
    its credit rating, the Central Bank's rate and prices on the exchange."""
    ticker: str
    name: str
    filing_label: str                  # the filing the figures are taken from
    price_kobo: Kobo
    shares_in_issue: int
    market_value_kobo: Kobo
    yearly_profit_kobo: Kobo
    yearly_sales_kobo: Kobo
    yearly_dividends_kobo: Kobo
    owners_funds_kobo: Kobo
    book_per_share_kobo: Kobo
    price_to_profit: float | None      # the whole company's price as a multiple of its yearly profit
    price_to_sales: float | None
    price_to_owners_funds: float | None
    market_price_to_profit: float | None
    dividend_yield_bps: int
    npv_per_share_kobo: Kobo
    npv_total_kobo: Kobo
    npv_method: str                    # 'profits' or 'assets'
    npv_gap_bps: int                   # the share price against the NPV: above zero means the price is higher
    growth_bps: int
    discount_bps: int
    long_run_bps: int
    schedule: list[NpvYear]
    verdict: str
    reasons: list[str]
    risks: list[str]
    shareholders: list[Shareholder]


class WatchRequest(Request):
    alert_above_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000, strict=True)
    alert_below_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000, strict=True)


class WatchedShare(BaseModel):
    ticker: str
    name: str
    price_kobo: Kobo
    change_bps: int
    alert_above_kobo: Kobo | None
    alert_below_kobo: Kobo | None
    reached: str | None                # 'above' or 'below' once an alert price has been reached


# ---------------------------------------------------------------------------
# Stage 4, slice 4: the ticker, the Closing Rush and Bell, company facts, industries.
# ---------------------------------------------------------------------------

class TickerShare(BaseModel):
    ticker: str
    price_kobo: Kobo
    change_bps: int


class TickerResponse(BaseModel):
    market_state: str
    closing_rush: bool
    index: float
    index_change_bps: int
    shares: list[TickerShare]


class LargeOrder(BaseModel):
    ticker: str
    name: str
    side: str
    quantity: int
    value_kobo: Kobo
    shown_at: datetime


class BellMover(BaseModel):
    ticker: str
    name: str
    close_kobo: Kobo
    change_bps: int


class ClosingBell(BaseModel):
    session_date: date
    rung_at: datetime
    index: float
    index_change_bps: int
    lines: list[str]                   # the day in a few sentences: the index, the winner, the loser, the boldest move
    stories: list[str]                 # the day's main headlines
    advisory: list[str]                # the market advisory: a short reading of the economy
    next: str                          # what is coming
    winner: BellMover | None
    loser: BellMover | None
    risers: int
    fallers: int


class ClosingBellResponse(BaseModel):
    in_rush: bool
    fee_bps: int                       # what a trade costs each side right now
    usual_fee_bps: int
    large_orders: list[LargeOrder]     # large orders placed in today's Closing Rush, newest first, without names
    bell: ClosingBell | None           # the latest broadcast


class ProfitPerShare(BaseModel):
    period: int
    label: str
    kobo_per_share: float              # in today's shares, allowing for any splits since
    net_profit_kobo: Kobo


class IndustryPlace(BaseModel):
    sector: str
    rank: int                          # by sales over the past year; 1 is the largest
    of: int
    share_bps: int                     # its share of the industry's sales


class NextResults(BaseModel):
    at: datetime
    label: str


class CompanyFactsResponse(BaseModel):
    ticker: str
    name: str
    filing_label: str
    profit_per_share: list[ProfitPerShare]       # oldest first
    yearly_profit_per_share_kobo: float
    compared_with: str                 # "the same quarter a year ago", "the quarter before", or empty
    sales_change_bps: int | None
    profit_change_bps: int | None
    sales_before_kobo: Kobo | None
    profit_before_kobo: Kobo | None
    cash_kobo: Kobo
    cash_change_quarter_kobo: Kobo
    cash_change_year_kobo: Kobo
    cash_in_three_months_kobo: Kobo    # an estimate: today's cash plus the average quarterly change over the past year
    cash_outlook: str
    year_high_kobo: Kobo | None        # over the past game year (four real weeks)
    year_low_kobo: Kobo | None
    next_results: NextResults | None
    industry: IndustryPlace


class ReportQuarter(BaseModel):
    period: int
    label: str


class ResultsReportResponse(BaseModel):
    ticker: str
    name: str
    period: int
    label: str
    title: str
    paragraphs: list[str]
    available: list[ReportQuarter]


class IndustryCompany(BaseModel):
    ticker: str
    name: str
    rank: int
    share_bps: int
    sales_kobo: Kobo                   # over the past four filed quarters
    sales_growth_bps: int | None       # against the four quarters before; empty until two years are filed
    price_kobo: Kobo | None
    change_bps: int
    market_value_kobo: Kobo


class Industry(BaseModel):
    code: str
    name: str
    market_value_kobo: Kobo
    change_bps: int                    # today, all its companies together
    sales_kobo: Kobo
    sales_growth_bps: int | None
    companies: list[IndustryCompany]


class NetWorthDay(BaseModel):
    session_date: date
    total_kobo: Kobo
