"""The Nigeria trial world as it stands on day one.

This file is a catalogue, not logic: the 12 sectors, the 50 companies, and the
opening size of each. `simulation/genesis.py` reads it once to create the world.

All companies are invented. Names follow the design document, section 4.

Figures marked "x revenue" are multiples of a company's yearly revenue, so one
number (yearly revenue) sets the scale of each company and its sector sets the
shape. Rates are in basis points (100 = 1%).
"""

from __future__ import annotations

from dataclasses import dataclass

LAGOS, ABUJA, PORT_HARCOURT, ABA, KANO = "Lagos", "Abuja", "Port Harcourt", "Aba", "Kano"


@dataclass(frozen=True)
class Sector:
    code: str
    name: str
    # --- shape of the income statement ---
    cost_of_sales_bps: int          # cost of sales as a share of revenue
    opex_bps: int                   # opening running costs as a share of revenue
    revenue_growth_bps: int         # growth per quarter, of sales and of running costs alike (stand-in until Stage 3)
    season_bps: tuple[int, int, int, int]   # each quarter against an average one (10000)
    # --- shape of the opening balance sheet, as multiples of yearly revenue, in bps ---
    fixed_assets_x: int
    cash_x: int
    debt_x: int
    customer_loans_x: int = 0       # banks: lending to the public
    customer_funds_x: int = 0       # banks: deposits. Insurers: reserves for claims
    # --- other ---
    loan_rate_bps: int = 0          # yearly interest its companies pay on bank loans
    payout_bps: int = 4000          # share of profit paid out as dividends


FLAT = (10000, 10000, 10000, 10000)

SECTORS: tuple[Sector, ...] = (
    Sector("banking", "Commercial banks", 3800, 3000, 350, FLAT,
           fixed_assets_x=2500, cash_x=10000, debt_x=0,
           customer_loans_x=35000, customer_funds_x=44000, payout_bps=4000),
    Sector("consumer", "Consumer goods, food and drinks", 6200, 2000, 400, (9700, 9800, 10000, 10500),
           fixed_assets_x=5500, cash_x=1000, debt_x=2000, loan_rate_bps=1900, payout_bps=4500),
    Sector("oil_gas", "Oil and gas", 5800, 1400, 350, FLAT,
           fixed_assets_x=14000, cash_x=1200, debt_x=4500, loan_rate_bps=1800, payout_bps=4000),
    Sector("telecoms", "Telecoms", 4000, 2800, 450, FLAT,
           fixed_assets_x=12000, cash_x=1000, debt_x=4000, loan_rate_bps=1800, payout_bps=5000),
    Sector("cement", "Cement and building materials", 4800, 1700, 400, (10600, 9200, 9400, 10800),
           fixed_assets_x=15000, cash_x=1000, debt_x=3500, loan_rate_bps=1750, payout_bps=5000),
    Sector("agriculture", "Agriculture", 6600, 1600, 400, (8500, 9000, 10500, 12000),
           fixed_assets_x=9000, cash_x=1200, debt_x=2500, loan_rate_bps=2100, payout_bps=3000),
    Sector("real_estate", "Real estate and construction", 6000, 1500, 400, FLAT,
           fixed_assets_x=20000, cash_x=1500, debt_x=4500, loan_rate_bps=2200, payout_bps=3500),
    Sector("manufacturing", "Manufacturing and industrial", 6800, 1500, 350, FLAT,
           fixed_assets_x=8000, cash_x=1000, debt_x=3000, loan_rate_bps=2000, payout_bps=3500),
    Sector("media", "Media houses", 4500, 4000, 350, (9500, 10000, 9700, 10800),
           fixed_assets_x=4000, cash_x=1500, debt_x=1000, loan_rate_bps=2200, payout_bps=3000),
    Sector("insurance", "Insurance", 6200, 2400, 400, FLAT,
           fixed_assets_x=2000, cash_x=12000, debt_x=0, customer_funds_x=9000, payout_bps=4000),
    Sector("power", "Power and utilities", 6000, 1500, 400, (10500, 9800, 9500, 10200),
           fixed_assets_x=16000, cash_x=1000, debt_x=5000, loan_rate_bps=2000, payout_bps=4000),
    Sector("transport", "Transport and logistics", 6600, 1800, 350, (9700, 9800, 10000, 10500),
           fixed_assets_x=9000, cash_x=1000, debt_x=3500, loan_rate_bps=2100, payout_bps=3500),
)

