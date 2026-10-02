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

export const api = {
  me: () => request<Player>("/me"),
  movements: () => request<Movement[]>("/me/movements?limit=10"),
  setProfileIcon: (profile_icon: ProfileIcon) =>
    request<Player>("/me/profile-icon", { method: "PATCH", body: JSON.stringify({ profile_icon }) }),
  clock: () => request<Clock>("/world/clock"),
  worldStatus: () => request<WorldStatus>("/world/status"),
  companies: () => request<{ sectors: Sector[] }>("/companies"),
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
