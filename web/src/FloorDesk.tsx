// The Floor, slices 2 and 3 (owner, 16 November 2026): price requests between clients and banks, as the owner played it
// in the investing challenge. A client asks one to five banks for a price (a share, a basket of shares, a block or a bond;
// for themselves or their empire) with a countdown; the prices land live; the client takes the best, or haggles. A banker
// opens a desk, sees each request with the market, their holdings and the client's record, and answers with firm or
// indicative prices. Chat between client and bank, where an agreed line becomes a deal ticket. A request reaching a
// banker's desk pops up wherever they are. Every figure comes from the server; the countdowns are the server's time.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type FloorIncoming, type FloorMyRequest, type FloorQuote, type FloorRequests, type Kobo } from "./api";
import { asKobo } from "./Empire";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { useLivePushes } from "./pushes";
import { Panel } from "./Shell";
import { play } from "./sound";

const SIDE_WORDS: Record<string, string> = { buy: "Buy", sell: "Sell", two_way: "Both ways" };
const nairaInput = (k: Kobo | null | undefined) => (k ? (Number(k) / 100).toFixed(2) : "");
const pct = (bps: number | null | undefined, digits = 2) => (bps === null || bps === undefined ? "—" : `${(bps / 100).toFixed(digits)}%`);
const signedBps = (bps: number) => `${bps > 0 ? "+" : bps < 0 ? "−" : ""}${(Math.abs(bps) / 100).toFixed(2)}%`;
const lagosTime = (iso: string) => new Date(iso).toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" });

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
  const busy = Boolean(d && (d.mine.some((r) => r.status === "open") || d.incoming.some((r) => r.status === "open")
    || d.chat.tickets.some((t) => t.status === "open")));
  useEffect(() => {
    const id = window.setInterval(reload, quiet ? 60_000 : busy ? 2_000 : 20_000);
    return () => window.clearInterval(id);
  }, [busy, quiet, reload]);
  return { d, reload, setFresh, error: page.error, loading: page.loading };
}
export type Floor = ReturnType<typeof useFloorRequests>;

