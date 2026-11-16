// The terminal (owner, 15 November 2026): the desk as one wall of the whole economy.
//
// A company in the middle (its price, its candles, who is waiting to trade), a monitor to choose it from, money on
// the move between the five cities, and every industry's day; and beside it why the chosen share moved, the duel
// with the empire next to yours in the league, and the wire. Choosing a row in the monitor moves the whole wall.
//
// Every figure is the server's. What is worked out here is only where to draw it.

import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent, type KeyboardEvent } from "react";
import { hintsFor, readCommand, type Command } from "./command";
import { TradePanel, type TradePreset } from "./Trade";
import { api, type CityFlow, type CompetitionScore, type DivisionRow, type Industry, type Player, type PriceLevel, type TradingDay } from "./api";
import { formatCompact, formatNaira } from "./format";
import { useLoad } from "./hooks";
import { Trend } from "./LeftColumn";
import { Panel } from "./Shell";

// ---------------------------------------------------------------------------
// The share the wall is showing: one choice, shared by the page and the rail beside it.
// ---------------------------------------------------------------------------

let chosen: string | null = null;
// The order a typed command filled in, for the share it names; the trade panel in the rail picks it up.
let preset: (TradePreset & { ticker: string }) | null = null;
let stamps = 0;
const watchers = new Set<() => void>();
const tellAll = () => watchers.forEach((tell) => tell());
function choose(ticker: string) {
  chosen = ticker;
  if (preset && preset.ticker !== ticker) preset = null;
  tellAll();
}
function fillOrder(ticker: string, side: "buy" | "sell", quantity: number, price_kobo: number | null) {
  chosen = ticker;
  preset = { ticker, side, quantity, price_kobo, stamp: ++stamps };
  tellAll();
}
const listen = (tell: () => void) => { watchers.add(tell); return () => { watchers.delete(tell); }; };
function useChosen(): string | null {
  return useSyncExternalStore(listen, () => chosen);
}
function usePreset() {
  return useSyncExternalStore(listen, () => preset);
}

/** Bring a panel of the wall into view (on a phone the rail sits below the wall), and put the cursor in it. */
function bringUp(id: string, field?: string) {
  window.setTimeout(() => {
    const panel = document.getElementById(id);
    if (!panel) return;
    panel.scrollIntoView?.({ behavior: "auto", block: "start" });
    if (field) (panel.querySelector(field) as HTMLElement | null)?.focus({ preventScroll: true });
  }, 60);
}

type Row = { ticker: string; name: string; price_kobo: string; change_bps: number };

/** The rows of the monitor: the player's watchlist when they keep one, otherwise the shares that moved most today. */
function useMonitor(onLoggedOut: () => void): { rows: Row[]; mine: boolean; ready: boolean; showing: (ticker: string | null) => Row | undefined } {
  const watched = useLoad(api.watchlist, "terminal-watchlist", onLoggedOut);
  const tape = useLoad(api.ticker, "terminal-ticker", onLoggedOut);
  const every: Row[] = tape.data?.shares ?? [];
  const mine = Boolean(watched.data && watched.data.length > 0);
  const rows: Row[] = mine ? watched.data!.slice(0, 9)
    : [...every].sort((a, b) => Math.abs(b.change_bps) - Math.abs(a.change_bps)).slice(0, 9);
  // The share the wall shows: the one chosen (from the monitor, or a company named on the wire), else the first row.
  const showing = (ticker: string | null) => rows.find((r) => r.ticker === ticker) ?? every.find((r) => r.ticker === ticker) ?? rows[0];
  return { rows, mine, ready: mine || (tape.data !== null && watched.data !== null), showing };
}

const wayOf = (bps: number | null) => (bps === null || bps === 0 ? "flat" : bps > 0 ? "up" : "down");
const arrowOf = (bps: number | null) => (bps === null || bps === 0 ? "–" : bps > 0 ? "▲" : "▼");

function Chip({ bps, big = false }: { bps: number | null; big?: boolean }) {
  if (bps === null) return <span className="muted small">no trade yet</span>;
  return <span className={`mono chip chip-${wayOf(bps)}${big ? " chip-big" : ""}`}>{arrowOf(bps)} {(Math.abs(bps) / 100).toFixed(1)}%</span>;
}

// ---------------------------------------------------------------------------
// The company in the middle
// ---------------------------------------------------------------------------

