import { describe, expect, it } from "vitest";
import { formatCountdown, formatLagosTime, formatMoney } from "./format";

describe("formatMoney", () => {
  it("shows kobo as naira", () => {
    expect(formatMoney({ amount_kobo: 50_000_000, currency: "NGN" })).toBe("₦500,000");
    expect(formatMoney({ amount_kobo: 150, currency: "NGN" })).toBe("₦1.5");
  });
  it("shortens large amounts when asked", () => {
    expect(formatMoney({ amount_kobo: 124_000_000_000, currency: "NGN" }, true)).toBe("₦1.24B");
    expect(formatMoney({ amount_kobo: 50_000_000, currency: "NGN" }, true)).toBe("₦500,000");
  });
});

describe("formatLagosTime", () => {
  it("shows Lagos time wherever the player is", () => {
    expect(formatLagosTime(new Date("2026-10-06T11:00:00Z"))).toBe("12:00:00");
  });
});

describe("formatCountdown", () => {
  it("picks sensible units", () => {
    expect(formatCountdown(3 * 3600_000 + 12 * 60_000)).toBe("in 3h 12m");
    expect(formatCountdown(45_000)).toBe("in 45s");
    expect(formatCountdown(-5)).toBe("in 0s");
  });
});
