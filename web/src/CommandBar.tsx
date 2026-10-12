// The command bar (redesign): type a company's code or name, a page, or an action, and jump there.
// Ctrl K (or ⌘K) puts the cursor in it from anywhere. Arrow keys move through the suggestions,
// Enter opens one, Escape closes the list. It only ever moves the player around the game's own pages.

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { api, type Player, type Ticker } from "./api";
import { formatNaira } from "./format";

export type Suggestion = { id: string; group: "Pages" | "Companies" | "Actions"; label: string; detail?: string; href: string;
  move?: { text: string; way: "up" | "down" | "flat" } };

/** Every page a player can open, with other words they might type for it. */
export function pagesFor(player: Player): { label: string; href: string; words: string }[] {
  const pages = [
    { label: "My desk", href: "#/", words: "home desk start needs" },
    ...(player.build_name ? [{ label: player.build_name, href: "#/build", words: "build desk tools" }] : []),
    { label: "Work", href: "#/work", words: "objectives tasks jobs work" },
    { label: player.empire ? "Empire" : "Empires", href: "#/empire", words: "empire firm head team league" },
    { label: "Market: shares", href: "#/market", words: "market shares stocks exchange buy sell trade" },
    { label: "Market: bonds and bills", href: "#/market/bonds", words: "bonds bills yield government lend" },
    { label: "Market: offers, votes and bids", href: "#/market/offers", words: "offers votes takeovers bids rights" },
    { label: "Market: industries", href: "#/market/industries", words: "industries sectors market share" },
    { label: "Market: who owns what", href: "#/market/owners", words: "owners holders who owns" },
    { label: "Portfolio", href: "#/portfolio", words: "portfolio holdings my shares orders" },
    { label: "News", href: "#/news", words: "news stories papers headlines" },
    { label: "Companies", href: "#/companies", words: "companies accounts results" },
    { label: "Economy", href: "#/economy", words: "economy inflation interest rate jobs prices central bank" },
    { label: "Career", href: "#/career", words: "career salary bank employer retirement pension level" },
    { label: "Messages", href: "#/messages", words: "messages chat write inbox" },
    { label: "Profile", href: "#/profile", words: "profile picture account" },
    ...(player.build_name ? [{ label: "Rank", href: "#/rank", words: "rank case gate mastery ceo" }] : []),
  ];
  if (player.empire && !player.empire.forming) {
    for (const [key, label] of [["deals", "Deals"], ["companies", "Companies we own"], ["takeovers", "Takeovers"], ["requests", "Requests and votes"],
                                ["money", "Money"], ["people", "People"], ["risk", "Risk"], ["warroom", "War Room"]]) {
      pages.push({ label: `Empire: ${label}`, href: `#/empire/${key}`, words: `empire ${label.toLowerCase()}` });
    }
  }
  return pages;
}

