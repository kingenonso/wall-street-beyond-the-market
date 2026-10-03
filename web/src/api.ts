// Every conversation between the website and the server goes through this file.
// The website only asks. The server decides.

/** Money: a whole number of kobo, sent as text so that very large amounts stay exact. */
export type Kobo = string;

export type Money = { amount_kobo: Kobo; currency: string };
export type ProfileIcon = "male" | "female";

export type Player = {
  id: string;
  display_name: string;
  reputation: number;
  profile_icon: ProfileIcon | null;
  cash: Money;
  /** Stage 5. All null until a build is chosen. */
  build: BuildCode | null;
  build_name: string | null;
  accent: string | null;
  level: number | null;
  employer: string | null;
};

export type BuildCode = "asset_manager" | "accountant" | "investment_banker" | "risk_manager" | "lawyer" | "journalist";
export type BuildInfo = {
  code: BuildCode; name: string; accent: string; track: string; work: string; earns: string; cannot: string; employer_words: string;
};
export type Payslip = {
  period_label: string; employer: string; level: number; days_worked: number; worked: boolean;
  gross_kobo: Kobo; pension_yours_kobo: Kobo; pension_employer_kobo: Kobo; tax_kobo: Kobo; living_costs_kobo: Kobo;
  take_home_kobo: Kobo; paid_kobo: Kobo; owed_kobo: Kobo; note: string;
};
export type PensionFund = {
  code: "growth" | "balanced" | "cautious" | "income"; name: string; who_for: string;
  shares_bps: number; bonds_bps: number; cash_bps: number; last_return_bps: number | null;
};
export type Career = {
  build: BuildCode | null;
  builds: BuildInfo[];
  later_builds: string[];
  reputation: number;
  can_change_build_at: string | null;
  career: null | {
    build: BuildCode; build_name: string; accent: string; track: string; level: number; level_words: string;
    experience: number; level_floor: number; next_level_at: number | null; at_cap: boolean; review_open: boolean;
    review: null | { opened_at: string; finished: number; passes: number; why: string; how_to_recover: string };
    other_builds: { build: string; name: string; level: number }[];
  };
  job: null | { ticker: string; name: string; headquarters: string; since: string; can_move: boolean; owed_kobo: Kobo };
  bank: null | { ticker: string; name: string; since: string; savings_rate_bps: number; can_move: boolean };
  pay: null | {
    gross_kobo: Kobo; pension_yours_kobo: Kobo; pension_employer_kobo: Kobo; tax_kobo: Kobo; living_costs_kobo: Kobo;
    take_home_kobo: Kobo; at_next_level_kobo: Kobo; worked_this_quarter: boolean;
  };
  payslips: Payslip[];
  interest: { period_label: string; bank: string; lowest_balance_kobo: Kobo; rate_bps: number; amount_kobo: Kobo }[];
  retirement: null | {
    fund: PensionFund["code"]; value_kobo: Kobo; can_change: boolean; funds: PensionFund[];
    entries: { period_label: string; fund: string; opening_kobo: Kobo; growth_kobo: Kobo; paid_in_by_you_kobo: Kobo;
               paid_in_by_employer_kobo: Kobo; closing_kobo: Kobo }[];
  };
  events: { kind: string; words: string; at: string }[];
  next_pay_day: string | null;
};
export type Opening = {
  ticker: string; name: string; sector: string; headquarters: string; rating: string | null; places_left: number;
  behind_on_bills: boolean; gross_kobo: Kobo; take_home_kobo: Kobo; yours: boolean;
};
export type PlayerBank = { ticker: string; name: string; headquarters: string; rating: string | null; savings_rate_bps: number; yours: boolean };

export type ObjectiveField =
  | { key: string; label: string; kind: "millions" | "percent" | "times" | "ticker" }
  | { key: string; label: string; kind: "choice"; options: { code: string; label: string }[] }
  | { key: string; label: string; kind: "classify"; options: { code: string; label: string }[];
      items: { key: string; label: string; kobo: Kobo }[] };
