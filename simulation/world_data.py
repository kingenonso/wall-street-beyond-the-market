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
    # --- Private equity stage, part 2: three industries whose companies are all private on day one. ---
    Sector("aviation", "Airlines", 6400, 2200, 400, (9600, 10400, 9800, 10600),
           fixed_assets_x=15000, cash_x=1200, debt_x=5000, loan_rate_bps=2200, payout_bps=2500),
    Sector("hospitality", "Hotels and leisure", 4200, 3200, 400, (9500, 9800, 10000, 11000),
           fixed_assets_x=22000, cash_x=1000, debt_x=4500, loan_rate_bps=2200, payout_bps=3000),
    Sector("shipping", "Shipping and ports", 6000, 1600, 350, FLAT,
           fixed_assets_x=16000, cash_x=1200, debt_x=5000, loan_rate_bps=2000, payout_bps=3500),
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
    listed: bool = True                # False: a private company, owned by its founders, not traded on the exchange


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

    # --- Private equity stage, part 2: thirty private companies, owned by their founders and not
    # listed. Some are gems, some are traps; the accounts tell part of the story and the rest is found
    # by digging. Players' empires may buy them, run them, and sell or list them. ---
    Company("MPK", "Mama Put Kitchens", "consumer", LAGOS, 18_000, lender="OTB", listed=False, trend_bps=250),
    Company("KGO", "Kano Groundnut Oils", "consumer", KANO, 26_000, lender="ZCB", listed=False),
    Company("SSC", "Suya Spot Chain", "consumer", ABUJA, 9_000, lender="HMB", listed=False, trend_bps=300, volatility_bps=900),
    Company("UGS", "Ughelli Gas Services", "oil_gas", PORT_HARCOURT, 40_000, lender="OBB", listed=False),
    Company("EFD", "Escravos Fuel Depots", "oil_gas", PORT_HARCOURT, 55_000, lender="IKB", listed=False,
            cost_extra_bps=400, debt_times_bps=15_000, cash_times_bps=5_000),
    Company("IDX", "Ikeja Data Centres", "telecoms", LAGOS, 15_000, lender="IKB", listed=False, trend_bps=350),
    Company("EWT", "Ewekoro Tiles", "cement", LAGOS, 12_000, lender="OTB", listed=False),
    Company("ASQ", "Ashaka Quarries", "cement", KANO, 8_000, lender="ZCB", listed=False, trend_bps=-200,
            cost_extra_bps=500, opex_times_bps=12_000),
    Company("JPG", "Jos Plateau Growers", "agriculture", ABUJA, 7_000, lender="HMB", listed=False, volatility_bps=1_200),
    Company("KRM", "Kebbi Rice Mills", "agriculture", KANO, 22_000, lender="ZCB", listed=False, trend_bps=200),
    Company("OPO", "Ogoni Palm Oil", "agriculture", PORT_HARCOURT, 11_000, lender="OBB", listed=False),
    Company("BID", "Bar Beach Developers", "real_estate", LAGOS, 30_000, lender="IKB", listed=False,
            debt_times_bps=17_000, cash_times_bps=4_000),
    Company("MTH", "Maitama Homes", "real_estate", ABUJA, 14_000, lender="HMB", listed=False),
    Company("ALW", "Aba Leather Works", "manufacturing", ABA, 10_000, lender="KCB", listed=False, trend_bps=150),
    Company("NAP", "Nnewi Auto Parts", "manufacturing", ABA, 24_000, lender="KCB", listed=False),
    Company("KNP", "Kano Plastics", "manufacturing", KANO, 13_000, lender="ZCB", listed=False, trend_bps=-150,
            unpaid_bills_bps=1_000, cash_times_bps=3_000),
    Company("OWR", "Owambe Radio", "media", LAGOS, 4_000, lender="OTB", listed=False, trend_bps=200),
    Company("KMG", "Kano Mini-Grids", "power", KANO, 6_000, lender="ZCB", listed=False, trend_bps=300),
    Company("OJH", "Ojota Haulage", "transport", LAGOS, 16_000, lender="OTB", listed=False),
    Company("KRF", "Kano Rail Freight", "transport", KANO, 20_000, lender="HMB", listed=False, cost_extra_bps=300),
    Company("EKS", "Eko Skyways", "aviation", LAGOS, 60_000, lender="IKB", listed=False),
    Company("ARW", "Arewa Air", "aviation", KANO, 35_000, lender="HMB", listed=False, cost_extra_bps=300),
    Company("GCA", "Garden City Airlines", "aviation", PORT_HARCOURT, 25_000, lender="OBB", listed=False,
            trend_bps=-200, debt_times_bps=16_000, cash_times_bps=4_000, unpaid_bills_bps=1_500),
    Company("IGH", "Ikoyi Grand Hotels", "hospitality", LAGOS, 28_000, lender="IKB", listed=False),
    Company("MPH", "Millennium Park Hotels", "hospitality", ABUJA, 18_000, lender="HMB", listed=False, trend_bps=200),
    Company("ENI", "Enyimba Inns", "hospitality", ABA, 6_000, lender="KCB", listed=False),
    Company("RWH", "Rivers Waterfront Hotel", "hospitality", PORT_HARCOURT, 9_000, lender="OBB", listed=False,
            trend_bps=-100, opex_times_bps=11_500),
    Company("ACL", "Apapa Container Lines", "shipping", LAGOS, 45_000, lender="OTB", listed=False),
    Company("OPS", "Onne Port Services", "shipping", PORT_HARCOURT, 30_000, lender="OBB", listed=False, trend_bps=150),
    Company("CCS", "Calabar Coastal Shipping", "shipping", PORT_HARCOURT, 14_000, lender="KCB", listed=False,
            overdue_bps=2_000, debt_times_bps=15_000, cash_times_bps=3_000),
)

