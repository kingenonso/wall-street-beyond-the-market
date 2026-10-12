import { describe, expect, it } from "vitest";
import { appendFigure, evaluate, percentChoices } from "./Calculator";
import { suggest } from "./CommandBar";
import { unitWarning } from "./Work";
import type { Player } from "./api";

describe("the calculator", () => {
  it("does arithmetic in the usual order, with brackets", () => {
    expect(evaluate("21.84 ÷ 41.90")).toBeCloseTo(0.52124, 4);
    expect(evaluate("2 + 3 × 4")).toBe(14);
    expect(evaluate("(2 + 3) × 4")).toBe(20);
    expect(evaluate("15191.81 + 8568")).toBeCloseTo(23759.81, 2);
    expect(evaluate("−5 + 2")).toBe(-3);
    expect(evaluate("1,000 × 2")).toBe(2000);
  });
  it("refuses anything that is not a sum, and never runs code", () => {
    expect(evaluate("alert(1)")).toBeNull();
    expect(evaluate("1 / 0")).toBeNull();
    expect(evaluate("2 +")).toBeNull();
    expect(evaluate("(2 + 3")).toBeNull();
    expect(evaluate("constructor")).toBeNull();
  });
});

describe("the wrong-unit warning", () => {
  const given = [{ kobo: "7511473000000" }, { kobo: "1519181000000" }];   // ₦75,114.73 million and ₦15,191.81 million
  it("warns when a percentage is written as a fraction, without giving the answer", () => {
    const w = unitWarning({ key: "m", label: "Margin", kind: "percent" }, "0.52", given);
    expect(w).toMatch(/percent/);
    expect(w).not.toMatch(/52%|52\.\d/);   // it repeats what was typed, never a corrected figure
    expect(unitWarning({ key: "m", label: "Margin", kind: "percent" }, "52.1", given)).toBeNull();
  });
  it("warns when a figure in millions is typed in naira", () => {
    expect(unitWarning({ key: "e", label: "EBITDA", kind: "millions" }, "23759810000", given)).toMatch(/millions/);
    expect(unitWarning({ key: "e", label: "EBITDA", kind: "millions" }, "23759.81", given)).toBeNull();
  });
  it("says nothing for an empty or nonsense answer", () => {
    expect(unitWarning({ key: "t", label: "Cover", kind: "times" }, "", given)).toBeNull();
    expect(unitWarning({ key: "t", label: "Cover", kind: "times" }, "abc", given)).toBeNull();
  });
});

describe("the command bar", () => {
  const player = { build_name: "Accountant", empire: null } as unknown as Player;
  const shares = [
    { ticker: "ARW", name: "Arewa Air", sector: "Transport", price_kobo: "2210", change_bps: 420, traded_today: true },
    { ticker: "IKB", name: "Ikenga Bank", sector: "Banking", price_kobo: "3850", change_bps: 160, traded_today: true },
  ];
  it("finds a company by its code or its name, then pages and actions", () => {
    const found = suggest("ikb", player, shares);
    expect(found[0].href).toBe("#/companies/IKB");
    expect(suggest("arewa", player, shares)[0].label).toContain("Arewa Air");
    expect(suggest("portfolio", player, shares).some((s) => s.href === "#/portfolio")).toBe(true);
    expect(suggest("bonds", player, shares).some((s) => s.href === "#/market/bonds")).toBe(true);
  });
  it("only ever offers the game's own pages", () => {
    for (const q of ["a", "e", "m", "w", "javascript:", "http"]) {
      for (const s of suggest(q, player, shares)) expect(s.href.startsWith("#/")).toBe(true);
    }
    expect(suggest("", player, shares)).toEqual([]);
  });
});

describe("tapping figures into the calculator", () => {
  it("never runs two figures together into one number", () => {
    expect(appendFigure("", "21.84")).toBe("21.84");
    expect(appendFigure("21.84", "41.90")).toBe("21.84 + 41.90");
    expect(appendFigure("(2 + 3)", "4")).toBe("(2 + 3) + 4");
    expect(appendFigure("21.84 ÷", "41.90")).toBe("21.84 ÷ 41.90");
    expect(appendFigure("21.84 ÷ ", "41.90")).toBe("21.84 ÷ 41.90");
    expect(appendFigure("(", "5")).toBe("(5");
    expect(evaluate(appendFigure("10", "5"))).toBe(15);
  });
});

describe("a percentage answer", () => {
  it("offers both readings and never guesses which one the player meant", () => {
    const [already, fraction] = percentChoices(0.5212);
    expect(already.value).toBeCloseTo(0.5212, 6);
    expect(fraction.value).toBeCloseTo(52.12, 6);
    expect(already.label).toContain("already a percentage");
    expect(fraction.label).toContain("52.12%");
    const big = percentChoices(52.12);
    expect(big[0].value).toBe(52.12);                 // a result over 1 is still offered both ways
    expect(big[1].value).toBeCloseTo(5212, 6);
  });
});
