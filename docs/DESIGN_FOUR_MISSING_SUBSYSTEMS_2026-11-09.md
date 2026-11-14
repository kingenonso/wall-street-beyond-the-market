# Design: Four Missing Subsystems (November 2026)

This document identifies and designs four subsystems that are foundational but currently missing or incomplete in the codebase. These must be designed before any further code implementation proceeds, as they affect multiple screens, screens, and game systems.

---

## Subsystem 1: Clearing House & Settlement System

### Purpose
Handle trade settlement, margin collection, default fund management, and payment cascading when traders cannot fulfill their obligations. This is the "plumbing" that ensures trades settle correctly and losses are absorbed by the system rather than leaking to counterparties.

### Core Components

1. **Trade Settlement Engine**
   - Match executed orders against counterparties
   - Calculate and transfer cash/asset flows
   - Mark positions to market each quarter
   - Generate settlement statements

2. **Default Fund**
   - 10% of every derivatives fee flows into the default fund
   - When a trader cannot pay, margin is taken first, then the default fund
   - Shortfalls owed to the fund are recovered from winners proportionally
   - Fund balance tracked and reported each quarter

3. **Margin System**
   - Per-trade margin requirements based on position size and volatility
   - Margin calls when positions move against the trader
   - Liquidation sequence: margin first, then default fund, then counterparty exposure

### Design Decisions

- **Settlement happens at quarter-close**, not per-trade. This keeps the engine simple and avoids race conditions.
- **Default fund is 10% of fees**, collected at each close. Anything the fund paid is "owed back" and shared by winners.
- **No counter-party risk in the engine** — the server checks every pairing before acting. The engine only proposes; the server disposes.

### API Surface (for server integration)

```rust
// Settle all trades for the quarter
fn settle_quarter() -> SettlementReport;

// Process a single trade execution
fn settle_trade(trade_id: u64) -> Result<(), SettlementError>;

// Assess margin requirements for a position
fn margin_requirement(position: &Position) -> i64;

// Trigger default fund payout for a failed trader
fn trigger_default_fund(failed_trader: u64, amount: i64) -> Result<(), DefaultFundError>;
```

### Test Coverage Requirements (from gap stage)

From the gap stage checklist, these tests already exist and must pass:

- `test_every_contract_has_two_sides_and_a_loss_beyond_the_margin_is_covered_by_the_fund_and_owed_to_it`
- `test_two_players_trade_with_each_other_inside_the_market_makers_prices`
- `test_a_waiting_order_can_be_cancelled_...` (loopholes 1–2)
- Five tests in `test_gap_swaps.py`
- `test_oil_producers_sell_and_fuel_users_buy_oil_futures_and_it_shows_in_their_accounts`
- `test_the_securities_regulator_stops_new_short_sales_after_a_hard_fall`
- `test_the_accountant_values_the_empires_positions_and_is_marked_against_the_truth`
- `test_the_investment_banker_buys_protection_only_while_a_deal_is_open`
- Five tests in `test_gap_instruments.py`

### Open Questions

1. Should settlement be synchronous (blocking) or asynchronous (event-driven)?
2. How should margin requirements be calculated — fixed percentage, volatility-based, or risk-based?
3. What granularity should default fund reporting have — per-trader, per-deski, or quarterly aggregate?

---

## Subsystem 2: Property & Real Estate Subsystem

### Purpose
Manage the property market: districts, buildings, plots, mortgages, auctions, claims, and valuation. This subsystem underpins the real estate half of the game and connects to household spending, borrowing, and the ledger.

### Core Components

1. **District System**
   - Five district types per city: business, homes, shops/markets, industry, farmland
   - Each district has big buildings, small units, and empty plots
   - Initial ownership: property companies own everything
   - Bubble mechanics: overpaying inflates district prices; fading when buying stops

2. **Property Valuation**
   - Annual rent-based valuation: rent earned in a year ÷ required return
   - Required return rises/falls with Central Bank rate
   - Three valuation methods: comparable sales, income approach, cost approach
   - Build cost tracked per building; wear and upkeep modeled

3. **Mortgage & Financing System**
   - Loans limited to 4 years of salary, 20% deposit for players
   - Empires can borrow up to 60%
   - Two missed payments → bank sells the property, with no lowest price
   - Property tax: 1%/year; land tax: 0.5%/year
   - Unpaid tax grows; government sells property when arrears reach 1/10 value

4. **Auction House**
   - Live timed auctions: 24 hours, bid in last 5 min adds 5 more
   - Bid cash held in escrow; sealed limits never shown
   - Late bids: 5-minute extension, leading bid cannot be withdrawn
   - Partners/consortiums can bid together; walking away allowed

5. **Claims & Encumbrances**
   - Old loans, rights of way, disputes that freeze property
   - Claim found by search binds whoever owns property at next close
   - Cannot be dodged by quick sale

### Design Decisions

