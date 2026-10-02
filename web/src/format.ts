import type { Kobo, MarketState } from "./api";

const LAGOS = "Africa/Lagos";
const MINUS = "−"; // a true minus sign, the same width as a plus

/** Kobo text to whole naira and leftover kobo, exactly, however large. */
function split(kobo: Kobo): { negative: boolean; naira: bigint; kobo: bigint } {
  const value = BigInt(kobo);
  const negative = value < 0n;
  const size = negative ? -value : value;
  return { negative, naira: size / 100n, kobo: size % 100n };
}

/** ₦500,000 in full. Kobo are shown only when there are any. */
export function formatNaira(kobo: Kobo): string {
  const parts = split(kobo);
  const whole = parts.naira.toLocaleString("en-NG");
  const fraction = parts.kobo === 0n ? "" : "." + parts.kobo.toString().padStart(2, "0");
  return `${parts.negative ? MINUS : ""}₦${whole}${fraction}`;
}

/** Large amounts shortened: ₦8.64B, ₦320.4M, ₦1.2T. Smaller amounts in full. */
export function formatCompact(kobo: Kobo): string {
  const parts = split(kobo);
  const naira = Number(parts.naira);
  const steps: [number, string][] = [[1e12, "T"], [1e9, "B"], [1e6, "M"]];
  for (const [size, letter] of steps) {
    if (naira >= size) {
      const scaled = naira / size;
      const digits = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
      return `${parts.negative ? MINUS : ""}₦${scaled.toFixed(digits)}${letter}`;
    }
  }
  return formatNaira(kobo);
}

/** For statement tables: millions of naira with separators, e.g. 85,000 or (1,250) for a negative. */
export function formatMillions(kobo: Kobo): string {
  const parts = split(kobo);
  const millions = Math.round(Number(parts.naira) / 1e6);
  const text = millions.toLocaleString("en-NG");
  if (millions === 0) return "0";
  return parts.negative ? `(${text})` : text;
}

/** A change in hundredths of a percent: 450 → "▲ 4.5%", -210 → "▼ 2.1%". The arrow carries the direction, not colour alone. */
export function formatChange(bps: number): string {
  if (bps === 0) return "– 0.0%";
  const size = (Math.abs(bps) / 100).toFixed(1);
  return `${bps > 0 ? "▲" : "▼"} ${size}%`;
}

/** The change from one kobo amount to another, in hundredths of a percent. Null when there is no base. */
export function changeBps(now: Kobo, before: Kobo | undefined): number | null {
  if (before === undefined) return null;
  const base = Number(BigInt(before));
  if (base <= 0) return null;
  return Math.round(((Number(BigInt(now)) - base) / base) * 10000);
}

export function formatPercent(bps: number, digits = 1): string {
  return `${(bps / 100).toFixed(digits)}%`;
}

export function formatCount(text: Kobo): string {
  return BigInt(text).toLocaleString("en-NG");
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

export function formatLagosDay(moment: Date): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: LAGOS, day: "numeric", month: "short" }).format(moment);
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

/** Game quarter number to words: 8 → "Year 2 Q4". */
export function periodLabel(period: number): string {
  if (period === 0) return "Opening";
  return `Year ${Math.floor((period - 1) / 4) + 1} Q${((period - 1) % 4) + 1}`;
}
