// The Floor, slice 2 (owner, 16 November 2026): price requests between clients and banks, as the owner played it in the
// investing challenge. A client asks one to five banks for a price with a countdown; the prices land live on the client's
// screen; the client takes the best. A banker opens a desk, sees each request with the market and their own holdings,
// and answers with prices that hold for some seconds. A request reaching a banker's desk pops up wherever they are.
// Every figure comes from the server; the countdowns are the server's time.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type FloorIncoming, type FloorMyRequest, type FloorRequests, type Kobo } from "./api";
import { asKobo } from "./Empire";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { useLivePushes } from "./pushes";
import { Panel } from "./Shell";
import { play } from "./sound";

const SIDE_WORDS: Record<string, string> = { buy: "Buy", sell: "Sell", two_way: "Both ways" };
const nairaInput = (k: Kobo | null | undefined) => (k ? (Number(k) / 100).toFixed(2) : "");

/** The server's clock, ticking every quarter second between loads, for the countdowns. */
function useClock(serverNow: string | undefined): number {
  const offset = useRef(0);
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => { if (serverNow) offset.current = new Date(serverNow).getTime() - Date.now(); }, [serverNow]);
  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 250);
    return () => window.clearInterval(id);
  }, []);
  return tick + offset.current;
}

const secondsLeft = (iso: string, now: number) => Math.max(0, Math.ceil((new Date(iso).getTime() - now) / 1000));

/** The requests page, read again the moment something changes, and every two seconds while anything is open. */
export function useFloorRequests(onLoggedOut: () => void, quiet = false) {
  const page = useLoad(api.floorRequests, "floor-requests", onLoggedOut);
  const [fresh, setFresh] = useState<FloorRequests | null>(null);
  const d = fresh ?? page.data;
  useEffect(() => { if (page.data) setFresh(null); }, [page.data]);
  const reload = page.reload;
  useLivePushes(reload, ["floor"]);
  const busy = Boolean(d && (d.mine.some((r) => r.status === "open") || d.incoming.some((r) => r.status === "open")));
  useEffect(() => {
    const id = window.setInterval(reload, quiet ? 60_000 : busy ? 2_000 : 20_000);
    return () => window.clearInterval(id);
  }, [busy, quiet, reload]);
  return { d, reload, setFresh, error: page.error, loading: page.loading };
}

function useAct(setFresh: (d: FloorRequests) => void, onLoggedOut: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const run = useCallback(async (ask: () => Promise<FloorRequests>, done: string | ((d: FloorRequests) => string)) => {
    setBusy(true); setError(null); setNotice(null);
    try {
      const answer = await ask();
      setFresh(answer);
      setNotice(typeof done === "string" ? done : done(answer));
      return true;
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) { onLoggedOut(); return false; }
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server.");
      return false;
    } finally {
      setBusy(false);
    }
  }, [setFresh, onLoggedOut]);
  return { busy, error, notice, run };
}
type Act = ReturnType<typeof useAct>;

// ---------------------------------------------------------------------------
// The client's side: ask the banks, and the live quotes
// ---------------------------------------------------------------------------

