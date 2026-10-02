import type { MarketState, Money } from "./api";

const LAGOS = "Africa/Lagos";

/** ₦500,000 from 50,000,000 kobo. Large amounts shorten to ₦1.24B, ₦320.4M. */
export function formatMoney(money: Money, compact = false): string {
  const naira = money.amount_kobo / 100;
  const symbol = money.currency === "NGN" ? "₦" : `${money.currency} `;
  if (compact && Math.abs(naira) >= 1_000_000) {
    return symbol + new Intl.NumberFormat("en-NG", { notation: "compact", maximumFractionDigits: 2 }).format(naira);
  }
  return symbol + new Intl.NumberFormat("en-NG", { maximumFractionDigits: 2 }).format(naira);
}

export function formatLagosDate(moment: Date): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: LAGOS, weekday: "short", day: "numeric", month: "short", year: "numeric",
  }).format(moment);
}

export function formatLagosTime(moment: Date, withSeconds = true): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: LAGOS, hour: "2-digit", minute: "2-digit", second: withSeconds ? "2-digit" : undefined, hour12: false,
  }).format(moment);
}

export const MARKET_LABEL: Record<MarketState, string> = {
  open: "Market Open",
  opening_auction: "Opening Auction",
  closed: "Market Closed",
};

/** "in 3h 12m", "in 45s" */
export function formatCountdown(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `in ${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `in ${minutes}m ${String(seconds).padStart(2, "0")}s`;
  return `in ${seconds}s`;
}
