// Live events, part 2: what the page takes from the server's quiet line. Only the kinds it knows, and only those it asked for.
import { describe, expect, it } from "vitest";
import { wanted } from "./pushes";

describe("the live line", () => {
  it("reads the kinds of change the server names", () => {
    expect(wanted('{"what":["chat","prediction"]}')).toEqual(["chat", "prediction"]);
  });
  it("keeps only the kinds a screen listens for", () => {
    expect(wanted('{"what":["chat","prediction","event"]}', ["chat"])).toEqual(["chat"]);
    expect(wanted('{"what":["prediction"]}', ["event"])).toEqual([]);
  });
  it("ignores anything it does not know, or cannot read", () => {
    expect(wanted('{"what":["secret","event"]}')).toEqual(["event"]);
    expect(wanted("not json")).toEqual([]);
    expect(wanted('{"what":"event"}')).toEqual([]);
    expect(wanted("{}")).toEqual([]);
  });
});