function AskForm({ d, ticker, act }: { d: FloorRequests; ticker: string; act: Act }) {
  const [side, setSide] = useState<"buy" | "sell" | "two_way">("buy");
  const [count, setCount] = useState("");
  const [seconds, setSeconds] = useState(30);
  const defaults = useMemo(() => {
    const players = d.desks.filter((x) => x.kind === "player").map((x) => x.key);
    const computers = d.desks.filter((x) => x.kind === "computer").map((x) => x.key);
    return [...players, ...computers].slice(0, Math.min(3 + players.length, d.limits.most_desks));
  }, [d.desks, d.limits.most_desks]);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const picked = (chosen ?? defaults).filter((k) => d.desks.some((x) => x.key === k));
  const n = Number(count.replace(/[,\s]/g, ""));
  const ok = Number.isInteger(n) && n > 0 && picked.length > 0 && picked.length <= d.limits.most_desks;
  const toggle = (k: string) => {
    const now = picked.includes(k) ? picked.filter((x) => x !== k) : [...picked, k];
    setChosen(now.slice(0, d.limits.most_desks));
  };
  const [least, most] = d.limits.window;
  const windows = [15, 30, 45, 60].filter((w) => w >= least && w <= most);
  return (
    <form className="floor-ask" onSubmit={(e) => {
      e.preventDefault();
      if (ok) act.run(() => api.floorAsk({ ticker, side, quantity: n, seconds, desks: picked }), `Asked ${picked.length} bank${picked.length > 1 ? "s" : ""} for a price on ${n.toLocaleString("en-NG")} ${ticker}.`)
        .then((sent) => sent && setCount(""));
    }}>
      <div className="floor-ask-row">
        <span className="floor-ex-ticker mono">{ticker}</span>
        <div className="floor-seg" role="radiogroup" aria-label="Buy or sell">
          {(["buy", "sell", "two_way"] as const).map((s) => (
            <button type="button" key={s} role="radio" aria-checked={side === s} className={side === s ? "on" : ""} onClick={() => setSide(s)}
                    title={s === "two_way" ? "Ask for a buying and a selling price without saying which you want" : undefined}>{SIDE_WORDS[s]}</button>
          ))}
        </div>
      </div>
      <div className="floor-ask-row">
        <input className="mono" inputMode="numeric" aria-label="How many shares" placeholder="Shares, e.g. 3000" value={count} onChange={(e) => setCount(e.target.value)} />
        <label className="small floor-inline">Banks have
          <select value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}>{windows.map((w) => <option key={w} value={w}>{w} seconds</option>)}</select>
        </label>
      </div>
      <fieldset className="floor-desks">
        <legend className="small muted">Ask up to {d.limits.most_desks} banks</legend>
        {d.desks.map((x) => (
          <label key={x.key} className={picked.includes(x.key) ? "floor-desk on" : "floor-desk"}>
            <input type="checkbox" checked={picked.includes(x.key)} onChange={() => toggle(x.key)} disabled={!picked.includes(x.key) && picked.length >= d.limits.most_desks} />
            <span>{x.name}</span>
            {x.kind === "player" && <span className="floor-player-tag">player</span>}
            {x.failed > 0 && <span className="small change-down" title="Deals this desk could not deliver"> · failed {x.failed}</span>}
          </label>
        ))}
      </fieldset>
      <button type="submit" className="button-primary" disabled={!ok || act.busy || d.market_state !== "open"}>
        {d.market_state === "open" ? "Ask for prices" : "The market is closed"}
      </button>
    </form>
  );
}

