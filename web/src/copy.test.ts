import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

/**
 * The words every screen says, checked so the design's promise of sentence case cannot quietly slip again.
 *
 * A shouted label is any string in a .tsx file that is ALL CAPITALS, in whole or in part, with more than one
 * capital letter in it. Share codes, currencies, ratings, abbreviations read that way and a few names that are
 * genuinely written in capitals are listed below and allowed. A single code with no lowercase at all ("GGM") is
 * not a label, but "RANK" and "FORCED SALE" are.
 */

/**
 * The node:fs stand-in declared in node-fs.d.ts, which marks each file "from node:fs". Vitest knows nothing of the
 * mark, so it stands in too; the array is copied into this realm so the test's own filter sees it.
 */
vi.mock("node:fs", async (importOriginal) => {
  const fs = await importOriginal<typeof import("node:fs")>();
  return { ...fs, readdirSync: (path: URL | string) => Array.from(fs.readdirSync(path)) };
});

const here = new URL(".", import.meta.url);
const files = readdirSync(here).filter((f) => f.endsWith(".tsx") && !f.endsWith(".test.tsx"));

const ALLOWED = new Set([
  // Codes, markets, ratings and currencies shown as they are written in the world: share codes (IDC is the hint
  // "e.g. IDC" beside a ticker field) and the commodity codes the derivatives desk lists beside FARM and METALS.
  "BSX", "BSX50", "USD", "GBP", "EUR", "NGN", "HSE", "NYSE", "LSE", "AA", "AAA", "BB", "BBB", "CCC", "IDC", "MATERIALS",
  // Words the game keeps in capitals because that is how they are read.
  "EBITDA", "UTC", "POST", "PUT", "DELETE", "GET", "P/E", "CEO", "CFO", "COO", "ETF", "ETFs", "PIN", "ID", "SWIFT",
  // Abbreviations an officer of the firm would write that way in a sentence.
  "US", "AI", "PDF", "NPV",
  // The contracts the derivatives desk writes on. They are codes the server sends and the desk matches by name; what
  // the player sees is the plan-English label in Derivatives.tsx ("BSX Banks", "Naira ($)"), never the code.
  "TOP30", "BANKS", "OILGAS", "OIL", "NAIRA", "FARM", "METALS",
  // The game's own name, set in capitals in the masthead and nowhere else.
  "WALL STREET", "BEYOND THE MARKET",
]);

/** Letters, digits and the underscore: after one of these a quote is prose ("company's"), not a string. */
const WORD = /[\p{L}\p{N}_]/u;

/** Code: a string is read where code says it, and a template, an element or a tag opens a text of its own. */
const CODE = 0;
/** A template's text, from its backtick to the next; `${` opens a code expression over it. */
const TEMPLATE = 1;
/** An element's bare text, from the end of its opening tag to its closing one; `{` opens code over it. */
const JSX = 2;

/** One place the walker has got to, and the words gathered there so far. */
interface Frame {
  mode: number;
  text: string;
  /** The line `text` began on. */
  line: number;
  /** The `{` still open in this code, so that a `}` knows its own. */
  braces: number;
  /** Elements opened inside this text and not yet closed. */
  depth: number;
}

/**
 * Every word a file shows, in the order it shows them, with the line each begins on.
 *
 * Strings in code are read where code says them, but two kinds of words are written in no quotes at all: the text
 * of a template literal (`` Fill up at ⛽ filling stations ``) and the bare text of a JSX element (`<td>Sell</td>`).
 * Neither can be told from code by a regex — an apostrophe in prose ("the company's page"), a quote in a comment,
 * or a quote inside a `${…}` would each open a "string" that never closes — so the file is walked a character at a
 * time, in three states: code, a template's text, and an element's text.
 *
 * A tag is read whole, so that a closing tag (`</Panel>`) returns to the code it came from rather than opening a
 * text of its own, and so that a self-closing one (`<Arrow />`) does not end the text around it. A word's line is
 * the line of its opening quote or of its first letter.
 */
