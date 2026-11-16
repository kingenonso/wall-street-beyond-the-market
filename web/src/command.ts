// The terminal's command line (owner, 16 November 2026): type it, press Enter.
//
// Every command is also a button somewhere on screen, so nobody has to learn them to play. This file only reads what
// was typed and says what it asks for; the terminal does it. Nothing typed here sends an order: "BUY HMB 500" fills
// the order form in, and the player still presses the button.

import { GLOSSARY } from "./Term";

/** The pages a command can open, by the words a player might type for them. */
export const PAGES: Record<string, { href: string; name: string }> = {
  MARKET: { href: "#/market", name: "the whole market" },
  NEWS: { href: "#/news", name: "the news" },
  GOV: { href: "#/government", name: "taxes, the budget and the Assembly" },
  ECO: { href: "#/economy", name: "the economy" },
  PF: { href: "#/portfolio", name: "your portfolio" },
  EMPIRE: { href: "#/empire", name: "your empire" },
  RIVALS: { href: "#/competition", name: "the competition: every empire's points" },
  LIVE: { href: "#/live", name: "the live event: the next bell, or the one running now" },
  RANK: { href: "#/rank", name: "the rankings" },
  WORK: { href: "#/work", name: "the work board" },
  INTEL: { href: "#/intel", name: "intelligence and sources" },
  BORROW: { href: "#/borrow", name: "borrowing" },
  FX: { href: "#/currencies", name: "currencies" },
  PROPERTY: { href: "#/property", name: "property" },
  COURT: { href: "#/court", name: "the courts" },
};
const PAGE_WORDS: Record<string, string> = {
  GOVERNMENT: "GOV", ECONOMY: "ECO", PORTFOLIO: "PF", COMPETITION: "RIVALS", LEAGUE: "RIVALS", CURRENCIES: "FX",
  COURTS: "COURT", TASKS: "WORK",
};

export type Command =
  | { kind: "nothing" }
  | { kind: "show"; ticker: string }
  | { kind: "trade"; ticker: string; side: "buy" | "sell"; quantity: number; price_kobo: number | null }
  | { kind: "ripple"; ticker: string }
  | { kind: "page"; href: string; name: string }
  | { kind: "help"; word: string; means: string; example?: string }
  | { kind: "help-list" }
  | { kind: "unknown"; message: string };

/** One line that says what a command does, for the list under the command line. */
export type Hint = { text: string; does: string };

const TICKER = /^[A-Z][A-Z0-9]{1,5}$/;

/** "20.50" or "₦20.50" or "20" as whole kobo; null when it is not a price. */
function price(text: string): number | null {
  const clean = text.replace(/^₦/, "").replace(/,/g, "");
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(clean)) return null;
  const [whole, part = ""] = clean.split(".");
  return Number(whole) * 100 + Number(part.padEnd(2, "0"));
}

/** The glossary entry for a word, found however it was typed ("p/e", "P/E", "market value"). */
export function lookUp(word: string): { word: string; means: string; example?: string } | null {
  const wanted = word.trim().toLowerCase();
  const found = Object.keys(GLOSSARY).find((key) => key.toLowerCase() === wanted);
  return found ? { word: found, ...GLOSSARY[found] } : null;
}

/** Glossary words that start with (or contain) what was typed, for the hints and for "did you mean". */
function nearWords(word: string): string[] {
  const wanted = word.trim().toLowerCase();
  if (!wanted) return [];
  const keys = Object.keys(GLOSSARY);
  return [...keys.filter((k) => k.toLowerCase().startsWith(wanted)), ...keys.filter((k) => !k.toLowerCase().startsWith(wanted) && k.toLowerCase().includes(wanted))].slice(0, 4);
}

/**
 * What a typed line asks for. `tickers` is every listed share, so a company the exchange does not list is answered in
 * words rather than opened as an empty wall.
 */