const CHART = { width: 640, price: 236, top: 8, volumeTop: 250, volume: 40 };

/** Each trading day as a candle: the wick is the day's range, the body runs from its open to its close. */
function Candles({ days }: { days: TradingDay[] }) {
  const shown = days.slice(-48);
  if (shown.length < 2) {
    return <p className="muted small term-empty">The chart starts once this share has two trading days behind it.</p>;
  }
  const n = (kobo: string) => Number(kobo) / 100;
  const low = Math.min(...shown.map((d) => n(d.low_kobo))), high = Math.max(...shown.map((d) => n(d.high_kobo)));
  const span = high - low || 1;
  const most = Math.max(1, ...shown.map((d) => d.volume));
  const slot = CHART.width / Math.max(shown.length, 24);
  const body = Math.max(3, slot * 0.62);
  const y = (value: number) => CHART.top + ((high - value) * (CHART.price - CHART.top)) / span;
  const first = shown[0], last = shown[shown.length - 1];
  return (
    <svg className="term-candles" viewBox={`0 0 ${CHART.width} ${CHART.volumeTop + CHART.volume}`} role="img"
         aria-label={`${shown.length} trading days, from ${formatNaira(first.close_kobo)} on ${first.session_date} to ${formatNaira(last.close_kobo)} on ${last.session_date}. The bars underneath are the shares traded each day.`}>
      {[0, 0.25, 0.5, 0.75, 1].map((part) => (
        <g key={part}>
          <line className="grid-line" x1={0} x2={CHART.width - 50} y1={y(low + span * part)} y2={y(low + span * part)} />
          <text className="tick-label" x={CHART.width - 44} y={y(low + span * part) + 3}>{(low + span * part).toFixed(2)}</text>
        </g>
      ))}
      {shown.map((d, i) => {
        const x = i * slot + slot / 2;
        const open = n(d.open_kobo), close = n(d.close_kobo);
        const way = close >= open ? "up" : "down";
        const top = y(Math.max(open, close)), height = Math.max(1.5, Math.abs(y(open) - y(close)));
        const bar = (d.volume * CHART.volume) / most;
        return (
          <g key={d.session_date} className={`candle candle-${way}`}>
            <line x1={x} x2={x} y1={y(n(d.high_kobo))} y2={y(n(d.low_kobo))} />
            <rect x={x - body / 2} y={top} width={body} height={height} />
            <rect className="candle-volume" x={x - body / 2} y={CHART.volumeTop + CHART.volume - bar} width={body} height={bar} />
          </g>
        );
      })}
    </svg>
  );
}

/** Who is waiting to trade: the sellers above the last price, the buyers below it, each with how much they want. */
function OrderBook({ offers, bids, last }: { offers: PriceLevel[]; bids: PriceLevel[]; last: string | null }) {
  const asks = [...offers].sort((a, b) => Number(a.price_kobo) - Number(b.price_kobo)).slice(0, 5).reverse();
  const buys = [...bids].sort((a, b) => Number(b.price_kobo) - Number(a.price_kobo)).slice(0, 5);
  const most = Math.max(1, ...asks.map((l) => l.quantity), ...buys.map((l) => l.quantity));
  const level = (l: PriceLevel, side: "sell" | "buy") => (
    <div key={`${side}-${l.price_kobo}`} className={`book-level book-${side}`}>
      <span className="book-depth" style={{ width: `${Math.max(3, (l.quantity * 100) / most)}%` }} />
      <span className="mono">{formatNaira(l.price_kobo)}</span>
      <span className="mono">{l.quantity.toLocaleString("en-NG")}</span>
    </div>
  );
  return (
    <div className="term-book">
      <div className="group-label">Order book</div>
      {asks.length === 0 && <p className="muted small">Nobody is offering to sell.</p>}
      {asks.map((l) => level(l, "sell"))}
      <div className="book-last"><span className="mono strong">{last ? formatNaira(last) : "no trade yet"}</span><span className="muted small">last trade</span></div>
      {buys.map((l) => level(l, "buy"))}
      {buys.length === 0 && <p className="muted small">Nobody is waiting to buy.</p>}
    </div>
  );
}

