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

  it("is two groups: what you can go to, and where you are", () => {
    for (const group of [".strip-left", ".strip-right"]) {
      expect(rule(group), `${group} has lost its layout`).toMatch(/display:\s*flex/);
    }
  });

  it("puts the game's date and the market's state on the tape row, not in the strip", () => {
    expect(ticker).toMatch(/className="tape-date"/);
    expect(ticker).toMatch(/<MarketPill/);
    expect(shell, "the date has crept back into the strip").not.toMatch(/tape-date/);
  });

  /**
   * The owner's decision of 9 November 2026: the row of four dimmed world switches comes out of the
   * strip. This is the guard on that decision, and it is deliberately the opposite of the guard it
   * replaces.
   *
   * The old guard held the four switches in place and demanded they stay dimmed, on the argument that
   * a switch with no engine behind it is a lie to the player. The owner looked at the row and reached
   * the stronger version of the same conclusion: a row of switches you can never press is not honesty,
   * it is furniture — you stop seeing it, and it costs the strip a third of its width. Insurance is now
   * a real thing to buy under Money, and this test fails the day the three unbuilt ones come back.
   */
  it("carries no world switches, and Insurance is a page rather than a switch", () => {
    // The words themselves may appear in prose: the comment above Strip records what stood there and
    // why it went. What may not come back is the switch, so the guard looks for the switch's shape.
    for (const label of ["Change Law Firm", "Toggle Global Autopilot", "Cheats", "Insurance"]) {
      expect(shell, `the ${label} switch has crept back into the strip`).not.toContain(`label="${label}"`);
    }
    expect(shell, "the strip still draws a middle group").not.toContain("strip-world");
    expect(shell, "WorldSwitch has come back").not.toContain("function WorldSwitch");
    expect(css, "the middle group's layout rule has come back").not.toContain(".strip-world");
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

/**
 * The owner's complaint of 9 November 2026: "I can't find a place to repay my loan."
 *
 * The button existed. It was at the foot of Money › Borrow, below two large panels offering to lend
 * more, and it only appeared once a loan existed. So the fix is about where things stand on a page,
 * and about there being one of them: a guard on the order, a guard on the button that settles a loan
 * in full, and a guard that the old second copy of the repayment form is gone for good.
 */
describe("where a debt is repaid", () => {
  const desk = readFileSync(new URL("./Desk.tsx", import.meta.url), "utf8");
  const borrow = readFileSync(new URL("./Borrow.tsx", import.meta.url), "utf8");
  const debts = readFileSync(new URL("./Debts.tsx", import.meta.url), "utf8");

  it("is one panel, drawn on the desk and on Borrow", () => {
    expect(desk, "the desk no longer says what is owed").toMatch(/<DebtsPanel[\s\S]*?where="desk"/);
    expect(borrow, "Borrow no longer says what is owed").toMatch(/<DebtsPanel[\s\S]*?where="borrow"/);
  });

  it("stands above the offer to lend more, never below it", () => {
    // Read where the page actually draws them, not where the file happens to define them: LoansTab and
    // ShortsTab are functions written higher up the file but drawn lower on the page.
    const page = borrow.slice(borrow.indexOf("export function BorrowWork"));
    const panel = page.indexOf("<DebtsPanel");
    expect(panel, "Borrow no longer draws the panel at all").toBeGreaterThan(-1);
    for (const drawn of ["{tab === \"loans\" && <LoansTab", "{tab === \"shorts\" && <ShortsTab", "{tab === \"empire\" && b.empire"]) {
      const at = page.indexOf(drawn);
      expect(at, `Borrow has lost ${drawn}`).toBeGreaterThan(-1);
      expect(panel, `what you owe has slipped below ${drawn}`).toBeLessThan(at);
    }
  });

  it("can settle a loan in full, not only in slices", () => {
    expect(debts, "there is no way to pay a loan off in one go").toMatch(/Pay it all off/);
    // Paying it all passes the whole outstanding figure, and the server clamps it; nothing is trusted from here.
    expect(debts).toMatch(/wholeKobo\(row\.loan\.outstanding\)/);
    // The two figures a repay form must never invent: the rate and the amount owed come from the server.
    expect(debts).toMatch(/formatPercent\(loan\.rate_bps/);
    expect(debts).toMatch(/formatNaira\(row\.loan\.outstanding\)/);
  });

  it("says where a mortgage is repaid instead of pretending to own that button", () => {
    expect(debts).toMatch(/A mortgage is repaid with the property it is secured on/);
    expect(debts).toMatch(/href="#\/property"/);
  });

  it("has exactly one repayment form in the front end", () => {
    // The old copy inside Borrow's Loans tab was removed in the same change. If it comes back, a player
    // can meet two repayment boxes for one loan and not know which the server will honour.
    expect(borrow, "the old Loans panel is back in Borrow.tsx").not.toMatch(/title="Loans"/);
    expect(borrow.match(/\/repay`/g)?.length ?? 0, "Borrow.tsx posts a repayment of its own again").toBe(0);
  });
});