# The same for every company (stand-ins until Stage 3).
DEPRECIATION_BPS = 125       # buildings and machines wear out 1.25% a quarter
COMPANY_TAX_BPS = 3000       # 30% of profit


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    sector: str
    headquarters: str
    yearly_revenue_m: int        # opening yearly revenue, in millions of naira
    lender: str | None = None    # ticker of the bank that holds its loan
    bond_share_bps: int = 0      # how much of its debt is a bond held by investors
    # --- What makes this company different from the usual one in its sector. ---
    # Left empty, a company gets a small variation of its own (see genesis).
    trend_bps: int | None = None       # its sales growth each quarter, above or below its sector's
    volatility_bps: int | None = None  # how far one quarter can swing from its usual
    cost_extra_bps: int = 0            # extra cost of sales, in points of revenue
    opex_times_bps: int = 10_000       # running costs against the sector's usual (10000 = the same)
    debt_times_bps: int | None = None  # borrowing against the sector's usual
    cash_times_bps: int = 10_000       # opening cash against the sector's usual
    funds_times_bps: int = 10_000      # banks: customers' money against the sector's usual
    overdue_bps: int = 0               # share of its bank loan that is ALREADY past its repayment date
    unpaid_bills_bps: int = 0          # bills already owed and unpaid, as a share of one quarter's sales