function useAct(setFresh: (d: FloorRequests) => void, onLoggedOut: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const run = useCallback(async (ask: () => Promise<FloorRequests>, done: string | ((d: FloorRequests & { result?: unknown }) => string)) => {
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
type Result = { price?: Kobo | null; margin_bps?: number | null; what?: string; desk?: string; bought?: boolean; waiting?: boolean; declined?: boolean };
const resultWords = (a: { result?: unknown }) => {
  const x = (a.result ?? {}) as Result;
  if (x.waiting) return "Sent: waiting for the bank's answer.";
  if (x.declined) return `${x.desk ?? "The bank"} declined.`;
  play("trade");
  return `${x.bought ? "Bought" : "Sold"} ${x.what ?? ""} ${x.price ? `at ${formatNaira(x.price)}` : x.margin_bps !== null && x.margin_bps !== undefined ? `at ${signedBps(x.margin_bps)} on the market` : ""} with ${x.desk}.`;
};

// ---------------------------------------------------------------------------
// The client's side: ask the banks, and the live quotes
// ---------------------------------------------------------------------------

type Mode = "share" | "basket" | "bond";

function AskForm({ d, ticker, act }: { d: FloorRequests; ticker: string; act: Act }) {
  const [mode, setMode] = useState<Mode>("share");
  const [side, setSide] = useState<"buy" | "sell" | "two_way">("buy");
  const [count, setCount] = useState("");
  const [seconds, setSeconds] = useState(30);
  const [forEmpire, setForEmpire] = useState(false);
  const [block, setBlock] = useState(false);
  const [legs, setLegs] = useState<{ ticker: string; count: string }[]>([{ ticker, count: "" }, { ticker: "", count: "" }]);
  const [bond, setBond] = useState("");
  const bonds = useLoad(() => (mode === "bond" ? api.floorBonds() : Promise.resolve({ bonds: [] })), `floor-bonds:${mode}`, () => undefined);
  const defaults = useMemo(() => {
    const players = d.desks.filter((x) => x.kind === "player").map((x) => x.key);
    const computers = d.desks.filter((x) => x.kind === "computer").map((x) => x.key);
    return [...players, ...computers].slice(0, Math.min(3 + players.length, d.limits.most_desks));
  }, [d.desks, d.limits.most_desks]);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const picked = (chosen ?? defaults).filter((k) => d.desks.some((x) => x.key === k));
  const n = Number(count.replace(/[,\s]/g, ""));
  const basket = legs.filter((l) => /^[A-Z]{3}$/.test(l.ticker.trim().toUpperCase()) && Number(l.count.replace(/[,\s]/g, "")) > 0)
    .map((l) => ({ ticker: l.ticker.trim().toUpperCase(), quantity: Number(l.count.replace(/[,\s]/g, "")) }));
  const sideOk = mode !== "basket" || side !== "two_way";
  const ok = picked.length > 0 && picked.length <= d.limits.most_desks && sideOk
    && (mode === "basket" ? basket.length >= 2 : Number.isInteger(n) && n > 0) && (mode !== "bond" || bond !== "");
  const toggle = (k: string) => setChosen((picked.includes(k) ? picked.filter((x) => x !== k) : [...picked, k]).slice(0, d.limits.most_desks));
  const [least, most] = d.limits.window;
  const windows = [15, 30, 45, 60].filter((w) => w >= least && w <= most);
  function send() {
    const common = { seconds, desks: picked, for_empire: forEmpire };
    const what = mode === "basket" ? `a basket of ${basket.length} shares` : mode === "bond" ? `${n.toLocaleString("en-NG")} ${bond}` : `${n.toLocaleString("en-NG")} ${ticker}`;
    act.run(() => mode === "basket" ? api.floorAskBasket({ ...common, legs: basket, side: side === "two_way" ? "buy" : side })
      : mode === "bond" ? api.floorAskBond({ ...common, code: bond, side, units: n })
      : api.floorAsk({ ...common, ticker, side, quantity: n, block }),
      `Asked ${picked.length} bank${picked.length > 1 ? "s" : ""} for a price on ${what}.`).then((sent) => sent && setCount(""));
  }
  return (
    <form className="floor-ask" onSubmit={(e) => { e.preventDefault(); if (ok) send(); }}>
      <div className="floor-ask-row">
        <div className="floor-seg" role="radiogroup" aria-label="What to ask for">
          {(["share", "basket", "bond"] as const).map((m) => (
            <button type="button" key={m} role="radio" aria-checked={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>
              {m === "share" ? "A share" : m === "basket" ? "A basket" : "A bond"}
            </button>
          ))}
        </div>
        <div className="floor-seg" role="radiogroup" aria-label="Buy or sell">
          {(["buy", "sell", "two_way"] as const).filter((s) => mode !== "basket" || s !== "two_way").map((s) => (
            <button type="button" key={s} role="radio" aria-checked={side === s} className={side === s ? "on" : ""} onClick={() => setSide(s)}
                    title={s === "two_way" ? "Ask for a buying and a selling price without saying which you want" : undefined}>{SIDE_WORDS[s]}</button>
          ))}
        </div>
      </div>
      {mode === "share" && (
        <div className="floor-ask-row">
          <span className="floor-ex-ticker mono">{ticker}</span>
          <input className="mono" inputMode="numeric" aria-label="How many shares" placeholder="Shares, e.g. 3000" value={count} onChange={(e) => setCount(e.target.value)} />
          <label className="small floor-inline" title={`A very large deal (up to 5% of the company, at least ${formatNaira(d.limits.block_least)}), reported to the market once done, without names`}>
            <input type="checkbox" checked={block} onChange={(e) => setBlock(e.target.checked)} /> A block
          </label>
        </div>
      )}
      {mode === "basket" && (
        <div className="floor-legs">
          {legs.map((l, i) => (
            <div key={i} className="floor-ask-row">
              <input className="mono floor-leg-ticker" aria-label={`Share ${i + 1}`} placeholder="Code" maxLength={3} value={l.ticker}
                     onChange={(e) => setLegs(legs.map((x, j) => (j === i ? { ...x, ticker: e.target.value.toUpperCase() } : x)))} />
              <input className="mono" inputMode="numeric" aria-label={`How many of share ${i + 1}`} placeholder="Shares" value={l.count}
                     onChange={(e) => setLegs(legs.map((x, j) => (j === i ? { ...x, count: e.target.value } : x)))} />
            </div>
          ))}
          {legs.length < d.limits.basket_most && <button type="button" className="button-outline small" onClick={() => setLegs([...legs, { ticker: "", count: "" }])}>Add a share</button>}
          <p className="small muted">The banks price the whole basket as one margin over the market (or under it, when you sell).</p>
        </div>
      )}
      {mode === "bond" && (
        <div className="floor-ask-row">
          <select aria-label="Which bond" value={bond} onChange={(e) => setBond(e.target.value)}>
            <option value="">Choose a bond…</option>
            {(bonds.data?.bonds ?? []).map((b) => <option key={b.code} value={b.code}>{b.name} · fair {formatNaira(b.fair)}</option>)}
          </select>
          <input className="mono" inputMode="numeric" aria-label="How many bonds" placeholder="Bonds" value={count} onChange={(e) => setCount(e.target.value)} />
        </div>
      )}
      <div className="floor-ask-row">
        <label className="small floor-inline">Banks have
          <select value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}>{windows.map((w) => <option key={w} value={w}>{w} seconds</option>)}</select>
        </label>
        {d.can_trade_for_empire && <label className="small floor-inline"><input type="checkbox" checked={forEmpire} onChange={(e) => setForEmpire(e.target.checked)} /> For my empire</label>}
      </div>
      <fieldset className="floor-desks">
        <legend className="small muted">Ask up to {d.limits.most_desks} banks</legend>
        {d.desks.map((x) => (
          <label key={x.key} className={picked.includes(x.key) ? "floor-desk on" : "floor-desk"}>
            <input type="checkbox" checked={picked.includes(x.key)} onChange={() => toggle(x.key)} disabled={!picked.includes(x.key) && picked.length >= d.limits.most_desks} />
            <span>{x.name}</span>
            {x.kind === "player" && <span className="floor-player-tag">player</span>}
            {x.axes.map((a) => <span key={a.ticker} className="floor-axe" title="What this desk wants">{a.side === "buy" ? "buys" : "sells"} {a.ticker}</span>)}
            {(x.failed > 0 || x.backed_away > 0) && <span className="small change-down" title="Deals this desk could not deliver, and prices it backed away from"> · failed {x.failed}, backed away {x.backed_away}</span>}
          </label>
        ))}
      </fieldset>
      <button type="submit" className="button-primary" disabled={!ok || act.busy || d.market_state !== "open"}>
        {d.market_state === "open" ? "Ask for prices" : "The market is closed"}
      </button>
    </form>
  );
}

function priceCell(r: FloorMyRequest, q: FloorQuote, side: "bid" | "offer") {
  if (r.kind === "basket") return q.margin_bps !== null && ((side === "offer" && r.side === "buy") || (side === "bid" && r.side === "sell")) ? `${signedBps(q.margin_bps)} on market` : "—";
  const p = q[side];
  if (!p) return "—";
  const y = side === "bid" ? q.bid_yield_bps : q.offer_yield_bps;
  return <>{formatNaira(p)}{y !== null && <span className="muted small"> · {pct(y)}</span>}</>;
}

function CounterBox({ r, q, act, onDone }: { r: FloorMyRequest; q: FloorQuote; act: Act; onDone: () => void }) {
  const side: "buy" | "sell" = r.side === "sell" ? "sell" : r.side === "buy" ? "buy" : q.offer ? "buy" : "sell";
  const [s, setS] = useState<"buy" | "sell">(side);
  const [value, setValue] = useState("");
  const kobo = asKobo(value);
  const margin = Math.round(Number(value.replace("%", "")) * 100);
  const ok = r.kind === "basket" ? value.trim() !== "" && Number.isFinite(margin) : kobo !== null;
  return (
    <form className="floor-counter" onSubmit={(e) => {
      e.preventDefault();
      if (ok) act.run(() => api.floorCounter({ request_id: r.id, quote_id: q.id, side: s, ...(r.kind === "basket" ? { margin_bps: margin } : { price_kobo: kobo! }) }), resultWords).then(onDone);
    }}>
      {r.side === "two_way" && <select value={s} onChange={(e) => setS(e.target.value as "buy" | "sell")} aria-label="Counter to buy or to sell"><option value="buy">Buy</option><option value="sell">Sell</option></select>}
      <input className="mono" inputMode="decimal" aria-label={r.kind === "basket" ? "Your margin, in percent" : "Your price, in naira"} placeholder={r.kind === "basket" ? "e.g. 0.2" : "e.g. 226.00"}
             value={value} onChange={(e) => setValue(e.target.value)} />
      <button type="submit" className="button-outline small" disabled={!ok || act.busy}>Send counter</button>
    </form>
  );
}

function LiveQuotes({ r, now, act }: { r: FloorMyRequest; now: number; act: Act }) {
  const [countering, setCountering] = useState<number | null>(null);
  const left = secondsLeft(r.quotes_until, now);
  const live = r.quotes.filter((q) => q.status === "live" && secondsLeft(q.valid_until, now) > 0);
  const bestOffer = live.filter((q) => q.offer).sort((a, b) => Number(a.offer) - Number(b.offer))[0]?.id;
  const bestBid = live.filter((q) => q.bid).sort((a, b) => Number(b.bid) - Number(a.bid))[0]?.id;
  const bestMargin = live.filter((q) => q.margin_bps !== null).sort((a, b) => (a.margin_bps ?? 0) - (b.margin_bps ?? 0))[0]?.id;
  const answered = new Set(r.quotes.map((q) => q.desk));
  const waiting = r.asked.filter((x) => !answered.has(x));
  const take = (q: FloorQuote, side: "buy" | "sell") => act.run(() => api.floorTake({ request_id: r.id, quote_id: q.id, side }), resultWords);
  return (
    <div className="floor-request">
      <div className="floor-request-head">
        <strong className="mono">{SIDE_WORDS[r.side]} {r.kind === "basket" ? "" : r.quantity.toLocaleString("en-NG")} {r.label}</strong>
        {r.block && <span className="floor-player-tag">block</span>}
        {r.for_empire && <span className="floor-player-tag">for the empire</span>}
        <span className="small muted">{left > 0 ? `banks have ${left}s` : "banks' time is up"}</span>
        <button className="button-outline small" disabled={act.busy} onClick={() => act.run(() => api.floorPass(r.id), "You passed.")}>Pass</button>
      </div>
      {r.kind === "basket" && <p className="small muted">{r.legs.map((l) => `${l.quantity.toLocaleString("en-NG")} ${l.ticker} (market ${formatNaira(l.mid)})`).join(" · ")}</p>}
      <div className="floor-scroll-x">
        <table className="dense floor-table floor-quotes">
          <thead><tr><th scope="col">Bank</th><th scope="col" className="num">Buys at</th><th scope="col" className="num">Sells at</th><th scope="col" className="num">Holds</th><th scope="col"><span className="sr-only">Take</span></th></tr></thead>
          <tbody>
            {r.quotes.length === 0 && <tr><td colSpan={5} className="muted small">Waiting for the banks' prices…</td></tr>}
            {r.quotes.map((q) => {
              const holds = secondsLeft(q.valid_until, now);
              const on = q.status === "live" && holds > 0;
              const pending = q.asked?.status === "open";
              const canBuy = r.side !== "sell" && (r.kind === "basket" ? q.margin_bps !== null : Boolean(q.offer));
              const canSell = r.side !== "buy" && (r.kind === "basket" ? q.margin_bps !== null : Boolean(q.bid));
              return (
                <tr key={q.id} className={on ? "" : "floor-gone"}>
                  <th scope="row">{q.desk}{q.kind === "player" && <span className="floor-player-tag">player</span>}
                    {!q.firm && <span className="floor-player-tag floor-indicative" title="Only a guide: taking it asks the bank to confirm">indicative</span>}
                    {(q.failed > 0 || q.backed_away > 0) && <span className="small change-down"> · failed {q.failed}, backed away {q.backed_away}</span>}
                    {q.asked && <span className="small muted"> · your {q.asked.kind === "counter" ? "counter" : "take"}: {q.asked.status === "open" ? "waiting" : q.asked.status}</span>}
                  </th>
                  <td className={`num mono ${q.id === bestBid || (r.side === "sell" && q.id === bestMargin) ? "floor-best" : ""}`}>{priceCell(r, q, "bid")}</td>
                  <td className={`num mono ${q.id === bestOffer || (r.side === "buy" && q.id === bestMargin) ? "floor-best" : ""}`}>{priceCell(r, q, "offer")}</td>
                  <td className="num mono">{on ? `${holds}s` : q.status === "live" ? "expired" : q.status}</td>
                  <td className="floor-take">
                    {on && !pending && canBuy && <button className="floor-take-buy" disabled={act.busy} onClick={() => take(q, "buy")}>Buy</button>}
                    {on && !pending && canSell && <button className="floor-take-sell" disabled={act.busy} onClick={() => take(q, "sell")}>Sell</button>}
                    {on && !pending && <button className="floor-take-counter" disabled={act.busy} onClick={() => setCountering(countering === q.id ? null : q.id)} aria-expanded={countering === q.id}>Counter</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {countering !== null && r.quotes.some((q) => q.id === countering) && (
        <CounterBox r={r} q={r.quotes.find((q) => q.id === countering)!} act={act} onDone={() => setCountering(null)} />
      )}
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
        <thead><tr><th scope="col">Asked</th><th scope="col">For</th><th scope="col">Outcome</th></tr></thead>
        <tbody>{list.map((r) => (
          <tr key={r.id}>
            <td className="mono small">{SIDE_WORDS[r.side]} {r.kind === "basket" ? "" : r.quantity.toLocaleString("en-NG")}</td>
            <th scope="row" className="mono">{r.label}</th>
            <td className="small">{r.deal ? `Done at ${r.kind === "basket" ? "the basket's margin" : formatNaira(r.deal.price)} with ${r.deal.desk}${r.deal.cover ? `; next best ${formatNaira(r.deal.cover)}` : ""}`
              : r.status === "passed" ? "You passed" : "No deal: time ran out"}
              {r.quotes.length > 0 && <span className="muted"> · {r.quotes.length} price{r.quotes.length > 1 ? "s" : ""}</span>}</td>
          </tr>
        ))}</tbody>
      </table>
    </details>
  );
}

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
      <AskForm key={ticker} d={f.d} ticker={ticker} act={act} />
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
  const bond = r.kind === "bond";
  const ref = r.market.best_bid && r.market.best_offer ? null : (r.market.last ?? r.market.reference);
  const fairYield = r.market.fair_yield_bps;
  const [bid, setBid] = useState(bond && fairYield !== undefined ? ((fairYield + 25) / 100).toFixed(2) : nairaInput(r.your_quote?.bid ?? r.market.best_bid ?? ref));
  const [offer, setOffer] = useState(bond && fairYield !== undefined ? ((fairYield - 25) / 100).toFixed(2) : nairaInput(r.your_quote?.offer ?? r.market.best_offer ?? ref));
  const [margin, setMargin] = useState(r.your_quote?.margin_bps !== null && r.your_quote?.margin_bps !== undefined ? (r.your_quote.margin_bps / 100).toFixed(2) : "0.40");
  const [holds, setHolds] = useState(30);
  const [firm, setFirm] = useState(true);
  const wantsBid = r.kind !== "basket" && r.side !== "buy", wantsOffer = r.kind !== "basket" && r.side !== "sell";
  const asYield = (t: string) => { const v = Number(t.replace("%", "")); return Number.isFinite(v) && t.trim() !== "" ? Math.round(v * 100) : null; };
  const b = wantsBid ? (bond ? asYield(bid) : asKobo(bid)) : null, o = wantsOffer ? (bond ? asYield(offer) : asKobo(offer)) : null;
  const m = asYield(margin);
  const ok = r.kind === "basket" ? m !== null && m >= -500 && m <= 500
    : (!wantsBid || b !== null) && (!wantsOffer || o !== null) && (b === null || o === null || (bond ? b > o : b < o));
  const [least, most] = d.limits.quote;
  return (
    <form className={compact ? "floor-quote-form compact" : "floor-quote-form"} onSubmit={(e) => {
      e.preventDefault();
      if (!ok) return;
      const body = r.kind === "basket" ? { request_id: r.id, bid_kobo: null, offer_kobo: null, margin_bps: m, valid_seconds: holds, firm }
        : bond ? { request_id: r.id, bid_kobo: null, offer_kobo: null, bid_yield_bps: b, offer_yield_bps: o, valid_seconds: holds, firm }
        : { request_id: r.id, bid_kobo: b, offer_kobo: o, valid_seconds: holds, firm };
      act.run(() => api.floorQuote(body), "Your price is with the client.");
    }}>
      {r.kind === "basket" && <label className="small">Your margin, % <input className="mono" inputMode="decimal" value={margin} onChange={(e) => setMargin(e.target.value)} aria-label="Your margin over the market, in percent" /></label>}
      {wantsBid && <label className="small">You buy at{bond ? " (yield %)" : ""} <input className="mono" inputMode="decimal" value={bid} onChange={(e) => setBid(e.target.value)} aria-label={bond ? "The yield you buy at, in percent" : "Your buying price, in naira"} /></label>}
      {wantsOffer && <label className="small">You sell at{bond ? " (yield %)" : ""} <input className="mono" inputMode="decimal" value={offer} onChange={(e) => setOffer(e.target.value)} aria-label={bond ? "The yield you sell at, in percent" : "Your selling price, in naira"} /></label>}
      <label className="small">Holds for <select value={holds} onChange={(e) => setHolds(Number(e.target.value))}>
        {[10, 20, 30, 45, 60].filter((s) => s >= least && s <= most).map((s) => <option key={s} value={s}>{s}s</option>)}
      </select></label>
      <label className="small floor-inline" title="An indicative price only guides: if the client takes it, you must confirm. Backing away is counted and shown to every client.">
        <input type="checkbox" checked={!firm} onChange={(e) => setFirm(!e.target.checked)} /> Indicative
      </label>
      <button type="submit" className="button-primary" disabled={!ok || act.busy}>{r.your_quote ? "Send a new price" : "Send price"}</button>
    </form>
  );
}

function Call({ r, d, now, act, compact = false }: { r: FloorIncoming; d: FloorRequests; now: number; act: Act; compact?: boolean }) {
  const left = secondsLeft(r.quotes_until, now);
  const wants = r.side === "two_way" ? "a price both ways on" : r.side === "buy" ? "to buy" : "to sell";
  const rec = r.record;
  return (
    <div className="floor-call">
      <div className="floor-request-head">
        <strong>{r.client}</strong>
        <span className="small">wants {wants} <span className="mono strong">{r.kind === "basket" ? r.label : `${r.quantity.toLocaleString("en-NG")} ${r.label}`}</span></span>
        {r.block && <span className="floor-player-tag">block</span>}
        {r.for_empire && <span className="floor-player-tag">for an empire</span>}
        <span className={`floor-clock mono ${left <= 5 ? "change-down" : ""}`} aria-label={`${left} seconds left`}>{left}s</span>
      </div>
      <p className="small muted floor-call-market">
        {r.kind === "basket" ? r.legs.map((l) => `${l.quantity.toLocaleString("en-NG")} ${l.ticker} at market ${formatNaira(l.mid)}`).join(" · ")
          : r.kind === "bond" ? <>Bond desk: buys {r.market.best_bid ? formatNaira(r.market.best_bid) : "—"}, sells {r.market.best_offer ? formatNaira(r.market.best_offer) : "—"}; fair {r.market.reference ? formatNaira(r.market.reference) : "—"} ({pct(r.market.fair_yield_bps)}). You hold {r.you_hold.toLocaleString("en-NG")}.</>
          : <>Exchange: buyers at {r.market.best_bid ? formatNaira(r.market.best_bid) : "—"}, sellers at {r.market.best_offer ? formatNaira(r.market.best_offer) : "—"}{r.market.last ? `, last ${formatNaira(r.market.last)}` : ""}. You hold {r.you_hold.toLocaleString("en-NG")}.</>}
        {" "}Client record: {rec.deals} deal{rec.deals === 1 ? "" : "s"}{rec.right_bps !== null ? `, right ${pct(rec.right_bps, 0)} of the time` : ""}
        {rec.asked > 0 ? `; dealt ${rec.dealt} of their last ${rec.asked} requests` : ""}.
        {rec.fishing && <span className="change-down"> Asks and never deals: fishing for prices.</span>}
      </p>
      {r.your_quote && <p className="small">Your price: {r.your_quote.margin_bps !== null ? `${signedBps(r.your_quote.margin_bps)} on the market` : ""}{r.your_quote.bid ? `buy ${formatNaira(r.your_quote.bid)}` : ""}{r.your_quote.bid && r.your_quote.offer ? " · " : ""}{r.your_quote.offer ? `sell ${formatNaira(r.your_quote.offer)}` : ""}{r.your_quote.firm ? "" : " (indicative)"}, holds {secondsLeft(r.your_quote.valid_until, now)}s.</p>}
      {r.asked_you && (
        <div className="floor-asked" role="alert">
          <span className="small"><strong>{r.asked_you.kind === "counter" ? "The client counters" : "The client takes your indicative price"}</strong>: {r.asked_you.side} at {r.asked_you.price ? formatNaira(r.asked_you.price) : `${signedBps(r.asked_you.margin_bps ?? 0)} on the market`}.</span>
          <button className="button-primary small" disabled={act.busy} onClick={() => act.run(() => api.floorAnswer(r.asked_you!.id, true), "Done: the deal is made.")}>Accept</button>
          <button className="button-outline small" disabled={act.busy} onClick={() => act.run(() => api.floorAnswer(r.asked_you!.id, false), r.asked_you!.kind === "confirm" ? "You backed away: it is counted." : "Declined.")}>Decline</button>
        </div>
      )}
      {left > 0 && !r.asked_you && <QuoteForm key={r.id} r={r} d={d} act={act} compact={compact} />}
    </div>
  );
}

function Axes({ d, ticker, act }: { d: FloorRequests; ticker: string; act: Act }) {
  const [side, setSide] = useState<"buy" | "sell">("sell");
  const [count, setCount] = useState("");
  const n = Number(count.replace(/[,\s]/g, ""));
  return (
    <div className="floor-axes">
      <span className="small muted">What your desk wants (clients see it):</span>
      {d.your_axes.map((a) => (
        <span key={a.ticker} className="floor-axe">{a.side === "buy" ? "buys" : "sells"} {a.quantity.toLocaleString("en-NG")} {a.ticker}
          <button className="floor-axe-x" aria-label={`Take down the ${a.ticker} advert`} onClick={() => act.run(() => api.floorAxe({ ticker: a.ticker, side: null, quantity: 0 }), "Taken down.")}>×</button></span>
      ))}
      <form className="floor-ask-row" onSubmit={(e) => { e.preventDefault(); if (n > 0) act.run(() => api.floorAxe({ ticker, side, quantity: n }), `Clients now see that you ${side} ${ticker}.`).then(() => setCount("")); }}>
        <select value={side} onChange={(e) => setSide(e.target.value as "buy" | "sell")} aria-label="Buy or sell"><option value="sell">Sells</option><option value="buy">Buys</option></select>
        <input className="mono" inputMode="numeric" placeholder={`Shares of ${ticker}`} value={count} onChange={(e) => setCount(e.target.value)} aria-label={`How many ${ticker}`} />
        <button type="submit" className="button-outline small" disabled={!(n > 0) || act.busy}>Advertise</button>
      </form>
    </div>
  );
}

export function DeskPanel({ f, ticker, onLoggedOut }: { f: Floor; ticker: string; onLoggedOut: () => void }) {
  const act = useAct(f.setFresh, onLoggedOut);
  const now = useClock(f.d?.now);
  if (!f.d || !f.d.is_banker) return null;
  const d = f.d;
  const open = d.incoming.filter((r) => r.status === "open" && (secondsLeft(r.quotes_until, now) > 0 || r.asked_you));
  const closed = d.incoming.filter((r) => !open.includes(r)).slice(0, 8);
  return (
    <Panel title="Your desk" aside={d.desk_open ? "open: taking requests" : "closed"} className="floor-panel floor-desk-panel">
      <div className="floor-desk-switch">
        <button className={d.desk_open ? "button-outline" : "button-primary"} disabled={act.busy}
                onClick={() => act.run(() => api.floorDesk(!d.desk_open), d.desk_open ? "Your desk is closed." : "Your desk is open: requests will come to you.")}>
          {d.desk_open ? "Close the desk" : "Open the desk"}
        </button>
        <span className="small muted">Clients, players and computer, ask you for prices while it is open. You deal with your own cash and shares.
          {(d.desk_failed > 0 || d.desk_backed_away > 0) ? ` Shown to clients: ${d.desk_failed} deals you could not deliver, ${d.desk_backed_away} prices you backed away from.` : ""}</span>
      </div>
      <Axes d={d} ticker={ticker} act={act} />
      {act.error && <p className="small change-down" role="alert">{act.error}</p>}
      {act.notice && <p className="small" role="status">{act.notice}</p>}
      {open.length === 0 ? <p className="muted small">{d.desk_open ? "No request waiting. They pop up wherever you are in the game." : "Open the desk to take requests."}</p>
        : open.map((r) => <Call key={r.id} r={r} d={d} now={now} act={act} />)}
      {closed.length > 0 && (
        <details className="floor-old">
          <summary className="small">Recent requests ({closed.length})</summary>
          <ul className="floor-outcomes small">{closed.map((r) => (
            <li key={r.id}><strong>{r.client}</strong> · {SIDE_WORDS[r.side]} {r.kind === "basket" ? r.label : `${r.quantity.toLocaleString("en-NG")} ${r.label}`} · <span className={r.outcome === "won" ? "change-up" : ""}>{r.outcome === "won" ? "you won it" : r.outcome ?? "no deal"}</span>
              {r.outcome === "won" && r.cover && <span className="muted"> (next best {formatNaira(r.cover)})</span>}
              {r.outcome === "traded away" && r.done_at_price && <span className="muted"> (done at {formatNaira(r.done_at_price)})</span>}</li>
          ))}</ul>
        </details>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The deals, the scorecard, the blocks reported, and the chat
// ---------------------------------------------------------------------------

export function FloorDeals({ f }: { f: Floor }) {
  if (!f.d || f.d.deals.length === 0) return null;
  return (
    <Panel title="Your deals on the Floor" aside="newest first" className="floor-panel">
      <div className="floor-scroll-x">
        <table className="dense floor-table">
          <thead><tr><th scope="col">Time</th><th scope="col">What</th><th scope="col">You</th><th scope="col" className="num">How many</th><th scope="col" className="num">Price</th><th scope="col">With</th></tr></thead>
          <tbody>{f.d.deals.map((t) => (
            <tr key={t.id}>
              <td className="mono small">{lagosTime(t.at)}</td>
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

export function ScorePanel({ f }: { f: Floor }) {
  const card = f.d?.scorecard;
  if (!card || card.deals.length === 0) return null;
  return (
    <Panel title="Best execution" aside={card.average_vs_exchange_bps !== null ? `on average ${signedBps(card.average_vs_exchange_bps)} against the exchange` : "your deals as a client"} className="floor-panel">
      <p className="small muted">Each deal against the exchange's best price when you asked (with its fee), and against the next best price you were given. Above nought is money saved.</p>
      <div className="floor-scroll-x">
        <table className="dense floor-table">
          <thead><tr><th scope="col">Time</th><th scope="col">What</th><th scope="col" className="num">Price</th><th scope="col" className="num">Against the exchange</th><th scope="col" className="num">Against the next best</th></tr></thead>
          <tbody>{card.deals.map((t) => (
            <tr key={t.id}>
              <td className="mono small">{lagosTime(t.at)}</td>
              <th scope="row" className="mono">{t.bought ? "Bought" : "Sold"} {t.quantity.toLocaleString("en-NG")} {t.what}</th>
              <td className="num mono">{formatNaira(t.price)}</td>
              <td className={`num mono ${t.vs_exchange_bps !== null && t.vs_exchange_bps >= 0 ? "change-up" : "change-down"}`}>{t.vs_exchange_bps === null ? "—" : signedBps(t.vs_exchange_bps)}</td>
              <td className={`num mono ${t.vs_cover_bps !== null && t.vs_cover_bps >= 0 ? "change-up" : "change-down"}`}>{t.vs_cover_bps === null ? "—" : signedBps(t.vs_cover_bps)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </Panel>
  );
}

export function BlocksPanel({ f }: { f: Floor }) {
  const list = f.d?.blocks ?? [];
  if (list.length === 0) return null;
  return (
    <Panel title="Blocks reported" aside="very large deals, without names" className="floor-panel">
      <ul className="floor-outcomes small">{list.map((b, i) => (
        <li key={i}><span className="mono">{lagosTime(b.at)}</span> · <strong className="mono">{b.quantity.toLocaleString("en-NG")} {b.ticker}</strong> at {formatNaira(b.price)}</li>
      ))}</ul>
    </Panel>
  );
}

/** "I'll take 3,000 HMB at 227" or "sell 500 IDC @ 20.50": an agreed line, read as a ticket. */
export function readTicket(line: string): { side: "buy" | "sell"; quantity: number; ticker: string; price: number } | null {
  const m = line.match(/\b(buy|take|sell|give|lift|hit)\b[^\d]*([\d,]+)\s+([A-Za-z]{3})\s*(?:at|@)\s*₦?\s*([\d,]+(?:\.\d{1,2})?)/i);
  if (!m) return null;
  const word = m[1].toLowerCase();
  const quantity = Number(m[2].replace(/,/g, ""));
  const price = asKobo(m[4]);
  if (!quantity || !price) return null;
  return { side: ["buy", "take", "lift"].includes(word) ? "buy" : "sell", quantity, ticker: m[3].toUpperCase(), price };
}

export function ChatPanel({ f, onLoggedOut }: { f: Floor; onLoggedOut: () => void }) {
  const act = useAct(f.setFresh, onLoggedOut);
  const now = useClock(f.d?.now);
  const d = f.d;
  const talks = d?.chat.talks ?? [];
  const desks = (d?.desks ?? []).filter((x) => x.kind === "player").map((x) => x.name.replace(/'s desk$/, ""));
  const names = Array.from(new Set([...talks.map((t) => t.with), ...desks]));
  const [withWho, setWithWho] = useState<string>("");
  const who = withWho || names[0] || "";
  const [body, setBody] = useState("");
  if (!d || names.length === 0) return null;
  const talk = talks.find((t) => t.with === who);
  const ticket = readTicket(body);
  const tickets = d.chat.tickets.filter((t) => t.other === who || t.status === "open");
  return (
    <Panel title="Floor chat" aside="kept for good; the Money Watch may read it" className="floor-panel floor-chat">
      <div className="floor-ask-row">
        <label className="small floor-inline">With <select value={who} onChange={(e) => setWithWho(e.target.value)}>{names.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
      </div>
      <div className="chat" role="log" aria-live="polite">
        {(talk?.lines ?? []).length === 0 && <p className="muted small">Nothing said yet. Agree a deal here, then make it a ticket.</p>}
        {(talk?.lines ?? []).map((l) => (
          <div key={l.id} className={l.yours ? "chat-line yours" : "chat-line"}>
            <div className="muted small">{l.yours ? "You" : who} · {lagosTime(l.at)}</div>
            <div>{l.body}</div>
          </div>
        ))}
      </div>
      <form className="chat-form" onSubmit={(e) => { e.preventDefault(); if (body.trim()) act.run(() => api.floorChat(who, body), "").then((ok) => ok && setBody("")); }}>
        <input type="text" maxLength={300} aria-label="Your message" placeholder="e.g. I'll take 3,000 HMB at 46.20" value={body} onChange={(e) => setBody(e.target.value)} />
        <button className="button-outline" disabled={act.busy || !body.trim()}>Send</button>
      </form>
      {ticket && (
        <p className="small">That reads as a deal: you {ticket.side} {ticket.quantity.toLocaleString("en-NG")} {ticket.ticker} at {formatNaira(String(ticket.price))}.{" "}
          <button className="button-primary small" disabled={act.busy} onClick={() => act.run(() => api.floorTicket({ to: who, ticker: ticket.ticker, side: ticket.side, quantity: ticket.quantity, price_kobo: ticket.price }),
            `Ticket sent to ${who}: they have a minute to confirm.`).then((ok) => ok && setBody(""))}>Make it a ticket</button></p>
      )}
      {act.error && <p className="small change-down" role="alert">{act.error}</p>}
      {act.notice && <p className="small" role="status">{act.notice}</p>}
      {tickets.length > 0 && (
        <ul className="floor-tickets small">{tickets.map((t) => {
          const left = secondsLeft(t.valid_until, now);
          const open = t.status === "open" && left > 0;
          return (
            <li key={t.id}>
              <span className="mono">{t.yours ? "You" : t.other} {t.side === "buy" ? "buy" : "sell"} {t.quantity.toLocaleString("en-NG")} {t.ticker} at {formatNaira(t.price)}</span>
              {" · "}{open ? `${left}s` : t.status}
              {open && !t.yours && <><button className="button-primary small" disabled={act.busy} onClick={() => act.run(() => api.floorTicketAnswer(t.id, true), () => { play("trade"); return "Done: the ticket is a deal."; })}>Confirm</button>
                <button className="button-outline small" disabled={act.busy} onClick={() => act.run(() => api.floorTicketAnswer(t.id, false), "Declined.")}>Decline</button></>}
              {open && t.yours && <button className="button-outline small" disabled={act.busy} onClick={() => act.run(() => api.floorTicketAnswer(t.id, false), "Withdrawn.")}>Withdraw</button>}
            </li>
          );
        })}</ul>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The pop-up: a request (or a client's answer) reaching a banker's desk, wherever they are
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
  const open = (f.d?.incoming ?? []).filter((r) => r.status === "open" && (secondsLeft(r.quotes_until, now) > 0 || r.asked_you) && !hidden.includes(r.id));
  const newest = open[0] ? `${open[0].id}:${open[0].asked_you?.id ?? ""}` : undefined;
  const rang = useRef<string | undefined>(undefined);
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
