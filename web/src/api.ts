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
