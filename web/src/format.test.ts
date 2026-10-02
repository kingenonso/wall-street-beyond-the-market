import { describe, expect, it } from "vitest";
import {
  changeBps, formatChange, formatCompact, formatCountdown, formatLagosTime, formatMillions, formatNaira, periodLabel,
} from "./format";

describe("formatNaira", () => {
  it("shows kobo as naira, in full", () => {
    expect(formatNaira("50000000")).toBe("₦500,000");
    expect(formatNaira("150")).toBe("₦1.50");
    expect(formatNaira("0")).toBe("₦0");
  });
  it("marks money out with a minus sign", () => {
    expect(formatNaira("-50000000")).toBe("−₦500,000");
  });
  it("keeps every kobo of an amount too large for ordinary numbers", () => {
    expect(formatNaira("900719925474099312345")).toBe("₦9,007,199,254,740,993,123.45");
  });
});

describe("formatCompact", () => {
  it("shortens large amounts", () => {
    expect(formatCompact("124000000000")).toBe("₦1.24B");
    expect(formatCompact("32040000000")).toBe("₦320M");
    expect(formatCompact("864000000000")).toBe("₦8.64B");
    expect(formatCompact("1471020000000000")).toBe("₦14.7T");
  });
  it("leaves smaller amounts in full", () => {
    expect(formatCompact("50000000")).toBe("₦500,000");
  });
  it("handles negatives", () => {
    expect(formatCompact("-250000000000")).toBe("−₦2.50B");
  });
});

describe("formatMillions", () => {
  it("shows millions of naira the way accounts do", () => {
    expect(formatMillions("8500000000000")).toBe("85,000");
    expect(formatMillions("-125000000000")).toBe("(1,250)");
    expect(formatMillions("0")).toBe("0");
  });
});

describe("changes", () => {
  it("uses an arrow as well as a sign", () => {
    expect(formatChange(450)).toBe("▲ 4.5%");
    expect(formatChange(-210)).toBe("▼ 2.1%");
    expect(formatChange(0)).toBe("– 0.0%");
  });
  it("works out the change between two amounts", () => {
    expect(changeBps("1045", "1000")).toBe(450);
    expect(changeBps("900", "1000")).toBe(-1000);
    expect(changeBps("900", "0")).toBeNull();
    expect(changeBps("900", undefined)).toBeNull();
  });
});

describe("time", () => {
  it("shows Lagos time wherever the player is", () => {
    expect(formatLagosTime(new Date("2026-10-06T11:00:00Z"))).toBe("12:00:00");
  });
  it("picks sensible units for a countdown", () => {
    expect(formatCountdown(3 * 3600_000 + 12 * 60_000)).toBe("in 3h 12m");
    expect(formatCountdown(45_000)).toBe("in 45s");
    expect(formatCountdown(-5)).toBe("in 0s");
  });
  it("names game quarters", () => {
    expect(periodLabel(1)).toBe("Year 1 Q1");
    expect(periodLabel(8)).toBe("Year 2 Q4");
    expect(periodLabel(0)).toBe("Opening");
  });
});