export type Milestone = { label: string; points: number; earned: boolean };
export type Objective = {
  id: number; template: string; module: string; title: string; kind: "hand_in" | "market"; idea: string;
  terms: {
    client?: { ticker: string; name: string }; situation: string; task: string[]; pass_when: string; deadline: string;
    given: { label: string; kobo?: Kobo; text?: string }[]; fields: ObjectiveField[]; notes?: string[];
  };
  reward_kobo: Kobo; experience: number; payer: string; accepted_at: string;
  state: "active" | "passed" | "failed" | "not_done" | "withdrawn";
  progress: Record<string, unknown>;
  submission: Record<string, unknown> | null; submitted_at: string | null;
  result: null | {
    summary: string; score: number; milestones: Milestone[]; debrief: { plain: string; method: string; maths: string };
    answers?: Record<string, unknown>; payment_note?: string;
  };
  judged_at: string | null; paid_kobo: Kobo; can_hand_in: boolean;
};
export type ObjectiveOffer = {
  template: string; module: string; title: string; idea: string; kind: "hand_in" | "market"; level: number; reward_kobo: Kobo;
  experience: number; available: boolean; why_not: string | null; payer: string | null;
  client: { ticker: string; name: string } | null; situation: string | null; pass_when: string | null; deadline: string | null;
  practise_again: boolean;
};
export type Skill = {
  module: string; title: string; idea: string; level: number; open: boolean; stage: string; passes: number; finished: number;
  practise_again: boolean;
};
export type ObjectiveBoard = {
  ready: boolean; why: string | null; active: Objective[]; offers: ObjectiveOffer[]; finished: Objective[]; skills: Skill[];
  coverage: { learned: number; modules: number }; limit: number;
};
export type Slice = { label: string; group: "shares" | "bonds" | "cash"; value_kobo: Kobo; share_bps: number };
export type AssetDesk = {
  total_kobo: Kobo; cash_kobo: Kobo; shares_kobo: Kobo; bonds_kobo: Kobo; change_today_bps: number | null;
  change_year_bps: number | null; index_change_year_bps: number | null; allocation: Slice[]; sectors: Slice[];
  largest_bps: number; companies_held: number; industries_held: number; retirement_kobo: Kobo;
};
export type StatementQuarter = {
  period: number; period_label: string; credit_rating: string; income_statement: Record<string, Kobo>;
  cash_flow: Record<string, Kobo>; balance_sheet: Record<string, Kobo>; notes: string[];
  ratios: Record<string, number | null>; tax_owed_kobo: Kobo; staff: number | null;
};
export type AccountantDesk = {
  ticker: string; name: string; sector: string; is_employer: boolean; quarters: StatementQuarter[];
  companies: { ticker: string; name: string; sector: string }[];
  watch: { ticker: string; name: string; credit_rating: string; unpaid_bills_kobo: Kobo; overdue_debt_kobo: Kobo; cash_kobo: Kobo }[];
  tax_rate_bps: number;
};

export type Movement = {
  at: string;
  kind: string;
  memo: string;
  counterparty: string;
  amount_kobo: Kobo;
  currency: string;
};

export type MarketState = "opening_auction" | "open" | "closed";

export type Clock = {
  lagos_time: string;
  market_state: MarketState;
  next_state: MarketState;
  next_change_at: string;
  world_started: boolean;
  game_date: { year: number; quarter: number; day_of_quarter: number } | null;
  test_weeks_ahead: number;
  closing_rush: boolean;
};

export type WorldStatus = { companies: number; last_closed_period: number; last_closed_label: string | null };

export type CompanySummary = {
  ticker: string;
  name: string;
  headquarters: string;
  period: number;
  period_label: string;
  credit_rating: string;
  revenue_kobo: Kobo;
  ebitda_kobo: Kobo;
  net_profit_kobo: Kobo;
  total_assets_kobo: Kobo;
  revenue_change_bps: number | null;
};

export type Sector = { code: string; name: string; companies: CompanySummary[] };

