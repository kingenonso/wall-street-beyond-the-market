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
    # --- Talent and funds stage, part 4c: six new industries. ---
    # Medicines: a high cost of sales because the ingredients are bought abroad, and steady demand all year.
    Sector("pharma", "Medicines and healthcare", 5500, 2600, 450, (9900, 10000, 10000, 10100),
           fixed_assets_x=7000, cash_x=1200, debt_x=2500, loan_rate_bps=1900, payout_bps=4000),
    # Shops: the thinnest margin in the game (a shop keeps a tenth of what it takes), and a festive last quarter.
    Sector("retail", "Groceries and retail", 7400, 2000, 380, (9500, 9800, 10000, 11000),
           fixed_assets_x=4500, cash_x=900, debt_x=2500, loan_rate_bps=2000, payout_bps=4500),
    # Technology: fast growing, little borrowing, and it pays out little because it puts its money back in.
    Sector("technology", "Technology and payments", 4200, 3600, 800, FLAT,
           fixed_assets_x=6000, cash_x=2500, debt_x=1500, loan_rate_bps=1800, payout_bps=1500),
    # Film and music: a hit-or-nothing industry, with the year's takings weighed to the last quarter.
    Sector("entertainment", "Film and entertainment", 5600, 2600, 500, (9400, 9900, 10000, 11100),
           fixed_assets_x=5000, cash_x=1200, debt_x=2000, loan_rate_bps=2100, payout_bps=2500),
    # Mining: heavy on machines and ground, so a large fixed-asset base and real borrowing.
    Sector("mining", "Solid minerals and mining", 5800, 1900, 350, FLAT,
           fixed_assets_x=16000, cash_x=1100, debt_x=4000, loan_rate_bps=2000, payout_bps=3000),
    # Fertilisers: gas is most of the cost, and the money is made in the planting season.
    Sector("fertiliser", "Fertilisers and agro-chemicals", 6400, 1800, 420, (9000, 10600, 10800, 9600),
           fixed_assets_x=13000, cash_x=1100, debt_x=4000, loan_rate_bps=1950, payout_bps=3500),
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

    # --- Talent and funds stage, part 4c: twenty-four companies in six new industries.
    # Eighteen are listed and six are private, one in each industry. Names were approved
    # by the owner on 3 November 2026; every one is invented. ---
    # Medicines and healthcare.
    Company("OGP", "Ogbomoso Pharma", "pharma", LAGOS, 95_000, lender="IKB"),
    Company("OVP", "Osun Valley Pharmaceuticals", "pharma", LAGOS, 210_000, lender="HMB", bond_share_bps=4000),
    Company("YBM", "Yaba Medicare", "pharma", ABUJA, 140_000, lender="ZCB", trend_bps=300),
    Company("ILD", "Ilesa Diagnostics", "pharma", PORT_HARCOURT, 28_000, lender="OBB", listed=False, trend_bps=250),
    # Groceries and retail.
    Company("WSG", "Wuse Grocers", "retail", ABUJA, 260_000, lender="HMB", bond_share_bps=4000),
    Company("GBF", "Gboko Fresh Markets", "retail", KANO, 75_000, lender="ZCB"),
    Company("ADK", "Aduke Stores", "retail", LAGOS, 22_000, lender="OTB", listed=False, trend_bps=200),
    Company("OTG", "Otukpo Grocers", "retail", ABA, 45_000, lender="KCB", cost_extra_bps=200),
    # Technology and payments.
    Company("ZGP", "Zanga Pay", "technology", LAGOS, 180_000, lender="IKB", bond_share_bps=4000, trend_bps=480),
    Company("OJD", "Oja Digital", "technology", LAGOS, 120_000, lender="KCB", trend_bps=450, volatility_bps=900),
    Company("NMS", "Nembe Softworks", "technology", ABUJA, 38_000, lender="ZCB"),
    Company("IKS", "Ikere Cloud Services", "technology", LAGOS, 26_000, lender="IKB", listed=False,
            trend_bps=350, cash_times_bps=2_500, debt_times_bps=13_000),
    # Film and entertainment.
    Company("GDS", "Gidi Screen", "entertainment", LAGOS, 88_000, lender="OTB", volatility_bps=1_100),
    Company("ILP", "Ilorin Pictures", "entertainment", ABUJA, 34_000, lender="ZCB", volatility_bps=1_200),
    Company("UFS", "Uyo Film Studios", "entertainment", PORT_HARCOURT, 15_000, lender="OBB"),
    Company("OTS", "Otun Sounds", "entertainment", LAGOS, 9_000, lender="IKB", listed=False,
            trend_bps=400, volatility_bps=1_400),
    # Solid minerals and mining.
    Company("KDG", "Kaduna Goldfields", "mining", ABUJA, 145_000, lender="HMB", bond_share_bps=4000,
            volatility_bps=800),
    Company("BTM", "Bauchi Tin Mines", "mining", KANO, 62_000, lender="ZCB"),
    Company("ECM", "Enugu Coal Mines", "mining", ABA, 40_000, lender="KCB", trend_bps=-300, cost_extra_bps=500),
    Company("OMM", "Omu Minerals", "mining", LAGOS, 18_000, lender="OTB", listed=False, volatility_bps=1_400),
    # Fertilisers and agro-chemicals.
    Company("WRU", "Warri Urea", "fertiliser", PORT_HARCOURT, 195_000, lender="OBB", bond_share_bps=4000),
    Company("GMF", "Gombe Fertilisers", "fertiliser", KANO, 110_000, lender="HMB"),
    Company("KAC", "Katsina Agro-Chemicals", "fertiliser", ABUJA, 30_000, lender="ZCB"),
    Company("ICS", "Ijebu Crop Science", "fertiliser", ABA, 21_000, lender="KCB", listed=False, trend_bps=200),
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
    # Part 4c: the six new industries.
    ("pharma", LAGOS): -200,               # near the ports the ingredients arrive at
    ("retail", LAGOS): -300,               # the biggest market in the country
    ("retail", KANO): -100,                # the northern trading centre
    ("technology", LAGOS): -400,           # where the engineers are
    ("technology", ABUJA): -150,
    ("entertainment", LAGOS): -400,        # the creative centre
    ("mining", KANO): -200,                # tin country
    ("mining", ABUJA): -50,
    ("fertiliser", PORT_HARCOURT): -300,   # the gas
    ("fertiliser", KANO): -150,            # beside the farms that buy it
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
    # Part 4c: the farms now buy crop chemicals and fertiliser, which is what gives the
    # fertiliser makers a customer of flesh and blood rather than only the household till:
    # a quarter of what a farm spends on supplies now goes to them.
    "agriculture":   {"oil_gas": 400, "transport": 500, "manufacturing": 500, "banking": 150, "insurance": 100,
                      "power": 100, "fertiliser": 600},
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
    # Part 4c. The medicine makers buy most of their ingredients from manufacturing, which is on the list of
    # things paid for in dollars, so a weak naira raises their costs without any new machinery.
    "pharma":        {"manufacturing": 3400, "power": 400, "transport": 300, "banking": 150, "telecoms": 100,
                      "insurance": 50},
    # The shops buy the goods they sell, and pay to move them.
    "retail":        {"consumer": 3600, "agriculture": 1200, "transport": 500, "manufacturing": 300, "power": 300,
                      "banking": 150, "telecoms": 50},
    "technology":    {"power": 800, "telecoms": 700, "manufacturing": 400, "real_estate": 300, "banking": 150,
                      "media": 100},
    "entertainment": {"media": 400, "manufacturing": 700, "telecoms": 500, "real_estate": 300, "power": 300,
                      "transport": 200, "banking": 100},
    # The miners run machines on fuel and power, and move what they dig.
    "mining":        {"oil_gas": 1200, "power": 700, "manufacturing": 700, "transport": 600, "cement": 200,
                      "banking": 150, "insurance": 100},
    # The fertiliser makers' cost is mostly gas.
    "fertiliser":    {"oil_gas": 3600, "power": 600, "transport": 400, "manufacturing": 300, "banking": 150,
                      "insurance": 50},
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
    # The economy upgrade: foreign investors. Small, so that they move prices without swamping
    # everybody else; on top of their own view they price shares up when they want to bring money in.
    "investors:foreign":      ("Foreign investors",  100,      150,      1,     15),
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
# The three builds an empire seats, two seats each, under its head: seven places in the Ministry (owner, 9 November
# 2026). It was six builds and thirteen seats. The retired three are gone from the game, not renamed: the Accountant's
# audit sits with the Asset Manager, the Legal Counsel's approvals and pacts with the Investment Banker, and the
# newsroom's work is open to every build. Nothing here may list a build that is not a key of careers.BUILDS.
EMPIRE_BUILDS = ("investment_banker", "asset_manager", "risk_manager")
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
AUDITOR_BASE_BPS = 5000                            # an auditor of the thief's own level finds each theft half the time...
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
EXPOSE_BASE_BPS = 1500                             # anyone's chance of uncovering a hidden pact...
EXPOSE_PER_LEVEL_BPS = 200                         # ...rises with the level they hold, up to 55%
# What a disguised entry is called in the books, by the desk that entered it. Three builds and the head, since the
# six became three on 9 November 2026: the professional costs and the legal fees are the Asset Manager's and the
# Investment Banker's now, and a key here for a build nobody can hold would be a fourth description of the game.
DISGUISES = {
    "asset_manager": ("Dealing and professional costs", "Brokerage and dealing costs on the quarter's trades, professional subscriptions and office costs"),
    "investment_banker": ("Advisory and legal fees", "Outside advisers' fees on deals in progress, counsel's fees and filing costs on matters in hand"),
    "risk_manager": ("Hedging costs", "Cost of protection bought against market moves"),
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

# ---------------------------------------------------------------------------
# Economy upgrade (owner, 12 October 2026): 1,000 consumer groups, and the rest of the world.
# ---------------------------------------------------------------------------
CONSUMER_GROUPS = 1_000                # split between the five locations by population (Lagos 350, Kano 200, ...)
# Five income levels: the share of a location's groups at each level, and what one group at that
# level earns against a middle-income group.
INCOME_BANDS = ("low", "lower_middle", "middle", "upper_middle", "high")
INCOME_BAND_NAMES = {"low": "Low income", "lower_middle": "Lower-middle income", "middle": "Middle income",
                     "upper_middle": "Upper-middle income", "high": "High income"}
INCOME_BAND_GROUPS_PERCENT = (30, 25, 22, 15, 8)
INCOME_BAND_EARNS_BPS = (4_000, 7_000, 10_000, 18_000, 40_000)
# How much of what they have to live on each level spends, against the households' usual habit
# (poorer households spend nearly all of it; the richest save much more).
INCOME_BAND_SPENDS_BPS = (11_400, 11_000, 10_400, 9_500, 7_700)
# How much of their savings each level dips into, against the usual habit.
INCOME_BAND_DIPS_BPS = (13_000, 11_500, 10_000, 9_000, 7_000)
# What each level spends more or less on than the average household (10000 = the same).
# Necessities weigh more for poorer households; travel, hotels, property and finance for richer ones.
INCOME_BAND_TASTES: dict[str, tuple[int, ...]] = {
    #                 low    l-mid   mid   u-mid   high
    "consumer":      (13_000, 12_000, 10_000, 8_500, 7_000),
    "agriculture":   (14_000, 12_000, 10_000, 8_000, 6_000),
    "power":         (11_000, 10_500, 10_000, 9_500, 9_000),
    "transport":     (12_000, 11_000, 10_000, 9_000, 8_500),
    "telecoms":      (10_500, 10_500, 10_000, 9_500, 9_500),
    "oil_gas":       (10_500, 10_500, 10_000, 9_500, 9_500),
    "banking":       (6_000, 8_000, 10_000, 12_000, 14_000),
    "insurance":     (4_000, 7_000, 10_000, 13_000, 16_000),
    "real_estate":   (6_000, 8_000, 10_000, 12_500, 15_000),
    "media":         (8_000, 9_000, 10_000, 11_000, 12_000),
    "hospitality":   (4_000, 6_500, 10_000, 14_000, 18_000),
    "aviation":      (2_000, 5_000, 10_000, 15_000, 21_000),
}
GROUP_TASTE_SPREAD_BPS = 1_000         # each group's own taste differs from its level's by up to a tenth either way
GROUP_SAVINGS_TILT = 13_000            # richer groups hold more of the savings: shares follow earnings to the power 1.3
GROUP_MOVE_BPS = 60                    # a group thinks of moving about once in 170 quarters by itself (and often stays)...
GROUP_MOVE_PER_JOBS_BPS = 2            # ...more often when jobs at home grow slower than in the country (per point of difference)
GROUP_MOVE_TOWARD_JOBS_BPS = 1_500     # where it goes: bigger places draw more, and each point of faster job growth there draws 15% more
GROUP_MOVES_MOST = 15                  # never more than this many groups move in one quarter
# The rest of the world (a simple version; the crises stage builds on it).
OIL_START_CENTS = 7_500                # $75 a barrel (a game figure)
OIL_RETURN_BPS = 1_500                 # the oil price drifts this far back towards its usual level each quarter...
OIL_SWING_BPS = 900                    # ...and swings up to 9% a quarter by itself, more when events hit supply
OIL_EVENT_MULTIPLE = 1                 # an event that moves energy prices at home moves the world oil price by as much
OIL_LIMITS_CENTS = (2_500, 20_000)     # between $25 and $200 a barrel
FX_START = 150_000                     # ₦1,500.00 to one US dollar (in hundredths of a naira; a game figure)
WORLD_INFLATION_BPS = 250              # prices abroad rise 2.5% a year
WORLD_RATE_BPS = 400                   # and lending abroad pays 4% a year
FX_ANCHOR_BPS = 1_000                  # the naira closes a tenth of the gap to its usual value (what prices at home and abroad say) each quarter
FX_OIL_BPS = 2_500                     # a 10% rise in oil strengthens the naira by 2.5%...
FX_TRADE_BPS = 500                     # ...a trade surplus as large as a quarter's imports strengthens it by 5%...
FX_RESERVE_BPS = 300                   # ...and the rest of the world holding fewer naira than usual strengthens it a little
FX_RATE_BPS = 2_000                    # interest rates above the neutral level strengthen it a little
FX_SWING_BPS = 250                     # and it swings up to 2.5% a quarter by itself
FX_MOST_MOVE_BPS = 1_500               # never more than 15% in one quarter
# Only goods can be bought abroad: power, phone lines, transport, banking and the like are bought at home.
IMPORTABLE_SUPPLIES = ("manufacturing", "oil_gas", "agriculture", "cement", "consumer")
# What each kind of company buys from abroad, as a share of the goods it buys.
IMPORT_SHARE_BPS: dict[str, int] = {
    "manufacturing": 2_500, "aviation": 3_500, "telecoms": 3_000, "power": 2_000, "oil_gas": 1_500,
    "consumer": 1_500, "cement": 1_500, "shipping": 2_000, "transport": 2_000, "agriculture": 800,
    "real_estate": 1_200, "media": 1_500, "hospitality": 1_200, "banking": 800, "insurance": 500,
    # Part 4c. The medicine makers buy most of their ingredients abroad, more than any other industry, which is
    # what makes a weak naira their story. The miners buy their machines and spares abroad but sell for dollars,
    # so the same fall in the naira costs them less than it earns them.
    "pharma": 5_500, "retail": 2_000, "technology": 2_500, "entertainment": 1_500, "mining": 2_500,
    "fertiliser": 800,
}
IMPORT_SWITCH_BPS = 8_000              # when goods abroad are 10% dearer, companies buy 8% less of them there (and more at home)
EXPORT_SWITCH_BPS = 10_000             # and buyers abroad buy 10% more farm produce and factory goods when the naira is 10% cheaper
IMPORT_PRICE_WEIGHT_BPS = 800          # imported goods are this much of what households pay for: a weaker naira raises prices
OIL_EXPORT_SHARE_BPS = 7_500           # oil and gas earn three quarters of what the country sells abroad on day one...
NON_OIL_EXPORTS = {"agriculture": 4_600, "manufacturing": 3_100, "mining": 2_300}   # ...farms, factories, and the mines the rest
# These three are shares of the non-oil quarter of exports, so they must add to 10,000: economy.split divides by
# their sum, and weights that did not add up would quietly dilute every exporter's share instead of failing. They
# were 6,000 and 4,000 before Part 4c put mining on the list at 3,000, which made 13,000 of 10,000 and left the
# split at 6/13, 4/13, 3/13. The numbers above are those same shares written as they always should have been, so
# no exporter's money moves: only the arithmetic in the test is now true.
OIL_ROYALTY_BPS = 2_000                # the Government takes a fifth of what oil sold abroad brings in
ABROAD_RESERVE_QUARTERS = 4            # the rest of the world starts with four quarters' imports in naira
ABROAD_MOST_SPEND_BPS = 6_000          # and spends at most 60% of what it holds in naira in one quarter
FOREIGN_START_SHARE_BPS = 1_000        # foreign investors' usual stake: a tenth of what the rest of the world holds in naira
FOREIGN_CARRY_BPS = 1_500              # each point of extra return over abroad moves what they want to hold by 15%
FOREIGN_WANT_LIMITS_BPS = (2_000, 25_000)
FOREIGN_MOVE_BPS = 5_000               # they close half the gap to what they want each quarter
FOREIGN_TILT_PER_CARRY_BPS = 2_000     # ...and price shares up or down by 20% of their extra return (as a share of a year)...
FOREIGN_MOST_TILT_BPS = 150            # ...at most 1.5%
FOREIGN_DAY_SHARE_BPS = 500            # they trade at most about 5% of a day's trading: once their buying or selling today
                                       # reaches 5% of what everybody else traded on an average recent day, they only wait
FOREIGN_DAY_LEAST_NAIRA = 2_000_000    # (in a new market with little trading yet, they may still trade this much a day)

# ---------------------------------------------------------------------------
# Stage 8: land, property, headquarters and the Auction House (owner, 12 October 2026).
# ---------------------------------------------------------------------------
# Each city's districts: name, character. Every district has big buildings, small units and empty plots.
DISTRICTS: dict[str, tuple[tuple[str, str], ...]] = {
    LAGOS: (("Victoria Island", "business"), ("Ikoyi", "homes"), ("Ikeja", "shops"), ("Apapa", "industry"), ("Epe", "farmland")),
    ABUJA: (("Central Business District", "business"), ("Maitama", "homes"), ("Wuse", "shops"), ("Idu", "industry"), ("Kuje", "farmland")),
    PORT_HARCOURT: (("Old GRA", "business"), ("Rumuola", "homes"), ("Mile One", "shops"), ("Trans-Amadi", "industry"), ("Oyigbo", "farmland")),
    ABA: (("Aba Township", "business"), ("Ogbor Hill", "homes"), ("Ariaria", "shops"), ("Osisioma", "industry"), ("Obingwa", "farmland")),
    KANO: (("Bompai", "business"), ("Nassarawa", "homes"), ("Kurmi", "shops"), ("Sharada", "industry"), ("Dawakin Kudu", "farmland")),
}
DISTRICT_KIND_NAMES = {"business": "Business district", "homes": "Homes", "shops": "Shops and markets", "industry": "Industry", "farmland": "Farmland"}
# What a district's buildings are: (big building kind, small unit kind).
DISTRICT_BUILDINGS = {"business": ("office", "office"), "homes": ("home", "home"), "shops": ("shop", "shop"),
                      "industry": ("factory", "warehouse"), "farmland": ("farmland", "farmland")}
PROPERTY_KIND_NAMES = {"office": "Offices", "home": "Homes", "shop": "Shops", "warehouse": "Warehouse", "factory": "Factory",
                       "farmland": "Farmland", "land": "An empty plot"}
# Rent a square metre earns a quarter, in naira, at the start, by city; and how each kind of building compares.
RENT_A_METRE_NAIRA = {LAGOS: 6_000, ABUJA: 5_500, PORT_HARCOURT: 4_500, ABA: 2_500, KANO: 2_200}
RENT_KIND_TIMES_BPS = {"office": 13_000, "home": 10_000, "shop": 15_000, "warehouse": 5_000, "factory": 4_500, "farmland": 60}
# What a square metre of empty land costs at the start, in naira, by city, and how each district's character changes it.
LAND_A_METRE_NAIRA = {LAGOS: 250_000, ABUJA: 180_000, PORT_HARCOURT: 120_000, ABA: 50_000, KANO: 40_000}
LAND_KIND_TIMES_BPS = {"business": 15_000, "homes": 10_000, "shops": 12_000, "industry": 5_000, "farmland": 200}
BUILD_A_METRE_NAIRA = 200_000          # what building costs a square metre, before the city's own costs
CITY_COST_BPS = {LAGOS: 15_000, ABUJA: 12_000, PORT_HARCOURT: 11_000, ABA: 9_000, KANO: 7_000}
# How many of each, in every district: big buildings, small units, empty plots.
DISTRICT_STOCK = (4, 6, 2)
PROPERTY_YIELD_BELOW_RATE_BPS = 400    # property is valued at a yearly rent of the Central Bank's rate less 4 points...
PROPERTY_LEAST_YIELD_BPS = 500         # ...but never below 5%
PROPERTY_RENT_SHARE_OF_COMPANY_BPS = 6000  # rent is six tenths of a property company's business; the rest is building work
RENT_FOLLOWS_DEMAND_BPS = 2500         # a district's rent moves a quarter of the way to what demand says each quarter
OCCUPANCY_LIMITS_BPS = (5000, 9800)
PREMIUM_DECAY_BPS = 2000               # a price bubble loses a fifth of itself each quarter as rents pull prices back...
PREMIUM_FROM_OVERPAYING_BPS = 5000     # ...and grows by half of what buyers paid above fair value in the district
PREMIUM_LIMITS_BPS = (-4000, 15_000)
PROPERTY_TAX_BPS = 100                 # property tax: 1% of the value a year...
LAND_TAX_BPS = 50                      # ...and land tax: half of one percent, both paid each quarter
TAX_ARREARS_SEIZE_BPS = 1000           # unpaid tax reaching a tenth of the value: the Government sells the property
TAX_ARREARS_PENALTY_BPS = 500          # unpaid tax grows by 5% a quarter
UPKEEP_BPS = 50                        # keeping a building as it is costs half of one percent of its value a quarter
WEAR_WITH_UPKEEP = 1                   # condition points lost a quarter when kept up...
WEAR_WITHOUT_UPKEEP = 5                # ...and when not
RENOVATION_BPS = 500                   # a renovation costs 5% of the value and restores 25 points
RENOVATION_POINTS = 25
POOR_CONDITION = 50                    # below this, tenants start to leave
# Mortgages.
MORTGAGE_SPREAD_BPS = 400              # the Central Bank's rate plus 4 points
MORTGAGE_TERM_QUARTERS = 40            # repaid over ten game years
MORTGAGE_DEPOSIT_BPS = 2000            # a fifth paid up front
MORTGAGE_SALARY_QUARTERS = 16          # a player may borrow at most four years of salary
EMPIRE_MORTGAGE_MOST_BPS = 6000        # an empire may borrow at most 60% of the price
MORTGAGE_MISSES_TO_REPOSSESS = 2       # two quarters missed and the bank takes the building
# The Auction House.
AUCTION_HOURS = 24
AUCTION_EXTEND_MINUTES = 5             # a bid in the last five minutes adds five minutes
AUCTION_STEP_BPS = 100                 # each bid at least 1% above the one before
AUCTION_LISTINGS_A_QUARTER = 12        # property companies put this many up for sale each quarter
AUCTION_RESERVE_BPS = (8500, 9500)     # a seller's secret lowest price: 85% to 95% of fair value
COMPUTER_BID_BPS = (8000, 9600)        # property companies bid for others' property up to 80% to 96% of fair value
TITLE_FLAW_BPS = 800                   # about one lot in twelve has a flaw in its title: the seller does not truly own all of it
TITLE_FLAW_LOSS_BPS = (3000, 10000)    # a buyer of a flawed title loses 30% to all of it to the true owner
# Headquarters.
HQ_LEVEL_BASE_NAIRA = 100_000          # what Level 1 costs; each level costs level^1.6 times this...
HQ_LEVEL_POWER = 16_000                # (the power, in bps)
HQ_MOST_LEVEL = 120
HQ_SEAT_EVERY = 10                     # ...and every ten levels add a seat
HQ_BONUS_PER_ROOT_BPS = 30             # the headquarters' standing: 0.3% times the square root of its level...
HQ_UPKEEP_BPS = 100                    # its upkeep: 1% of what has been spent on it, a quarter
HQ_WEAR_WITHOUT_UPKEEP = 8             # condition lost a quarter when its upkeep is not approved or not paid
HQ_WARN_AT = (50, 30, 15)              # warnings to the head and the Risk Manager as its condition falls
HQ_COLLAPSE_BELOW = 15                 # below this it may fall down: one chance in ten for each point below
HQ_COLLAPSE_REPUTATION = 5             # what the head and the Risk Manager lose if they ignored the warnings
# What each city's headquarters favours: its industries (work for clients in them earns the bonus twice over).
HQ_CITY_INDUSTRIES = {LAGOS: ("banking", "telecoms", "media", "insurance"), ABUJA: ("insurance", "real_estate", "power"),
                      PORT_HARCOURT: ("oil_gas", "shipping", "power"), KANO: ("agriculture", "consumer", "transport"),
                      ABA: ("manufacturing", "consumer", "cement")}
HQ_CITY_WORDS = {LAGOS: "the best deals and recruits, but the dearest land", ABUJA: "lobbying (felt fully when the Government stage comes)",
                 PORT_HARCOURT: "energy deals", KANO: "the cheapest land, trade and farming", ABA: "manufacturing"}
LAGOS_RECRUIT_POINTS = 5              # a Lagos headquarters: players may join with a reputation 5 lower

# ---------------------------------------------------------------------------
# Stage 9, Part A: the stochastic engine, "What could happen?", borrowing and short selling.
# ---------------------------------------------------------------------------
# How much each industry leans on the quarter's common forces (economy, energy, building, farming, money).
# The squares of a row add up to less than 1; the rest of an industry's luck is its own.
SECTOR_FACTOR_LOADINGS = {
    "consumer": {"economy": 0.6}, "hospitality": {"economy": 0.7}, "aviation": {"economy": 0.6, "energy": -0.3},
    "manufacturing": {"economy": 0.5}, "transport": {"economy": 0.5, "energy": -0.2}, "telecoms": {"economy": 0.3},
    "media": {"economy": 0.5}, "banking": {"economy": 0.4, "money": 0.4}, "insurance": {"economy": 0.3, "money": 0.3},
    "oil_gas": {"energy": 0.8}, "power": {"economy": 0.3, "energy": 0.3}, "cement": {"building": 0.6, "economy": 0.3},
    "real_estate": {"building": 0.6, "economy": 0.3}, "agriculture": {"farming": 0.8}, "shipping": {"economy": 0.4, "energy": 0.2},
    # Part 4c. Technology leans hardest of any industry on the money force, which is what makes a rise in the
    # long interest rate hurt its shares most. Fertilisers lean on gas (energy) and on the farms that buy them.
    "pharma": {"economy": 0.4}, "retail": {"economy": 0.7}, "technology": {"economy": 0.3, "money": 0.6},
    "entertainment": {"economy": 0.6}, "mining": {"economy": 0.4, "energy": 0.3}, "fertiliser": {"energy": 0.6, "farming": 0.4},
}
COMPANY_SHARES_OF_SECTOR = 0.5         # a company carries half of its industry's lean; the rest of its luck is its own
OIL_LOADINGS = {"energy": 0.9}
NAIRA_LOADINGS = {"money": 0.7}
HOUSEHOLD_MOOD_LOADINGS = {"economy": 0.6}
COMMODITY_LOADINGS = {"energy": {"energy": 0.8}, "agriculture": {"farming": 0.8}, "metals": {"economy": 0.5},
                      "materials": {"building": 0.7}}
# The computer investors' tempers: how much of a share's move over the last five trading days each kind
# adds to (or, for those who go against the crowd, takes from) its view. In hundredths of a percent per percent.
INVESTOR_TEMPER_BPS = {"investors:institutions": -15, "investors:public": 30, "investors:founders": -5, "investors:foreign": 20}
INVESTOR_TEMPER_MOST_BPS = 300         # never more than 3% either way
SQUEEZE_BPS_PER_SHORT_PERCENT = 20     # small investors price a heavily shorted, rising share up: 0.2% for each 1% of shares shorted...
SQUEEZE_MOST_BPS = 400                 # ...up to 4%
RISK_SESSIONS = 60                     # a share's risk figures use its last 60 trading days

# "What could happen?" (Monte Carlo).
MONTE_CARLO_PATHS = 1_000
MONTE_CARLO_FREE_A_DAY = 1             # one free run a day...
MONTE_CARLO_FEE_NAIRA = 5_000          # ...then each run costs this, paid to the exchange (it leaves the players' hands)
MONTE_CARLO_HORIZONS = {"quarter": 7, "year": 28}   # in trading days

# Personal loans.
PERSONAL_LOAN_SALARY_QUARTERS = 4      # at most a year's salary...
PERSONAL_LOAN_SPREAD_BPS = 800         # uninsured spread over the policy rate, for personal loans

# Insurance: the spread narrows when the borrower has active cover in force.
# INSURED_PERSONAL_LOAN_STEP1_BPS: one step (500 bps) reduction for any cover in force.
# INSURED_PERSONAL_LOAN_STEP2_BPS: second step (500 bps reduction) if cover > 50% of liabilities.
INSURED_PERSONAL_LOAN_STEP1_BPS = 500
INSURED_PERSONAL_LOAN_STEP2_BPS = 500
PERSONAL_LOAN_TERM_QUARTERS = 8        # ...repaid over two years
LOAN_MISSES_TO_DEFAULT = 2             # two quarters missed and the loan is in default: no more borrowing until it is cleared
LOAN_LATE_PENALTY_BPS = 500            # what is unpaid grows by 5% a quarter
# Loans against shares and bonds (margin loans).
MARGIN_LOAN_MOST_BPS = 5000            # borrow up to half the value of the shares and bonds held
MARGIN_LOAN_SPREAD_BPS = 200           # at the Central Bank's rate plus 2%
MARGIN_CALL_BPS = 7000                 # a margin call when the loan reaches 70% of shares, bonds and cash...
MARGIN_SELL_BPS = 8000                 # ...and shares are sold when it reaches 80%, or a call is not met by the next Closing Bell
FORCED_SALE_DISCOUNT_BPS = 500         # shares sold by force go to the market's computer investors at 5% below the closing price
MOST_DEBT_TIMES_EQUITY = 2             # all a player's borrowing together: at most twice what they are worth after debts
# Short selling.
SHORT_COLLATERAL_BPS = 15000           # cash held as collateral: 150% of the borrowed shares' value
SHORT_CALL_BPS = 12500                 # a margin call when the collateral falls below 125% of their value...
SHORT_BUY_IN_BPS = 11000               # ...and they are bought back by force below 110%, or when a call is not met by the next bell
SHORT_FEE_BPS = 200                    # the lender's fee: 2% a year of the borrowed shares' value
LENDING_POOL_BPS = 3000                # a pension fund lends at most 30% of its holding of a share
BUY_IN_PREMIUM_BPS = 500               # shares bought back by force cost 5% above the closing price
EMPIRE_LEVERAGE_DEFAULT_BPS = 0        # an empire may borrow against its holdings and short only inside limits its Risk Manager signs

# ---------------------------------------------------------------------------
# Stage 9, Part B: options, futures, commodities, the hedging desk and the crash fund.
# ---------------------------------------------------------------------------
OPTION_SHARES_PER_CONTRACT = 100       # a share option is on 100 shares
INDEX_KOBO_PER_POINT = 10_000          # a BSX 50 contract: ₦100 for each point of the index
OIL_BARRELS_PER_CONTRACT = 10          # an oil contract: ten barrels, valued in naira at the day's exchange rate
NAIRA_DOLLARS_PER_CONTRACT = 1_000     # a naira contract: $1,000, valued in naira
COMMODITY_KOBO_PER_POINT = 1_000_000   # a farm produce, metals or building materials contract: ₦10,000 for each point of its index
OPTION_STRIKES_BPS = (9000, 10000, 11000)              # share options: strikes at 90%, 100% and 110% of the price when listed

# ---------------------------------------------------------------------------
# Stage 12: the goods themselves — gold, oil, farm produce and building materials.
# ---------------------------------------------------------------------------
COMMODITY_MARKET_FLOAT = 200_000_000_000  # ₦2 billion the pension funds put behind the goods market, so it can bid from its first day (kobo)
COMMODITY_HEDGE_QUOTES = 3              # the desk quotes at most this many companies a quarter
COMMODITY_QUOTE_EDGE_BPS = 150          # the desk's price to a client sits this far its own way of the market
COMMODITY_HEDGE_FEE_BPS = 75            # and it charges this much of the value as its fee
COMMODITY_CLIENT_TAKE_BPS = 6000        # a client takes a hedge when it is not more than 60% worse than its own idea of the price
COMMODITY_DESK_DEFAULT_BPS = 4000       # a client that fails pays at most this much of what it owes, ever
COMMODITY_DESK_LEAST_LIMIT = 50_000_000 # a desk may not be given less than ₦500,000 of risk
COMMODITY_DESK_MOST_LIMIT_BPS = 2500    # ...nor more than a quarter of the firm's own funds
INDEX_OPTION_STRIKES_BPS = (9000, 9500, 10000, 10500, 11000)
OPTION_EXPIRIES = 2                    # options and futures run to the end of this quarter and the next
OPTION_LEAST_VOLATILITY_BPS = 1500     # the market makers never price a share's swing below 15% a year...
INDEX_VOLATILITY_BPS = 2000            # ...and take the BSX 50 to swing 20% a year until its own record says otherwise
DESK_SPREAD_BPS = 500                  # options: the market makers buy at 5% below their price and sell at 5% above...
DESK_LEAST_SPREAD_KOBO = 1_000         # ...and never closer than ₦10 a contract either side
FUTURE_SPREAD_BPS = 25                 # futures: 0.25% either side
WORLD_RATE_BPS = 400                   # interest abroad, for the naira future's price
FUTURE_MARGIN_BPS = 1500               # a futures position: 15% of its value held as margin...
FUTURE_MAINTENANCE_BPS = 1000          # ...a call when it falls below 10%; closed at the next bell if not met
WRITER_MARGIN_BPS = 2000               # writing (selling) an option: 20% of the underlying value held, plus the option's own value
WRITER_CALL_SHARE_BPS = 8500           # a call when what is held falls below 85% of what is needed
MOST_CONTRACTS_A_SERIES = 1_000        # at most this many contracts of one series for one account
EMPIRE_DERIVATIVES_DEFAULT_NAIRA = 0   # an empire trades derivatives only inside a limit its Risk Manager signs
# The crash fund: empires pay in each quarter for cover that pays out when the market falls hard.
CRASH_PREMIUM_BPS = 300                # 3% of the cover, each quarter...
CRASH_TRIGGER_BPS = 1500               # ...and it pays the cover when the BSX 50 falls 15% or more in a quarter
CRASH_MOST_COVER_BPS = 5000            # cover at most half of what the empire is worth

# ---------------------------------------------------------------------------
# The gap stage, Part 1: the clearing house, unlocking by level and mastery, the Securities Regulator.
# ---------------------------------------------------------------------------
DERIVATIVE_FEE_BPS = 5                 # each side of an option or futures trade pays 0.05% of what the contracts are on...
DEFAULT_FUND_SHARE_BPS = 1000          # ...and a tenth of that fee goes to the clearing house's default fund
MAKER_SEQUENCE = 2 ** 62               # the market makers' standing quote waits behind every player's order at the same price
UNLOCK_BORROW_LEVEL = 10               # loans against shares and short selling open at Level 10
UNLOCK_OPTIONS_LEVEL = 15              # buying options at Level 15
UNLOCK_ADVANCED_LEVEL = 25             # futures, writing options and swaps at Level 25, with the build's own Stage 9 module learned
STAGE9_MODULE = {"asset_manager": "Leverage and margin", "investment_banker": "Option pricing", "risk_manager": "Value at risk"}
SHORT_BAN_SHARE_FALL_BPS = 1500        # the Securities Regulator stops new short sales in a share that falls 15% in a day...
SHORT_BAN_MARKET_FALL_BPS = 1000       # ...and in every share when the BSX 50 falls 10% in a day...
SHORT_BAN_DAYS = 3                     # ...for three trading days
HEDGE_SELLERS = ("OPP", "BRE", "DCG", "UGS")            # oil and gas producers sell oil futures for part of next quarter's output...
HEDGE_BUYERS_SECTORS = ("aviation", "transport", "shipping", "power", "mining", "fertiliser")   # ...and the big users of fuel buy them
HEDGE_SELL_SHARE_BPS = 2500            # a producer hedges about a quarter of a quarter's sales...
HEDGE_BUY_SHARE_BPS = 1000             # ...a user about a tenth
HEDGE_MOST_CONTRACTS = 400             # and never more than this many contracts a company
SWAP_MOST_QUARTERS = 8                 # a swap runs one to eight quarters
SWAP_MOST_NOTIONAL = 1_000_000_000_000 # a rate swap on at most ₦10bn
SWAP_MOST_BARRELS = 100_000            # an oil swap on at most 100,000 barrels a quarter
SWAP_BANK_RATE_SPREAD_BPS = 50         # a bank's fixed rate: half a point in its favour
SWAP_BANK_OIL_SPREAD_BPS = 200         # a bank's fixed oil price: 2% in its favour
SWAP_MOST_TIMES_WORTH = 5              # swaps carry no collateral: all of an account's together on at most five times its worth
PREFERRED_SECTORS = ("banking", "insurance", "telecoms", "power", "real_estate", "technology")   # who may sell preferred shares...
PREFERRED_RATINGS = ("AAA", "AA", "A")  # ...if sound...
PREFERRED_ONE_IN = 4                    # ...about one quarter in four for each such company
PREFERRED_SIZE_BPS = 200                # 2% of what the company owns
PREFERRED_PAR = 10_000                  # ₦100 each
PREFERRED_DEALER_MOST_BPS = 1000        # the pension funds put at most a tenth of their cash into one issue
PREFERRED_EXTRA_BPS = 100               # their yield: a long Government bond's, plus the company's spread, plus 1%
PREFERRED_SPREAD_BPS = 100              # the desk's two prices, 1% either side
WARRANT_SPREAD_BPS = 500                # warrants, 5% either side
WARRANT_PER_NEW_SHARES = 5              # one warrant with every five new shares taken up in a rights issue
WARRANT_PER_BONDS = 4                   # one warrant with every four high-yield bonds
WARRANT_STRIKE_BPS = 12_000             # at 120% of the share price when handed out
WARRANT_QUARTERS = 8                    # usable for eight quarters
MEZZ_MOST_BPS = 2000                    # mezzanine: at most a fifth of the price...
MEZZ_WITH_LOAN_MOST_BPS = 8000          # ...and the bank's loan and the mezzanine together at most four fifths
MEZZ_EXTRA_BPS = 600                    # six points dearer than the bank's buyout loan
MEZZ_EQUITY_BPS = 500                   # its warrants: 5% of the company, used at once
EARNOUT_MOST_BPS = 3000                 # an earn-out: at most 30% of the price paid later...
EARNOUT_QUARTERS = 4                    # ...after four quarters...
EARNOUT_TARGET_BPS = 10_000             # ...in full if the company's sales over them match its last year's (in proportion if less)
EARNOUT_SELLER_COUNTS_BPS = 6000        # a seller counts an earn-out at 60% of its face when judging bids
DEAL_LEAST_EQUITY_BPS = 1000           # with mezzanine or an earn-out, at least a tenth of the price is the buyers' own cash
LEASEBACK_DISCOUNT_BPS = 300           # sale-and-leaseback: sold at 3% below its value...
LEASEBACK_EXTRA_YIELD_BPS = 200        # ...and rented back at the yield investors want, plus two points...
LEASEBACK_LEAST_QUARTERS = 4           # ...for four...
LEASEBACK_MOST_QUARTERS = 20           # ...to twenty quarters
LEASEBACK_MISSES_TO_BREAK = 2          # two rents missed and the lease is broken

# ---------------------------------------------------------------------------
# The gap stage, Part 2: Stage 8's missing pieces (zoning, infrastructure, the twelve-step purchase, claims,
# development, hotels and malls, households' home loans, valuation work and property funds).
# ---------------------------------------------------------------------------
ZONES = ("residential", "commercial", "industrial", "agricultural", "resource", "mixed")
ZONE_NAMES = {"residential": "Residential", "commercial": "Commercial", "industrial": "Industrial", "agricultural": "Agricultural",
              "resource": "Resource (mining and oil)", "mixed": "Mixed use"}
DISTRICT_ZONE = {"business": "commercial", "homes": "residential", "shops": "commercial", "industry": "industrial", "farmland": "agricultural"}
ZONE_ALLOWS = {"residential": ("home",), "commercial": ("office", "shop", "hotel", "mall"), "industrial": ("factory", "warehouse"),
               "agricultural": ("farmland",), "resource": ("warehouse", "factory"), "mixed": ("home", "office", "shop", "hotel", "mall")}
RESOURCE_CITIES = ("Port Harcourt",)     # where some farmland plots sit on oil and gas and are zoned for it
ZONE_LAND_TIMES_BPS = {"residential": 10_000, "commercial": 13_500, "industrial": 5_000, "agricultural": 200, "resource": 3_000, "mixed": 14_000}
REZONE_FEE_NAIRA = 500_000             # applying to the planning office to rezone a plot
REZONE_STRONG_OCCUPANCY_BPS = 9300     # a rezoning is granted when the city's district of the new use is this full...
REZONE_PLANNER_OCCUPANCY_BPS = 9600    # ...and the planners rezone a plot themselves when a district stays this full
INFRA_EVERY_QUARTERS = 4               # about one big project a game year
INFRA_KINDS = {"road": ("Expressway", 4, 1200), "rail": ("Rail Line", 6, 1800), "port": ("Port Terminal", 6, 2200)}  # name, quarters, uplift
INFRA_PORT_CITIES = ("Lagos", "Port Harcourt")
INFRA_COST_A_QUARTER_NAIRA = 6_000_000_000    # what the Government spends on the works each quarter they run (before the city's costs)
INFRA_BESIDE_TIMES = 2                 # land beside the works gains twice the district's uplift
# The twelve-step purchase, outside the Auction House.
SALE_STEPS = ("seller", "title", "claims", "zoning", "valuation", "money", "terms", "consent_asked", "consent", "contract", "registered", "handover")
SALE_CHECK_STEPS = ("seller", "title", "claims", "zoning", "valuation")      # skipping these never blocks; the risk shows later
CONSENT_DAYS = 2                       # the Governor's consent takes about two real days
CONSENT_FEE_BPS = 50                   # the consent fee: half of one percent of the price
REGISTRATION_FEE_BPS = 50              # registering any transfer at the Land Registry: half of one percent, paid by the buyer
CLAIMS_SEARCH_FEE_NAIRA = 30_000
# Claims besides a bad title (secret until searched for or they come to light).
CLAIM_OLD_LOAN_BPS = 500               # about one property in twenty has an old loan secured on it...
CLAIM_OLD_LOAN_SIZE_BPS = (500, 2000)  # ...for 5% to 20% of its value, which the owner must pay off
CLAIM_RIGHT_OF_WAY_BPS = 400           # one in twenty-five has a right of way across it...
CLAIM_RIGHT_OF_WAY_CUT_BPS = 1000      # ...which takes a tenth off its value
CLAIM_DISPUTE_BPS = 300                # one in thirty-odd has a family or community dispute...
CLAIM_DISPUTE_SETTLE_BPS = 500         # ...frozen until settled with the claimants for 5% of its value (courts come later)
CLAIM_DISPUTE_FADES_QUARTERS = 8       # ...or, unsettled, it fades after eight quarters
# Development projects.
PERMIT_FEE_BPS = 100                   # a building permit: 1% of the budget
PERMIT_DAYS = 2
PERMIT_DELAY_CHANCE_BPS = 2000         # one permit in five is held up a quarter
DEVELOPMENT_PHASES = 4                 # foundations, frame, building, fitting out: one a quarter
DEVELOPMENT_SAVING_BPS = 1000          # managing the work yourself saves a tenth on a turnkey build...
DEVELOPMENT_SPLIT_BPS = {"cement": 3500, "steel": 2500, "works": 4000}      # ...bought from the cement, steel and building companies
STEEL_SECTOR = "manufacturing"
STRIKE_CHANCE_BPS = 800                # a strike holds a phase up a quarter
CONSTRUCTION_LOAN_MOST_BPS = 7000      # a bank lends at most 70% of the budget, paid out phase by phase
CONSTRUCTION_LOAN_SPREAD_BPS = 600     # at the Central Bank's rate plus six points
# Hotels and malls.
RENT_KIND_TIMES_BPS.update({"hotel": 14_000, "mall": 16_000})
PROPERTY_KIND_NAMES.update({"hotel": "Hotel", "mall": "Shopping mall"})
BUILD_KIND_BPS = {"hotel": 13_000, "mall": 13_000}    # fitting out a hotel or a mall costs 30% more than other buildings
BETTERMENT_LEVY_BPS = 5000             # a rezoning granted on request: half of the land's gain in value is paid to the Government
# Households' home loans.
HOME_LOAN_SHARE_BPS = 150              # each quarter households borrow about 1.5% of their income for homes, at the neutral rate...
HOME_LOAN_RATE_SENSITIVITY_BPS = 1500  # ...15% less for each point the mortgage rate stands above it (more below)...
HOME_LOAN_TERM_QUARTERS = 60           # ...repaid over fifteen game years
HOME_LOAN_SPREAD_BPS = 500             # the Central Bank's rate plus five points
HOME_DEFAULT_BASE_BPS = 40             # a quarter's defaults: 0.4% of the book in calm times...
HOME_DEFAULT_PER_RATE_POINT_BPS = 30   # ...plus 0.3% for each point the rate rose over the last year...
HOME_DEFAULT_PER_JOBS_FALL_BPS = 50    # ...plus 0.5% for each percent fewer jobs...
HOME_DEFAULT_BURDEN_BPS = 3000         # ...and more when repayments take over 30% of income
HOME_RECOVERY_BPS = 6000               # a repossessed home sells for 60% of the loan
HOME_BUILD_COST_BPS = 5500             # the property companies spend 55% of a new home's price on cement and steel
HOME_PRICE_FROM_BUYING_BPS = 1400      # home buying lifts the homes districts' prices (by 14% of what was lent, against their worth)
HOME_SEED_SHARE_BPS = 2000             # at the start, a fifth of what households owe the banks is home loans
HOME_REPOSSESSION_PRICE_HIT = 1        # repossessions push the homes districts' prices down (by what defaulted, against their worth)
# Property funds.
PROPERTY_FUND_LEVEL = 20
PROPERTY_FUND_FEE_MOST_BPS = 200       # a manager's fee: at most 2% of the fund a year
PROPERTY_FUND_ONE_BUILDING_BPS = 3000  # no building more than 30% of the fund
PROPERTY_FUND_LEAST_CASH_BPS = 1000    # at least 10% in cash, for those who leave
PROPERTY_FUND_SPREAD_BPS = 100         # units bought at 1% above their value, sold at 1% below (kept by the fund)
PROPERTY_FUND_SEED_NAIRA = 3_000_000_000   # the pension funds' stake in the computer-run property trust

# ---------------------------------------------------------------------------
# Stage 10, Part 1: the newsroom (owner's answers, 16 October 2026: the suggested defaults)
# ---------------------------------------------------------------------------
STORY_MOST_FACTS = 5                   # a story uses one to five confirmed facts
STORY_COMMENT_MOST = 280               # the author's own view, in words: at most this many characters, no figures
STORIES_A_DAY = 3                      # a journalist publishes at most three stories a game day
AUDIENCE_PER_STAFF = 10                # a media house reaches about ten readers for each person it employs
INDEPENDENT_AUDIENCE = 2_000           # an independent starts with a small audience of their own, plus their following
SCOOP_READERS_BPS = 15_000             # a scoop is read half as much again
OLD_NEWS_READERS_BPS = 4_000           # news the wire already carried is read less than half as much
FOLLOWERS_READ_BPS = 3_000             # about a third of an author's following read each new story
INTERVIEW_READERS_BPS = 1_000          # each answered interview brings a tenth more readers
FOLLOW_SHARE_BPS = 200                 # 2% of a story's readers start following its author
REACH_PAY_PER_FOLLOWER_BPS_MILLION = 10_000   # an employed journalist's pay rises 100% per million followers...
REACH_PAY_MOST_BPS = 5_000             # ...up to half as much again
FREELANCE_KOBO_PER_READER = 500        # an independent is paid ₦5 a reader by the paper that picks the story up...
FREELANCE_MOST_NAIRA = 2_000_000       # ...at most ₦2 million a story
SCOOP_BONUS_NAIRA = 250_000            # a scoop: ₦250,000...
SCOOP_REPUTATION = 2                   # ...and two points of reputation
CORRECTION_REPUTATION = 3              # a correction costs three points
LATE_CORRECTION_REPUTATION = 6         # a correction not made within the day costs six...
LATE_CORRECTION_FOLLOWING_BPS = 1_000  # ...and a tenth of the author's following
DISMISS_BELOW_CREDIBILITY = 20         # a media house lets go a journalist whose credibility falls below this after a late correction
CORRECTION_HOURS = 24                  # a story whose facts changed in the record must be corrected within 24 real hours
CORRECTION_WATCH_DAYS = 120            # stories are watched for changed facts for about a game year
INTERVIEW_HOURS = 24                   # a company or empire has 24 real hours to answer a journalist
WIDELY_READ = 10_000                   # a story read by this many moves investors, and enters the Chronicle
NUDGE_MOST_BPS = 200                   # a story moves how investors value a company by at most 2%...
NUDGE_DAYS = 5                         # ...fading to nothing over five trading days; one nudge per company a day
READERS_PER_NUDGE_BPS = 1_000          # a hundredth of a percent for each thousand readers
NUDGE_MOST_COMPANIES = 3               # a story about more than three companies moves none of them
STORY_BLOCK_TRADING_DAYS = 2           # no trading a company from the first draft until two trading days after publication
UNDECLARED_REPUTATION = 5              # an undeclared interest, exposed: five points of the author's reputation...
UNDECLARED_CREDIBILITY = 10            # ...ten of their credibility...
UNDECLARED_EMPIRE_REPUTATION = 5       # ...and five of the empire's reputation
# How late each kind of computer-run investor reads the news, in trading days (None: never).
NEWS_LAG_DAYS = {"investors:public": 0, "investors:institutions": 1, "investors:foreign": 2, "investors:founders": None}
ARTICLES_A_DAY = 20                    # full articles written for the wire each game day, at most
INTERVIEWS_A_STORY = 3                 # a story may ask at most three companies or empires for comment...
INTERVIEWS_COUNTED = 2                 # ...and at most two answers add readers
FREELANCE_MOST_A_QUARTER_NAIRA = 20_000_000       # an independent is paid at most ₦20 million a quarter...
FREELANCE_HOUSE_MOST_A_QUARTER_NAIRA = 200_000_000  # ...and the paper that picks up independents' stories pays out at most ₦200 million
FOLLOWING_FADES_BPS = 500              # each quarter a twentieth of a journalist's following drifts away
ARTICLE_FRESH_DAYS = 3                 # full articles are written for items from the last three game days

# ---------------------------------------------------------------------------
# Stage 10, Part 2: information, tips, sources and rumours
# ---------------------------------------------------------------------------
TIP_USEFUL_HOURS = 4                   # a Sealed Tip stops being useful four real hours after it is opened
TIP_VALUABLE_BPS = 3_334               # about a third of tips are about something real and still to come...
TIP_FALSE_BPS = 3_333                  # ...a third are false...                (the rest: true but already public)
TIP_CONFIDENTIAL_BPS = 3_000           # ...and three in ten of the valuable company tips come from someone inside (about 1 in 10 of all)
CHECK_FEE_NAIRA = 50_000               # checking a piece of information costs ₦50,000...
CHECK_RIGHT_BPS = 7_000                # ...and is right 70% of the time...
CHECK_RIGHT_PER_LEVEL_BPS = 50         # ...plus half a percent a level...
CHECK_RIGHT_MOST_BPS = 9_500           # ...at most 95%
SOURCE_QUARTERS = 2                    # a source takes two quarters to build
SOURCE_RELIABILITY_BPS = 8_000         # its hints are true 80% of the time (a little more for a senior journalist)
SOURCE_RELIABILITY_PER_LEVEL_BPS = 25
SOURCE_RELIABILITY_RANGE_BPS = (7_000, 9_000)
SOURCES_LEAST = 2                      # a journalist may keep two sources, and one more for every ten levels...
SOURCES_MOST = 5                       # ...at most five
SOURCE_HINT_USEFUL_HOURS = 48          # a source's hint is useful for two real days
SOURCE_BURN_STORY_BPS = 3_000          # printing a source's hint as an unconfirmed story burns the source three times in ten...
SOURCE_BURN_SALE_BPS = 2_000           # ...selling it, twice in ten
INTEL_PRICE_LEAST_NAIRA = 10_000       # a piece of information sells for ₦10,000...
INTEL_PRICE_MOST_NAIRA = 50_000_000    # ...to ₦50 million
INTEL_LISTINGS_MOST = 10               # a player may have at most ten pieces on the market at once
RUMOUR_IMPORTANCE = 60                 # how big an unconfirmed report counts, for its readers
RUMOUR_READERS_BPS = 7_000             # an unconfirmed report is read by seven in ten of those who would read a confirmed one
RUMOUR_NUDGE_SHARE_BPS = 5_000         # investors mark a company on an unconfirmed report half as far, and only as far as they trust the author
RUMOUR_CONFIRMED_CREDIBILITY = 2       # a rumour borne out adds two points to the author's credibility
INVESTIGATIONS_OPEN_MOST = 2           # a journalist works at most two investigation files at once
DIG_FINDS_BPS = 2_500                  # a day's search finds a document a quarter of the time (when there is something to find)...
DIG_FINDS_PER_LEVEL_BPS = 50           # ...more for a senior journalist...
DIG_FINDS_MOST_BPS = 5_500             # ...at most 55%; a true tip that started the file helps
DIG_TIP_HELPS_BPS = 1_500
DOCUMENTS_NEEDED = 3                   # an exposé needs three documents...
SECOND_SOURCE_BPS = 3_500              # ...and a second source, found a third of the time each day once two documents are in hand
SECOND_SOURCE_PER_LEVEL_BPS = 50
SECOND_SOURCE_MOST_BPS = 7_000
EXPOSE_BONUS_NAIRA = 2_000_000         # an exposé of a real theft or unlawful pact: a ₦2 million prize from the paper...
EXPOSE_REPUTATION = 5                  # ...five points of reputation...
EXPOSE_CREDIBILITY = 5                 # ...and five of credibility
EXPOSE_IMPORTANCE = 90
CRISIS_HOURS = 24                      # an empire has 24 real hours to answer a crisis
# What answering a crisis does to the empire's reputation, by what was really so and what it said (None: it said nothing).
CRISIS_OUTCOMES = {
    ("true", "admit"): -1, ("true", "regret"): -2, ("true", "deny"): -6, ("true", None): -4,
    ("false", "admit"): -3, ("false", "regret"): -1, ("false", "deny"): 1, ("false", None): -2,
    ("worthless", "admit"): 0, ("worthless", "regret"): 0, ("worthless", "deny"): -1, ("worthless", None): 0,
}
LEAKS_A_QUARTER = 1                    # a member may pass one thing a quarter to the press
LEAK_USEFUL_HOURS = 48
LEAK_HUNT_BPS = 5_000                  # a leak hunt names the leaker half the time...
LEAK_HUNT_PER_LEVEL_BPS = 100          # ...more when the hunter is more senior than the leaker, less when less...
LEAK_HUNT_RANGE_BPS = (2_000, 9_000)
RANDOM_LEAK_BPS = 500                  # each hidden pact has a one-in-twenty chance a quarter of leaking to the press on its own
SPIN_REPUTATION = 2                    # a reply that spins a story helps the empire for now...
SPIN_COMES_OUT_BPS = 2_500             # ...but each quarter one in four comes out...
SPIN_EXPOSED_EMPIRE_REPUTATION = 4     # ...costing the empire four points,
SPIN_EXPOSED_REPUTATION = 5            # ...the journalist five of reputation...
SPIN_EXPOSED_CREDIBILITY = 10          # ...and ten of credibility
SPIN_REFUSED_REPUTATION = 1            # refusing keeps a clean name
PRESS_TONE_REPUTATION = 1              # a widely read story moves the reputation of the empires it names by a point, its way
TRACES_QUARTERS = 2                    # the counter-investigation looks at the last two quarters of public traces
# Charities (owner's suggestion 10)
CHARITY_CAUSES = {"education": "Education", "health": "Health", "water": "Clean water", "arts": "The arts", "relief": "Disaster relief"}
CHARITY_LEAST_FOUNDING_NAIRA = 1_000_000          # founding a charity takes at least ₦1 million of the founder's own money
CHARITY_LEAST_GIFT_NAIRA = 10_000
CHARITY_LEAST_GRANT_NAIRA = 10_000
CHARITY_REPUTATION_PER_NAIRA = 25_000_000         # an empire gains a point of reputation for each ₦25 million its charity grants to its cause...
CHARITY_REPUTATION_MOST = 3                       # ...at most three points a quarter
CHARITY_PLAYER_REPUTATION_PER_NAIRA = 5_000_000   # a player, a point for each ₦5 million given away to a cause...
CHARITY_PLAYER_REPUTATION_MOST = 2                # ...at most two a quarter
CHARITY_CONNECTED_FLAG_BPS = 2_500                # the Money Watch looks at a charity whose grants to connected people pass a quarter of its grants
CHARITY_EXPOSED_REPUTATION = 6
# Media titles sold at the Auction House (owner's suggestion 1)
MEDIA_TITLES = (                                  # name, kind, city, audience
    ("The Garden City Courier", "paper", PORT_HARCOURT, 60_000),
    ("The Harmattan Post", "paper", KANO, 50_000),
    ("Capital Bulletin", "paper", ABUJA, 45_000),
    ("The Evening Drum", "paper", LAGOS, 80_000),
    ("Aba Market Voice", "radio", ABA, 35_000),
)
MEDIA_KOBO_PER_READER = 4_000                     # each regular reader brings in ₦40 a quarter (sales and advertising), from the city's households
MEDIA_STORY_KOBO_PER_READER = 200                 # each reader of a story printed in it, ₦2 more
MEDIA_COST_BPS = 6_000                            # its staff, paper and print take three-fifths of what it brings in
MEDIA_GROWTH_BPS = 100                            # its audience grows by a hundredth of the readers of the stories printed in it...
MEDIA_AUDIENCE_MOST_TIMES = 3                     # ...up to three times where it began; with nothing printed in it, it drifts back
MEDIA_DRIFT_BPS = 500
MEDIA_VALUE_TIMES = 5                             # a title is worth about five years' profit
MEDIA_RESERVE_BPS = (8_000, 10_000)               # the Government's lowest price when it sells one: 80% to 100% of what it is worth
MEDIA_COMPUTER_BID_BPS = (7_000, 9_500)           # the big media houses bid up to 70%-95% of what a title is worth
CHARITY_PEOPLE_FLAG_NAIRA = 5_000_000            # the Money Watch also looks at a charity that gives most of its money (₦5m or more) to named people
MEDIA_RESERVE_MOST_TIMES = 2                      # an owner's lowest price, and an empire's bid, are at most twice what a title is worth

# ---------------------------------------------------------------------------
# The crises stage, Part 1: deposits, trust, bank runs and their cures (owner's suggestions 2 and 4; design section 14)
# ---------------------------------------------------------------------------
DEPOSIT_GUARANTEE_NAIRA = 5_000_000              # each saver's money at each bank is guaranteed up to ₦5 million
HOUSEHOLD_COVERED_BPS = 6_500                    # about two-thirds of what households keep at the banks belongs to savers below that line
GUARANTEE_PREMIUM_BPS = 5                        # each bank pays the guarantee fund 0.05% of its savers' money every quarter
TERM_SAVINGS_RATE_SHARE_BPS = {"AAA": 5_200, "AA": 5_600, "A": 6_000, "BBB": 6_500, "BB": 7_200, "B": 8_000, "CCC": 9_000, "D": 0}
SAVINGS_LEAST_NAIRA = 10_000                     # the smallest sum put into or taken out of savings
CONFIDENCE_START = 70
CONFIDENCE_WORRIED = 45                          # below this, savers start to draw their money out
CONFIDENCE_RUN = 35                              # below this, a run: queues at the branches
CONFIDENCE_PANIC = 20
CONFIDENCE_WARNING = 55                          # a bank below this is a warning sign on the Crisis Watch
CONFIDENCE_DAILY_MOVE_BPS = 4_000                # each game day trust moves two-fifths of the way to where its signals put it
# What savers draw out each game day, in hundredths of a percent of their savings: (above the guarantee, below it)
RUN_WITHDRAWAL_BPS = {"calm": (0, 0), "worried": (30, 5), "run": (400, 40), "panic": (1_000, 150)}
REDEPOSIT_SAME_DAY_BPS = 7_000                   # of what is drawn out in a run, seven-tenths goes the same day to the banks most trusted...
HOME_RETURN_BPS = 500                            # ...the rest is kept at home, and a twentieth of it goes back each calm day
CALM_NATIONAL = 55                               # trust in the banks taken together at which savers think it calm again
EMERGENCY_PENALTY_BPS = 300                      # the Central Bank's emergency lending costs three points above its rate...
EMERGENCY_COLLATERAL_BPS = 6_000                 # ...and goes no further than three-fifths of the loans the bank holds, less what it owes already
BLANKET_NATIONAL = 35                            # the Government guarantees every saving when trust in the banks falls this low...
BLANKET_RUNS = 2                                 # ...or when this many banks have runs at once...
BLANKET_LIFT_NATIONAL = 60                       # ...and lifts it at a close when trust is back above this
PLACEMENT_DAYS = 3                               # a bank below the run line this many days running raises new money from its institutional owners
PLACEMENT_EQUITY_BPS = 1_000                     # a tenth of its owners' funds...
PLACEMENT_DISCOUNT_BPS = 3_000                   # ...in new shares at 30% below the market price
BANK_MINIMUM_CAPITAL_BPS = 1_000                 # to open again after it is closed, a bank needs owners' funds of a tenth of its loans
RESCUE_OLD_OWNERS_BPS = 500                      # after a rescue, the old owners keep 5% of the bank; the rescuer has the rest
PUBLIC_RESALE_QUARTERS = 4                       # a bank in public hands is sold again after a year
RESCUE_COMPUTER_BID_BPS = (10_000, 13_000)       # a sound bank bids up to 100%-130% of the new money needed
CRISIS_FADE_DAYS = 3                             # a warning fades when every bank has been back above the warning line this many days
CRISIS_RECOVERY_DAYS = 5                         # recovery begins when every bank has been above the worried line this many days
CRISIS_END_DAYS = 10                             # and it ends, and goes into history, when trust in the banks is calm this many days
CRISIS_LONG_WEAKNESS_QUARTERS = 2                # a recovery not done in two quarters is a long weakness
CONFIDENCE_BASE = 76                             # where a sound bank's trust sits with nothing for or against it
CONFIDENCE_REOPEN = 55                           # a closed bank that opens again under new owners starts here
BLANKET_TRUST_POINTS = 12                        # the Government's promise that every saving is safe calms savers this much
CRISIS_RATE_RELIEF_BPS = 100                     # past a banking crisis's tipping point the Central Bank leans a point lower
CRISIS_LENDING_BPS = {"calm": 10_000, "worried": 7_000, "run": 3_000, "panic": 0, "closed": 0}   # new lending, by its savers' mood
COMPANY_SAVINGS_BPS = 5_000                      # a company keeps half its cash above what it likes to hold in savings at its bank
CONTAGION_MOST = 25                              # trouble at other banks costs a bank at most this much trust
REOPEN_GRACE_DAYS = 15                           # a bank opened again under a new owner: its savers give it this many game days...
REOPEN_SUPPORT_POINTS = 15                       # ...and this much trust for the fresh money behind it

# ---------------------------------------------------------------------------
# Run Your Own Fund (the talent and funds stage, Part 2): open investment funds anybody may put money into
# ---------------------------------------------------------------------------
INVEST_FUND_LEVEL = 20                       # an Asset Manager of this level or above may launch one
INVEST_FUND_REGISTRATION_NAIRA = 2_000_000   # paid into the prize pool
INVEST_FUND_SEED_NAIRA = 5_000_000           # the least the manager puts in of their own money
INVEST_FUND_MANAGER_KEEPS_BPS = 100          # while managing, the manager keeps at least 1% of the units (or all they put in)
INVEST_FUND_FEE_MOST_BPS = 200               # the yearly fee: at most 2% of the fund, taken at each closing bell
INVEST_FUND_PERF_FEE_MOST_BPS = 2_000        # the performance fee: at most 20% of the gain above the fund's previous best
INVEST_FUND_SWING_BPS = 25                   # money coming in pays 0.25% above the price, money going out 0.25% below: kept by the fund
INVEST_FUND_ONE_HOLDING_BPS = 1_000          # no holding above 10% of the fund
INVEST_FUND_LEAST_CASH_BPS = 500             # at least 5% kept in cash
INVEST_FUND_BALANCED_MOST_BPS = 7_000        # a balanced fund: at most 70% in shares and at most 70% in bonds
INVEST_FUND_STRATEGY_LEAST_BPS = 8_000       # a banks fund keeps at least 80% of its holdings in banks
INVEST_FUND_BORROW_MOST_BPS = 1_000          # it may borrow at most 10% of the fund, and only to pay investors who leave
INVEST_FUND_LOAN_OVER_POLICY_BPS = 300       # ...at the Central Bank's rate and 3% more
INVEST_FUND_GATE_BPS = 1_000                 # a gated fund pays leavers at most 10% of the fund at a bell
INVEST_FUND_GATE_LONGEST_BELLS = 7           # a gate lasts at most a game quarter
INVEST_FUND_LEAST_IN_LIMITS_NAIRA = (10_000, 50_000_000)
INVEST_FUND_SMALL_NAIRA = 50_000_000         # a fund this small at two quarter ends running (after its first two) is closed
INVEST_FUND_SMALL_QUARTERS = 2
INVEST_FUND_STAR_FLOWS_BPS = {5: 800, 4: 400, 3: 100, 2: -300, 1: -600}   # computer investors' money in or out each quarter
INVEST_FUND_NEW_FLOW_BPS = 200               # a fund too young for stars draws a little new money
INVEST_FUND_NEW_FLOW_LEAST_NAIRA = 20_000_000
INVEST_FUND_RUN_FALL_BPS = 1_500             # a fall of 15% from its high, or a banking panic, starts a run by its computer investors
INVEST_FUND_RUN_DAILY_BPS = 800              # ...who ask back 8% of their units at each bell...
INVEST_FUND_RUN_BELLS = 5                    # ...for five bells
INVEST_FUND_COSTS_BPS = 100                  # a manager may sign for costs of 1% of the fund in a quarter
INVEST_FUND_AUDIT_FINDS_BPS = 4_000          # the regulator's audit finds a false cost 40% of the time each quarter it is looked at
INVEST_FUND_FINE_BPS = 5_000                 # a manager proved to have taken money repays it and a fine of half as much
INVEST_FUND_SESSIONS_PER_YEAR = 28
# The computer-run funds every player fund is compared with: (name, strategy, fee, seed).
COMPUTER_FUNDS = (
    ("Broad Street Equity Fund", "shares", 120, 20_000_000_000),
    ("Lagoon Banks Fund", "banks", 150, 8_000_000_000),
    ("Niger Delta Bond Fund", "bonds", 60, 15_000_000_000),
    ("Harmattan Balanced Fund", "balanced", 100, 12_000_000_000),
)

# ---------------------------------------------------------------------------
# Index funds and ETFs (the talent and funds stage, Part 3)
# ---------------------------------------------------------------------------
INDEX_START_LEVEL = 100_000                  # every index starts at 1,000.00 (hundredths of a point)
INDEX_CAP_BPS = 1_500                        # no company above 15% of an index...
INDEX_CAP_FEW_MEMBERS = 7                    # ...unless it has fewer than seven members: then one and a half times an equal share
INDEX_STRATEGIC_HOLDER_BPS = 3_000           # shares held by founders, or by any one owner with 30% or more, are not freely traded
INDEX_CHANGE_NOTICE_BELLS = 3                # a review's changes are announced as the quarter closes and made at the third bell after
INDEX_DIVIDEND_MEMBERS = 10                  # the High Dividend index: the ten best dividend payers of the last year
INDEX_CUSTOM_MOST = 30                       # a manager's own index: at most 30 companies
INDEX_FUTURES = ("TOP30", "BANKS", "OILGAS")  # futures and options on these indexes, alongside the BSX 50's
# The game's own indexes: (code, name, kind, rule, published rules).
INDEXES = (
    ("TOP30", "BSX Top 30", "shares", "top30",
     "The 30 largest companies on the Broad Street Exchange by the value of their freely traded shares."),
    ("BANKS", "BSX Banks", "shares", "sector:banking", "Every listed bank."),
    ("OILGAS", "BSX Oil & Gas", "shares", "sector:oil_gas", "Every listed oil and gas company."),
    ("CONSUMER", "BSX Consumer", "shares", "sector:consumer", "Every listed company making food, drinks and household goods."),
    ("DIVIDEND", "BSX High Dividend", "shares", "dividend",
     "The ten listed companies that paid the most in dividends over the last year, for their size."),
    ("PROPERTY", "BSX Property", "shares", "sector:real_estate", "Every listed property and construction company."),
    # --- Part 4c: a basket for each of the six new industries, so index funds and ETFs may copy them.
    # The owner approved no futures on these: a basket of three is too thin for a contract, and a thin
    # basket is the easiest place to move a price by hand. ---
    ("PHARMA", "BSX Medicines", "shares", "sector:pharma",
     "Every listed company that makes medicines, runs hospitals or does medical tests."),
    ("RETAIL", "BSX Retail", "shares", "sector:retail", "Every listed grocery and retail company."),
    ("TECH", "BSX Technology", "shares", "sector:technology", "Every listed technology and payments company."),
    ("FILM", "BSX Film & Entertainment", "shares", "sector:entertainment",
     "Every listed film, music and entertainment company."),
    ("MINING", "BSX Mining", "shares", "sector:mining", "Every listed mining company."),
    ("FERT", "BSX Fertilisers", "shares", "sector:fertiliser",
     "Every listed maker of fertilisers and crop chemicals."),
    ("GOVBOND", "Federal Government Bond", "bonds", "govbond", "Every Federal Government bond and bill still to be repaid, by the amount owed."),
    ("CORPBOND", "Company Bond", "bonds", "corpbond", "Every company bond still to be repaid and not in default, by the amount owed."),
)

ETF_LEVEL = 20                               # an Asset Manager of this level launches an ETF or an index fund (as in Part 2)
ETF_FEE_MOST_BPS = 100                       # an index vehicle's yearly fee: at most 1%
ETF_FIRST_NAV_KOBO = 10_000                  # a new ETF's first unit is worth ₦100
ETF_CREATION_UNITS = 10_000                  # units are made and unmade in blocks of 10,000
ETF_BASKET_FEE_BPS = 5                       # making or unmaking units against a basket of shares: 0.05%
ETF_CASH_FEE_BPS = 25                        # ...against cash (the fund buys or sells the basket): 0.25%
ETF_TRADE_FEE_BPS = 5                        # each side of a trade in ETF units pays 0.05% to the exchange
ETF_PRICE_BAND_BPS = 1_000                   # an ETF trades within 10% of the last bell's price (20% for 2x and inverse)
ETF_MAKER_HALF_SPREAD_BPS = 20               # the market makers quote 0.2% either side of where they put the value...
ETF_MAKER_SPECIAL_HALF_SPREAD_BPS = 50       # ...0.5% for 2x, inverse and commodity ETFs
ETF_MAKER_DEPTH_BPS = 50                     # ...for up to 0.5% of the units in issue (and at least 5,000)
ETF_MAKER_LEAST_DEPTH = 5_000
ETF_PREMIUM_MOST_BPS = 75                    # the game's own dealers make or unmake units once the price is 0.75% from value...
ETF_SPECIAL_PREMIUM_MOST_BPS = 150           # ...1.5% for 2x, inverse and commodity ETFs
# Buying (or selling) the makers' whole depth moves where they quote by their half spread: never enough to buy from them and
# sell straight back at a profit.
ETF_PREMIUM_DECAY_BPS = 5_000                # at each bell half of the gap closes...
ETF_PREMIUM_SHOCK_BPS = 25                   # ...and a new day's mood moves it by up to this much either way
ETF_OFF_VALUE_ALERT_BPS = 100                # a closing price 1% or more from value is news for its holders
ETF_SPECIAL_LEVEL = 15                       # 2x and inverse ETFs: a player of Level 15 or more in any build, who has read the warning
ETF_DEALER_LEAST_WORTH_NAIRA = 500_000_000   # an empire worth this much, with a clean record, may be approved as a dealer
ETF_SAMPLE_COVER_BPS = 8_000                 # a sampling fund holds the largest members up to 80% of the index (and at least five)
ETF_FOUNDERS_PREMIUM_BPS = 100               # founders sell to index funds only once the dealers have none, and at 1% above the price
ETF_ROOM_SHORT_BPS = 200                     # new cash goes in only while the dealers can supply all but 2% of the basket
ETF_CASH_TARGET_BPS = 100                    # an index vehicle keeps about 1% in cash for its fee
ETF_SMALL_NAIRA = 50_000_000                 # a player's ETF this small at two quarter ends running (after its first two) is closed
# Passive money: the households put a growing share of their savings into index funds and ETFs.
PASSIVE_START_BPS = 300                      # 3% of the market at the start...
PASSIVE_RISE_BPS_A_YEAR = 300                # ...rising 3% a game year...
PASSIVE_MOST_BPS = 3_500                     # ...to at most 35%
PASSIVE_STEP_BPS = 2_500                     # each quarter the households move a quarter of the gap to their target
PASSIVE_RECORD_ALERT_NAIRA = 1_000_000_000   # money in or out of one vehicle in a quarter above this is news
# The computer's own ETFs: (code, name, index or commodity, leverage, method, fee, seed in naira).
COMPUTER_ETFS = (
    ("TOPX", "Broad Street Top 30 ETF", "TOP30", 10_000, "full", 20, 6_000_000_000),
    ("BNKX", "Broad Street Banks ETF", "BANKS", 10_000, "full", 30, 2_000_000_000),
    ("OGX", "Broad Street Oil & Gas ETF", "OILGAS", 10_000, "full", 35, 1_500_000_000),
    ("DIVX", "Broad Street High Dividend ETF", "DIVIDEND", 10_000, "full", 35, 1_500_000_000),
    ("GBND", "Broad Street Government Bond ETF", "GOVBOND", 10_000, "full", 15, 3_000_000_000),
    ("TOPL", "Broad Street Top 30 2x Daily ETF", "TOP30", 20_000, "swap", 75, 1_000_000_000),
    ("TOPI", "Broad Street Top 30 Inverse Daily ETF", "TOP30", -10_000, "swap", 75, 1_000_000_000),
    ("OILX", "Broad Street Oil ETF", "OIL", 10_000, "swap", 50, 1_000_000_000),
    ("MTLX", "Broad Street Gold & Metals ETF", "METALS", 10_000, "swap", 50, 1_000_000_000),
)
# The computer's own index funds (Part 2's funds, copying an index): (name, index, fee, seed in naira).
COMPUTER_INDEX_FUNDS = (
    ("Broad Street Top 30 Index Fund", "TOP30", 25, 5_000_000_000),
    ("Broad Street Bond Index Fund", "GOVBOND", 20, 3_000_000_000),
)


# ---------------------------------------------------------------------------
# The talent and funds stage, Part 4a: the currency desk and money from abroad
# ---------------------------------------------------------------------------
FX_CURRENCIES = (("USD", "US dollar", "$"), ("GBP", "British pound", "£"), ("EUR", "Euro", "€"))
FX_GBP_USD_START = 1.27                      # dollars for one pound when the desk opens
FX_EUR_USD_START = 1.08                      # dollars for one euro
FX_CROSS_RETURN_BPS = 1_500                  # and each quarter they move 15% of the way back to their usual level
FX_CROSS_SWING_BPS = 300                     # each quarter the pound and the euro move by up to about 3% against the dollar
FX_RESERVES_START_QUARTERS = 2               # the Central Bank opens with two quarters' imports in dollars (its first Eurobonds add more)
FX_OIL_TO_RESERVES_BPS = 6_000               # 60% of oil sold abroad comes back as dollars to the Central Bank
FX_IMPORTS_FROM_RESERVES_BPS = 3_500         # 35% of what companies buy abroad is paid with dollars from the official window
FX_RESERVES_OTHER_BPS = 300                  # money from abroad and back (loans, aid, debts): 3% of the gap to usual reserves a quarter
FX_COMFORT_COVER_BPS = 25_000                # 2.5 quarters of imports: comfortable reserves
FX_DEFEND_COVER_BPS = 20_000                 # the Central Bank defends the naira while it has 2 quarters of imports or more...
FX_DEFEND_GAP_BPS = 500                      # ...once the street is 5% or more above the official rate
FX_DEFEND_MOST_BPS = 1_000                   # it sells at most a tenth of its reserves defending in one quarter
FX_DEVALUE_GAP_BPS = 1_500                   # a gap of 15% with reserves under comfortable: it devalues to the market
FX_FLOAT_COVER_BPS = 10_000                  # reserves under one quarter of imports: it lets the naira float
FX_REPEG_COVER_BPS = 30_000                  # reserves back over three quarters of imports: it manages the rate again
FX_CRAWL_BPS = 2_500                         # a managed rate moves a quarter of the way to the market each quarter
FX_SHORTAGE_PREMIUM_BPS = 400                # the street's extra for each quarter of imports the reserves are short of comfortable
FX_BACKLOG_PREMIUM_BPS = 300                 # and up to 3% more while foreign investors wait for dollars
FX_FLOAT_PREMIUM_BPS = 50                    # a floating naira: the street is barely above the official rate
FX_STREET_NOISE_BPS = 60                     # the street's daily swing
FX_STREET_SPREAD_BPS = 150                   # the street buys 1.5% below its middle rate and sells 1.5% above
FX_STREET_DEPTH_BPS = 1_000                  # a tenth of a quarter's imports bought on the street in a day moves it 1%
FX_STREET_MOST_IMPACT_BPS = 800
FX_STREET_MOST_DEAL_CENTS = 100_000_000      # $1 million in one street deal
FX_WINDOW_DAILY_BPS = 20                     # the official window hands out 0.2% of the reserves at each bell...
FX_WINDOW_LIMIT_PLAYER_CENTS = 5_000_000     # ...a player may have $50,000 from it a quarter
FX_WINDOW_LIMIT_EMPIRE_CENTS = 50_000_000    # ...an empire $500,000
FX_WINDOW_HOLD_EXTRA_BPS = 1_000             # naira held for a request: 10% over the official rate, in case it moves
FX_WINDOW_BUYBACK_BPS = 100                  # the window buys dollars back 1% under the official rate...
FX_WINDOW_KEEP_QUARTERS = 2                  # dollars from the window cannot be sold on the street for two quarters
FX_LEAST_CENTS = 1_000                       # the smallest currency deal: $10
FX_BDC_LICENCE_NAIRA = 25_000_000            # a bureau de change's licence (to the regulator)
FX_BDC_LEAST_CAPITAL_NAIRA = 200_000_000     # and the money its empire must have to open one
FX_BDC_REPORT_CENTS = 1_000_000              # every deal of $10,000 or more is reported to the regulator
FX_BDC_MOST_DEAL_CENTS = 20_000_000          # a bureau deals at most $200,000 at a time
FX_RETAIL_DAILY_BPS = 100                    # households buy and sell about 1% of a quarter's imports a day through the bureaux
FX_RETAIL_TO_PLAYERS_MOST_BPS = 6_000        # players' bureaux win at most 60% of it
FX_REMIT_IMPORTS_BPS = 4_000                 # Nigerians abroad send home about 40% of what the country buys abroad, a quarter
FX_REMIT_FESTIVE = {2: 1.15, 4: 1.35}        # more at Easter and at Christmas
FX_REMIT_CHEAP_BPS = 20_000                  # families abroad send more when the street pays more naira: twice the street premium
FX_REMIT_GROWTH_BPS = 500                    # and 5% more each year
FX_REMIT_LICENCE_NAIRA = 50_000_000
FX_REMIT_COST_PER_FAST_DAY_BPS = 30          # each day faster than five costs a remitter 0.3% of what it carries
FX_COMPUTER_REMITTERS = (("Diaspora Express", 300, 3), ("HomeLink Transfers", 450, 1), ("Kola Remit", 200, 5))
FX_EUROBOND_SPREAD_BPS = 450                 # what Nigeria pays over lending abroad on dollar bonds...
FX_EUROBOND_SHORT_SPREAD_BPS = 150           # ...and more for each quarter of imports its reserves are short of comfortable
FX_EUROBOND_COMPANY_EXTRA_BPS = 150          # a company pays more than the Government
FX_EUROBOND_DISTRESS_BPS = 1_500             # a bond in default is priced at 15% more yield...
FX_EUROBOND_RECOVERY_BPS = 6_000             # ...and on 60% of what it promises
FX_EUROBOND_DEAL_BPS = 50                    # the dealers buy 0.5% below the fair price and sell 0.5% above
FX_EUROBOND_FACE_CENTS = 100_000             # one Eurobond: $1,000
FX_EUROBOND_TERM_QUARTERS = 20
FX_GOVERNMENT_EUROBOND_BPS = 10_000          # the Government borrows a quarter's imports in dollars when its reserves run low
FX_COMPANY_EUROBONDS = (("oil_gas", 3), ("telecoms", 1), ("mining", 2))   # the largest companies of these kinds borrow in dollars (how many)
FX_COMPANY_EUROBOND_SHARE_BPS = 1_000        # each borrows a tenth of a year's sales, in dollars...
FX_COMPANY_EUROBOND_MOST_BPS = 1_500         # ...but at most 15% of a quarter's imports
FX_HEDGE_SHARE_BPS = 3_000                   # companies with dollar debts hedge 30% of a year's interest with currency forwards
FX_EXIT_FROM_RESERVES_BPS = 500              # foreign investors leaving get at most 5% of the reserves a quarter
FX_BACKLOG_TILT_BPS = 200                    # a backlog of a quarter's foreign money makes them 2% keener to sell
SWAP_BANK_FX_SPREAD_BPS = 150                # a bank prices a currency forward 1.5% in its favour
SWAP_MOST_DOLLARS_CENTS = 10_000_000_000     # a currency forward on at most $100 million a quarter

# ---------------------------------------------------------------------------
# The talent and funds stage, Part 4b: foreign markets
# ---------------------------------------------------------------------------
# Real countries and cities; every company, exchange and central bank name is invented.
# The three exchanges: (code, name, city, economy, time zone, currency, opens, closes (their own time), index code, index name).
WORLD_EXCHANGES = (
    ("HSE", "Hudson Stock Exchange", "New York", "US", "America/New_York", "USD", (9, 30), (16, 0), "HUD10", "Hudson 10"),
    ("THX", "Thames Exchange", "London", "UK", "Europe/London", "GBP", (8, 0), (16, 30), "THM10", "Thames 10"),
    ("RMX", "Rhine-Main Exchange", "Frankfurt", "EA", "Europe/Berlin", "EUR", (9, 0), (17, 30), "RMX10", "Rhine-Main 10"),
)
# The three economies: (code, name, central bank, trend growth, inflation target, opening growth, opening inflation,
# opening interest rate, neutral rate above inflation), all a year, in basis points.
WORLD_ECONOMIES = (
    ("US", "the United States", "the Union Reserve", 200, 200, 210, 250, 400, 75),
    ("UK", "the United Kingdom", "the Sterling Monetary Board", 140, 200, 120, 300, 425, 75),
    ("EA", "the euro area", "the Continental Central Bank", 110, 200, 100, 220, 250, 25),
)
WORLD_OIL_WEIGHTS = {"US": 5_000, "EA": 3_000, "UK": 2_000}   # how much each economy's demand counts for the oil price
WORLD_OIL_DEMAND_BPS = 600              # growth a point above trend abroad lifts the next oil price 6%
WORLD_GROWTH_RETURN_BPS = 3_500         # each quarter growth moves 35% of the way back to its trend...
WORLD_GROWTH_SHOCK_BPS = 60             # ...and swings with the world's common force and its own
WORLD_INFLATION_RETURN_BPS = 2_500      # inflation moves a quarter of the way back to its target...
WORLD_INFLATION_HEAT_BPS = 1_500        # ...rises with growth above trend...
WORLD_INFLATION_OIL_BPS = 300           # ...and with dearer oil (a 10% rise adds 0.3 of a point)
WORLD_INFLATION_SHOCK_BPS = 20
WORLD_RATE_STEP_BPS = 25                # central banks move their rates in quarter points...
WORLD_RATE_SPEED_BPS = 4_000            # ...40% of the way to where their rule says each quarter
WORLD_RATE_LIMITS_BPS = (10, 1_200)
WORLD_CROSS_RATE_BPS = 400              # a pound's (or a euro's) interest rate rising a point against the dollar's lifts it 4%
WORLD_CROSS_GROWTH_BPS = 200            # and growth a point faster than America's lifts it 2%

# Kinds of company abroad: (name, extra return investors want over the interest rate, growth they expect for ever), a year.
WORLD_SECTORS = {
    "technology": ("Technology", 300, 250), "pharmaceuticals": ("Medicines", 300, 250), "cars": ("Cars", 650, 100),
    "oil_gas": ("Oil and gas", 650, 50), "banking": ("Banks", 600, 150), "food": ("Food", 350, 200),
    "household": ("Household goods", 330, 200), "mining": ("Mining", 650, 100), "retail": ("Shops", 400, 200),
    "drinks": ("Drinks", 350, 200), "telecoms": ("Telecoms", 500, 150), "insurance": ("Insurance", 500, 150),
    "shipping": ("Shipping", 700, 100), "luxury": ("Luxury goods", 350, 250), "chemicals": ("Chemicals", 550, 150),
    "utilities": ("Power", 400, 150),
}
# The companies: (ticker, name, exchange, city, kind, a quarter's sales (millions), shares (millions), usual profit on sales,
# share of profit paid out, own growth a year, how much it swings with its market (10000 = as much), what it does).
WORLD_COMPANIES = (
    ("TSRN", "Tessarine Software", "HSE", "Seattle", "technology", 20_000, 7_500, 2_600, 2_000, 300, 12_000,
     "Software and cloud computing for businesses and governments."),
    ("MRWD", "Marrowind Devices", "HSE", "San Jose", "technology", 30_000, 15_000, 2_400, 2_500, 150, 12_500,
     "Phones, laptops and the chips inside them."),
    ("QLNT", "Quillon Therapeutics", "HSE", "Boston", "pharmaceuticals", 12_000, 2_500, 2_200, 4_500, 100, 7_000,
     "Medicines for heart disease, cancer and diabetes."),
    ("OSTM", "Ostrander Motors", "HSE", "Detroit", "cars", 45_000, 1_400, 600, 3_000, -50, 14_000,
     "Cars, trucks and electric vehicles."),
    ("MSQR", "Mesquite Ridge Oil", "HSE", "Houston", "oil_gas", 60_000, 4_000, 1_100, 4_500, -100, 9_000,
     "Oil and gas from Texas to West Africa."),
    ("LDGR", "Ledgerline Bank", "HSE", "New York", "banking", 40_000, 3_000, 2_500, 3_000, 0, 11_000,
     "Lending, savings and investment banking."),
    ("PRHF", "Prairie Harvest Foods", "HSE", "Chicago", "food", 15_000, 2_000, 1_200, 5_000, 0, 6_000,
     "Cereals, snacks and frozen meals."),
    ("HLGR", "Hollis & Grant", "HSE", "Cincinnati", "household", 21_000, 2_400, 1_800, 6_000, 50, 5_500,
     "Soap, nappies, toothpaste and razors, sold in 180 countries."),
    ("CPFM", "Copperfield Mining", "HSE", "Denver", "mining", 7_000, 1_500, 1_800, 4_000, 0, 13_000,
     "Copper, gold and lithium mines."),
    ("WBRK", "Westbrook Retail", "HSE", "Bentonville", "retail", 160_000, 2_700, 350, 3_500, 100, 8_000,
     "Supermarkets and online shopping across the country."),
    ("HRWB", "Harrowgate Brewers", "THX", "London", "drinks", 4_500, 2_300, 2_800, 5_500, 0, 7_000,
     "Beers, stouts and spirits, with breweries in Africa and Asia."),
    ("MRTA", "Meridian Telecom Africa", "THX", "London", "telecoms", 1_100, 3_700, 2_000, 4_500, 200, 9_500,
     "Mobile phone networks and mobile money in fourteen African countries."),
    ("CRMR", "Crownmoor Energy", "THX", "London", "oil_gas", 50_000, 15_000, 900, 4_500, -100, 9_500,
     "Oil and gas from the North Sea to the Gulf of Guinea."),
    ("ASHD", "Ashdown Pharma", "THX", "Cambridge", "pharmaceuticals", 8_000, 4_000, 2_200, 5_000, 50, 7_000,
     "Vaccines and medicines."),
    ("SLTM", "Saltmarsh Bank", "THX", "London", "banking", 7_000, 16_000, 2_600, 4_000, 0, 11_500,
     "A bank for households and companies across Britain."),
    ("PNNT", "Pennant Insurance", "THX", "Edinburgh", "insurance", 6_000, 2_500, 1_100, 6_000, 0, 9_000,
     "Life insurance, pensions and savings."),
    ("WXCM", "Wexcombe Mining", "THX", "London", "mining", 14_000, 1_700, 2_200, 5_500, 0, 13_000,
     "Iron ore, copper and aluminium."),
    ("HRTW", "Hartwell Stores", "THX", "Leeds", "retail", 17_000, 7_000, 400, 5_000, 0, 8_000,
     "Supermarkets on Britain's high streets."),
    ("TYNS", "Tyneside Shipping", "THX", "Newcastle", "shipping", 2_500, 900, 1_500, 5_000, 0, 14_000,
     "Container ships between Europe, Africa and Asia."),
    ("ELSM", "Ellesmere & Co", "THX", "London", "luxury", 800, 380, 1_700, 4_000, 300, 12_000,
     "Coats, leather goods and fashion."),
    ("RHWM", "Rheinwerk Motoren", "RMX", "Stuttgart", "cars", 38_000, 1_000, 800, 3_500, 0, 13_500,
     "Luxury cars, vans and trucks."),
    ("KLTC", "Kaltenbach Chemie", "RMX", "Ludwigshafen", "chemicals", 17_000, 900, 900, 5_000, 0, 12_000,
     "Chemicals, plastics and fertiliser."),
    ("SNEN", "Seine Energies", "RMX", "Paris", "oil_gas", 50_000, 2_300, 1_100, 5_000, -100, 9_000,
     "Oil, gas, solar and wind power in 130 countries."),
    ("PLDG", "Polder Dairy Group", "RMX", "Amsterdam", "food", 3_300, 800, 1_200, 5_500, 50, 6_000,
     "Milk, cheese and baby food, made in the Netherlands and across Africa."),
    ("VCLX", "Vauclair Luxe", "RMX", "Paris", "luxury", 21_000, 500, 2_400, 5_000, 300, 12_000,
     "Handbags, perfume, watches and champagne."),
    ("HNSF", "Hanseatic Freight", "RMX", "Hamburg", "shipping", 5_000, 175, 1_200, 4_500, 0, 14_000,
     "Container shipping and ports."),
    ("BRNB", "Brenner Bank", "RMX", "Frankfurt", "banking", 7_000, 2_000, 2_200, 3_500, 0, 12_000,
     "Lending and investment banking across Europe."),
    ("LMRA", "Lumora Pharma", "RMX", "Milan", "pharmaceuticals", 5_000, 1_200, 2_000, 4_500, 100, 7_000,
     "Medicines and vaccines."),
    ("ISRT", "Isar Technik", "RMX", "Munich", "technology", 9_000, 1_200, 2_300, 3_000, 250, 12_000,
     "Software that runs factories, banks and shops."),
    ("TGSP", "Tagus Power", "RMX", "Madrid", "utilities", 12_000, 6_500, 1_300, 6_500, 50, 6_000,
     "Electricity from wind, sun and water in Spain and Portugal."),
)
# Nigerian companies whose founders' stake belongs to a company listed abroad: (Nigerian ticker, parent's ticker).
WORLD_ARMS = (("AHP", "HLGR"), ("TMB", "HRWB"), ("SGN", "MRTA"), ("DCG", "SNEN"), ("AYD", "PLDG"))
# The computer's ETFs of foreign shares on the Broad Street Exchange: (code, name, index, fee, households' first money in naira).
WORLD_ETFS = (
    ("HUDX", "Broad Street Hudson 10 ETF", "HUD10", 50, 1_500_000_000),
    ("THMX", "Broad Street Thames 10 ETF", "THM10", 50, 1_000_000_000),
    ("RMXX", "Broad Street Rhine-Main 10 ETF", "RMX10", 50, 1_000_000_000),
)
WORLD_STEP_MINUTES = 10                 # prices abroad move every ten minutes while an exchange is open
WORLD_MARKET_DAY_BPS = 220              # a market's typical move in a day...
WORLD_OWN_DAY_BPS = 250                 # ...and a company's own, on top
WORLD_OVERNIGHT_SHARE_BPS = 4_000       # 40% of a day's move happens overnight (seen at the open)
WORLD_FAIR_PULL_BPS = 500               # each day a price closes 5% of the way to what the share is worth
WORLD_NEWS_PRICED_BPS = 8_000           # a quarter's results move the price 80% of the way at once (logarithmically)
WORLD_REVENUE_SWING_BPS = 150           # a quarter's sales swing about 1.5% by themselves
WORLD_MARGIN_SWING_BPS = 120
WORLD_EARNINGS_YIELD_LIMITS_BPS = (250, 2_000)   # a share is never priced above 40 or below 5 times its profit
WORLD_SPREAD_BPS = 15                   # the brokers abroad buy 0.15% below the price and sell 0.15% above
WORLD_IMPACT_TIMES = 10                 # a deal worth 0.01% of a company moves its price 0.1%
WORLD_MOST_DEAL_CENTS = 200_000_000     # at most $2 million (or its worth) in one deal
WORLD_DAY_MOST_SHARES_BPS = 10          # and at most 0.1% of a company's shares a day, for each account
WORLD_WITHHOLDING_BPS = 1_500           # 15% of a dividend is kept as tax abroad
WORLD_ETF_DEAL_BPS = 50                 # an ETF of foreign shares changes its naira at 0.5% either side of the street's middle rate
WORLD_ETF_CASH_FEE_BPS = 75             # and charges 0.75% for units made or unmade against cash (only cash, never a basket)
WORLD_HOUSEHOLD_SHARE_BPS = 300         # households want 3% of what they hold in index vehicles in ETFs of foreign shares...
WORLD_HOUSEHOLD_PREMIUM_TIMES = 5       # ...more when the street's premium is high (5 times it)...
WORLD_HOUSEHOLD_STEP_BPS = 2_500        # ...and move a quarter of the way there each quarter
WORLD_PARENT_ROOM_BPS = 600             # parents abroad may send home at most 6% of the reserves a quarter, between them...
WORLD_PARENT_TRAPPED_YEARS = 2          # ...two years' dividends stuck here, or...
WORLD_PARENT_NAIRA_FALL_BPS = 4_000     # ...the naira 40% weaker than two years ago, is a reason to leave...
WORLD_PARENT_LEAVE_CHANCE_BPS = 1_500   # ...and in each quarter with a reason there is a 15% chance the parent decides to go
WORLD_PARENT_SALE_QUARTERS = 2          # it sells for two quarters; what is left goes to the pension funds
WORLD_PARENT_ASKING_BPS = 0             # empires may buy pieces of its stake at the market price (never below: that would be free money)
WORLD_PARENT_FINAL_BPS = 2_000          # the pension funds take the rest at 20% below

# ---------------------------------------------------------------------------
# Stage 11: the courts, as a docket
# ---------------------------------------------------------------------------
COURT_REGULATOR_START_NAIRA = 250_000_000   # the Government's first budget for the market regulator
COURT_CASE_COST_NAIRA = 5_000_000           # what it costs the regulator to prove one case (paid to the Treasury)
COURT_MIN_CLAIM_NAIRA = 100_000             # a claim worth less than this is not worth a case
COURT_BOND_BPS = 1_000                      # a player bringing a case posts a tenth of the claim...
COURT_BOND_FLOOR_NAIRA = 1_000_000          # ...but never less than ₦1 million
COURT_SETTLE_BPS = 6_000                    # settling costs six tenths of the claim, paid at once
COURT_FINE_BPS = {"insider": 10_000, "manipulation": 1_000, "undisclosed_stake": 5_000, "naked_short": 5_000, "insurance_fraud": 10_000}
COURT_COSTS_BPS = 500                       # the loser pays a twentieth of the claim as the winner's costs
COURT_BAN_QUARTERS = {"manipulation": 4, "naked_short": 4, "insurance_fraud": 4}   # a judgment that bans trading, and for how long
COURT_ENFORCE_BPS = {"insider": 2_500, "manipulation": 2_000, "undisclosed_stake": 3_000, "naked_short": 2_500, "insurance_fraud": 2_500}
COURT_FINE_TO_REGULATOR_BPS = 5_000         # half of every fine funds the regulator; the rest goes to the Treasury
COURT_PAYMENT_BPS = 2_500                   # a judgment is paid down a quarter at a time, as much as the defendant has
COURT_REPUTATION = 5                        # a judgment costs the defendant five points of reputation
COURT_WINDOW_QUARTERS = 8                   # a wrong is looked at for two years after it is recorded
COURT_WASH_TRADES = 3                       # this many trades with itself in a quarter is a pattern
COURT_RAMP_BUYS = 3                         # this many buys before sales into the rise is a ramp
COURT_STAKE_STEP_BPS = 500                  # every 5% step in a listed company must be made public
COURT_SHORT_PREMIUM_BPS = 500               # a forced buy-in costs 5% above the close (the same as the buy-in itself)
