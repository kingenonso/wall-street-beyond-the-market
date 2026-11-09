import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Guards on the design rules themselves, so a later change cannot quietly undo them.
 *
 * These are not screen tests: they read styles.css as text and check the promises the design makes —
 * sentence case everywhere, sections ruled and not boxed, every figure readable — and they run in a
 * fraction of a second with no database and no browser.
 */
const css = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

/** The declarations of one rule, by selector, exactly as written. */
function rule(selector: string): string {
  const at = css.indexOf(`\n${selector} {`);
  expect(at, `no rule named ${selector} in styles.css`).toBeGreaterThan(-1);
  const open = css.indexOf("{", at);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

/** Every colour token of a theme, as hex, so a theme can be checked against itself. */
function tokens(theme: "dark" | "light"): Record<string, string> {
  const start = theme === "dark" ? css.indexOf(":root {") : css.indexOf(':root[data-theme="light"] {');
  expect(start, `no ${theme} palette`).toBeGreaterThan(-1);
  const end = css.indexOf("}", start);
  const found: Record<string, string> = {};
  for (const [, name, value] of css.slice(start, end).matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)) found[name] = value;
  return found;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => channel(parseInt(hex.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("sentence case everywhere", () => {
  it("never shouts a label in capitals", () => {
    expect(css).not.toMatch(/text-transform:\s*uppercase/);
  });
});

describe("the sheet is ruled, not boxed", () => {
  it("gives a panel no box and no fill", () => {
    const panel = rule(".panel");
    expect(panel).toMatch(/border:\s*0/);
    expect(panel).toMatch(/background:\s*transparent/);
  });

  it("marks a panel that must stand out in the margin, not with a box round it", () => {
    expect(rule(".panel-urgent")).toMatch(/box-shadow:\s*inset/);
    expect(rule(".panel-warn")).toMatch(/box-shadow:\s*inset/);
  });
});

describe("a rule is drawn once and on the right side", () => {
  it("defines .tiles exactly once, so no two rules fight over the gaps", () => {
    expect(css.match(/\n\.tiles \{/g)?.length).toBe(1);
  });

  it("draws the rule between figures on the figure to the right, so a wrapped row never starts with one", () => {
    expect(css).not.toMatch(/\.tile:first-child/);
    expect(rule(".tile + .tile")).toMatch(/box-shadow:\s*inset 1px 0 0/);
  });

  it("folds a band of four into twos, never into three and an orphan", () => {
    const wide = css.indexOf("@media (max-width: 1180px)");
    const narrow = css.lastIndexOf("@media (max-width: 700px)");
    expect(wide).toBeGreaterThan(-1);
    expect(narrow).toBeGreaterThan(wide);
    const fold = css.slice(wide, narrow);
    expect(fold).toMatch(/\.band-4 \{ grid-template-columns: repeat\(2,/);
  });
});

describe("tables stay usable", () => {
  it("lets a phone scroll the whole page instead of trapping it in a four-row window", () => {
    // The phone-only rules are spread over more than one block; any of them may hold this one.
    const fold = css.slice(css.indexOf("@media (max-width: 700px)"));
    expect(fold).toMatch(/\.scroll-sticky \{ max-height: none/);
  });

  it("gives a table that scrolls sideways room at its cells and a focus ring, without gapping its brass rule", () => {
    expect(rule(".scroll")).not.toMatch(/padding:/);
    expect(css).toMatch(/\.scroll > table > tbody > tr > :first-child \{ padding-left:/);
    expect(rule(".scroll:focus-visible")).toMatch(/outline/);
  });

  it("holds headings still only in a table with a height of its own", () => {
    expect(css).toMatch(/\.no-sticky thead th \{ position: static/);
  });
});

describe("every figure is readable", () => {
  // The colours a player actually reads text in, against the three surfaces a panel can sit on.
  const INK = ["text", "text-2", "muted", "gold", "up", "down", "warn", "info"];
  const SURFACES = ["bg", "panel", "raised"];

  for (const theme of ["dark", "light"] as const) {
    const palette = tokens(theme);
    for (const ink of INK) {
      for (const surface of SURFACES) {
        it(`${theme}: ${ink} on ${surface} passes 4.5 to 1`, () => {
          expect(contrast(palette[ink], palette[surface])).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
  }
});

describe("the desk's two devices survive", () => {
  it("keeps the tape's brass stamp gutter", () => {
    expect(rule(".tape-gutter")).toMatch(/border-right/);
    expect(rule(".tape-gutter")).toMatch(/--gold/);
  });

  it("keeps the crimson margin on the first thing that needs the player", () => {
    expect(rule(".needs-lead")).toMatch(/--margin/);
  });

  it("keeps the wire in the serif and the exchange in the mono", () => {
    expect(rule(".tape-row.wire .tape-text")).toMatch(/--serif/);
    expect(rule(".tape-row.wire .tape-text")).toMatch(/-webkit-line-clamp:\s*2/);
  });
});
