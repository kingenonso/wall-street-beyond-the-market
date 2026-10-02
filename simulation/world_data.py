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

# --- Opening money (design document, section 10) ---
# The Central Bank issues the opening money. From then on, no new naira appears.

# The Treasury's reserve. Each new player's starting cash is paid out of it.
TREASURY_OPENING_M = 500_000              # ₦500 billion: enough for one million players
# TEMPORARY STAND-IN (replaced in Stage 3 by real households): one account standing
# for every household and small business. It buys from the companies and is paid
# their wages and supplier bills.
PUBLIC_OPENING_M = 12_000_000             # ₦12 trillion

STARTING_GRANT_NAIRA = 500_000            # what each new player receives (section 10)

SHARE_CAPITAL_BPS = 4000                  # 40% of opening equity is share capital, the rest past profits
BOOK_VALUE_PER_SHARE_NAIRA = 20           # sets how many shares each company starts with
SHARE_LOT = 10_000_000                    # share counts are rounded to the nearest 10 million

LOAN_TERM_QUARTERS = 24                   # bank loans are repaid over six game years
BOND_TERM_QUARTERS = 32                   # bonds are repaid in one go after eight game years
BOND_DISCOUNT_BPS = 150                   # bonds pay 1.5 points less interest than bank loans