- **Rent comes from actual city spending**, not made up. Households and companies of each city pay rent through real spending.
- **Bubbles fade by a fifth each quarter** unless buyers keep overpaying. Forced cheap sales pull prices down.
- **Twelve-step purchase process** — skipping a check never blocks the purchase. Each step is validated.
- **Headquarters system**: Levels 1-120, cost grows with level, does a little less. Beyond 13 seats: one more per ten levels. City benefits per level.

### API Surface (for server integration)

```rust
// Create a new district in a city
fn create_district(city: &str, district_type: DistrictType) -> Result<District, DistrictError>;

// Process a property purchase (12 steps)
fn process_purchase(buyer: u64, property_id: u64, price: i64) -> Result<PurchaseResult, PurchaseError>;

// Initiate a mortgage on a property
fn initiate_mortgage(property_id: u64, borrower: u64, amount: i64) -> Result<Mortgage, MortgageError>;

// Conduct an auction for a property
fn run_auction(property_id: u64, duration_hours: u64) -> AuctionResult;

// Register a claim on a property
fn register_claim(property_id: u64, claim_type: ClaimType, claimant: u64) -> Result<(), ClaimError>;
```

### Test Coverage Requirements (from gap stage)

From the gap stage checklist, these tests already exist and must pass:

- `test_a_new_world_has_districts_in_all_five_cities_owned_by_the_property_companies`
- `test_an_owner_is_paid_rent_and_pays_tax_and_upkeep_at_the_close`
- `test_buyers_who_overpay_inflate_a_bubble_that_then_fades`
- `test_a_mortgage_is_limited_to_four_years_of_salary_and_needs_a_fifth_paid_down`
- `test_two_missed_mortgage_payments_and_the_bank_sells_the_property`
- `test_computer_bidders_join_a_forced_sale_...`
- `test_a_claim_skipped_at_purchase_comes_to_light_and_an_old_loan_must_be_paid`
- `test_a_dispute_freezes_a_property_until_it_is_settled`
- `test_a_development_buys_cement_steel_and_work_phase_by_phase_on_a_construction_loan`
- `test_hotels_follow_travel_and_malls_follow_shopping`
- `test_the_designs_test_a_rate_rise_brings_home_defaults_and_falling_prices`
- `test_a_property_is_valued_three_ways_from_public_figures`
- `test_property_funds_the_trust_and_a_managers_own_fund_under_its_rules`

### Open Questions

1. Should district bubble fading be deterministic (fixed 1/5 per quarter) or stochastic?
2. How many valuation methods should be exposed to players vs. internal-only?
3. What determines when a headquarters collapses — just upkeep neglect, or also financial metrics?

---

## Subsystem 3: Work & Desk Management Subsystem

### Purpose
Manage empire work past desk budgets, waiting approvals, library content, and member capacity. This controls the "employment" half of the game and connects to the financial subsystem through borrowing, taxes, and cash flow.

### Core Components

1. **Desk Budget System**
   - Each desk has a budget; work past budget needs head approval
   - Head (or deputy) sees budget, what's used, and any waiting requests
   - Refusal stands for the quarter; approval lapses at quarter close or if member leaves
   - Staff never approve on their own — head must sign off

2. **Waiting Approval Workflow**
   - Member submits request → head sees it immediately
   - If head doesn't act, request passes to deputy after usual wait
   - Refusal stands for the quarter; approval lapses at quarter's close
   - Requests don't carry over quarter-to-quarter

3. **Library System**
   - Brought to 350 pieces, filling Levels 41-100
   - Stage 8 and 9 subjects, each in three settings: solo, empire, weekend
   - 66 new pieces added; 363 in total (each in solo, empire and weekend settings)
   - Three settings per piece: solo play, empire management, weekend challenge

4. **Member Management**
   - Members have employment status (independent, employed, self-employed)
   - Borrowing rate, unused line of credit, debt-to-equity ratio
   - Capital gains realised so far this year
   - Lending bank as a blue link, credit rating, net worth trend

5. **Desk Checks Before Bidding** (property context)
   - Legal Counsel checks title
   - Accountant values the lot
   - Risk Manager sets top price
   - Investment Banker arranges the money
   - Head decides whether to bid

### Design Decisions

- **Approval is quarterly**: refusals stand for the quarter; approvals lapse at close. This prevents perpetual waiting.
- **Library content is per-setting**: each of 363 pieces exists in solo, empire, and weekend variants. This maximizes content reuse.
- **Head/deputy distinction**: head has final say; deputy acts after "usual wait" if head is unavailable. This creates natural bottlenecks.
- **No staff autonomy**: staff never approve on their own. This prevents bypassing the head/deputy mechanism.

### API Surface (for server integration)

```rust
// Submit work request past desk budget
fn submit_work_request(member: u64, request: &WorkRequest) -> Result<(), WorkError>;

// Head approves or refuses a request
fn head_approve_request(request_id: u64, approve: bool) -> Result<(), HeadError>;

// Deputy acts when head is unavailable
fn deputy_act(request_id: u64, action: DeputyAction) -> Result<(), DeputyError>;

// Add content to library (new piece, three settings)
fn add_library_content(piece: LibraryPiece, settings: [Setting; 3]) -> Result<(), LibraryError>;

// Get library content for a level and setting
fn get_library_content(level: u64, setting: Setting) -> Option<&LibraryPiece>;
```