export function readCommand(line: string, tickers: string[]): Command {
  const typed = line.trim();
  if (!typed) return { kind: "nothing" };
  const words = typed.toUpperCase().split(/\s+/);
  const listed = new Set(tickers);
  const known = (code: string) => listed.has(code);
  const notListed = (code: string): Command => ({ kind: "unknown", message: `${code} is not a share on the exchange. Type the company's code, such as ${tickers[0] ?? "HMB"}.` });
  const head = words[0];
  const rest = words.slice(1).filter((w) => w !== "GO");

  if (head === "HELP" || head === "?") {
    if (rest.length === 0) return { kind: "help-list" };
    const word = typed.split(/\s+/).slice(1).join(" ").replace(/\s+GO$/i, "");
    const entry = lookUp(word);
    if (entry) return { kind: "help", ...entry };
    const near = nearWords(word);
    return { kind: "unknown", message: near.length ? `No entry for "${word}". Did you mean ${near.join(", ")}?` : `No entry for "${word}" yet. Type HELP and a word from the game, such as HELP P/E.` };
  }

  if (head === "BUY" || head === "SELL") {
    const [code, count, ...after] = rest;
    if (!code) return { kind: "unknown", message: `Type ${head} then the company and how many, such as ${head} HMB 500.` };
    if (!known(code)) return notListed(code);
    if (!count || !/^\d{1,11}$/.test(count.replace(/,/g, "")) || Number(count.replace(/,/g, "")) <= 0) {
      return { kind: "unknown", message: `How many ${code} shares? Type ${head} ${code} 500, for example.` };
    }
    const quantity = Number(count.replace(/,/g, ""));
    let at: number | null = null;
    const priceWords = after.filter((w) => w !== "AT" && w !== "@");
    if (priceWords.length > 0) {
      at = price(priceWords[0].replace(/^@/, ""));
      if (at === null || at === 0) return { kind: "unknown", message: `"${priceWords[0]}" is not a price. Write it in naira, such as ${head} ${code} ${quantity} AT 20.50.` };
    }
    return { kind: "trade", ticker: code, side: head === "BUY" ? "buy" : "sell", quantity, price_kobo: at };
  }

  if (head === "RIPPLE" || head === "WHY") {
    const code = rest[0];
    if (!code) return { kind: "unknown", message: `Type ${head} and a company, such as ${head} ${tickers[0] ?? "HMB"}.` };
    return known(code) ? { kind: "ripple", ticker: code } : notListed(code);
  }

  const page = PAGES[head] ? head : PAGE_WORDS[head];
  if (page && rest.length === 0) return { kind: "page", ...PAGES[page] };

  if (rest.length === 0 && TICKER.test(head)) return known(head) ? { kind: "show", ticker: head } : notListed(head);

  return { kind: "unknown", message: `"${typed}" is not a command. Type HELP to see them all.` };
}

/** The lines under the command line while a player types: what each matching command would do. */
export function hintsFor(line: string, shares: { ticker: string; name: string }[]): Hint[] {
  const typed = line.trim().toUpperCase();
  const words = typed.split(/\s+/);
  const first = shares[0]?.ticker ?? "HMB";
  if (!typed) {
    return [
      { text: `${first} GO`, does: "open a company on the wall by its code" },
      { text: `BUY ${first} 500`, does: "fill the order form in for you; you still press the button" },
      { text: `RIPPLE ${first}`, does: "why a share moved, step by step, back to the cause" },
      { text: "HELP P/E", does: "any finance word, in plain language" },
      { text: "GOV GO", does: "taxes, the budget and the Assembly" },
      { text: "RIVALS GO", does: "every empire's points this year" },
    ];
  }
  const hints: Hint[] = [];
  const head = words[0];
  if (head === "HELP" || head === "?") {
    const word = line.trim().split(/\s+/).slice(1).join(" ");
    const near = word ? nearWords(word) : ["P/E", "BSX 50", "Market value"].filter((w) => GLOSSARY[w]);
    near.forEach((w) => hints.push({ text: `HELP ${w}`, does: GLOSSARY[w].means }));
    return hints.slice(0, 6);
  }
  if ("BUY".startsWith(head) || "SELL".startsWith(head)) {
    const verb = "BUY".startsWith(head) ? "BUY" : "SELL";
    const code = words[1] ?? "";
    shares.filter((s) => s.ticker.startsWith(code)).slice(0, 5)
      .forEach((s) => hints.push({ text: `${verb} ${s.ticker} ${words[2] ?? "500"}`, does: `${verb === "BUY" ? "buy" : "sell"} ${s.name}: fills the form in` }));
  }
  if ("RIPPLE".startsWith(head) || "WHY".startsWith(head)) {
    const code = words[1] ?? "";
    shares.filter((s) => s.ticker.startsWith(code)).slice(0, 4)
      .forEach((s) => hints.push({ text: `RIPPLE ${s.ticker}`, does: `why ${s.name} moved` }));
  }
  if (words.length === 1 || (words.length === 2 && "GO".startsWith(words[1]))) {
    shares.filter((s) => s.ticker.startsWith(head) || s.name.toUpperCase().startsWith(head)).slice(0, 5)
      .forEach((s) => hints.push({ text: `${s.ticker} GO`, does: `open ${s.name}` }));
    Object.entries(PAGES).filter(([word]) => word.startsWith(head))
      .forEach(([word, p]) => hints.push({ text: `${word} GO`, does: p.name }));
    if ("HELP".startsWith(head)) hints.push({ text: "HELP", does: "every command, and any finance word in plain language" });
  }
  return hints.slice(0, 6);
}