COMPANIES: tuple[Company, ...] = (
    # Commercial banks (6)
    Company("IKB", "Ikenga Bank", "banking", LAGOS, 340_000),
    Company("OTB", "Olumo Trust Bank", "banking", LAGOS, 210_000, cost_extra_bps=1_200, cash_times_bps=6_000, funds_times_bps=10_800),
    Company("HMB", "Harmattan Bank", "banking", ABUJA, 280_000),
    Company("KCB", "Kainji Commercial Bank", "banking", LAGOS, 150_000, cost_extra_bps=2_000, cash_times_bps=4_500, funds_times_bps=11_000),
    Company("ZCB", "Zuma Capital Bank", "banking", ABUJA, 120_000, cost_extra_bps=800, cash_times_bps=7_000, funds_times_bps=10_500),
    Company("OBB", "Obudu Bank", "banking", PORT_HARCOURT, 90_000),
    # Consumer goods, food and drinks (6)
    Company("ADF", "Adunni Foods", "consumer", LAGOS, 260_000, lender="OTB"),
    Company("TMB", "Tamuno Breweries", "consumer", PORT_HARCOURT, 310_000, lender="OBB"),
    Company("ZRB", "Zobo Royal Beverages", "consumer", ABUJA, 95_000, lender="ZCB"),
    Company("GFM", "Garki Flour Mills", "consumer", ABUJA, 420_000, lender="HMB", bond_share_bps=4000),
    Company("AYD", "Ayo Dairy", "consumer", LAGOS, 130_000, lender="KCB"),
    Company("AHP", "Amaka Household Products", "consumer", LAGOS, 110_000, lender="IKB"),
    # Oil and gas (4)
    Company("OPP", "Opobo Petroleum", "oil_gas", PORT_HARCOURT, 780_000, lender="IKB", bond_share_bps=5000),
    Company("BRE", "Brass River Energy", "oil_gas", PORT_HARCOURT, 520_000, lender="HMB", bond_share_bps=5000),
    Company("DCG", "Delta Creek Gas", "oil_gas", PORT_HARCOURT, 300_000, lender="OBB"),
    Company("ORM", "Okrika Refining & Marketing", "oil_gas", PORT_HARCOURT, 640_000, lender="OTB", bond_share_bps=5000),
    # Telecoms (3)
    Company("GGM", "Gangan Mobile", "telecoms", LAGOS, 900_000, lender="IKB", bond_share_bps=5000),
    Company("EKC", "Ekwe Communications", "telecoms", LAGOS, 380_000, lender="KCB", bond_share_bps=4000),
    Company("SGN", "Sango Networks", "telecoms", ABUJA, 210_000, lender="ZCB"),
    # Cement and building materials (3)
    Company("IDC", "Idanre Cement", "cement", LAGOS, 700_000, lender="HMB", bond_share_bps=5000),
    Company("KRC", "Kogi Ridge Cement", "cement", ABUJA, 290_000, lender="ZCB"),
    Company("ABA", "Aso Blocks & Aggregates", "cement", ABUJA, 60_000, lender="HMB"),
    # Agriculture (3)
    Company("OFF", "Ofada Farms", "agriculture", LAGOS, 85_000, lender="OTB"),
    Company("SPA", "Sokoto Plains Agro", "agriculture", ABUJA, 120_000, lender="HMB"),
    Company("ICE", "Ikom Cocoa Estates", "agriculture", PORT_HARCOURT, 70_000, lender="OBB"),
    # Real estate and construction (3)
    Company("EYP", "Eyo Properties", "real_estate", LAGOS, 75_000, lender="IKB"),
    Company("GDC", "Gidan Construction", "real_estate", ABUJA, 180_000, lender="HMB"),
    Company("ULE", "Ulo Estates", "real_estate", PORT_HARCOURT, 55_000, lender="OBB"),
    # Manufacturing and industrial (3)
    Company("ARI", "Ariaria Industries", "manufacturing", PORT_HARCOURT, 140_000, lender="KCB"),
    Company("DSW", "Dala Steel Works", "manufacturing", ABUJA, 230_000, lender="ZCB"),
    Company("ONP", "Onitsha Packaging", "manufacturing", LAGOS, 65_000, lender="OTB"),
    # Media houses (3)
    Company("TLH", "The Lagoon Herald", "media", LAGOS, 18_000, lender="OTB"),
    Company("ONN", "Ogene News Network", "media", ABUJA, 32_000, lender="ZCB"),
    Company("TNL", "The Naira Ledger", "media", LAGOS, 12_000, lender="IKB"),
    # Insurance (2)
    Company("AGA", "Agbada Assurance", "insurance", LAGOS, 95_000),
    Company("KKI", "Kuka Insurance", "insurance", ABUJA, 48_000, cost_extra_bps=300, cash_times_bps=8_500),
    # Power and utilities (2)
    Company("AMP", "Amadioha Power", "power", LAGOS, 260_000, lender="IKB", bond_share_bps=4000),
    Company("JPE", "Jos Plateau Electric", "power", ABUJA, 110_000, lender="KCB"),
    # Transport and logistics (2)
    Company("DFL", "Danfo Logistics", "transport", LAGOS, 150_000, lender="OTB"),
    Company("LFS", "Lokoja Freight & Shipping", "transport", PORT_HARCOURT, 90_000, lender="OBB"),

    # --- Ten more, added by the owner on 2 October 2026: built weak or troubled on
    # purpose, so that credit ratings run all the way from AAA to D from day one. ---
    # Already in default: a loan has passed its repayment date unpaid.
    Company("BTS", "Bonny Tide Shipping", "transport", PORT_HARCOURT, 40_000, lender="OBB",
            trend_bps=-500, volatility_bps=900, cost_extra_bps=500, opex_times_bps=12_000,
            debt_times_bps=20_000, cash_times_bps=2_500, overdue_bps=3_000),
    Company("KTX", "Kainji Textiles", "manufacturing", KANO, 35_000, lender="ZCB",
            trend_bps=-600, volatility_bps=800, cost_extra_bps=600, opex_times_bps=12_500,
            debt_times_bps=22_000, cash_times_bps=2_000, overdue_bps=2_500),
    # Behind on their bills.
    Company("ZRH", "Zuma Rock Hotels", "real_estate", ABUJA, 28_000, lender="HMB",
            trend_bps=-450, volatility_bps=1_000, cost_extra_bps=400, opex_times_bps=14_000,
            debt_times_bps=16_000, cash_times_bps=1_500, unpaid_bills_bps=2_500),
    Company("OGA", "Oguta Airways", "transport", LAGOS, 120_000, lender="KCB",
            trend_bps=0, volatility_bps=1_200, cost_extra_bps=900, opex_times_bps=11_000,
            debt_times_bps=17_000, cash_times_bps=1_500, unpaid_bills_bps=2_000),
    Company("CPM", "Calabar Paper Mills", "manufacturing", ABA, 22_000, lender="OTB",
            trend_bps=-550, volatility_bps=700, cost_extra_bps=900, opex_times_bps=12_000,
            debt_times_bps=15_000, cash_times_bps=2_000, unpaid_bills_bps=1_500),
    # Weak, but paying their way.
    Company("LFN", "Lekki Fibre Networks", "telecoms", LAGOS, 60_000, lender="IKB",
            trend_bps=250, volatility_bps=900, cost_extra_bps=500, opex_times_bps=11_000,
            debt_times_bps=19_000, cash_times_bps=9_000),
    Company("BHF", "Benue Harvest Foods", "agriculture", KANO, 45_000, lender="HMB",
            trend_bps=-50, volatility_bps=1_400, cost_extra_bps=300, opex_times_bps=10_500,
            debt_times_bps=16_000, cash_times_bps=9_000),
    Company("NBS", "Niger Bridge Steel", "manufacturing", ABA, 160_000, lender="IKB", bond_share_bps=3000,
            trend_bps=50, volatility_bps=700, cost_extra_bps=0,
            debt_times_bps=15_000, cash_times_bps=25_000),
    Company("SCM", "Sahel Crest Microfinance Bank", "banking", KANO, 9_000,
            trend_bps=0, volatility_bps=900, cost_extra_bps=2_200, opex_times_bps=11_000,
            cash_times_bps=3_000, funds_times_bps=8_300),
    Company("ISP", "Ibom Solar Power", "power", PORT_HARCOURT, 30_000, lender="OBB",
            trend_bps=150, volatility_bps=500, debt_times_bps=13_000, cash_times_bps=22_000),
)