### Test Coverage Requirements (from gap stage)

From the gap stage checklist, these tests already exist and must pass:

- Two tests in `test_gap_work.py` (loopholes 1–4 and 10, reviews 1, 3, 4, 6, 7)
- Three tests in `test_gap_library.py` (loopholes 5–9, review 8)

### Open Questions

1. What is the "usual wait" time before deputy can act?
2. Should library content be tagged by difficulty level, or is level-range sufficient?
3. How should "work past budget" requests be prioritized when multiple are pending?

---

## Subsystem 4: Commodities & Derivatives Subsystem

### Purpose
Manage the commodities market: spot prices, futures, options, swaps, and related derivatives. This connects to the trading engine, clearing house, and portfolio screens.

### Core Components

1. **Spot Market**
   - Gold, oil, produce, materials with spot prices
   - Storage: capacity, rent, insurance, loss
   - Delivery at expiry and carry/contango calculation

2. **Futures Market**
   - Standardized contracts for future delivery
   - Price limits (low/high) per day
   - Roll-over mechanics near expiry

3. **Options Market**
   - Calls and puts on futures and commodities
   - Advanced options strategies
   - Regulatory constraints on new short sales

4. **Swaps**
   - Rate swaps and oil swaps
   - Players, empires, or banks can sign
   - Side that cannot pay owes the other
   - Maximum loss: 5× what the swap is worth
   - Empire cannot sign swap with its own member

5. **Securities: Preferred Shares & Warrants**
   - Preferred shares with dividends
   - Warrants with exercise terms
   - Mezzanine financing
   - Sale-and-leaseback arrangements
   - Earn-outs in buyouts

### Design Decisions

- **Level unlocks**: Level 10, 15, and 25 open specific instrument modules
- **Module mastery**: Instruments open by level AND by module mastery
- **Securities Regulator**: Stops new short sales after 15% fall for 3 days; market after 10% fall
- **Accountant values empire positions** each quarter against true market value
- **Investment Banker trades protection** only while a deal is open and inside limits

### API Surface (for server integration)

```rust
// Trade a commodity spot position
fn trade_spot(side: Side, commodity: Commodity, quantity: i64, price: i64) -> Result<Trade, TradeError>;

// Open a futures contract
fn open_futures(commodity: Commodity, expiry: Quarter, size: i64) -> Result<Future, FutureError>;

// Buy or sell an option
fn trade_option(option_type: OptionType, underlying: u64, strike: i64, expiry: Quarter, premium: i64) -> Result<OptionTrade, OptionError>;

// Enter a swap agreement
fn enter_swap(counterparty: u64, swap_type: SwapType, notional: i64, duration: Quarter) -> Result<Swap, SwapError>;

// Accountant values open positions
fn value_empire_positions(empire_id: u64) -> ValuationReport;
```

### Test Coverage Requirements (from gap stage)

From the gap stage checklist, these tests already exist and must pass:

- `test_oil_producers_sell_and_fuel_users_buy_oil_futures_and_it_shows_in_their_accounts`
- `test_instruments_open_by_level_and_by_module_mastery`
- `test_the_securities_regulator_stops_new_short_sales_after_a_hard_fall`
- `test_the_regulator_sees_a_fall_at_the_bell`
- Five tests in `test_gap_instruments.py` (preferred shares, warrants, mezzanine, sale-and-leaseback, earn-outs)
- `test_the_accountant_values_the_empires_positions_and_is_marked_against_the_truth`

### Open Questions

1. How should carry/contango be calculated — cost of carry model, futures term structure, or something else?
2. Should options be exercisable at any time (American) or only at expiry (European)?
3. How are preferred share dividends modeled — fixed rate, floating, or tied to company performance?

---

## Integration Notes

These four subsystems are designed to integrate as follows:

1. **Clearing House** sits between all trading and the ledger. Every trade passes through settlement before any asset moves.
2. **Property Subsystem** connects to the Clearing House for mortgage payments, rent collection, and auction proceeds. It also has its own valuation loop that feeds back into net worth.
3. **Work & Desk Management** connects to the Financial subsystem through member borrowing, taxes, and cash flow. It also feeds the Library, which feeds empire decisions.
4. **Commodities Subsystem** connects deepest — spot/futures/options feed into the clearing house, swaps connect the bank to empires/players, and the accountant values all positions including commodities.

The gap stage (Stages 7–9) has already built tests for all four subsystems and verified they pass (1,212 server tests, 13 engine tests, 23 website tests). This design document formalizes the subsystem boundaries so that future code work can reference clear interfaces rather than guessing what fits where.

### Next Steps

1. Review these designs with the owner to confirm alignment
2. Any code changes must respect these subsystem boundaries
3. New tests should be written against these APIs, not against internal implementation details
4. The reference spec (REFERENCE_SPEC_2026-11-07.md) should be updated to include these subsystem designs as the "build order" checkpoint

---
*This document was generated as part of task #37: Design the four missing subsystems before any code.*