export type Borrowing = {
  name: string;
  kind: "bank_loan" | "bond";
  lender: string;
  principal_outstanding: Kobo;
  annual_rate_bps: number;
  maturity_period: number;
  repayment: "amortising" | "bullet";
};

export type Figures = {
  income_statement: Record<string, Kobo>;
  cash_flow: Record<string, Kobo>;
  balance_sheet: Record<string, Kobo>;
  notes: {
    shares_in_issue: Kobo;
    principal_overdue: Kobo;
    borrowings: Borrowing[];
    why_revenue: string[];
    management_notes: string[];
    /** Present from Stage 3. */
    sales_to?: { households: Kobo; other_companies: Kobo; government: Kobo };
    staff?: number;
    wages?: Kobo;
  };
};

export type FiledReport = {
  period: number;
  period_label: string;
  version: number;
  amended: boolean;
  filed_by: string;
  filed_at: string;
  credit_rating: string;
  rating_reasons: string[];
  figures: Figures;
};

export type Company = {
  ticker: string;
  name: string;
  sector: string;
  headquarters: string;
  shares_in_issue: Kobo;
  owners: { name: string; shares: Kobo; share_bps: number }[];
  reports: FiledReport[];
  location: { running_cost_bps: number; reasons: string[] } | null;
  buys_from: { sector: string; share_bps: number }[];
};

export type HouseholdGroup = {
  location: string;
  population_bps: number;
  income_kobo: Kobo;
  wages_kobo: Kobo;
  government_kobo: Kobo;
  pensions_kobo: Kobo;
  spending_kobo: Kobo;
  savings_kobo: Kobo;
  claims_kobo: Kobo;
  debt_kobo: Kobo;
  jobs: number;
  income_change_bps: number | null;
  jobs_change_bps: number | null;
};

export type Economy = {
  period: number;
  period_label: string | null;
  money_in_existence_kobo: Kobo;
  households: HouseholdGroup[];
  money: { holder: string; amount_kobo: Kobo; share_bps: number }[];
  history: {
    period: number;
    period_label: string;
    company_sales_kobo: Kobo;
    household_income_kobo: Kobo;
    household_spending_kobo: Kobo;
    jobs: number;
  }[];
  household_spending: { sector: string; share_bps: number }[];
  prices: PricesAndRates | null;
  macro_history: { period: number; period_label: string; inflation_bps: number; policy_rate_bps: number; money_kobo: Kobo }[];
  money_watch: MoneyWatch | null;
};

export type PricesAndRates = {
  inflation_bps: number;
  inflation_target_bps: number;
  inflation_low_bps: number;
  inflation_high_bps: number;
  price_index_bps: number;
  wage_index_bps: number;
  policy_rate_bps: number;
  previous_rate_bps: number;
  rate_reason: string;
  household_loan_rate_bps: number;
  confidence_bps: number;
  demand_gap_bps: number;
  household_debt_kobo: Kobo;
  central_bank_lending_kobo: Kobo;
  commodities: { name: string; index_bps: number; change_bps: number | null }[];
};

export type MoneyWatch = {
  reading: "green" | "amber" | "red";
  reasons: string[];
  action: string;
  money_growth_bps: number;
  output_growth_bps: number;
};

export type NewsItem = {
  period: number;
  period_label: string;
  day: number;
  outlet: string;
  kind: string;
  story: string;
  importance: number;
  headline: string;
  body: string;
  tickers: string[];
  locations: string[];
};

export type News = { outlets: string[]; items: NewsItem[] };

export type PriceLevel = { price_kobo: Kobo; quantity: number; orders: number };
export type PublicTrade = { price_kobo: Kobo; quantity: number; in_auction: boolean; traded_at: string };

/** What everybody may see of one share on the exchange. */
export type Quote = {
  ticker: string;
  name: string;
  market_state: "opening_auction" | "open" | "closed";
  last_price_kobo: Kobo | null;
  reference_price_kobo: Kobo;
  lowest_today_kobo: Kobo;
  highest_today_kobo: Kobo;
  fee_bps: number;
  bids: PriceLevel[];
  offers: PriceLevel[];
  trades: PublicTrade[];
};

