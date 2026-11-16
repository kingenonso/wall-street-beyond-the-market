import { describe, expect, it } from "vitest";
import { hintsFor, lookUp, readCommand } from "./command";

const LISTED = ["HMB", "DSW", "IKB", "KKI"];
const SHARES = [{ ticker: "HMB", name: "Harmattan Bank" }, { ticker: "DSW", name: "Delta Swift" }, { ticker: "IKB", name: "Ikoyi Bank" }];

describe("the command line", () => {
  it("opens a company by its code, with or without GO, however it is typed", () => {
    expect(readCommand("HMB GO", LISTED)).toEqual({ kind: "show", ticker: "HMB" });
    expect(readCommand("  hmb ", LISTED)).toEqual({ kind: "show", ticker: "HMB" });
    expect(readCommand("ZZZ GO", LISTED).kind).toBe("unknown");
  });

  it("fills an order in and never sends one", () => {
    expect(readCommand("BUY HMB 500", LISTED)).toEqual({ kind: "trade", ticker: "HMB", side: "buy", quantity: 500, price_kobo: null });
    expect(readCommand("sell dsw 1,200 at 9.50", LISTED)).toEqual({ kind: "trade", ticker: "DSW", side: "sell", quantity: 1200, price_kobo: 950 });
    expect(readCommand("BUY HMB 10 @ ₦20", LISTED)).toMatchObject({ price_kobo: 2000 });
    // Each mistake is answered in words: a missing count, a nought, a share that is not listed, a price that is not one.
    expect(readCommand("BUY HMB", LISTED).kind).toBe("unknown");
    expect(readCommand("BUY HMB 0", LISTED).kind).toBe("unknown");
    expect(readCommand("BUY ZZZ 5", LISTED).kind).toBe("unknown");
    expect(readCommand("BUY HMB 5 AT cheap", LISTED).kind).toBe("unknown");
  });

  it("asks why a share moved, opens the pages, and explains finance words", () => {
    expect(readCommand("RIPPLE DSW", LISTED)).toEqual({ kind: "ripple", ticker: "DSW" });
    expect(readCommand("why ikb go", LISTED)).toEqual({ kind: "ripple", ticker: "IKB" });
    expect(readCommand("GOV GO", LISTED)).toMatchObject({ kind: "page", href: "#/government" });
    expect(readCommand("rivals", LISTED)).toMatchObject({ kind: "page", href: "#/live" });
    expect(readCommand("HELP P/E", LISTED)).toMatchObject({ kind: "help", word: "P/E" });
    expect(readCommand("help market value", LISTED)).toMatchObject({ kind: "help", word: "Market value" });
    expect(readCommand("HELP", LISTED)).toEqual({ kind: "help-list" });
    expect(readCommand("HELP flibbertigibbet", LISTED).kind).toBe("unknown");
    expect(lookUp("bsx 50")?.word).toBe("BSX 50");
  });

  it("says what nonsense is, and does nothing for an empty line", () => {
    expect(readCommand("", LISTED)).toEqual({ kind: "nothing" });
    expect(readCommand("make me rich", LISTED)).toMatchObject({ kind: "unknown" });
  });

  it("offers the matching commands while a player types", () => {
    expect(hintsFor("", SHARES).length).toBeGreaterThan(3);
    expect(hintsFor("BU", SHARES).map((h) => h.text)).toContain("BUY HMB 500");
    expect(hintsFor("BUY D", SHARES).map((h) => h.text)).toEqual(["BUY DSW 500"]);
    expect(hintsFor("ik", SHARES).map((h) => h.text)).toContain("IKB GO");
    expect(hintsFor("gov", SHARES).map((h) => h.text)).toContain("GOV GO");
    expect(hintsFor("HELP p/", SHARES).map((h) => h.text)).toContain("HELP P/E");
  });
});