# Whole sectors have good and bad quarters too: up to this far above or below trend.
SECTOR_VOLATILITY_BPS = 150      # most of a sector's ups and downs now come from real events
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
    ("shipping", LAGOS): -300,
    ("shipping", PORT_HARCOURT): -300,
    ("aviation", LAGOS): -200,             # the busiest airport
    ("hospitality", ABUJA): -200,          # government travel
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
    "aviation":      {"oil_gas": 2500, "manufacturing": 500, "insurance": 300, "banking": 150, "telecoms": 100,
                      "consumer": 150, "media": 100},
    "hospitality":   {"consumer": 1200, "power": 500, "real_estate": 300, "manufacturing": 300, "telecoms": 150,
                      "insurance": 100, "banking": 100, "media": 150},
    "shipping":      {"oil_gas": 2000, "manufacturing": 700, "insurance": 300, "banking": 150, "power": 100,
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
HOUSEHOLD_MOOD_BPS = 150           # households spend up to this much more or less than their habit, quarter to quarter
EXTRA_DIVIDEND_LIMIT_BPS = 500     # an extra dividend may take at most this share of past profits kept in the business

# ---------------------------------------------------------------------------
# Stage 3, Part B: prices, the Central Bank, lending, events.
# ---------------------------------------------------------------------------

# The Central Bank's published rule (design document, section 10).
INFLATION_TARGET_BPS = 600         # it aims for prices rising 6% a year...
INFLATION_BAND_BPS = 300           # ...and accepts anything from 3% to 9%
NEUTRAL_RATE_BPS = 1300            # the interest rate that neither pushes the economy on nor holds it back
RATE_RESPONSE_BPS = 10_000         # for each point inflation is above target, the rate goes one point above neutral
RATE_DEMAND_RESPONSE_BPS = 2500    # and a quarter of a point for each point spending runs ahead of what the economy can supply
RATE_HOLD_WITHIN_BPS = 50          # it holds when its rule points to a rate within half a point of today's
RATE_STEP_BPS = 50                 # it moves the rate at most half a point a quarter
RATE_FLOOR_BPS, RATE_CEILING_BPS = 400, 3000
OPENING_RATE_BPS = 1300

# Prices.
CAPACITY_GROWTH_BPS = 50           # what the economy can produce grows 0.5% a quarter
PRICE_ADJUST_BPS = 1000            # on top of the expected rise, prices close a tenth of the gap to what demand justifies each quarter
WAGE_FOLLOWS_PRICES_BPS = 10_000   # wages keep pace with prices
COMMODITY_RETURN_BPS = 1500        # a commodity's price drifts this far back towards the general price level
COMMODITY_SWING_BPS = 400          # and swings up to 4% a quarter by itself
# Which kind of company sells each commodity, and how much of the general price level it carries.
COMMODITIES: dict[str, tuple[str, int]] = {
    "energy": ("oil_gas", 500), "agriculture": ("agriculture", 400),
    "metals": ("manufacturing", 150), "materials": ("cement", 150),
}

# What a borrower pays above the Central Bank's rate, by credit rating.
LOAN_SPREAD_BPS = {"AAA": 200, "AA": 300, "A": 400, "BBB": 550, "BB": 750, "B": 1000, "CCC": 1400, "D": 1800}
HOUSEHOLD_LOAN_SPREAD_BPS = 600
HOUSEHOLD_REPAY_BPS = 500          # households repay 5% of what they owe each quarter
CREDIT_GROWTH_BPS = 200            # at the neutral rate, lending grows 2% a quarter, in step with a healthy economy
CREDIT_RATE_SENSITIVITY_BPS = 1000 # each point the rate is below neutral raises new lending by a tenth, and the reverse
CREDIT_APPETITE_LIMITS_BPS = (2000, 25_000)
HOUSEHOLD_DEBT_COMFORT_QUARTERS = 3 # households grow their borrowing while they owe about three quarters' income; less as they owe more
BANK_RESERVE_BPS = 1000            # a bank keeps ready cash of at least 10% of its customers' money
BANK_LENDING_LIMIT_X = 8           # a bank's total lending may not pass eight times its owners' funds
CENTRAL_BANK_LENDING_LIMIT_X = 8    # and the Central Bank will not lend a bank more than eight times those funds
LOAN_LOSS_BPS = 1000               # each quarter a lender writes off 10% of a loan that is past its date
EXPANSION_LOAN_BPS = 50            # a sound company may borrow 0.5% of its buildings and machines a quarter to expand
EXPANSION_DEBT_LIMIT_YEARS = 2.5   # ...while its borrowings stay under 2.5 years of EBITDA

# Insurance.
INSURED_SHARE_BPS = 7000           # insurers pay 70% of damage to buildings and machines
HOUSEHOLD_CLAIM_BPS = 30           # after a severe local event, insurers pay households 0.3% of their quarter's spending

# The Money Watch (design document, section 10).
MONEY_AMBER_GAP_BPS = 500          # amber when money grows five points a year faster than the economy...
MONEY_AMBER_GROWTH_BPS = 1000      # ...and is itself growing more than 10% a year (a slump alone is not too much money)
MONEY_RED_GAP_BPS = 1500           # red at fifteen points faster...
MONEY_RED_GROWTH_BPS = 2000        # ...with money growing more than 20% a year
MONEY_AMBER_INFLATION_BPS = 1200   # amber when prices rise more than 12% a year, however the money figures look
MONEY_RED_INFLATION_BPS = 2000     # red at 20%
MONEY_POOLING_AMBER_BPS = 600      # amber when one group's share of all money rises six points in a year
MONEY_UNUSUAL_RECEIPT_NAIRA = 50_000_000   # a player receiving more than this in one quarter is looked at
MONEY_LOW_GRANTS = 50_000          # amber when the Treasury's reserve covers fewer starting grants than this

# The ten kinds of people (design document, section 4): each location's mix, in percent.
MINDSETS = ("optimistic", "pessimistic", "risk_averse", "risk_seeking", "herding",
            "contrarian", "loyal", "fearful", "sceptical", "opportunistic")
MINDSET_MIX: dict[str, tuple[int, ...]] = {
    #               opt pes avr sek hrd con loy fear scp opp
    LAGOS:         (18,  6,  6, 16, 14,  6,  6,  6,  8, 14),
    ABUJA:         (10,  8, 18,  6, 12,  6, 14,  8, 12,  6),
    PORT_HARCOURT: (10, 12, 10, 10, 12,  8,  8, 14,  8,  8),
    ABA:           (12,  6,  8, 12, 10, 10, 10,  6,  8, 18),
    KANO:          ( 8, 10, 16,  6, 12,  6, 20,  8, 10,  4),
}
assert all(sum(mix) == 100 and len(mix) == len(MINDSETS) for mix in MINDSET_MIX.values())

# --- Opening money (design document, section 10) ---
# The Central Bank issues the opening money. From then on, no new naira appears.

# The Treasury's reserve. Each new player's starting cash is paid out of it.
TREASURY_OPENING_M = 500_000              # ₦500 billion: enough for one million players
# The savings of all households on day one, shared out by population.
HOUSEHOLDS_OPENING_M = 5_000_000          # ₦5 trillion
HOUSEHOLD_OPENING_INCOME_BPS = 8_600       # what households are taken to have earned just before the game, against what they will spend

STARTING_GRANT_NAIRA = 500_000            # what each new player receives (section 10)

SHARE_CAPITAL_BPS = 4000                  # 40% of opening equity is share capital, the rest past profits
BOOK_VALUE_PER_SHARE_NAIRA = 20           # sets how many shares each company starts with
SHARE_LOT = 10_000_000                    # share counts are rounded to the nearest 10 million

LOAN_TERM_QUARTERS = 24                   # bank loans are repaid over six game years
BOND_TERM_QUARTERS = 32                   # bonds are repaid in one go after about eight game years
BOND_STAGGER_QUARTERS = 3                 # ...but not all in the same quarter: each company's falls a little later than the last
BOND_DISCOUNT_BPS = 150                   # bonds pay 1.5 points less interest than bank loans


# ---------------------------------------------------------------------------
# Stage 4, Part A: the Broad Street Exchange.
# ---------------------------------------------------------------------------
DAILY_PRICE_LIMIT_BPS = 1000       # a share may not trade more than 10% above or below yesterday's last price
EXCHANGE_FEE_BPS = 30              # on every trade, buyer and seller each pay 0.3% to the exchange...
STAMP_DUTY_BPS = 20                # ...and 0.2% to the Government as stamp duty
ORDER_LIFE_DAYS = 7                # an order still unmatched after seven real days (one game quarter) is handed back
MOST_OPEN_ORDERS = 50              # the most orders one player may have waiting at once
LOWEST_LISTING_PRICE_KOBO = 100    # no share is listed below ₦1

# What a company is worth, and the computer-run investors.
SHARE_RISK_PREMIUM_BPS = 300       # owning a share is riskier than lending: investors want 3 points more a year
REAL_GROWTH_BPS = 200              # profits are expected to grow 2 points a year faster than prices
LEAST_DISCOUNT_ABOVE_GROWTH_BPS = 500   # the return wanted is never taken as less than 5 points above long-run growth

INVESTOR_REFRESH_SECONDS = 300     # the computer-run investors look at the market again every five minutes
ORDER_STEP_BPS = 50                # each of an investor's waiting orders is half a percent from the next
IMPACT_PER_LEVEL_BPS = 50          # selling one order's worth raises the prices an investor asks by half a percent
MOST_IMPACT_BPS = 800              # ...but never by more than 8% in all
ORDER_VALUE_SHARE_PPM = 4          # one waiting order is worth four millionths of the whole company...
ORDER_VALUE_LIMITS_NAIRA = (500_000, 20_000_000)      # ...but at least ₦500,000 and at most ₦20 million
MOST_CASH_PER_ORDER_BPS = 100      # an investor puts at most 1% of its cash behind one buy order
EVENT_MOOD_BPS = 3000              # small investors mark a share by three tenths of an event's effect on its sales...
MOST_EVENT_MOOD_BPS = 300          # ...and never by more than 3%
# Each kind of investor: how much its own view differs day to day, how far from that view it
# is willing to buy and sell, how many orders it keeps waiting each way, and how large they are.
INVESTORS = {
    #                          label              own view   margin   orders  size
    "investors:institutions": ("Pension funds",      100,       50,      3,    150),
    "investors:public":       ("Small investors",    250,       40,      3,    100),
    "investors:founders":     ("Founders",            50,      300,      2,    200),
}
MARKET_PAUSE_FALL_BPS = 500        # trading pauses when the whole market falls 5% in a day...
MARKET_PAUSE_MINUTES = 30          # ...for half an hour, once a day

# ---------------------------------------------------------------------------
# Stage 4, slice 4: the Closing Rush and the Closing Bell.
# ---------------------------------------------------------------------------
RUSH_FEE_DISCOUNT_BPS = 5000       # during the Closing Rush (21:50 to 22:00) trading fees are halved
LARGE_ORDER_NAIRA = 250_000        # a player's order this large placed in the rush is shown to everybody, without a name
GAME_YEAR_REAL_DAYS = 28           # four real weeks are one game year

# ---------------------------------------------------------------------------
# Stage 4, Part B: bonds, share offers, votes and takeovers.
# ---------------------------------------------------------------------------
BOND_FACE_NAIRA = 1_000            # every bond and bill is repaid at ₦1,000
# The yield curve: what lending to the Government for so many quarters pays, against the Central Bank's rate.
YIELD_CURVE_BPS = ((1, -50), (8, 0), (20, 75), (40, 150))
DISTRESSED_RECOVERY_BPS = 4000     # lenders to a company in trouble count on getting back 40% of what they are owed
BOND_HALF_SPREAD_BPS = {"bill": 5, "government": 20, "company": 60, "distressed": 300}   # the desk's margin each way
BOND_IMPACT_BPS = 50               # buying 1% of a whole bond issue moves the desk's prices by half a percent...
MOST_BOND_IMPACT_BPS = 300         # ...and never by more than 3% in all
GOVERNMENT_BOND_LINES = (          # kind, quarters to run, and what it is called
    ("fixed", 8, "two-year"), ("fixed", 20, "five-year"), ("fixed", 40, "ten-year"),
    ("floating", 12, "floating-rate"), ("inflation_linked", 20, "inflation-linked"),
)
GOVERNMENT_FIRST_ISSUE_NAIRA = 5_000_000_000    # of each of its first bonds
GOVERNMENT_DEFICIT_BPS = 300       # the Government spends 3% more than it collects, and borrows the difference
GOVERNMENT_BOND_APPETITE_BPS = 1000   # the pension funds put at most a tenth of their cash into one quarter's Government bonds
COMPANY_BOND_APPETITE_BPS = 500    # ...and at most a twentieth into one company's new bond
CONVERTIBLE_DISCOUNT_BPS = 300     # a bond that can be swapped for shares pays 3 points less interest
CONVERSION_PREMIUM_BPS = 2500      # ...and swaps at a share price a quarter above the market's when it was issued
COMPANY_BOND_QUARTERS = 20         # a company's new bond runs five game years
MOST_BOND_ISSUES_A_QUARTER = 2
BOND_ISSUE_GAP_QUARTERS = 12       # a company sells a new bond at most once in three game years
BOND_SHARE_OF_LOAN_BPS = 2000      # a new bond replaces a fifth of what the company owes its bank
PROJECT_BOND_ASSETS_BPS = 400      # a project bond raises 4% of the company's buildings and machines

# Share offers.
RIGHTS_DISCOUNT_BPS = 3000         # a rights issue is priced 30% below the market
RIGHTS_TERMS = (1, 3)              # one new share for every three held
OFFER_DISCOUNT_BPS = 0             # a sale to the public is at the market price: the buyer saves only the trading fee
OFFER_SIZE_BPS = 800               # ...and adds 8% to the shares in issue
OFFER_WHEN_DEAR_BPS = 10_000       # a company sells new shares only when its price is no lower than what it is worth
OFFER_GAP_QUARTERS = 12            # one share offer in three game years, at most
MOST_RIGHTS_ISSUES_A_QUARTER = 2
SMALL_INVESTORS_TAKE_UP_BPS = 7000 # small investors take up 70% of their rights
SPLIT_ABOVE_KOBO = 10_000          # a company whose share costs ₦100 or more splits it
VOTE_ABOVE_BPS = 1000              # new shares worth more than a tenth of the company need the owners' vote

# Takeovers.
TAKEOVER_STAKE_BPS = 6000          # a bidder offers for 60% of the shares
TAKEOVER_PREMIUM_BPS = (2000, 4500)   # 20% to 45% above the market price
TAKEOVER_ONE_IN = 3                # in about one quarter in three, a company makes an offer for another
TAKEOVER_TARGET_SIZE_BPS = 4000    # the target is worth at most 40% of the bidder
TAKEOVER_VOTE_ABOVE_BPS = 2500     # a purchase costing more than a quarter of the bidder's own value needs its owners' vote
INTEGRATION_QUARTERS = 8           # joining two businesses takes two game years
INTEGRATION_SAVING_BPS = 300       # the plan: costs lower by 3% of the target's sales

# The starting grant is paid in parts (section 10).
GRANT_ON_JOINING_NAIRA = 100_000
GRANT_STEP_NAIRA = 100_000         # four further parts, each for a real thing the player has done
GRANT_STEP_GAP_HOURS = 20          # at most one part in twenty real hours (about eleven game days)
SMALL_INVESTORS_WITH_BOARD_BPS = 6500   # in a vote, about two thirds of small investors follow the board
OFFER_CASH_BPS = 1000              # a computer-run investor puts at most a tenth of its cash into one share offer
OFFER_FUNDS_SHARE_BPS = 5000       # in a sale to the public, pension funds ask for half the shares...
OFFER_PUBLIC_SHARE_BPS = 3000      # ...and small investors for three tenths
FUNDS_ACCEPT_PREMIUM_BPS = 2500    # pension funds accept a takeover offer 25% or more above the market price
BOARD_ACCEPTS_PREMIUM_BPS = 3000   # a target's board recommends an offer 30% or more above the market price

# ---------------------------------------------------------------------------
# Stage 5: players as professionals (sections 7, 9 and 10).
# ---------------------------------------------------------------------------
# Salary for each game month, by level, at the start of the game. Between these levels pay rises
# smoothly. It keeps pace with wages in the economy.
SALARY_PER_MONTH_NAIRA = ((1, 300_000), (20, 750_000), (40, 2_000_000), (60, 6_000_000), (80, 20_000_000), (100, 60_000_000))
# "About 40% of salary is taken automatically for tax and living costs": 12% income tax, 20% living
# costs, and the 8% every worker saves for retirement.
SALARY_TAX_BPS = 1200
SALARY_LIVING_BPS = 2000
LEVEL_EXPERIENCE = 30              # level n needs 30 x n x (n - 1) experience: 60 for level 2, 11,400 for level 20
EARLY_LEVELS = 10                  # the redesign: Levels 1 to 10 come twice as fast (about two real weeks)...
EARLY_LEVEL_EXPERIENCE = 15        # ...needing 15 x n x (n - 1); from Level 11 the curve eases back to meet the old one at Level 20
LEVEL_CAP = 20                     # the level a career stops at until its first rank case is passed (see RANK_GATES)
STAFF_PER_OPENING = 500            # a company has one opening for a player for every 500 people it employs
BUILD_CHANGE_DAYS = 30             # a player may change build once in a real month
MAX_BUILDS = 3
MAX_ACTIVE_OBJECTIVES = 3
REVIEW_FAILURES = 5                # five failures in any ten consecutive objectives opens a performance review
REVIEW_WINDOW = 10
REVIEW_LENGTH = 5                  # the next five pieces of work decide it...
REVIEW_PASSES_NEEDED = 3           # ...three passes close it; fewer means stepping down a level
# The six banks a player may choose from, and what share of the Central Bank's rate each pays on
# cash left with it: the weaker the bank, the more it must pay to keep its customers.
PLAYER_BANKS = ("HMB", "IKB", "KCB", "OBB", "OTB", "ZCB")
SAVINGS_RATE_SHARE_BPS = {"AAA": 2400, "AA": 2700, "A": 3000, "BBB": 3300, "BB": 3700, "B": 4100, "CCC": 4500, "D": 0}
# The four kinds of retirement fund: what share each keeps in shares, in bonds and in cash.
PENSION_FUNDS = {
    "growth":   {"name": "Growth",   "shares": 8000, "bonds": 2000, "cash": 0,    "for": "Players far from retirement who accept swings",
                 "good": "The highest return over the years", "bad": "Can fall hard in a bad quarter for shares"},
    "balanced": {"name": "Balanced", "shares": 5000, "bonds": 5000, "cash": 0,    "for": "The usual choice",
                 "good": "A smoother ride than Growth", "bad": "Never the best, never the worst"},
    "cautious": {"name": "Cautious", "shares": 2000, "bonds": 8000, "cash": 0,    "for": "Players close to retirement",
                 "good": "Small swings", "bad": "Its bonds lose value when the Central Bank raises its rate, and a company that defaults is a real loss"},
    "income":   {"name": "Income",   "shares": 0,    "bonds": 7000, "cash": 3000, "for": "Players already drawing a pension",
                 "good": "Lends only to the Government, so nothing defaults", "bad": "The lowest return: in a year of fast-rising prices it can buy less than before"},
}
PENSION_MANAGER_FEE_BPS = 5        # the fund manager's fee each quarter: a twentieth of one percent of the savings


# ---------------------------------------------------------------------------
# Stage 6: retirement savings with risks and rewards (added by the owner, 3 October 2026).
# ---------------------------------------------------------------------------
EXTRA_SAVING_MOST_BPS = 2000       # a player may save up to 20% of salary on top of the usual 8%
EMPLOYER_MATCH_MOST_BPS = 300      # the employer matches extra saving, naira for naira, up to 3% of salary
SOUND_FINANCES_QUARTERS = 2        # savings worth two quarters' salary earn the "sound finances" mark
EARLY_WITHDRAWAL_MOST_BPS = 5000   # the one early withdrawal may take up to half of the savings
RETIREMENT_LEVEL = 50              # retirement opens at Level 50...
RETIREMENT_AFTER_QUARTERS = 40     # ...or after ten game years of work, whichever comes first
PENSION_PAID_BPS = 250             # a pension pays out 2.5% of the savings each quarter
# Early retirement (owner, 9 October 2026): sooner, with a smaller pension, fixed for good when it begins.
EARLY_RETIREMENT_LEVEL = 35
EARLY_RETIREMENT_AFTER_QUARTERS = 20
EARLY_PENSION_PAID_BPS = 150
BOND_FUND_YEARS = 3.5              # how hard a one-point move in interest rates hits a fund's bonds, in points
COMPANY_BOND_SHARE_BPS = {"growth": 5000, "balanced": 5000, "cautious": 5000, "income": 0}   # of a fund's bonds, the part lent to companies
DEFAULT_LOSS_BPS = 60              # each company newly in default costs this much of the company-bond part


# ---------------------------------------------------------------------------
# Stage 6: empires (sections 6, 13 and 15).
# ---------------------------------------------------------------------------
EMPIRE_BUILDS = ("investment_banker", "asset_manager", "risk_manager", "accountant", "lawyer", "journalist")
EMPIRE_FOUNDING_LEVEL = 20
EMPIRE_REGISTRATION_NAIRA = 25_000_000
EMPIRE_LEAST_HUMANS = 3
COMPUTER_EMPIRES = ("Savannah Crown Holdings", "Delta Meridian Group", "Niger Bend Partners", "Atlantic Gate Holdings", "Kola Ridge Group")
COMPUTER_EMPIRE_CAPITAL_NAIRA = 5_000_000_000      # each, put up by the founders (the private investors of the world)
COMPUTER_EMPIRE_CASH_KEPT_BPS = 2000               # a computer-run empire keeps a fifth of its money in cash and lends the rest to the Government
STAFF_LEVEL = 40                                   # computer-run staff work at a fixed Level 40
JOIN_LEAST_REPUTATION = 40
SACKED_BAN_QUARTERS = 4                            # a member sacked for theft cannot rejoin that empire for a game year
SIGNING_LIMIT_NAIRA = 500_000                      # what a member may sign for in a quarter: the same for everybody, at every level.
                                                   # It is also where a player-run empire starts, until its head sets another figure
HEAD_LIMIT_BPS = 200                               # a head may spend up to 2% of the empire's cash in a quarter without anybody else
THEFT_FINE_BPS = 10_000                            # a proved theft is repaid, with a fine of the same amount again
THEFT_REPUTATION = 10
DEBT_FROM_SALARY_BPS = 2500                        # a quarter of each take-home pay goes to a debt owed to an empire
REPORT_REWARD_BPS = 1000                           # whoever reports a theft that is proved gets a tenth of it
REPORTS_A_QUARTER = 3
REPORT_FINDS_BPS = 9000                            # looking at one reported entry finds a false one nine times in ten
AUDITOR_BASE_BPS = 5000                            # an Accountant of the thief's own level finds each theft half the time...
AUDITOR_PER_LEVEL_BPS = 300                        # ...and 3 points more or less for each level between them
AUDITOR_RANGE_BPS = (2000, 9000)
AI_AUDIT_FINDS_BPS = 9500                          # the AI audit is right 95 times in 100
AI_AUDIT_FEE_BPS = 200                             # it costs 2% of what the empire is worth...
AI_AUDIT_LEAST_NAIRA = 5_000_000                   # ...and never less than this
AI_AUDIT_LOOKS_BACK = 4                            # quarters. Older thefts escape
AUDIT_SEASON_EVERY = 4                             # the AI audit can be hired in one quarter in four: the last of each game year
TASK_SHARE_OF_CASH_BPS = 500                       # an investment task puts 5% of the empire's cash to work...
TASK_MOST_NAIRA = 50_000_000                       # ...and never more than this
STAFF_WAITS_TICKS = 2                              # staff leave a step to the players for two bells before doing it themselves
PACT_KINDS = {
    "alliance": ("An alliance: to stand together and not act against each other", True),
    "truce": ("A truce: no poaching each other's people, and no offers or stake-building against each other's companies", True),
    "joint_bid": ("A joint bid: to bid together for a company or a contract", True),
    "share_information": ("Sharing information: each side sees what the other holds", True),
    "same_candidate": ("Backing the same election candidate", True),
    "stay_out": ("Staying out of each other's deals", False),
    "divide_market": ("Dividing a market between them", False),
    "fix_prices": ("Fixing prices", False),
    "rig_bids": ("Rigging bids", False),
}
PACT_BREAK_TRUST = 10
PACT_EXPOSED_TRUST = 15
EXPOSE_BASE_BPS = 1500                             # a journalist's chance of uncovering a hidden pact...
EXPOSE_PER_LEVEL_BPS = 200                         # ...rises with level, up to 55%
# How each build's false entry is written in the books.
DISGUISES = {
    "asset_manager": ("Dealing costs", "Brokerage and dealing costs on the quarter's trades"),
    "investment_banker": ("Advisory fees", "Outside advisers' fees on deals in progress"),
    "risk_manager": ("Hedging costs", "Cost of protection bought against market moves"),
    "accountant": ("Office and professional costs", "Professional subscriptions, software and office costs"),
    "lawyer": ("Legal fees and filings", "Counsel's fees and filing costs on matters in hand"),
    "journalist": ("Research and sources", "Research subscriptions and payments to sources"),
    "head": ("Management expenses", "Travel, entertaining and management expenses"),
}

# Pension funds run by players (Stage 6).
FUND_MANAGER_LEVEL = 20                            # an Asset Manager may open a pension fund at this level
FUND_REGISTRATION_NAIRA = 5_000_000                # paid into the prize pool
FUND_FEE_MOST_BPS = 50                             # the most a manager may charge: half of one percent of the fund each quarter
FUND_SIGNING_BPS = 100                             # a manager can sign for costs of up to 1% of the fund in a quarter
FUND_AI_AUDIT_LEAST_NAIRA = 1_000_000              # the least an AI audit of a pension fund costs

# After the independent review of Stage 6.
HEAD_BONUS_BPS = 1000                              # a head may pay out bonuses of up to a tenth of the empire's worth in a quarter
# What a player may trade for a computer-run empire in a quarter: a share of what the empire is worth, growing with rank
# (Associate, Professional, Senior, Principal, Master). Decided by the owner on 3 October 2026; it was ₦1 million for each level.
COMPUTER_EMPIRE_TRADE_BPS = (50, 200, 500, 1000, 2000)
FAIR_DEALING_BPS = 200                             # other people's money is dealt within 2% of the last session's price
FUND_TURNOVER_BPS = 10_000                         # a pension fund may trade once its own worth in a quarter
FUND_LEAST_SAVINGS_NAIRA = 1_000                   # the least a saver may bring to a fund run by a player


# ---------------------------------------------------------------------------
# Stage 7: mastery, rank cases, leagues (sections 6, 9 and 13).
# ---------------------------------------------------------------------------
TOP_LEVEL = 100
RANK_GATES = (20, 40, 60, 80)                      # a career stops at each of these levels until its rank case is passed
# What must be mastered before the rank case at each gate can be sat: of a build's modules, how many
# learned (alone), practised (with the empire) and proven (in a weekend challenge). "all" = every one.
RANK_MASTERY = {20: {"learned": "all", "practised": 3, "proven": 1},
                40: {"learned": "all", "practised": "all", "proven": 3},
                60: {"learned": "all", "practised": "all", "proven": "all"},
                80: {"learned": "all", "practised": "all", "proven": "all"}}
RANK_CASE_FEE_NAIRA = {20: 200_000, 40: 500_000, 60: 1_000_000, 80: 2_000_000}      # paid into the prize pool at each attempt
RANK_CASE_PASS = {20: 80, 40: 85, 60: 90, 80: 95}                                     # points out of 100
RANK_CASE_RETRY_DAYS = 3                           # real days before a failed case can be sat again
RANK_CASE_HOURS = 48                               # real hours to hand a case in, and never past the end of the quarter
RANK_NAMES = ("Associate", "Professional", "Senior", "Principal", "Master")           # the rank held below Level 20, 40, 60, 80 and above
# Work done after a rank case is harder to come by and teaches more: experience from one piece of
# work is multiplied by one more than the number of rank cases passed.
# The three settings a module's work comes in.
SETTINGS = {"solo": "On your own", "empire": "With your empire", "live": "Weekend challenge"}
WEEKEND_OPENS = (4, 18)                            # Friday (Monday = 0), 18:00 Lagos time...
WEEKEND_CLOSES = (6, 22)                           # ...to Sunday, 22:00
WEEKEND_BONUS_BPS = 15_000                         # a weekend challenge pays and teaches one and a half times as much
WEEKEND_HOURS = 3                                  # real hours to hand a weekend challenge in, once it is taken
EMPIRE_WORK_A_QUARTER = 8                          # pieces of work one member may do for their empire in a quarter, besides task steps

# The CEO rank (section 6).
CEO_LEVEL = 60
CEO_REPUTATION = 75
CEO_MEMBER_LEVEL = 40                              # the leadership work opens to a member at this level; to a head at once
CEO_CASE_FEE_NAIRA = 1_000_000
CEO_CASE_PASS = 90
CEO_LIMIT_BPS = 500                                # a CEO may sign for 5% of the empire's cash in a quarter (an Acting Head: 2%)
CEO_BONUS_BPS = 2500                               # ...and pay bonuses of up to a quarter of its worth (an Acting Head: a tenth)
CEO_TASK_MOST_NAIRA = 200_000_000                  # ...and approve investments up to this size (an Acting Head: 50 million)

# Leaving an empire (added by the owner, 3 October 2026).
NOTICE_DAYS = 14                                   # real days between a resignation letter and leaving, in an empire run by players
COUNTER_OFFER_MOST_BPS = 500                       # a counter-offer's bonus may be up to 5% of the empire's worth

# Leagues: divisions of empires, with promotion and relegation as each game year ends.
DIVISION_SIZE = 5
DIVISION_MOVES = 1                                 # how many go up and down between two divisions each year
LEAGUE_POINTS = {"task": 10, "work": 2, "challenge": 3, "theft": -5, "growth_most": 20}

# Quick fixes: messages between players. Limits keep anyone from flooding others.
MESSAGE_MAX_CHARS = 1000
MESSAGES_PER_HOUR = 30                 # messages one player may send in any hour
NEW_PEOPLE_PER_DAY = 10                # different players one may write to first, in any day
UNANSWERED_IN_A_ROW = 3                # messages to someone who has not answered yet
REPORTS_TO_BE_LIMITED = 3              # different players reporting one sender within a week...
REPORT_WINDOW_DAYS = 7                 # ...and the sender may only answer people who wrote first, for that week
MESSAGE_REPORT_MAX_CHARS = 300