export type Why = {
  ticker: string;
  name: string;
  summary: string;
  move_bps: number;
  reference_price_kobo: Kobo;
  last_price_kobo: Kobo | null;
  bought_in_a_hurry: number;
  sold_in_a_hurry: number;
  reasons: string[];
  valuation_label: string | null;
  valuation_reasons: string[];
};

export type Order = {
  id: number;
  ticker: string;
  name: string;
  side: "buy" | "sell";
  kind: "limit" | "market";
  limit_price_kobo: Kobo | null;
  quantity: number;
  remaining: number;
  held_kobo: Kobo;
  value_traded_kobo: Kobo;
  fees_paid_kobo: Kobo;
  status: "open" | "filled" | "cancelled" | "expired";
  closed_reason: string | null;
  placed_at: string;
  closed_at: string | null;
};

export type Holding = {
  ticker: string;
  name: string;
  shares: number;
  held_for_orders: number;
  price_kobo: Kobo;
  value_kobo: Kobo;
};

export type MarketShare = {
  ticker: string;
  name: string;
  sector: string;
  price_kobo: Kobo;
  traded: boolean;
  change_bps: number;
  volume: number;
  market_value_kobo: Kobo;
  credit_rating: string | null;
};

export type Market = {
  market_state: "opening_auction" | "open" | "closed";
  paused_until: string | null;
  index: number;
  index_change_bps: number;
  market_value_kobo: Kobo;
  volume: number;
  trades: number;
  shares: MarketShare[];
  index_history: { session_date: string; level: number }[];
};

export type TradingDay = {
  session_date: string;
  open_kobo: Kobo;
  close_kobo: Kobo;
  high_kobo: Kobo;
  low_kobo: Kobo;
  volume: number;
};

export type PortfolioHolding = {
  ticker: string;
  name: string;
  shares: number;
  held_for_orders: number;
  price_kobo: Kobo;
  change_bps: number;
  value_kobo: Kobo;
  cost_kobo: Kobo;
  gain_kobo: Kobo;
  dividends_kobo: Kobo;
};

export type Portfolio = {
  cash_kobo: Kobo;
  held_for_orders_kobo: Kobo;
  shares_value_kobo: Kobo;
  total_kobo: Kobo;
  dividends_kobo: Kobo;
  realised_kobo: Kobo;
  holdings: PortfolioHolding[];
  bonds_value_kobo: Kobo;
  held_for_offers_kobo: Kobo;
  offered_to_bidders_kobo: Kobo;
  advice: string[];
  net_worth: { session_date: string; total_kobo: Kobo }[];
};

export type Ticker = {
  market_state: MarketState;
  closing_rush: boolean;
  index: number;
  index_change_bps: number;
  shares: { ticker: string; price_kobo: Kobo; change_bps: number; traded_today: boolean }[];
};

export type BellMover = { ticker: string; name: string; close_kobo: Kobo; change_bps: number };
export type ClosingBell = {
  in_rush: boolean;
  fee_bps: number;
  usual_fee_bps: number;
  large_orders: { ticker: string; name: string; side: "buy" | "sell"; quantity: number; value_kobo: Kobo; shown_at: string }[];
  bell: null | {
    session_date: string; rung_at: string; index: number; index_change_bps: number; lines: string[]; stories: string[];
    advisory: string[]; next: string; winner: BellMover | null; loser: BellMover | null; risers: number; fallers: number;
  };
};

export type Notice = { ticker: string | null; kind: string; title: string; body: string; posted_at: string; period_label: string };

export type CompanyFacts = {
  ticker: string;
  name: string;
  filing_label: string;
  profit_per_share: { period: number; label: string; kobo_per_share: number; net_profit_kobo: Kobo }[];
  yearly_profit_per_share_kobo: number;
  compared_with: string;
  sales_change_bps: number | null;
  profit_change_bps: number | null;
  sales_before_kobo: Kobo | null;
  profit_before_kobo: Kobo | null;
  cash_kobo: Kobo;
  cash_change_quarter_kobo: Kobo;
  cash_change_year_kobo: Kobo;
  cash_in_three_months_kobo: Kobo;
  cash_outlook: string;
  year_high_kobo: Kobo | null;
  year_low_kobo: Kobo | null;
  next_results: { at: string; label: string } | null;
  industry: { sector: string; rank: number; of: number; share_bps: number };
  control: string;
  notices: Notice[];
};