function strings(source: string): { value: string; line: number }[] {
  const found: { value: string; line: number }[] = [];
  const stack: Frame[] = [{ mode: CODE, text: "", line: 1, braces: 0, depth: 0 }];
  let i = 0;
  let line = 1; // the line at `i`

  const top = () => stack[stack.length - 1];
  const newlines = (text: string) => (text.match(/\n/g) ?? []).length;

  /** A text's words, from its first letter (never from the blank space above it), then start a new text. */
  const flush = () => {
    const at = top();
    const first = at.text.search(/\S/);
    if (first >= 0) {
      found.push({ value: at.text, line: at.line + newlines(at.text.slice(0, first)) });
    }
    at.text = "";
    at.line = line;
  };

  const enter = (mode: number) => {
    // An element's text is broken by an element or an expression inside it, so each run of its words stands alone;
    // a template's text is one sentence however many values are threaded through it, and is gathered at its end.
    if (top().mode === JSX) flush();
    stack.push({ mode, text: "", line, braces: 0, depth: 0 });
  };

  const leave = () => {
    if (stack.length === 1) return; // the file's own code never ends
    flush();
    stack.pop();
  };

  /** The end of the string opened at `at`: past its closing quote, or the end of the file. */
  const skipQuoted = (at: number): number => {
    const quote = source[at];
    let j = at + 1;
    while (j < source.length) {
      if (source[j] === "\\") {
        if (source[j + 1] === "\n") line += 1;
        j += 2;
      } else if (source[j] === quote) {
        return j + 1;
      } else if (source[j] === "\n" && quote !== "`") {
        return j; // an unclosed quote ends at the line
      } else {
        if (source[j] === "\n") line += 1;
        j += 1;
      }
    }
    return j;
  };

  /** The `}` that closes the `{` at `at`, counting the braces and stepping over the strings in between. */
  const closeBrace = (at: number): number => {
    let depth = 0;
    let j = at;
    while (j < source.length) {
      const c = source[j];
      if (c === '"' || c === "'" || c === "`") {
        j = skipQuoted(j);
      } else if (c === "{") {
        depth += 1;
        j += 1;
      } else if (c === "}") {
        depth -= 1;
        if (depth === 0) return j;
        j += 1;
      } else if (c === "\n") {
        line += 1;
        j += 1;
      } else {
        j += 1;
      }
    }
    return source.length;
  };

  /**
   * The tag that opens at `at`, or null where `<` is an operator or a type's angle.
   *
   * A tag is named at once (`<div`, `</Panel`, `<Arrow`) and stands where an expression may start — after `(`, `{`,
   * `=`, `,`, `?`, `:` or `return` — so `Array<string>` and `useState<Foo>` are read as code. The words in its
   * attributes are words the screen says ("sentence case", `{"Fine"}`), so they are gathered here.
   */
  const readTag = (at: number, inText = false): { end: number; kind: "open" | "close" | "self" } | null => {
    let j = at + 1;
    let kind: "open" | "close" = "open";
    if (source[j] === "/") {
      kind = "close";
      j += 1;
    } else if (!inText) {
      // An opening tag stands where an expression may start; a closing one always ends an element.
      const before = source.slice(0, at).replace(/\s+$/, "");
      const previous = before.slice(-1);
      if (previous && !/[=(,{[?:&|;!>]/.test(previous) && !/(?:^|[^\w$])return$/.test(before)) return null;
    }
    if (source[j] === ">") return { end: j + 1, kind }; // a fragment, <> or </>
    const name = /^[A-Za-z][\w.:$-]*/.exec(source.slice(j));
    if (!name || source[j + name[0].length]?.match(/[A-Za-z0-9_$]/)) return null;
    j += name[0].length;

    let self = false;
    while (j < source.length) {
      const c = source[j];
      if (c === "\n") {
        line += 1;
        j += 1;
      } else if (c === ">") {
        j += 1;
        break;
      } else if (c === "/" && source[j + 1] === ">") {
        self = true;
        j += 2;
        break;
      } else if (c === '"' || c === "'") {
        const opened = line;
        const end = skipQuoted(j);
        const raw = source.slice(j + 1, source[end - 1] === c ? end - 1 : end);
        found.push({ value: raw.replace(/\\(.)/g, "$1"), line: opened });
        j = end;
      } else if (c === "{") {
        const close = closeBrace(j);
        const opened = line - newlines(source.slice(j, close));
        const inner = source.slice(j + 1, close);
        for (const word of strings(inner)) found.push({ value: word.value, line: word.line + opened - 1 });
        j = close + 1;
      } else {
        j += 1;
      }
    }
    return { end: j, kind: self ? "self" : kind };
  };

  while (i < source.length) {
    const at = top();
    const c = source[i];

    if (at.mode === TEMPLATE) {
      if (c === "\\") {
        at.text += source[i + 1] ?? "";
        if (source[i + 1] === "\n") line += 1;
        i += 2;
      } else if (c === "`") {
        i += 1;
        leave();
      } else if (c === "$" && source[i + 1] === "{") {
        at.text += " "; // where the value goes
        i += 2;
        enter(CODE);
      } else if (c === "\n") {
        line += 1; // a template's line break shows as the space between the words
        i += 1;
      } else {
        at.text += c;
        i += 1;
      }
      continue;
    }

    if (at.mode === JSX) {
      if (c === "{") {
        i += 1;
        enter(CODE);
      } else if (c === "<") {
        const tag = readTag(i, true);
        if (!tag) {
          at.text += c;
          i += 1;
        } else {
          flush();
          i = tag.end;
          if (tag.kind === "close") {
            if (at.depth > 0) at.depth -= 1;
            else stack.pop(); // this element's text is over; its closing tag ends it
          } else if (tag.kind === "open") {
            at.depth += 1;
          }
        }
      } else {
        at.text += c;
        if (c === "\n") line += 1;
        i += 1;
      }
      continue;
    }

    // Code: the file itself, or an expression laid over a template's or an element's text.
    if (c === "}") {
      i += 1;
      if (at.braces > 0) at.braces -= 1;
      else leave();
    } else if (c === "{") {
      at.braces += 1;
      i += 1;
    } else if (c === "\n") {
      line += 1;
      i += 1;
    } else if (c === "/" && source[i + 1] === "/") {
      while (i < source.length && source[i] !== "\n") i += 1;
    } else if (c === "/" && source[i + 1] === "*") {
      i += 2;
      while (i < source.length && !(source[i] === "*" && source[i + 1] === "/")) {
        if (source[i] === "\n") line += 1;
        i += 1;
      }
      i += 2;
    } else if (c === "`") {
      i += 1;
      enter(TEMPLATE);
    } else if (c === "<") {
      const tag = readTag(i);
      if (!tag) {
        i += 1;
      } else {
        i = tag.end;
        if (tag.kind === "open") enter(JSX);
      }
    } else if (c === '"' || c === "'") {
      const back = i === 0 ? "" : source[i - 1];
      if (WORD.test(back)) {
        // A quote after a letter is prose ("the company's page"), not a string's opening.
        i += 1;
      } else if (source[i + 1] === c) {
        // Two facing quotes are the empty string, "" or '', and close where they open.
        i += 2;
      } else {
        const opened = line;
        let value = "";
        i += 1;
        while (i < source.length && source[i] !== c && source[i] !== "\n") {
          value += source[i] === "\\" ? source[i + 1] ?? "" : source[i];
          i += source[i] === "\\" ? 2 : 1;
        }
        i += 1;
        found.push({ value, line: opened });
      }
    } else {
      i += 1;
    }
  }
  return found;
}

/**
 * True when a string is a code and not a word a screen says: a share code with a digit in it ("BSX50", "Q1"), or a run of
 * at most three capitals ("GGM", "AA, AA, A", "BSX 50"). The length matters. A first version of this let any word of six
 * capitals through, which is the shape of nearly every shouted label — "RANK", "NEXT", "SHARES" all passed, and the guard
 * was blind to the very thing it exists to catch. Three letters is the longest that is reliably a code and not a word.
 */
function isBareCode(value: string): boolean {
  return value.trim().split(/\s+/).every((word) => /^[A-Z0-9][A-Z0-9&\-/.,:'’()]*$/.test(word)
    && (/\d/.test(word) || word.replace(/[^A-Z]/g, "").length <= 3));
}

/** A literal that is only a colour — "#8B7CF6" — is code, not a label. */
function isColour(value: string): boolean {
  return /^#[0-9A-Fa-f]{3,8}$/.test(value.trim());
}

/** True when every run of capitals in the string is a word we allow. */
function onlyAllowedCapitals(value: string): boolean {
  const runs = value.split(/[^A-Za-z]+/).filter((w) => w.length > 1 && w === w.toUpperCase());
  return runs.every((word) => ALLOWED.has(word));
}

/** True when this is a word a screen shows in capitals, and therefore a fault. */
function shouted(value: string): boolean {
  const trimmed = value.trim();
  // Code a template carries but the screen never shows: a locale ("en-NG"), a field name, a route ("market-offers").
  if (/^(?:[a-z]{2}-[A-Z]{2}|[a-z0-9]+(?:-[a-z0-9]+)+)$/.test(trimmed)) return false;
  if (trimmed.length < 4 || ALLOWED.has(trimmed) || isBareCode(trimmed) || isColour(trimmed)) return false;
  return trimmed.split(/[^A-Za-z]+/).some((w) => w.length > 1 && w === w.toUpperCase()) && !onlyAllowedCapitals(trimmed);
}

describe("the words every screen says", () => {
  for (const file of files) {
    it(`${file} says nothing in capitals`, () => {
      const found = strings(readFileSync(new URL(file, here), "utf8"))
        .filter(({ value }) => shouted(value))
        .map(({ value, line }) => `line ${line}: ${value.trim().replace(/\s+/g, " ").slice(0, 80)}`);
      expect(found).toEqual([]);
    });
  }

  it("reads every screen, not only some", () => {
    expect(files.length).toBeGreaterThan(30);
  });

  // A guard that cannot be caught being blind stays blind. This one waved through every word of up to six capitals —
  // the shape of almost every shouted heading — and so missed them all for a whole sitting. These two tests feed it.
  it("would catch a shout if a screen still wrote one", () => {
    for (const label of ["RANK", "NEXT", "SHARES", "CAREER", "FORCED SALE", "THE SHADOW SIDE", "YOUR ETFS", "● BREAKING",
                         "READ THIS FIRST", "BONDS AND BILLS", "WHAT COULD GO WRONG", "Now the market SHUTS"]) {
      expect(shouted(label), label).toBe(true);
    }
  });

  it("leaves codes, market figures and the game's own name alone", () => {
    for (const code of ["GGM", "BSX 50", "BSX50", "AA, AA, A", "MATERIALS", "EBITDA", "WALL STREET", "en-GB", "#8B7CF6",
                        "₦12,345,678", "+2.4%", "Q1", "IDC"]) {
      expect(shouted(code), code).toBe(false);
    }
  });

  it("reads the words out of the code, not the code as words", () => {
    const source = [
      "// An officer's duty: RANK and FORCED SALE are both shouted in this comment.",
      'const n = shares.toLocaleString("en-GB");',
      "const rate = `managed by ${show ? \"ME\" : \"ke\"} at ${style[\"BACKGROUND\"]}`;",
      "const label = RANKS[level];",
      '<Panel title="sentence case" aside={"Fine"}>Text with an apostrophe\'s test <Arrow /> Sell these</Panel>;',
      'const broken = "FORCED SALE";',
    ].join("\n");
    expect(strings(source).map(({ value }) => value)).toEqual([
      "en-GB",
      "ME",
      "ke",
      "BACKGROUND",
      "managed by   at  ",
      "sentence case",
      "Fine",
      "Text with an apostrophe's test ",
      " Sell these",
      "FORCED SALE",
    ]);
  });

  it("gives a label the line of its own opening quote", () => {
    const source = "const a = 1;\nconst b = `x ${y}\n z`;\nconst c = \"SHOUT\";";
    expect(strings(source).map(({ value, line }) => [value, line])).toEqual([
      ["x   z", 2],
      ["SHOUT", 4],
    ]);
  });
});