function LiveQuotes({ r, now, act }: { r: FloorMyRequest; now: number; act: Act }) {
  const left = secondsLeft(r.quotes_until, now);
  const live = r.quotes.filter((q) => q.status === "live" && secondsLeft(q.valid_until, now) > 0);
  const bestOffer = live.filter((q) => q.offer).sort((a, b) => Number(a.offer) - Number(b.offer))[0]?.id;
  const bestBid = live.filter((q) => q.bid).sort((a, b) => Number(b.bid) - Number(a.bid))[0]?.id;
  const answered = new Set(r.quotes.map((q) => q.desk));
  const waiting = r.asked.filter((x) => !answered.has(x));
  return (
    <div className="floor-request">
      <div className="floor-request-head">
        <strong className="mono">{SIDE_WORDS[r.side]} {r.quantity.toLocaleString("en-NG")} {r.ticker}</strong>
        <span className="small muted">{left > 0 ? `banks have ${left}s` : "banks' time is up"}</span>
        <button className="button-outline small" disabled={act.busy} onClick={() => act.run(() => api.floorPass(r.id), "You passed.")}>Pass</button>
      </div>
      <table className="dense floor-table floor-quotes">
        <thead><tr><th scope="col">Bank</th><th scope="col" className="num">Buys at</th><th scope="col" className="num">Sells at</th><th scope="col" className="num">Holds</th><th scope="col"><span className="sr-only">Take</span></th></tr></thead>
        <tbody>
          {r.quotes.length === 0 && <tr><td colSpan={5} className="muted small">Waiting for the banks' prices…</td></tr>}
          {r.quotes.map((q) => {
            const holds = secondsLeft(q.valid_until, now);
            const on = q.status === "live" && holds > 0;
            return (
              <tr key={q.id} className={on ? "" : "floor-gone"}>
                <th scope="row">{q.desk}{q.kind === "player" && <span className="floor-player-tag">player</span>}{q.failed > 0 && <span className="small change-down"> · failed {q.failed}</span>}</th>
                <td className={`num mono ${q.id === bestBid ? "floor-best" : ""}`}>{q.bid ? formatNaira(q.bid) : "—"}</td>
                <td className={`num mono ${q.id === bestOffer ? "floor-best" : ""}`}>{q.offer ? formatNaira(q.offer) : "—"}</td>
                <td className="num mono">{on ? `${holds}s` : q.status === "live" ? "expired" : q.status}</td>
                <td className="floor-take">
                  {on && q.offer && r.side !== "sell" && <button className="floor-take-buy" disabled={act.busy}
                    onClick={() => act.run(() => api.floorTake({ request_id: r.id, quote_id: q.id, side: "buy" }),
                      (a) => { play("trade"); const x = (a as unknown as { result: { price: Kobo; quantity: number; desk: string } }).result; return `Bought ${x.quantity.toLocaleString("en-NG")} ${r.ticker} at ${formatNaira(x.price)} from ${x.desk}.`; })}>Buy</button>}
                  {on && q.bid && r.side !== "buy" && <button className="floor-take-sell" disabled={act.busy}
                    onClick={() => act.run(() => api.floorTake({ request_id: r.id, quote_id: q.id, side: "sell" }),
                      (a) => { play("trade"); const x = (a as unknown as { result: { price: Kobo; quantity: number; desk: string } }).result; return `Sold ${x.quantity.toLocaleString("en-NG")} ${r.ticker} at ${formatNaira(x.price)} to ${x.desk}.`; })}>Sell</button>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {waiting.length > 0 && left > 0 && <p className="small muted">Still waiting for: {waiting.join(", ")}.</p>}
    </div>
  );
}

function Closed({ list }: { list: FloorMyRequest[] }) {
  if (list.length === 0) return null;
  return (
    <details className="floor-old">
      <summary className="small">Old quotes ({list.length})</summary>
      <table className="dense floor-table">
        <thead><tr><th scope="col">Asked</th><th scope="col">Share</th><th scope="col">Outcome</th></tr></thead>
        <tbody>{list.map((r) => (
          <tr key={r.id}>
            <td className="mono small">{SIDE_WORDS[r.side]} {r.quantity.toLocaleString("en-NG")}</td>
            <th scope="row" className="mono">{r.ticker}</th>
            <td className="small">{r.deal ? `Done at ${formatNaira(r.deal.price)} with ${r.deal.desk}` : r.status === "passed" ? "You passed" : "No deal: time ran out"}
              {r.quotes.length > 0 && <span className="muted"> · {r.quotes.length} price{r.quotes.length > 1 ? "s" : ""}</span>}</td>
          </tr>
        ))}</tbody>
      </table>
    </details>
  );
}

export type Floor = ReturnType<typeof useFloorRequests>;

export function AskPanel({ f, ticker, onTraded, onLoggedOut }: { f: Floor; ticker: string; onTraded: () => void; onLoggedOut: () => void }) {
  const act = useAct(f.setFresh, onLoggedOut);
  const now = useClock(f.d?.now);
  const done = f.d?.deals[0]?.id;
  const seen = useRef(done);
  useEffect(() => { if (done !== seen.current) { seen.current = done; onTraded(); } }, [done, onTraded]);
  if (!f.d) return <Panel title="Ask the banks" className="floor-panel"><p className="muted small">{f.error ?? "Reading the floor…"}</p></Panel>;
  const open = f.d.mine.filter((r) => r.status === "open");
  return (
    <Panel title="Ask the banks" aside="prices away from the exchange, no exchange fee" className="floor-panel floor-ask-panel">
      <AskForm d={f.d} ticker={ticker} act={act} />
      {act.error && <p className="small change-down" role="alert">{act.error}</p>}
      {act.notice && <p className="small" role="status">{act.notice}</p>}
      <div className="floor-live" aria-live="polite">{open.map((r) => <LiveQuotes key={r.id} r={r} now={now} act={act} />)}</div>
      <Closed list={f.d.mine.filter((r) => r.status !== "open")} />
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The banker's side: the desk
// ---------------------------------------------------------------------------

function QuoteForm({ r, d, act, compact = false }: { r: FloorIncoming; d: FloorRequests; act: Act; compact?: boolean }) {
  const ref = r.market.best_bid && r.market.best_offer ? null : (r.market.last ?? r.market.reference);
  const [bid, setBid] = useState(nairaInput(r.your_quote?.bid ?? r.market.best_bid ?? ref));
  const [offer, setOffer] = useState(nairaInput(r.your_quote?.offer ?? r.market.best_offer ?? ref));
  const [holds, setHolds] = useState(30);
  const wantsBid = r.side !== "buy", wantsOffer = r.side !== "sell";
  const b = wantsBid ? asKobo(bid) : null, o = wantsOffer ? asKobo(offer) : null;
  const ok = (!wantsBid || b !== null) && (!wantsOffer || o !== null) && (b === null || o === null || b < o);
  const [least, most] = d.limits.quote;
  return (
    <form className={compact ? "floor-quote-form compact" : "floor-quote-form"} onSubmit={(e) => {
      e.preventDefault();
      if (ok) act.run(() => api.floorQuote({ request_id: r.id, bid_kobo: b, offer_kobo: o, valid_seconds: holds }), "Your price is with the client.");
    }}>
      {wantsBid && <label className="small">You buy at <input className="mono" inputMode="decimal" value={bid} onChange={(e) => setBid(e.target.value)} aria-label="Your buying price, in naira" /></label>}
      {wantsOffer && <label className="small">You sell at <input className="mono" inputMode="decimal" value={offer} onChange={(e) => setOffer(e.target.value)} aria-label="Your selling price, in naira" /></label>}
      <label className="small">Holds for <select value={holds} onChange={(e) => setHolds(Number(e.target.value))}>
        {[10, 20, 30, 45, 60].filter((s) => s >= least && s <= most).map((s) => <option key={s} value={s}>{s}s</option>)}
      </select></label>
      <button type="submit" className="button-primary" disabled={!ok || act.busy}>{r.your_quote ? "Send a new price" : "Send price"}</button>
    </form>
  );
}

function Call({ r, d, now, act, compact = false }: { r: FloorIncoming; d: FloorRequests; now: number; act: Act; compact?: boolean }) {
  const left = secondsLeft(r.quotes_until, now);
  const wants = r.side === "two_way" ? "a price both ways on" : r.side === "buy" ? "to buy" : "to sell";
  return (
    <div className="floor-call">
      <div className="floor-request-head">
        <strong>{r.client}</strong>
        <span className="small">wants {wants} <span className="mono strong">{r.quantity.toLocaleString("en-NG")} {r.ticker}</span></span>
        <span className={`floor-clock mono ${left <= 5 ? "change-down" : ""}`} aria-label={`${left} seconds left`}>{left}s</span>
      </div>
      <p className="small muted floor-call-market">
        Exchange: buyers at {r.market.best_bid ? formatNaira(r.market.best_bid) : "—"}, sellers at {r.market.best_offer ? formatNaira(r.market.best_offer) : "—"}
        {r.market.last ? `, last ${formatNaira(r.market.last)}` : ""}. You hold {r.you_hold.toLocaleString("en-NG")}.
        {r.side !== "sell" && r.you_hold < r.quantity && <span className="change-down"> You must hold the shares to sell them.</span>}
      </p>
      {r.your_quote && <p className="small">Your price: {r.your_quote.bid ? `buy ${formatNaira(r.your_quote.bid)}` : ""}{r.your_quote.bid && r.your_quote.offer ? " · " : ""}{r.your_quote.offer ? `sell ${formatNaira(r.your_quote.offer)}` : ""}, holds {secondsLeft(r.your_quote.valid_until, now)}s.</p>}
      {left > 0 && <QuoteForm key={r.id} r={r} d={d} act={act} compact={compact} />}
    </div>
  );
}

export function DeskPanel({ f, onLoggedOut }: { f: Floor; onLoggedOut: () => void }) {
  const act = useAct(f.setFresh, onLoggedOut);
  const now = useClock(f.d?.now);
  if (!f.d || !f.d.is_banker) return null;
  const d = f.d;
  const open = d.incoming.filter((r) => r.status === "open" && secondsLeft(r.quotes_until, now) > 0);
  const closed = d.incoming.filter((r) => !open.includes(r)).slice(0, 8);
  return (
    <Panel title="Your desk" aside={d.desk_open ? "open: taking requests" : "closed"} className="floor-panel floor-desk-panel">
      <div className="floor-desk-switch">
        <button className={d.desk_open ? "button-outline" : "button-primary"} disabled={act.busy}
                onClick={() => act.run(() => api.floorDesk(!d.desk_open), d.desk_open ? "Your desk is closed." : "Your desk is open: requests will come to you.")}>
          {d.desk_open ? "Close the desk" : "Open the desk"}
        </button>
        <span className="small muted">Clients, players and computer, ask you for prices while it is open. You deal with your own cash and shares.{d.desk_failed > 0 ? ` Deals you could not deliver: ${d.desk_failed}, shown to clients.` : ""}</span>
      </div>
      {act.error && <p className="small change-down" role="alert">{act.error}</p>}
      {act.notice && <p className="small" role="status">{act.notice}</p>}
      {open.length === 0 ? <p className="muted small">{d.desk_open ? "No request waiting. They pop up wherever you are in the game." : "Open the desk to take requests."}</p>
        : open.map((r) => <Call key={r.id} r={r} d={d} now={now} act={act} />)}
      {closed.length > 0 && (
        <details className="floor-old">
          <summary className="small">Recent requests ({closed.length})</summary>
          <ul className="floor-outcomes small">{closed.map((r) => (
            <li key={r.id}><strong>{r.client}</strong> · {SIDE_WORDS[r.side]} {r.quantity.toLocaleString("en-NG")} {r.ticker} · <span className={r.outcome === "won" ? "change-up" : ""}>{r.outcome === "won" ? "you won it" : r.outcome ?? "no deal"}</span></li>
          ))}</ul>
        </details>
      )}
    </Panel>
  );
}

export function FloorDeals({ f }: { f: Floor }) {
  if (!f.d || f.d.deals.length === 0) return null;
  return (
    <Panel title="Your deals on the Floor" aside="newest first" className="floor-panel">
      <div className="floor-scroll-x">
        <table className="dense floor-table">
          <thead><tr><th scope="col">Time</th><th scope="col">Share</th><th scope="col">You</th><th scope="col" className="num">Shares</th><th scope="col" className="num">Price</th><th scope="col">With</th></tr></thead>
          <tbody>{f.d.deals.map((t) => (
            <tr key={t.id}>
              <td className="mono small">{new Date(t.at).toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" })}</td>
              <th scope="row" className="mono">{t.ticker}</th>
              <td className={t.bought ? "change-up" : "change-down"}>{t.bought ? "Bought" : "Sold"}{t.as === "bank" ? " (as the bank)" : ""}</td>
              <td className="num mono">{t.quantity.toLocaleString("en-NG")}</td>
              <td className="num mono">{formatNaira(t.price)}</td>
              <td className="small">{t.with}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The pop-up: a request reaching a banker's desk, wherever they are
// ---------------------------------------------------------------------------

export function FloorCalls({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [here, setHere] = useState(() => window.location.hash.startsWith("#/floor"));
  useEffect(() => {
    const look = () => setHere(window.location.hash.startsWith("#/floor"));
    window.addEventListener("hashchange", look);
    return () => window.removeEventListener("hashchange", look);
  }, []);
  const f = useFloorRequests(onLoggedOut, here);
  const act = useAct(f.setFresh, onLoggedOut);
  const now = useClock(f.d?.now);
  const [hidden, setHidden] = useState<number[]>([]);
  const open = (f.d?.incoming ?? []).filter((r) => r.status === "open" && secondsLeft(r.quotes_until, now) > 0 && !hidden.includes(r.id));
  const newest = open[0]?.id;
  const rang = useRef<number | undefined>(undefined);
  useEffect(() => { if (newest && newest !== rang.current) { rang.current = newest; play("decision"); } }, [newest]);
  if (here || !f.d || !f.d.desk_open || open.length === 0) return null;
  const r = open[0];
  return (
    <div className="floor-pop-region">
      <div className="floor-pop" role="alertdialog" aria-labelledby={`floor-pop-${r.id}`}>
        <div className="floor-pop-tag" id={`floor-pop-${r.id}`}>● Price request{open.length > 1 ? ` · ${open.length} waiting` : ""}</div>
        <Call r={r} d={f.d} now={now} act={act} compact />
        {act.error && <p className="small change-down" role="alert">{act.error}</p>}
        <div className="floor-pop-foot">
          <a href="#/floor" className="small">Open the Floor</a>
          <button className="button-outline small" onClick={() => setHidden((h) => [...h, r.id])}>Not this one</button>
        </div>
      </div>
    </div>
  );
}
