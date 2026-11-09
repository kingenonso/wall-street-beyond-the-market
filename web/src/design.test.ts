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

describe("the terminal's lettering", () => {
  /**
   * The one way this design shouts. A terminal sets a panel's name and a table's headings in capitals; the
   * words themselves stay in sentence case, which is copy.test.ts's job. So capitals are allowed to come from
   * the stylesheet — but only on the handful of rules that are labels, so the allowance cannot spread.
   */
  const MAY_SHOUT = /^(\.panel-head h2|\.panel-head h3|thead th|\.group-label|\.why-title|\.tape-table thead th)$/;

  it("shouts only on a label, and never on anything else", () => {
    const shouting = [...css.matchAll(/\n([^\n{}]+)\{[^}]*text-transform:\s*uppercase[^}]*\}/g)]
      .flatMap((found) => found[1].split(",").map((selector) => selector.trim()));
    expect(shouting.length, "nothing shouts: the panel bars and table headings have lost their capitals").toBeGreaterThan(0);
    for (const selector of shouting) expect(selector, `a rule that is not a label shouts: ${selector}`).toMatch(MAY_SHOUT);
  });
});

describe("the terminal is boxed", () => {
  it("gives every panel a box, a ground and a bar across its top", () => {
    const panel = rule(".panel");
    expect(panel).toMatch(/border:\s*1px solid var\(--border\)/);
    expect(panel).toMatch(/background:\s*var\(--panel\)/);
    expect(panel).toMatch(/border-radius:\s*3px/);
    // The bar is what makes a panel look like a panel here, so it must be there and must bleed to the edges.
    expect(rule(".panel-head")).toMatch(/background:\s*var\(--head\)/);
    expect(rule(".panel-head")).toMatch(/margin:\s*-10px -12px/);
    expect(panel).toMatch(/padding:\s*10px 12px/);
  });

  it("marks a panel that must stand out with a coloured edge, not by unboxing it", () => {
    expect(rule(".panel-urgent")).toMatch(/border-left:\s*3px solid/);
    expect(rule(".panel-warn")).toMatch(/border-left:\s*3px solid/);
    expect(rule(".panel-yours")).toMatch(/border-left:\s*3px solid/);
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

  it("takes the rule off every figure that starts a row when a band folds into twos on a phone", () => {
    // A band of six wraps three times, so the reset belongs on the odd figures. Resetting only the third left a
    // stray rule down the left of the fifth, which is the figure that starts the third row.
    const fold = css.slice(css.lastIndexOf("@media (max-width: 700px)"));
    expect(fold).toMatch(/\.band-cell:nth-child\(odd\) \{ border-left: 0/);
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

  it("holds a long table's headings still inside its own window, and lets them travel on a phone", () => {
    // The headings hold still only where the table has a window of its own, which the phone block takes away.
    expect(css).toMatch(/\.scroll-sticky thead th \{ position: sticky/);
    expect(css).not.toMatch(/\.no-sticky/);
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

describe("the strip across the top", () => {
  const shell = readFileSync(new URL("./Shell.tsx", import.meta.url), "utf8");
  const ticker = readFileSync(new URL("./Ticker.tsx", import.meta.url), "utf8");

  it("is three groups, and sets the world's switches apart from the navigation", () => {
    for (const group of [".strip-left", ".strip-world", ".strip-right"]) {
      expect(rule(group), `${group} has lost its layout`).toMatch(/display:\s*flex/);
    }
    // The middle group is not a page among pages: a rule keeps the eye from reading it as navigation.
    expect(rule(".strip-world")).toMatch(/border-left/);
  });

  it("puts the game's date and the market's state on the tape row, not in the strip", () => {
    expect(ticker).toMatch(/className="tape-date"/);
    expect(ticker).toMatch(/<MarketPill/);
    expect(shell, "the date has crept back into the strip").not.toMatch(/tape-date/);
  });

  /**
   * The loophole check for the four switches that have no engine behind them — the law firm, the two
   * autopilots, the cheats and insurance. A button that looks ready and does nothing is a lie to the
   * player, so while a switch is unbuilt it must be shown dimmed and disabled, which is also what the
   * colour grammar already means by dimmed. When one of them is built, this test changes with it, in
   * the same commit, and that change is the reminder that the others are still dark.
   */
  it("ships no switch that pretends to work before its engine does", () => {
    for (const label of ["Change Law Firm", "Toggle Global Autopilot", "Cheats", "Insurance"]) {
      expect(shell, `the strip has lost the ${label} switch`).toContain(`label="${label}"`);
    }
    const start = shell.indexOf("function WorldSwitch");
    expect(start, "no WorldSwitch in Shell.tsx").toBeGreaterThan(-1);
    const body = shell.slice(start, shell.indexOf("\n}", start));
    expect(body, "WorldSwitch now renders a button that does something, but no engine exists yet").toMatch(/disabled/);
    expect(rule(".strip-item:disabled")).toMatch(/opacity|color/);
  });

  it("keeps the search line reachable now that it is not in the strip", () => {
    expect(rule(".work-bar")).toMatch(/margin-bottom/);
    expect(shell).toMatch(/<div className="work-bar"><CommandBar/);
  });
});

describe("the column that never moves", () => {
  const shell = readFileSync(new URL("./Shell.tsx", import.meta.url), "utf8");
  const column = readFileSync(new URL("./LeftColumn.tsx", import.meta.url), "utf8");
  const phone = css.slice(css.indexOf("@media (max-width: 760px)"));

  it("stands at the left edge of every screen, wide or narrow", () => {
    // One call, outside the `!wide` condition that drops the right-hand rail: the column is not a rail.
    expect(shell.match(/<LeftColumn/g)?.length, "the column is drawn more than once, or not at all").toBe(1);
    const left = shell.indexOf("<LeftColumn");
    const rail = shell.indexOf("{!wide && <aside");
    expect(left, "no column in the shell").toBeGreaterThan(-1);
    expect(rail, "the rail's condition has moved").toBeGreaterThan(-1);
    expect(left, "the column has been put behind the rail's condition, so a focused screen loses it").toBeLessThan(rail);
    expect(rule(".column")).toMatch(/position:\s*sticky/);
    expect(rule(".shell")).toMatch(/grid-template-columns:\s*260px/);
  });

  it("is the reference's three panels, in the reference's order", () => {
    for (const name of ["Net worth history", "Market indicators", "Quotes and news"]) {
      expect(column, `the column has lost its ${name} panel`).toContain(`<Panel title="${name}"`);
    }
  });

  it("lies down at the foot of the page on a phone rather than dropping out of it", () => {
    // Working rule 2: nothing is dropped for a phone. The column stops being sticky and takes its turn after the
    // page's own work, so a phone player keeps the chart and the indicators at the cost of one scroll.
    const at = phone.indexOf(".column {");
    expect(at, "no column in the phone block").toBeGreaterThan(-1);
    const laid = phone.slice(at, phone.indexOf("}", at));
    expect(laid, "a phone hides the readout entirely").not.toMatch(/display:\s*none/);
    expect(laid).toMatch(/position:\s*static/);
    expect(laid).toMatch(/order:\s*2/);
    expect(phone, "the page's own work must still come first on a phone").toMatch(/\.work \{ order: 1;/);
    // And the rail last: without an order of its own it sorts before the work it sits beside on a desk, and the
    // page opens on a rail panel with the work underneath it.
    expect(phone, "the rail has crept above the page on a phone").toMatch(/\.rail \{ grid-column: 1; order: 3; \}/);
  });

  /**
   * The sections menu is not down the page any more: it is behind the strip's Menu, which is what frees the left
   * edge for a readout. The dot is the loophole check — a count that only exists inside a closed menu is a count
   * nobody finds, so the menu says when one of its sections is waiting.
   */
  it("carries no navigation, and the strip's menu says when a section is waiting", () => {
    expect(shell, "the sections menu has crept back down the page").not.toContain('className="sections"');
    expect(css, "styles.css still lays out a page-level sections menu").not.toMatch(/\n\.sections \{/);
    expect(shell).toMatch(/className="waiting-dot"/);
  });

  it("never cuts a figure's name, and never lets a list rule squeeze a headline", () => {
    // A name loses letters only by ellipsis or by being held on one line, so neither is allowed here.
    const name = rule(".indicator-name");
    expect(name).not.toMatch(/ellipsis/);
    expect(name).not.toMatch(/white-space:\s*nowrap/);
    expect(name).not.toMatch(/overflow:\s*hidden/);
    // The list's own rule is more specific than .news-line: without the :not(), a headline is set beside its
    // own outlet in half the column, which is how this fault was first found — in the look book's pixels.
    expect(css).toMatch(/\.column-list li:not\(\.news-line\)/);
  });

  it("fills the chart under its line, and anchors the first and last month inward", () => {
    // The fill runs from the zero line, so the colour is where the money is; and a month centred on the plot's
    // edge loses its first letter — "Mar" came out as "lar" in the first look book.
    expect(column).toMatch(/points=\{`\$\{PLOT\.left\},\$\{y\(0\)\}/);
    expect(column).toMatch(/textAnchor=\{p\.i === 0 \? "start"/);
  });

  it("reads every figure from the server and computes none of them on this side", () => {
    expect(column).toMatch(/useLoad\(api\.readout/);
    // The indicator's value and its move are printed as the server wrote them, not rebuilt from a number.
    expect(column).toMatch(/\{item\.value\}/);
    expect(column).toMatch(/\{item\.change\}/);
    // The quotes are read the first time somebody asks for them, not on every screen in the game.
    expect(column).toMatch(/quotesSeen/);
  });
});