/** The suggestions for what has been typed, best first, at most ten. */
export function suggest(query: string, player: Player, shares: Ticker["shares"]): Suggestion[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const out: Suggestion[] = [];
  const found = shares
    .map((s) => {
      const code = s.ticker.toLowerCase(), name = s.name.toLowerCase();
      const score = code === q ? 0 : code.startsWith(q) ? 1 : name.startsWith(q) ? 2 : name.includes(q) ? 3 : -1;
      return { s, score };
    })
    .filter((x) => x.score >= 0)
    .sort((a, b) => a.score - b.score || a.s.ticker.localeCompare(b.s.ticker))
    .slice(0, 5);
  for (const { s } of found) {
    const way = s.change_bps > 0 ? "up" : s.change_bps < 0 ? "down" : "flat";
    out.push({
      id: `c-${s.ticker}`, group: "Companies", label: `${s.ticker} · ${s.name}`, detail: s.sector, href: `#/companies/${s.ticker}`,
      move: { text: `${formatNaira(s.price_kobo)} ${s.traded_today ? `${way === "up" ? "▲" : way === "down" ? "▼" : "–"} ${(Math.abs(s.change_bps) / 100).toFixed(1)}%` : ""}`.trim(), way },
    });
  }
  for (const page of pagesFor(player)) {
    if (page.label.toLowerCase().includes(q) || page.words.split(" ").some((w) => w.startsWith(q))) {
      out.push({ id: `p-${page.href}`, group: "Pages", label: page.label, href: page.href });
    }
  }
  const first = found[0]?.s;
  if (first) {
    out.push({ id: `a-buy-${first.ticker}`, group: "Actions", label: `Buy or sell shares in ${first.name}`, href: `#/companies/${first.ticker}` });
    out.push({ id: `a-res-${first.ticker}`, group: "Actions", label: `Read ${first.name}’s latest results`, href: `#/companies/${first.ticker}` });
  }
  if ("write message".split(" ").some((w) => w.startsWith(q))) {
    out.push({ id: "a-write", group: "Actions", label: "Write to a player", href: "#/messages" });
  }
  if ("start work".split(" ").some((w) => w.startsWith(q))) {
    out.push({ id: "a-work", group: "Actions", label: "See work you can start", href: "#/work" });
  }
  // Keep the groups together, in a fixed order.
  const order = { Companies: 0, Pages: 1, Actions: 2 } as const;
  return out.sort((a, b) => order[a.group] - order[b.group]).slice(0, 10);
}

export function CommandBar({ player, compact = false }: { player: Player; compact?: boolean }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [shares, setShares] = useState<Ticker["shares"]>([]);
  const input = useRef<HTMLInputElement>(null);
  const loaded = useRef(false);
  const uid = useId().replace(/:/g, "");
  const inputId = `command-input-${uid}`, listId = `command-list-${uid}`;

  // Ctrl K or ⌘K from anywhere puts the cursor here.
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && input.current && input.current.offsetParent !== null) {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);

  function load() {
    if (loaded.current) return;
    loaded.current = true;
    api.ticker().then((t) => setShares(t.shares)).catch(() => { loaded.current = false; });
  }

  const results = useMemo(() => suggest(query, player, shares), [query, player, shares]);
  const shown = open && results.length > 0;

  function go(item: Suggestion | undefined) {
    if (!item) return;
    window.location.hash = item.href;
    setQuery("");
    setOpen(false);
    input.current?.blur();
  }

  function onKey(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setActive((i) => Math.min(i + 1, results.length - 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    else if (event.key === "Enter") { event.preventDefault(); go(results[active]); }
    else if (event.key === "Escape") { setOpen(false); }
  }

  let lastGroup = "";
  return (
    <form role="search" className={compact ? "command command-compact" : "command"} onSubmit={(e) => { e.preventDefault(); go(results[active]); }}>
      <label htmlFor={inputId} className="sr-only">Search or jump to a company, a page or an action</label>
      <svg className="command-icon" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
      </svg>
      <input
        ref={input} id={inputId} type="search" autoComplete="off" spellCheck={false}
        role="combobox" aria-expanded={shown} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={shown && results[active] ? `cmd-${uid}-${results[active].id}` : undefined}
        placeholder="Search: a company, a page, an action…"
        value={query}
        onFocus={() => { load(); setOpen(true); }}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onChange={(e) => { setQuery(e.target.value); setActive(0); setOpen(true); }}
        onKeyDown={onKey}
      />
      <kbd className="command-key" aria-hidden="true">Ctrl K</kbd>
      {shown && (
        <ul id={listId} role="listbox" aria-label="Suggestions" className="command-list">
          {results.map((item, i) => {
            const head = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <li key={item.id} role="none">
                {head && <div className="command-group" aria-hidden="true">{head}</div>}
                <div
                  id={`cmd-${uid}-${item.id}`} role="option" aria-selected={i === active}
                  className={i === active ? "command-option active" : "command-option"}
                  onMouseDown={(e) => { e.preventDefault(); go(item); }}
                  onMouseEnter={() => setActive(i)}
                >
                  <span>{item.label}{item.detail && <span className="muted"> · {item.detail}</span>}</span>
                  {item.move && <span className={`mono change-${item.move.way}`}>{item.move.text}</span>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </form>
  );
}