# Whole sectors have good and bad quarters too: up to this far above or below trend.
SECTOR_VOLATILITY_BPS = 300
assert 0 <= SECTOR_VOLATILITY_BPS < 5_000

# ---------------------------------------------------------------------------
# Stage 3: the people and the places.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Location:
    name: str
    population_bps: int        # its share of the country's people
    running_cost_bps: int      # cost of running a business here, against the average (10000)
    monthly_wage_naira: int    # what one worker here is paid in a month


LOCATIONS: tuple[Location, ...] = (
    Location(LAGOS, 3500, 11_000, 300_000),
    Location(ABUJA, 1500, 10_500, 280_000),
    Location(PORT_HARCOURT, 1500, 10_000, 260_000),
    Location(ABA, 1500, 8_800, 200_000),
    Location(KANO, 2000, 8_500, 185_000),
)

# Where a kind of business fits especially well or badly: added to the location's
# running cost. -500 = five points cheaper to run there.
SECTOR_FIT: dict[tuple[str, str], int] = {
    ("oil_gas", PORT_HARCOURT): -600,      # the oil and gas hub
    ("banking", LAGOS): -400,              # the financial centre
    ("telecoms", LAGOS): -300,
    ("media", LAGOS): -300,
    ("manufacturing", ABA): -500,          # the manufacturing and trading hub
    ("manufacturing", KANO): -200,
    ("agriculture", KANO): -600,           # farmland and the northern market
    ("real_estate", ABUJA): -300,          # close to government contracts
    ("transport", PORT_HARCOURT): -300,    # a port
    ("transport", LAGOS): -300,            # the main port
    ("cement", KANO): 500,                 # far from the ports
    ("manufacturing", ABUJA): 300,
    ("oil_gas", KANO): 800,
    ("power", KANO): 400,
    ("power", ABA): 300,
}

# What each kind of company buys from other kinds, as a share of its own sales
# (hundredths of a percent). The rest of its cost of sales is paid to people.
INPUTS: dict[str, dict[str, int]] = {
    "banking":       {"telecoms": 200, "real_estate": 150, "power": 50, "media": 50, "insurance": 50},
    "consumer":      {"agriculture": 1800, "manufacturing": 900, "transport": 500, "power": 300, "oil_gas": 300,
                      "banking": 100, "telecoms": 50, "media": 150, "insurance": 50},
    "oil_gas":       {"manufacturing": 800, "transport": 500, "power": 200, "real_estate": 100, "banking": 150,
                      "insurance": 150, "telecoms": 50},
    "telecoms":      {"power": 500, "manufacturing": 400, "real_estate": 300, "oil_gas": 200, "banking": 100,
                      "media": 150, "insurance": 50},
    "cement":        {"oil_gas": 900, "power": 600, "transport": 600, "manufacturing": 300, "banking": 100,
                      "insurance": 50},
    "agriculture":   {"oil_gas": 400, "transport": 500, "manufacturing": 500, "banking": 150, "insurance": 100,
                      "power": 100},
    "real_estate":   {"cement": 2000, "manufacturing": 900, "transport": 300, "oil_gas": 200, "banking": 250,
                      "insurance": 100, "power": 100},
    "manufacturing": {"power": 700, "oil_gas": 500, "transport": 500, "agriculture": 400, "manufacturing": 600,
                      "cement": 100, "banking": 150, "insurance": 50, "telecoms": 50},
    "media":         {"telecoms": 500, "power": 200, "manufacturing": 200, "real_estate": 200, "banking": 50},
    "insurance":     {"banking": 150, "telecoms": 100, "media": 100, "real_estate": 100},
    "power":         {"oil_gas": 2500, "manufacturing": 400, "transport": 200, "banking": 150, "insurance": 100},
    "transport":     {"oil_gas": 2000, "manufacturing": 500, "insurance": 200, "banking": 150, "power": 100,
                      "telecoms": 50},
}