export type ResultsReport = {
  ticker: string; name: string; period: number; label: string; title: string; paragraphs: string[];
  available: { period: number; label: string }[];
};

export type IndustryCompany = {
  ticker: string; name: string; rank: number; share_bps: number; sales_kobo: Kobo; sales_growth_bps: number | null;
  price_kobo: Kobo | null; change_bps: number; market_value_kobo: Kobo;
};
export type Industry = {
  code: string; name: string; market_value_kobo: Kobo; change_bps: number; sales_kobo: Kobo; sales_growth_bps: number | null;
  companies: IndustryCompany[];
};

export type Bond = {
  code: string; name: string; kind: string; kind_label: string; issuer: string; ticker: string | null; rating: string | null;
  pays: string; face_kobo: Kobo; maturity_label: string; quarters_left: number; yield_bps: number; distressed: boolean;
  conversion_shares: number | null; project: string | null; green: boolean; outstanding: number | null;
  fair_kobo: Kobo; ask_kobo: Kobo; bid_kobo: Kobo; on_offer: number | null;
};
export type BondHolding = Bond & { units: number; held_for_swap: number; value_kobo: Kobo; cost_kobo: Kobo; gain_kobo: Kobo };
export type BondDesk = {
  desk_open: boolean;
  policy_rate_bps: number;
  curve: { label: string; quarters: number; yield_bps: number }[];
  spreads: { rating: string; spread_bps: number }[];
  bonds: Bond[];
  holdings: BondHolding[];
  income_kobo: Kobo;
  swaps: { id: number; code: string; name: string; units: number; shares: number }[];
};

export type Offer = {
  id: number; ticker: string; name: string; kind: "ipo" | "public" | "rights"; price_kobo: Kobo; shares: number;
  rights_new: number | null; rights_held: number | null; reason: string; status: string; closes_label: string;
  needs_vote: boolean; outcome: string | null; asked: number; held_kobo: Kobo; allotted: number | null;
};
export type Vote = {
  id: number; ticker: string; name: string; subject: string; question: string; explanation: string; board: "for" | "against";
  status: string; closes_label: string; my_choice: "for" | "against" | null; my_shares: number;
  votes_for: number | null; votes_against: number | null; tally: Record<string, { for: number; against: number }> | null;
};
export type Takeover = {
  id: number; bidder: string; bidder_ticker: string; target: string; ticker: string; price_kobo: Kobo;
  market_price_kobo: Kobo | null; premium_bps: number; shares_sought: number; hostile: boolean; status: string;
  closes_label: string; needs_vote: boolean; outcome: string | null; offered: number; free: number;
};
export type Integration = {
  bidder: string; target: string; ticker: string; planned_saving_bps: number; quarters: number;
  done: { label: string; cost_bps: number; notes: string[] }[];
};
export type Corporate = { offers: Offer[]; votes: Vote[]; takeovers: Takeover[]; integrations: Integration[]; notices: Notice[] };
export type Ownership = { ticker: string; name: string; controller: string | null; share_bps: number; summary: string };
export type Grant = {
  received_kobo: Kobo; total_kobo: Kobo; next_payment_at: string | null;
  steps: { step: string; what: string; earned: boolean; paid: boolean }[];
};

