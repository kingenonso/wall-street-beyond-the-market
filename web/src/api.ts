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