function CompanyBoard({ row, onLoggedOut }: { row: Row; onLoggedOut: () => void }) {
  const quote = useLoad(() => api.quote(row.ticker), `terminal-quote:${row.ticker}`, onLoggedOut);
  const days = useLoad(() => api.priceHistory(row.ticker), `terminal-days:${row.ticker}`, onLoggedOut);
  const q = quote.data;
  return (
    <Panel title={`${row.ticker} · ${row.name}`} aside={<a href={`#/companies/${row.ticker}`}>The company&rsquo;s page</a>}>
      <div className="term-company">
        <div className="term-chart">
          <div className="term-price">
            <span className="mono term-last">{formatNaira(row.price_kobo)}</span>
            <Chip bps={row.change_bps} big />
            {q && (
              <span className="term-range muted small">
                today {formatNaira(q.lowest_today_kobo)} to {formatNaira(q.highest_today_kobo)} · fee {(q.fee_bps / 100).toFixed(2)}%
              </span>
            )}
          </div>
          {days.data === null ? <p className="muted small term-empty">Reading the price record…</p> : <Candles days={days.data} />}
        </div>
        {q ? <OrderBook offers={q.offers} bids={q.bids} last={q.last_price_kobo} /> : <div className="term-book"><p className="muted small">Reading the order book…</p></div>}
      </div>
      <div className="term-actions">
        <button type="button" className="button-primary" onClick={() => bringUp("term-trade", "input")}>Buy or sell {row.ticker}</button>
        <a className="button-outline" href="#/market">The whole market</a>
        <a className="button-outline" href="#/empire">Trade for my empire</a>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The monitor
// ---------------------------------------------------------------------------

function MonitorRow({ row, on, onLoggedOut }: { row: Row; on: boolean; onLoggedOut: () => void }) {
  const days = useLoad(() => api.priceHistory(row.ticker), `terminal-days:${row.ticker}`, onLoggedOut);
  const closes = (days.data ?? []).slice(-20).map((d) => Number(d.close_kobo));
  return (
    <button type="button" className={on ? "monitor-row current" : "monitor-row"} aria-pressed={on} onClick={() => choose(row.ticker)}>
      <span className="monitor-name"><span className="mono strong">{row.ticker}</span><span className="muted small">{row.name}</span></span>
      <Trend values={closes} way={wayOf(row.change_bps)} />
      <span className="mono">{formatNaira(row.price_kobo)}</span>
      <Chip bps={row.change_bps} />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Money on the move
// ---------------------------------------------------------------------------

// Where each city stands on the drawing: roughly where it stands in the country.
const PLACE: Record<string, { x: number; y: number; anchor: "start" | "end" }> = {
  Lagos: { x: 96, y: 232, anchor: "start" }, Abuja: { x: 268, y: 138, anchor: "start" }, "Port Harcourt": { x: 300, y: 282, anchor: "start" },
  Aba: { x: 372, y: 236, anchor: "start" }, Kano: { x: 338, y: 52, anchor: "start" },
};

function MoneyMap({ onLoggedOut }: { onLoggedOut: () => void }) {
  const flows = useLoad(api.flows, "terminal-flows", onLoggedOut);
  const d = flows.data;
  if (d === null) return <Panel title="Money on the move"><p className="muted small">Reading the quarter…</p></Panel>;
  if (d.cities.length === 0) {
    return <Panel title="Money on the move"><p className="muted small">No quarter has closed yet. The map fills in when the first one does.</p></Panel>;
  }
  const centre = PLACE[d.capital];
  const biggest = Math.max(1, ...d.cities.flatMap((c) => [Number(c.taxes_kobo), Number(c.government_kobo)]));
  const mostSpent = Math.max(1, ...d.cities.map((c) => Number(c.spending_kobo)));
  const width = (kobo: string) => 1.2 + (Number(kobo) * 5.5) / biggest;
  const others = d.cities.filter((c) => c.name !== d.capital && PLACE[c.name]);
  // Two lines between a city and the capital, bowed apart so that neither hides the other.
  const curve = (c: CityFlow, bow: number) => {
    const p = PLACE[c.name];
    const mx = (p.x + centre.x) / 2, my = (p.y + centre.y) / 2;
    const dx = centre.x - p.x, dy = centre.y - p.y, long = Math.hypot(dx, dy) || 1;
    return `M${p.x} ${p.y} Q ${mx - (dy / long) * bow} ${my + (dx / long) * bow} ${centre.x} ${centre.y}`;
  };
  return (
    <Panel title="Money on the move" aside={d.period_label ?? undefined}>
      <div className="term-money">
      <svg className="term-map" viewBox="0 0 520 320" role="img"
           aria-label={`Money between the five cities in ${d.period_label}: company tax flowing to the Government in ${d.capital}, and the Government's money flowing back to households. The table underneath has every figure.`}>
        <defs><pattern id="term-dots" width="14" height="14" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" /></pattern></defs>
        <rect className="map-ground" width="520" height="320" fill="url(#term-dots)" />
        {others.map((c) => (
          <g key={c.name}>
            <path className="flow flow-tax" d={curve(c, 16)} strokeWidth={width(c.taxes_kobo)} />
            <path className="flow flow-spend" d={curve(c, -16)} strokeWidth={width(c.government_kobo)} />
          </g>
        ))}
        {d.cities.filter((c) => PLACE[c.name]).map((c) => {
          const p = PLACE[c.name];
          const r = 6 + (Number(c.spending_kobo) * 10) / mostSpent;
          return (
            <g key={c.name}>
              <circle className={c.name === d.capital ? "map-city map-capital" : "map-city"} cx={p.x} cy={p.y} r={r} />
              <text className="map-name" x={p.x + r + 6} y={p.y + 1}>{c.name}</text>
              <text className="map-note" x={p.x + r + 6} y={p.y + 14}>{formatCompact(c.spending_kobo)} spent</text>
            </g>
          );
        })}
      </svg>
      <div className="term-money-side">
      <div className="map-key small">
        <span><span className="key-line key-tax" /> company tax, to the Government</span>
        <span><span className="key-line key-spend" /> the Government&rsquo;s money, to households</span>
        <span className="muted">A thicker line is more money; a bigger city spent more.</span>
      </div>
      <div className="table-scroll" tabIndex={0}>
        <table className="dense">
          <thead><tr><th scope="col">City</th><th scope="col" className="num">Spent</th><th scope="col" className="num">Wages</th><th scope="col" className="num">Tax paid</th><th scope="col" className="num">From Government</th><th scope="col" className="num">Jobs</th></tr></thead>
          <tbody>{d.cities.map((c) => (
            <tr key={c.name}><th scope="row">{c.name}</th><td className="num mono">{formatCompact(c.spending_kobo)}</td><td className="num mono">{formatCompact(c.wages_kobo)}</td>
              <td className="num mono">{formatCompact(c.taxes_kobo)}</td><td className="num mono">{formatCompact(c.government_kobo)}</td><td className="num mono">{c.jobs.toLocaleString("en-NG")}</td></tr>
          ))}</tbody>
        </table>
      </div>
      </div>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Every industry's day
// ---------------------------------------------------------------------------

function heatClass(bps: number): string {
  if (bps >= 200) return "heat-up-2";
  if (bps > 0) return "heat-up-1";
  if (bps === 0) return "heat-flat";
  return bps > -200 ? "heat-down-1" : "heat-down-2";
}

function Heat({ onLoggedOut }: { onLoggedOut: () => void }) {
  const list = useLoad(api.industries, "terminal-industries", onLoggedOut);
  const industries: Industry[] = [...(list.data ?? [])].sort((a, b) => Number(b.market_value_kobo) - Number(a.market_value_kobo));
  const most = Math.max(1, ...industries.map((i) => Number(i.market_value_kobo)));
  return (
    <Panel title="Every industry today" aside="a wider tile is a bigger industry">
      {list.data === null ? <p className="muted small">Reading the market…</p> : (
        <div className="term-heat">
          {industries.map((i) => (
            <a key={i.code} href="#/market" className={`heat-tile ${heatClass(i.change_bps)}`}
               style={{ flexGrow: 1 + Math.round((Number(i.market_value_kobo) * 6) / most) }}>
              <span className="heat-name">{i.name}</span>
              <span className="mono heat-move">{arrowOf(i.change_bps)} {(Math.abs(i.change_bps) / 100).toFixed(1)}%</span>
            </a>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------

type Answer = { tone: "plain" | "problem"; title?: string; text: string; example?: string; list?: { text: string; does: string }[] };

/**
 * The command line across the top of the wall: type a command, press Enter. The lines under it say what each matching
 * command would do while the player types; the arrow keys move between them and Enter or a click runs one. "/" anywhere
 * on the desk puts the cursor here.
 */
function CommandLine({ onLoggedOut }: { onLoggedOut: () => void }) {
  const tape = useLoad(api.ticker, "terminal-ticker", onLoggedOut);
  const shares = tape.data?.shares ?? [];
  const [line, setLine] = useState("");
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState(0);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const field = useRef<HTMLInputElement>(null);
  const hints = hintsFor(line, shares);

  useEffect(() => {
    function slash(event: globalThis.KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target && (["input", "textarea", "select"].includes(target.tagName.toLowerCase()) || target.isContentEditable);
      if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        field.current?.focus();
      }
    }
    window.addEventListener("keydown", slash);
    return () => window.removeEventListener("keydown", slash);
  }, []);

  function run(text: string) {
    const command: Command = readCommand(text, shares.map((s) => s.ticker));
    const name = (code: string) => shares.find((s) => s.ticker === code)?.name ?? code;
    setOpen(false);
    switch (command.kind) {
      case "nothing": return;
      case "show":
        choose(command.ticker);
        setAnswer({ tone: "plain", text: `${name(command.ticker)} is on the wall.` });
        bringUp("term-company");
        break;
      case "trade": {
        fillOrder(command.ticker, command.side, command.quantity, command.price_kobo);
        const at = command.price_kobo === null ? "" : ` at ${formatNaira(String(command.price_kobo))} each`;
        setAnswer({ tone: "plain", text: `The order form is filled in: ${command.side} ${command.quantity.toLocaleString("en-NG")} ${name(command.ticker)} shares${at}. Check it, then press the button to send it. Nothing is sent until you do.` });
        bringUp("term-trade", "button[type=submit]");
        break;
      }
      case "ripple":
        choose(command.ticker);
        setAnswer({ tone: "plain", text: `Why ${name(command.ticker)} moved is beside the wall.` });
        bringUp("term-ripple");
        break;
      case "page":
        window.location.hash = command.href;
        break;
      case "help":
        setAnswer({ tone: "plain", title: command.word, text: command.means, example: command.example });
        break;
      case "help-list":
        setAnswer({ tone: "plain", title: "What you can type", text: "Every command is also a button somewhere on the screen.", list: hintsFor("", shares) });
        break;
      case "unknown":
        setAnswer({ tone: "problem", text: command.message });
        return;
    }
    setLine("");
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    run(open && hints[at] && line.trim() && hints[at].text.toUpperCase().startsWith(line.trim().toUpperCase()) && hints[at].text.toUpperCase() !== line.trim().toUpperCase()
      ? hints[at].text : line);
  }
  function keys(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setAt((a) => Math.min(hints.length - 1, a + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setAt((a) => Math.max(0, a - 1)); }
    else if (event.key === "Escape") { setOpen(false); setAnswer(null); }
    else if (event.key === "Tab" && open && hints[at] && line.trim()) { event.preventDefault(); setLine(hints[at].text + " "); }
  }

  return (
    <section className="cmd" aria-label="The command line">
      <form className="cmd-form" onSubmit={submit} role="search">
        <span className="cmd-prompt mono" aria-hidden="true">&gt;</span>
        <input ref={field} className="cmd-input mono" value={line} spellCheck={false} autoComplete="off"
               aria-label="Type a command, such as HMB GO, BUY HMB 500, RIPPLE HMB or HELP P/E, and press Enter"
               aria-expanded={open && hints.length > 0} aria-controls="cmd-hints" role="combobox"
               aria-activedescendant={open && hints[at] ? `cmd-hint-${at}` : undefined}
               placeholder="Type a command: HMB GO · BUY HMB 500 · RIPPLE HMB · HELP P/E"
               onFocus={() => setOpen(true)} onBlur={() => window.setTimeout(() => setOpen(false), 150)}
               onChange={(event) => { setLine(event.target.value); setOpen(true); setAt(0); }} onKeyDown={keys} />
        <span className="cmd-key mono small" aria-hidden="true">{line ? "Enter" : "/"}</span>
      </form>
      {open && hints.length > 0 && (
        <ul className="cmd-hints" id="cmd-hints" role="listbox">
          {hints.map((h, i) => (
            <li key={h.text} id={`cmd-hint-${i}`} role="option" aria-selected={i === at} className={i === at ? "cmd-hint on" : "cmd-hint"}
                onMouseDown={(event) => { event.preventDefault(); run(h.text); }} onMouseEnter={() => setAt(i)}>
              <span className="mono cmd-hint-text">{h.text}</span><span className="cmd-hint-does">{h.does}</span>
            </li>
          ))}
        </ul>
      )}
      {answer && (
        <div className={answer.tone === "problem" ? "cmd-answer cmd-problem" : "cmd-answer"} role="status">
          <div className="cmd-answer-text">
            {answer.title && <span className="mono strong cmd-answer-title">{answer.title}</span>}
            <span>{answer.text}</span>
            {answer.example && <span className="muted small">For example: {answer.example}</span>}
            {answer.list && (
              <ul className="cmd-list">
                {answer.list.map((h) => <li key={h.text}><button type="button" className="mono link-button" onClick={() => { setLine(h.text); field.current?.focus(); }}>{h.text}</button> <span className="muted">{h.does}</span></li>)}
              </ul>
            )}
          </div>
          <button type="button" className="button-quiet small" onClick={() => setAnswer(null)} aria-label="Close this answer">✕</button>
        </div>
      )}
    </section>
  );
}

export function TerminalWork({ onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const monitor = useMonitor(onLoggedOut);
  const picked = useChosen();
  const row = monitor.showing(picked);
  return (
    <>
      <CommandLine onLoggedOut={onLoggedOut} />
      {row && <div id="term-company"><CompanyBoard key={row.ticker} row={row} onLoggedOut={onLoggedOut} /></div>}
      <div className="term-pair">
        <Panel title="Monitor" aside={monitor.mine ? "your watchlist" : "today's biggest moves"}>
          {!monitor.ready && <p className="muted small">Reading the market…</p>}
          {monitor.ready && monitor.rows.length === 0 && <p className="muted small">No share has a price yet.</p>}
          <div className="monitor">
            {monitor.rows.map((r) => <MonitorRow key={r.ticker} row={r} on={row?.ticker === r.ticker} onLoggedOut={onLoggedOut} />)}
          </div>
          <p className="muted small monitor-foot">Choose a row and the whole wall follows it: the chart, the order book and the reasons.</p>
        </Panel>
        <Heat onLoggedOut={onLoggedOut} />
      </div>
      <MoneyMap onLoggedOut={onLoggedOut} />
    </>
  );
}

// ---------------------------------------------------------------------------
// The rail: why it moved, the duel, the wire
// ---------------------------------------------------------------------------

function Ripple({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const why = useLoad(() => api.why(ticker), `terminal-why:${ticker}`, onLoggedOut);
  const w = why.data;
  return (
    <Panel title={`Why ${ticker} moved`} aside="cause, then effect">
      {w === null ? <p className="muted small">Reading the record…</p> : (
        <>
          <p className="ripple-summary">{w.summary}</p>
          <ol className="ripple">
            {w.reasons.map((reason, i) => <li key={i}><span className="ripple-dot" aria-hidden="true" /><span>{reason}</span></li>)}
            {w.valuation_reasons.map((reason, i) => <li key={`v${i}`} className="ripple-value"><span className="ripple-dot" aria-hidden="true" /><span>{reason}</span></li>)}
          </ol>
          {w.reasons.length === 0 && w.valuation_reasons.length === 0 && <p className="muted small">Nothing on the record has moved it today.</p>}
          <a className="button-outline ripple-more" href={`#/companies/${ticker}`}>Follow the whole chain</a>
        </>
      )}
    </Panel>
  );
}

/**
 * The duel: your empire against the one next to it in the league (without an empire, the two at the top), on the
 * four things the league publishes about every empire, and on this year's competition points once any are scored.
 */
function Duel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const league = useLoad(api.empires, "terminal-league", onLoggedOut);
  const page = useLoad(api.competition, "terminal-competition", onLoggedOut);
  if (league.data === null) return <Panel title="The duel"><p className="muted small">Reading the league…</p></Panel>;
  const divisions = league.data.directory.divisions;
  const table: DivisionRow[] = (divisions.find((d) => d.empires.some((e) => e.yours)) ?? divisions[0])?.empires ?? [];
  const mine = table.findIndex((e) => e.yours);
  if (table.length < 2) return <Panel title="The duel"><p className="muted small">The league needs two empires before there is a duel.</p></Panel>;
  const you = mine >= 0 ? table[mine] : table[0];
  const them = mine > 0 ? table[mine - 1] : table[1];
  const scores = page.data?.ready ? page.data.scoreboard : [];
  const scored = (name: string) => scores.find((s: CompetitionScore) => s.empire === name)?.total ?? 0;
  const gap = you.points - them.points;
  const parts: { label: string; a: number; b: number; shownA: string; shownB: string }[] = [
    { label: "League points", a: you.points, b: them.points, shownA: String(you.points), shownB: String(them.points) },
    { label: "Competition points", a: scored(you.name), b: scored(them.name), shownA: String(scored(you.name)), shownB: String(scored(them.name)) },
    { label: "Worth", a: Number(you.worth_kobo), b: Number(them.worth_kobo), shownA: formatCompact(you.worth_kobo), shownB: formatCompact(them.worth_kobo) },
    { label: "Trust", a: you.trust, b: them.trust, shownA: String(you.trust), shownB: String(them.trust) },
    { label: "Reputation", a: you.reputation ?? 50, b: them.reputation ?? 50, shownA: String(you.reputation ?? 50), shownB: String(them.reputation ?? 50) },
  ];
  return (
    <Panel title="The duel" aside={mine >= 0 ? "the empire next to yours" : "the race at the top"}>
      <div className="duel-heads">
        <div className="duel-side duel-you"><span className="small">{mine >= 0 ? `${you.name} (yours)` : you.name}</span><span className="mono duel-score">{you.points}</span></div>
        <span className={`mono small ${gap > 0 ? "change-up" : gap < 0 ? "change-down" : "muted"}`}>{gap === 0 ? "level" : `${Math.abs(gap)} ${gap > 0 ? "ahead" : "behind"}`}</span>
        <div className="duel-side duel-them"><span className="small">{them.name}</span><span className="mono duel-score">{them.points}</span></div>
      </div>
      {parts.map(({ label, a, b, shownA, shownB }) => {
        const share = a + b === 0 ? 50 : Math.min(96, Math.max(4, Math.round((a * 100) / (a + b))));
        return (
          <div key={label} className="duel-part">
            <div className="duel-figures mono small"><span>{shownA}</span><span className="muted">{label}</span><span>{shownB}</span></div>
            <div className="duel-bar" role="img" aria-label={`${label}: ${you.name} ${shownA}, ${them.name} ${shownB}`}>
              <span className="duel-bar-you" style={{ width: `${share}%` }} /><span className="duel-bar-them" />
            </div>
          </div>
        );
      })}
      <p className="small duel-foot">
        {mine < 0
          ? <>You are not in an empire yet, so these are the two at the top. <a href="#/empire">Join one</a> and the duel is yours.</>
          : <>Points come from tasks, forecasts and mandates. <a href="#/competition">See what is open</a>.</>}
      </p>
    </Panel>
  );
}

function Wire({ onLoggedOut }: { onLoggedOut: () => void }) {
  const list = useLoad(() => api.news({ limit: 7 }), "terminal-wire", onLoggedOut);
  const items = list.data?.items ?? [];
  return (
    <Panel title="The wire" aside={<a href="#/news">all of it</a>}>
      {list.data === null && <p className="muted small">Reading the wire…</p>}
      {list.data !== null && items.length === 0 && <p className="muted small">Nothing written yet today.</p>}
      <ul className="wire">
        {items.map((item, i) => (
          <li key={`${item.story}-${i}`}>
            <span className="mono muted small">d{item.day}</span>
            <span>
              <a href="#/news" className="wire-head">{item.headline}</a>
              <span className="wire-foot small">
                <span className="muted">{item.outlet}</span>
                {item.tickers.slice(0, 3).map((t) => <button key={t} type="button" className="wire-ticker mono" onClick={() => choose(t)}>{t}</button>)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function TerminalRail({ onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const monitor = useMonitor(onLoggedOut);
  const picked = useChosen();
  const ticker = monitor.showing(picked)?.ticker;
  const filled = usePreset();
  return (
    <>
      {ticker && (
        <div id="term-trade">
          <TradePanel key={ticker} ticker={ticker} layout="rail" onLoggedOut={onLoggedOut} onTraded={() => undefined}
                      preset={filled && filled.ticker === ticker ? filled : null} />
        </div>
      )}
      {ticker && <div id="term-ripple"><Ripple key={ticker} ticker={ticker} onLoggedOut={onLoggedOut} /></div>}
      <Duel onLoggedOut={onLoggedOut} />
      <Wire onLoggedOut={onLoggedOut} />
    </>
  );
}
