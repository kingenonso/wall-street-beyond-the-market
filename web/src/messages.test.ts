import { describe, expect, it } from "vitest";
import { partnerFrom } from "./Messages";

describe("partnerFrom", () => {
  it("reads a player's name from the address", () => {
    expect(partnerFrom("Ada%20Obi")).toBe("Ada Obi");
    expect(partnerFrom("bola")).toBe("bola");
  });
  it("names nobody for a broken or empty address, instead of breaking the page", () => {
    expect(partnerFrom("%E0")).toBeUndefined();
    expect(partnerFrom("%")).toBeUndefined();
    expect(partnerFrom(undefined)).toBeUndefined();
    expect(partnerFrom("%20")).toBeUndefined();
    expect(partnerFrom("x".repeat(41))).toBeUndefined();
  });
});