export type Analysis = {
  ticker: string;
  name: string;
  filing_label: string;
  price_kobo: Kobo;
  shares_in_issue: number;
  market_value_kobo: Kobo;
  yearly_profit_kobo: Kobo;
  yearly_sales_kobo: Kobo;
  yearly_dividends_kobo: Kobo;
  owners_funds_kobo: Kobo;
  book_per_share_kobo: Kobo;
  price_to_profit: number | null;
  price_to_sales: number | null;
  price_to_owners_funds: number | null;
  market_price_to_profit: number | null;
  dividend_yield_bps: number;
  npv_per_share_kobo: Kobo;
  npv_total_kobo: Kobo;
  npv_method: "profits" | "assets";
  npv_gap_bps: number;
  growth_bps: number;
  discount_bps: number;
  long_run_bps: number;
  schedule: { label: string; profit_kobo: Kobo; value_today_kobo: Kobo }[];
  verdict: string;
  reasons: string[];
  risks: string[];
  shareholders: { holder: string; shares: number; share_bps: number }[];
};

export type Watched = {
  ticker: string;
  name: string;
  price_kobo: Kobo;
  change_bps: number;
  alert_above_kobo: Kobo | null;
  alert_below_kobo: Kobo | null;
  reached: "above" | "below" | null;
};

export type NewOrder = {
  ticker: string;
  side: "buy" | "sell";
  kind: "limit" | "market";
  quantity: number;
  limit_price_kobo?: number;
};

/** Sign-up is not finished until the emailed code is typed in. */
export type SignUpPending = {
  detail: string;
  email: string;
  /** Only filled in while no email service is connected (running on your own computer). */
  code_shown_on_screen: string | null;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function readableError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  // The server lists each problem with a field when the details are malformed.
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => String(item?.msg ?? "").replace(/^Value error, /, ""))
      .filter(Boolean)
      .join(" ");
  }
  return "Something went wrong. Please try again.";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, readableError(body?.detail));
  return body as T;
}

/** Told to every part of the page showing the watchlist, so that each reads it again. */
export const WATCHLIST_CHANGED = "watchlist-changed";
const announce = (name: string) => <T,>(result: T): T => {
  window.dispatchEvent(new Event(name));
  return result;
};

