// The Floor (owner, 16 November 2026): the multiplayer home is its own section, and Live events and Competition moved
// into it from Work. The command line opens it.
import { describe, expect, it } from "vitest";
import type { Player } from "./api";
import { readCommand } from "./command";
import { sectionOf, sectionsFor } from "./Shell";

const player = { build: "asset_manager", build_name: "Asset Manager", work_in_hand: 0, empire: null, margin_calls: 0 } as unknown as Player;

describe("the Floor", () => {
  it("is a section of its own with the multiplayer tabs", () => {
    const floor = sectionsFor(player).find((s) => s.path === "floor");
    expect(floor?.label).toBe("The Floor");
    expect(floor?.tabs?.map((t) => t.path)).toEqual(["floor", "live", "auctions"]);
    for (const page of ["floor", "live", "auctions"]) expect(sectionOf(player, page)?.path).toBe("floor");
  });
  it("took Live events and Competition out of Work", () => {
    const work = sectionsFor(player).find((s) => s.path === "work");
    expect(work?.tabs?.map((t) => t.path)).not.toContain("live");
    expect(work?.tabs?.map((t) => t.path)).not.toContain("competition");
  });
  it("opens from the command line", () => {
    expect(readCommand("FLOOR", [])).toMatchObject({ kind: "page", href: "#/floor" });
    expect(readCommand("auctions", [])).toMatchObject({ kind: "page", href: "#/auctions" });
  });
});

import { readTicket } from "./FloorDesk";

describe("a chat line read as a deal ticket", () => {
  it("reads who does what, how many, of which share and at what price", () => {
    expect(readTicket("I'll take 3,000 HMB at 46.20")).toEqual({ side: "buy", quantity: 3000, ticker: "HMB", price: 4620 });
    expect(readTicket("sell 500 idc @ ₦20.5")).toEqual({ side: "sell", quantity: 500, ticker: "IDC", price: 2050 });
    expect(readTicket("hit 1,200 ABA at 40")).toMatchObject({ side: "sell", quantity: 1200 });
  });
  it("leaves an ordinary line alone", () => {
    expect(readTicket("what do you think of HMB?")).toBeNull();
    expect(readTicket("take it at 40")).toBeNull();
  });
});