# Where the Government's purchases go, and where companies' spending on buildings
# and machines goes. Each adds up to 10000.
GOVERNMENT_BUYS: dict[str, int] = {
    "cement": 2500, "real_estate": 2500, "power": 1000, "manufacturing": 1000, "transport": 1000,
    "telecoms": 500, "media": 500, "consumer": 500, "oil_gas": 500,
}
INVESTMENT_BUYS: dict[str, int] = {
    "manufacturing": 3500, "cement": 3000, "real_estate": 2500, "transport": 500, "telecoms": 500,
}
assert sum(GOVERNMENT_BUYS.values()) == 10_000 and sum(INVESTMENT_BUYS.values()) == 10_000

# TEMPORARY STAND-IN (Stage 12 gives the Government a real budget): of the tax it
# collects, this share buys from companies and the rest pays public-sector wages.
GOVERNMENT_PURCHASE_BPS = 4000

HOME_STAFF_BPS = 5000              # half a company's staff work where its head office is; the rest are spread by population
LOCAL_PREFERENCE_BPS = 13_000      # buyers favour companies based in their own location by this much
HOUSEHOLD_SPEND_FROM_INCOME_BPS = 8500
INVESTOR_SPEND_FROM_INCOME_BPS = 8500
INVESTOR_SPEND_FROM_SAVINGS_BPS = 1000

# Pensions (design document, section 11).
PENSION_EMPLOYEE_BPS = 800         # taken from each wage
PENSION_EMPLOYER_BPS = 1000        # added by the employer on top of the wage
# TEMPORARY STAND-IN (the market opens in Stage 4, pension managers arrive with the
# Asset Manager build): until funds have a market to invest in, they hold what they
# own and pay out pensions at about the rate money comes in.
PENSION_PAY_FROM_INFLOW_BPS = 9000
PENSION_PAY_FROM_SAVINGS_BPS = 300

# How companies behave.
OPEX_ADJUST_BPS = 2500             # each quarter, running costs move this far towards what sales justify
DISTRESS_CUT_BPS = 300             # a company in trouble cuts running costs a further 3% a quarter
CASH_TARGET_QUARTERS = 3           # cash a healthy company likes to hold, in quarters of running costs
SPARE_CASH_TO_EXPANSION_BPS = 2500 # of cash above that target, this share is spent on expanding
SPARE_CASH_TO_OWNERS_BPS = 2500    # and this share is paid to owners as an extra dividend
EXPANSION_PULL_BPS = 5000          # how strongly expanding raises a company's share of its market
PULL_RETURN_BPS = 500              # each quarter a company's pull drifts this far back towards where it began,
                                   # so no company can swallow its whole market just by trending
HOUSEHOLD_MOOD_BPS = 300           # households spend up to this much more or less than their habit, quarter to quarter
EXTRA_DIVIDEND_LIMIT_BPS = 500     # an extra dividend may take at most this share of past profits kept in the business

# --- Opening money (design document, section 10) ---
# The Central Bank issues the opening money. From then on, no new naira appears.

# The Treasury's reserve. Each new player's starting cash is paid out of it.
TREASURY_OPENING_M = 500_000              # ₦500 billion: enough for one million players
# The savings of all households on day one, shared out by population.
HOUSEHOLDS_OPENING_M = 12_000_000         # ₦12 trillion

STARTING_GRANT_NAIRA = 500_000            # what each new player receives (section 10)

SHARE_CAPITAL_BPS = 4000                  # 40% of opening equity is share capital, the rest past profits
BOOK_VALUE_PER_SHARE_NAIRA = 20           # sets how many shares each company starts with
SHARE_LOT = 10_000_000                    # share counts are rounded to the nearest 10 million

LOAN_TERM_QUARTERS = 24                   # bank loans are repaid over six game years
BOND_TERM_QUARTERS = 32                   # bonds are repaid in one go after about eight game years
BOND_STAGGER_QUARTERS = 3                 # ...but not all in the same quarter: each company's falls a little later than the last
BOND_DISCOUNT_BPS = 150                   # bonds pay 1.5 points less interest than bank loans