export const api = {
  me: () => request<Player>("/me"),
  movements: () => request<Movement[]>("/me/movements?limit=10"),
  setProfileIcon: (profile_icon: ProfileIcon) =>
    request<Player>("/me/profile-icon", { method: "PATCH", body: JSON.stringify({ profile_icon }) }),
  clock: () => request<Clock>("/world/clock"),
  worldStatus: () => request<WorldStatus>("/world/status"),
  companies: () => request<{ sectors: Sector[] }>("/companies"),
  economy: () => request<Economy>("/economy"),
  news: (filter: { outlet?: string; ticker?: string; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (filter.outlet) query.set("outlet", filter.outlet);
    if (filter.ticker) query.set("ticker", filter.ticker);
    query.set("limit", String(filter.limit ?? 60));
    return request<News>(`/news?${query}`);
  },
  market: () => request<Market>("/market"),
  portfolio: () => request<Portfolio>("/market/portfolio"),
  watchlist: () => request<Watched[]>("/market/watchlist"),
  watch: (ticker: string, alerts: { alert_above_kobo?: number; alert_below_kobo?: number } = {}) =>
    request<Watched[]>(`/market/watchlist/${encodeURIComponent(ticker)}`, { method: "PUT", body: JSON.stringify(alerts) })
      .then(announce(WATCHLIST_CHANGED)),
  unwatch: (ticker: string) =>
    request<Watched[]>(`/market/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }).then(announce(WATCHLIST_CHANGED)),
  priceHistory: (ticker: string) => request<TradingDay[]>(`/market/${encodeURIComponent(ticker)}/history`),
  analysis: (ticker: string) => request<Analysis>(`/market/${encodeURIComponent(ticker)}/analysis`),
  quote: (ticker: string) => request<Quote>(`/market/${encodeURIComponent(ticker)}`),
  why: (ticker: string) => request<Why>(`/market/${encodeURIComponent(ticker)}/why`),
  myOrders: () => request<Order[]>("/market/orders"),
  myHoldings: () => request<Holding[]>("/market/holdings"),
  placeOrder: (order: NewOrder) =>
    request<{ order: Order; trades: PublicTrade[] }>("/market/orders", { method: "POST", body: JSON.stringify(order) }),
  cancelOrder: (id: number) => request<Order>(`/market/orders/${id}`, { method: "DELETE" }),
  ticker: () => request<Ticker>("/market/ticker"),
  closingBell: () => request<ClosingBell>("/market/closing-bell"),
  industries: () => request<Industry[]>("/market/industries"),
  facts: (ticker: string) => request<CompanyFacts>(`/market/${encodeURIComponent(ticker)}/facts`),
  resultsReport: (ticker: string, period?: number) =>
    request<ResultsReport>(`/market/${encodeURIComponent(ticker)}/results${period === undefined ? "" : `?period=${period}`}`),
  bonds: () => request<BondDesk>("/bonds"),
  tradeBond: (code: string, side: "buy" | "sell", units: number) =>
    request<{ name: string; side: string; units: number; price_kobo: Kobo; value_kobo: Kobo }>(
      "/bonds/trade", { method: "POST", body: JSON.stringify({ code, side, units }) }),
  swapBond: (code: string, units: number) => request<unknown>("/bonds/swaps", { method: "POST", body: JSON.stringify({ code, units }) }),
  cancelSwap: (id: number) => request<void>(`/bonds/swaps/${id}`, { method: "DELETE" }),
  corporate: () => request<Corporate>("/corporate"),
  applyForShares: (id: number, shares: number) =>
    request<Corporate>(`/corporate/offers/${id}`, { method: "PUT", body: JSON.stringify({ shares }) }),
  castVote: (id: number, choice: "for" | "against") =>
    request<Corporate>(`/corporate/votes/${id}`, { method: "PUT", body: JSON.stringify({ choice }) }),
  answerTakeover: (id: number, shares: number) =>
    request<Corporate>(`/corporate/takeovers/${id}`, { method: "PUT", body: JSON.stringify({ shares }) }),
  ownership: () => request<Ownership[]>("/corporate/ownership"),
  grant: () => request<Grant>("/me/grant", { method: "POST", body: "{}" }),
  career: () => request<Career>("/career"),
  chooseBuild: (build: BuildCode) => request<Career>("/career/build", { method: "PUT", body: JSON.stringify({ build }) }),
  employers: () => request<Opening[]>("/career/employers"),
  takeJob: (ticker: string) => request<Career>("/career/job", { method: "PUT", body: JSON.stringify({ ticker }) }),
  leaveJob: () => request<Career>("/career/job", { method: "DELETE" }),
  banks: () => request<PlayerBank[]>("/career/banks"),
  chooseBank: (ticker: string) => request<Career>("/career/bank", { method: "PUT", body: JSON.stringify({ ticker }) }),
  chooseFund: (fund: string) => request<Career>("/career/retirement", { method: "PUT", body: JSON.stringify({ fund }) }),
  objectives: () => request<ObjectiveBoard>("/objectives"),
  takeWork: (template: string) => request<Objective>("/objectives", { method: "POST", body: JSON.stringify({ template }) }),
  handIn: (id: number, answers: Record<string, unknown>) =>
    request<Objective>(`/objectives/${id}/hand-in`, { method: "POST", body: JSON.stringify({ answers }) }),
  giveUp: (id: number) => request<Objective>(`/objectives/${id}`, { method: "DELETE" }),
  assetDesk: () => request<AssetDesk>("/desk/asset-manager"),
  accountantDesk: (ticker?: string) => request<AccountantDesk>(`/desk/accountant${ticker ? `?ticker=${encodeURIComponent(ticker)}` : ""}`),
  company: (ticker: string) => request<Company>(`/companies/${encodeURIComponent(ticker)}?periods=8`),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  login: (email: string, password: string) =>
    request<Player>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  signup: (details: {
    email: string;
    display_name: string;
    password: string;
    date_of_birth: string;
    profile_icon: ProfileIcon;
  }) => request<SignUpPending>("/auth/signup", { method: "POST", body: JSON.stringify(details) }),
  confirmEmail: (email: string, code: string) =>
    request<Player>("/auth/confirm-email", { method: "POST", body: JSON.stringify({ email, code }) }),
};
