import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Every build screen opens the same way: its name and one line saying what the page is for, then a band of
 * figures, then the work. Checked against the files rather than trusted, because a screen that opens with a
 * row of small boxes again is exactly the drift the redesign exists to stop, and it would look fine in a diff.
 *
 * This reads source, so it is deliberately loose about layout and strict about the two things that give the
 * page its shape: a PageHead first, a Band straight after, and no bare row of tiles left at the top.
 */

const here = new URL(".", import.meta.url);
const read = (name: string) => readFileSync(new URL(name, here), "utf8");

/** The six builds, and the file each screen is written in. The head of an empire is not a build and has its own head. */
const BUILDS = [
  { screen: "AssetManagerWork", build: "asset manager", file: "BuildDesk.tsx" },
  { screen: "AccountantWork", build: "asset_manager", file: "BuildDesk.tsx" },
  { screen: "InvestmentBankerWork", build: "investment banker", file: "Desks2.tsx" },
  { screen: "RiskManagerWork", build: "risk manager", file: "Desks2.tsx" },
  { screen: "LawyerWork", build: "legal counsel", file: "Desks2.tsx" },
  { screen: "JournalistWork", build: "financial journalist", file: "Desks2.tsx" },
];

/** One component's source, from its declaration to the next export. */
function body(file: string, screen: string): string {
  const text = read(file);
  const start = text.indexOf(`export function ${screen}(`);
  expect(start, `${screen} is missing from ${file}`).toBeGreaterThan(-1);
  const next = text.indexOf("\nexport function ", start + 1);
  return text.slice(start, next === -1 ? undefined : next);
}

describe("a build screen opens with its head and its band", () => {
  for (const { screen, build, file } of BUILDS) {
    it(`${build}: a page head, then a band of figures`, () => {
      const source = body(file, screen);
      const head = source.indexOf("<PageHead");
      const band = source.indexOf("<Band ");
      expect(head, `${screen} does not open with a PageHead`).toBeGreaterThan(-1);
      expect(band, `${screen} has no Band`).toBeGreaterThan(-1);
      expect(head, `${screen} puts its band above its head`).toBeLessThan(band);
      // The band is the top of the page, so nothing else may come between the head and it: no panel, no queue.
      const between = source.slice(head, band);
      expect(between, `${screen} has a section between its head and its band`).not.toMatch(/<(Panel|NeedsYouNow)/);
      // Three or four figures is a band; one figure is a stray box wearing a band's clothes.
      expect(source.split("<BandCell").length - 1, `${screen} has too few figures in its band`).toBeGreaterThan(2);
    });
  }

  it("leaves no row of small boxes at the top of a build screen", () => {
    for (const { screen, file } of BUILDS) {
      expect(body(file, screen), `${screen} still opens with a row of tiles`).not.toMatch(/className="tiles"/);
    }
  });
});
