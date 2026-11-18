// The Floor (owner, 16 November 2026: "the floor should be where alot happen multiplayer"): the multiplayer home, its own
// section of the sidebar. Its tabs: the trading floor, live events, competition and the Auction House.
//
// The trading floor is modelled on the simulation the owner played in the investing challenge (his screenshots): a
// profit-and-loss bar along the top, the market, a news feed with a keyword search, positions and a blotter of every
// trade, an exchange box that shows a deal's value and fee before it is done, and an intraday chart with zooms. Price
// requests between asset managers and banks are the next slice. Every figure comes from the server; the screen is the
// player's own trading account.

import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type AuctionLot, type FloorChart, type FloorPage, type FloorRisk, type NewsItem, type Player } from "./api";
import { formatChange, formatCompact, formatNaira } from "./format";
import { AskPanel, BlocksPanel, ChatPanel, DeskPanel, FloorDeals, MandatePanel, ScorePanel, SwapPanel, useFloorRequests } from "./FloorDesk";
import { AlertsPanel } from "./FloorAlerts";
import { BankPanel } from "./FloorBank";
import { RiskPanel, StormBanner, useFloorRisk } from "./FloorRisk";
import { WealthPanel } from "./FloorWealth";
import { useLoad } from "./hooks";
import { Failed, Loading, PageHead, Panel } from "./Shell";
import { play } from "./sound";

type Props = { player: Player; onLoggedOut: () => void };

const big = (k: string) => BigInt(k);
const tone = (k: string) => (big(k) > 0n ? "change-up" : big(k) < 0n ? "change-down" : "");
const signed = (k: string) => (big(k) > 0n ? "+" : "") + formatNaira(k);
const lagosTime = (iso: string) => new Date(iso).toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" });

/** Reads something again every few seconds while the page is open. */
function useEvery(reload: () => void, ms: number) {
  useEffect(() => {
    const id = window.setInterval(reload, ms);
    return () => window.clearInterval(id);
  }, [reload, ms]);
}

// ---------------------------------------------------------------------------
// The bar along the top
// ---------------------------------------------------------------------------

function Bar({ d }: { d: FloorPage }) {
  const b = d.bar;
  // [label, figure, what it means, the amount to colour by (profit and loss only)]
  const cells: [string, string, string, string | null][] = [
    ["Realised P&L", signed(b.realised), "gains less losses on shares sold, after fees", b.realised],
    ["Unrealised P&L", signed(b.unrealised), "what the shares you hold have gained or lost", b.unrealised],
    ["Total P&L", signed(b.total), "the two together", b.total],
    ["Fees paid", formatNaira(b.fees), "every trade's fee and stamp duty", null],
    ["Exposure", formatNaira(b.exposure), "what your shares are worth now", null],
    ["Cash", formatNaira(b.cash), big(b.held_for_orders) > 0n ? `${formatNaira(b.held_for_orders)} held for orders` : "free to trade", null],
    ["Account value", formatNaira(b.value), "cash, held cash and shares", null],
    ...(d.event ? [["Live event", signed(d.event.pnl), `what the event's shares have done to what you hold, since the bell: ${d.event.name}`, d.event.pnl] as [string, string, string, string | null]] : []),
  ];
  return (
    <div className={d.event ? "floor-bar floor-bar-live" : "floor-bar"} role="group" aria-label="Your profit and loss">
      {cells.map(([label, value, note, by]) => (
        <div key={label} className="floor-bar-cell" title={note}>
          <span className="floor-bar-label">{label}</span>
          <span className={`floor-bar-value mono ${by ? tone(by) : ""}`}>{value}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The deal tape, and the squawk (headlines read out, if the player turns it on)
// ---------------------------------------------------------------------------

function useSquawk(d: FloorPage) {
  const [on, setOn] = useState(() => { try { return window.localStorage.getItem("wsbm-squawk") === "on"; } catch { return false; } });
  const heard = useRef<Set<string>>(new Set());
  const first = useRef(true);
  useEffect(() => {
    const fresh = d.notes.filter((n) => !heard.current.has(`${n.at}${n.words}`));
    fresh.forEach((n) => heard.current.add(`${n.at}${n.words}`));
    if (first.current) { first.current = false; return; }
    if (!on || typeof window.speechSynthesis === "undefined") return;
    for (const n of fresh.reverse()) window.speechSynthesis.speak(new SpeechSynthesisUtterance(n.words));
  }, [d.notes, on]);
  const toggle = () => setOn((was) => {
    try { window.localStorage.setItem("wsbm-squawk", was ? "off" : "on"); } catch { /* not remembered: fine */ }
    if (was && typeof window.speechSynthesis !== "undefined") window.speechSynthesis.cancel();
    return !was;
  });
  return { on, toggle };
}

function Tape({ d }: { d: FloorPage }) {
  const squawk = useSquawk(d);
  return (
    <div className="floor-tape" aria-label="The deal tape">
      <button className={squawk.on ? "floor-squawk on" : "floor-squawk"} aria-pressed={squawk.on} onClick={squawk.toggle}
              title="Read the Floor's notes out loud as they come">{squawk.on ? "Squawk on" : "Squawk off"}</button>
      <div className="floor-tape-run">
        {d.tape.length === 0 ? <span className="muted small">No deals yet today.</span> : d.tape.map((t, i) => (
          <span key={i} className={`floor-tape-item floor-tape-${t.venue}`}>
            <span className="mono muted">{lagosTime(t.at)}</span> {t.venue === "block" ? "Block: " : ""}{t.words} <strong className="mono">{t.quantity.toLocaleString("en-NG")} {t.what}</strong> at <span className="mono">{formatNaira(t.price)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The market, the news, positions and the blotter
// ---------------------------------------------------------------------------

function MarketList({ chosen, onChoose, onLoggedOut }: { chosen: string | null; onChoose: (t: string) => void; onLoggedOut: () => void }) {
  const tape = useLoad(api.ticker, "floor-ticker", onLoggedOut);
  useEvery(tape.reload, 15_000);
  const rows = tape.data?.shares ?? [];
  return (
    <Panel title="Market" aside={tape.data ? `BSX 50 ${formatChange(tape.data.index_change_bps)}` : undefined} className="floor-panel">
      {!tape.data && <p className="muted small">Reading the market…</p>}
      <div className="floor-scroll">
        <table className="dense floor-table">
          <thead><tr><th scope="col">Share</th><th scope="col" className="num">Price</th><th scope="col" className="num">% chg</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.ticker} className={r.ticker === chosen ? "floor-on" : ""}>
              <th scope="row"><button className="floor-pick mono" onClick={() => onChoose(r.ticker)} title={r.name}>{r.ticker}</button></th>
              <td className="num mono">{formatNaira(r.price_kobo)}</td>
              <td className={`num mono ${r.change_bps > 0 ? "change-up" : r.change_bps < 0 ? "change-down" : ""}`}>{formatChange(r.change_bps)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </Panel>
  );
}

function NewsFeed({ notes, onChoose, onLoggedOut }: { notes: FloorPage["notes"]; onChoose: (t: string) => void; onLoggedOut: () => void }) {
  const list = useLoad(() => api.news({ limit: 60 }), "floor-news", onLoggedOut);
  useEvery(list.reload, 30_000);
  const [words, setWords] = useState("");
  const items: NewsItem[] = useMemo(() => {
    const all = list.data?.items ?? [];
    const look = words.trim().toLowerCase();
    if (!look) return all;
    return all.filter((n) => `${n.headline} ${n.tickers.join(" ")} ${n.outlet}`.toLowerCase().includes(look));
  }, [list.data, words]);
  return (
    <Panel title="News" aside="newest first" className="floor-panel">
      <input className="floor-search" type="search" aria-label="Search the news" placeholder="Search keywords" value={words} onChange={(e) => setWords(e.target.value)} />
      <div className="floor-scroll">
        {!list.data && <p className="muted small">Reading the wire…</p>}
        {list.data && items.length === 0 && <p className="muted small">Nothing matches.</p>}
        <ul className="floor-news">
          {notes.filter((n) => !words.trim() || n.words.toLowerCase().includes(words.trim().toLowerCase())).map((n, i) => (
            <li key={`note-${i}`} className={`floor-note floor-note-${n.kind}`}>
              <span className="floor-tag mono">{n.kind === "hour" ? "Hour" : n.kind === "drop" ? (n.ticker ?? "Live") : "Note"}</span>
              <span className="floor-headline">{n.words}</span>
            </li>
          ))}
          {items.map((n, i) => (
          <li key={`${n.story}-${i}`}>
            {n.tickers[0]
              ? <button className="floor-tag mono" onClick={() => onChoose(n.tickers[0])} title={`Show ${n.tickers[0]}`}>{n.tickers[0]}</button>
              : <span className="floor-tag mono muted">{n.kind.startsWith("macro") || n.kind.includes("rate") ? "Economy" : "News"}</span>}
            <a href={`#/news`} className="floor-headline">{n.headline}</a>
          </li>
        ))}</ul>
      </div>
    </Panel>
  );
}

function Positions({ d, chosen, onChoose }: { d: FloorPage; chosen: string | null; onChoose: (t: string) => void }) {
  const [tab, setTab] = useState<"positions" | "blotter">("positions");
  return (
    <section className="panel floor-panel">
      <div className="panel-head floor-tabs" role="tablist" aria-label="Positions and trades">
        <button role="tab" aria-selected={tab === "positions"} className={tab === "positions" ? "floor-tab on" : "floor-tab"} onClick={() => setTab("positions")}>Positions</button>
        <button role="tab" aria-selected={tab === "blotter"} className={tab === "blotter" ? "floor-tab on" : "floor-tab"} onClick={() => setTab("blotter")}>Trade blotter</button>
      </div>
      <div className="floor-scroll">
        {tab === "positions" ? (
          d.positions.length === 0 ? <p className="muted small">You hold no shares yet. Choose a share and buy in the exchange box.</p> : (
            <table className="dense floor-table">
              <thead><tr><th scope="col">Share</th><th scope="col" className="num">Held</th><th scope="col" className="num">Avg price</th><th scope="col" className="num">Value</th><th scope="col" className="num">P&L</th></tr></thead>
              <tbody>{d.positions.map((p) => (
                <tr key={p.ticker} className={p.ticker === chosen ? "floor-on" : ""}>
                  <th scope="row"><button className="floor-pick mono" onClick={() => onChoose(p.ticker)} title={p.name}>{p.ticker}</button></th>
                  <td className="num mono">{p.shares.toLocaleString("en-NG")}</td>
                  <td className="num mono">{formatNaira(p.average_price)}</td>
                  <td className="num mono">{formatCompact(p.value)}</td>
                  <td className={`num mono ${tone(p.gain)}`}>{signed(p.gain)}</td>
                </tr>
              ))}</tbody>
            </table>
          )
        ) : (
          d.blotter.length === 0 ? <p className="muted small">No trades yet.</p> : (
            <table className="dense floor-table">
              <thead><tr><th scope="col">Time</th><th scope="col">Share</th><th scope="col">Side</th><th scope="col" className="num">Shares</th><th scope="col" className="num">Price</th><th scope="col" className="num">Fee</th></tr></thead>
              <tbody>{d.blotter.map((t) => (
                <tr key={t.id}>
                  <td className="mono small" title={new Date(t.traded_at).toLocaleString("en-NG", { timeZone: "Africa/Lagos" })}>{lagosTime(t.traded_at)}</td>
                  <th scope="row" className="mono">{t.ticker}</th>
                  <td className={t.side === "buy" ? "change-up" : t.side === "sell" ? "change-down" : "muted"}>{t.side === "both" ? "own trade" : t.side === "buy" ? "Bought" : "Sold"}{t.venue === "floor" && <span className="floor-player-tag" title="Done with a bank on the Floor, away from the exchange">floor</span>}</td>
                  <td className="num mono">{t.quantity.toLocaleString("en-NG")}</td>
                  <td className="num mono">{formatNaira(t.price)}</td>
                  <td className="num mono muted">{formatNaira(t.fee)}</td>
                </tr>
              ))}</tbody>
            </table>
          )
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// The exchange box
// ---------------------------------------------------------------------------

function ExchangeBox({ ticker, feeBps, chart, onTraded, onLoggedOut }: {
  ticker: string; feeBps: number; chart: FloorChart | null; onTraded: () => void; onLoggedOut: () => void;
}) {
  const [count, setCount] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ ok: boolean; words: string } | null>(null);
  useEffect(() => setSaid(null), [ticker]);
  const n = Number(count.replace(/[,\s]/g, ""));
  const ok = Number.isInteger(n) && n > 0;
  const bid = chart?.best_bid ?? null, offer = chart?.best_offer ?? null;
  const value = (price: string | null) => (ok && price ? big(price) * BigInt(n) : null);
  const fee = (v: bigint | null) => (v === null ? null : (v * BigInt(feeBps) + 9999n) / 10000n);
  const buyValue = value(offer), sellValue = value(bid);
  const shown = buyValue ?? sellValue;

  async function trade(side: "buy" | "sell") {
    setBusy(true); setSaid(null);
    try {
      const done = await api.placeOrder({ ticker, side, kind: "market", quantity: n });
      const traded = done.trades.reduce((sum, t) => sum + t.quantity, 0);
      if (traded > 0) play("trade");
      setSaid({ ok: traded > 0, words: traded > 0
        ? `${side === "buy" ? "Bought" : "Sold"} ${traded.toLocaleString("en-NG")} ${ticker}${traded < n ? `; the other ${(n - traded).toLocaleString("en-NG")} found no match` : ""}.`
        : done.order.closed_reason ?? "Nothing matched." });
      onTraded();
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setSaid({ ok: false, words: problem instanceof ApiError ? problem.message : "Could not reach the server." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Exchange" aside={chart?.state === "open" ? "market open" : chart?.state === "opening_auction" ? "opening auction" : "market closed"} className="floor-panel floor-exchange">
      <div className="floor-ex-row">
        <span className="floor-ex-ticker mono" aria-label="Share">{ticker}</span>
        <input className="mono" inputMode="numeric" aria-label="How many shares" placeholder="Shares, e.g. 5000" value={count} onChange={(e) => setCount(e.target.value)} />
      </div>
      <div className="floor-ex-sides">
        <button className="floor-ex-sell" disabled={!ok || !bid || busy} onClick={() => trade("sell")}>
          <span className="small">Sell at</span><span className="mono">{bid ? formatNaira(bid) : "no buyers"}</span>
        </button>
        <button className="floor-ex-buy" disabled={!ok || !offer || busy} onClick={() => trade("buy")}>
          <span className="small">Buy at</span><span className="mono">{offer ? formatNaira(offer) : "no sellers"}</span>
        </button>
      </div>
      <dl className="floor-ex-figures">
        <div><dt>Deal value</dt><dd className="mono">{shown !== null ? formatNaira(String(shown)) : "—"}</dd></div>
        <div><dt>Fee ({(feeBps / 100).toFixed(1)}%)</dt><dd className="mono">{shown !== null ? formatNaira(String(fee(shown))) : "—"}</dd></div>
      </dl>
      <p className="muted small">At the best price waiting on the exchange, at once. A big order eats through several prices, so it may cost more than shown. For a bank's price, with no exchange fee, ask the banks above.</p>
      {said && <p className={`small ${said.ok ? "" : "change-down"}`} role="status">{said.words}</p>}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The intraday chart
// ---------------------------------------------------------------------------

const W = 640, H = 230, PAD = { l: 22, r: 104, t: 10, b: 22 };

/** The chart's zoom is a window of time, as on the screen the owner played on: the last 5, 15, 30 or 60 minutes, or the
 * whole day. The server gives a point a minute. */
function Chart({ chart, zoom, setZoom, now }: { chart: FloorChart | null; zoom: number; setZoom: (m: number) => void; now: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const zooms = [5, 15, 30, 60, 0];
  const head = (
    <div className="floor-zoom" role="group" aria-label="Zoom">
      {zooms.map((m) => <button key={m} className={m === zoom ? "on" : ""} aria-pressed={m === zoom} onClick={() => setZoom(m)}>{m ? `${m}min` : "All"}</button>)}
    </div>
  );
  if (!chart) return <Panel title="Chart" aside={head} className="floor-panel"><p className="muted small">Reading the chart…</p></Panel>;
  const dayOpens = new Date(`${chart.session_date}T12:00:00+01:00`).getTime();
  const dayCloses = new Date(`${chart.session_date}T22:00:00+01:00`).getTime();
  const every = chart.points.map((p) => ({ t: new Date(p.at).getTime(), p: Number(p.price), v: p.volume }));
  const end = zoom === 0 ? dayCloses
    : Math.max(Math.min(chart.today ? now : (every.length ? every[every.length - 1].t + 60_000 : dayCloses), dayCloses), dayOpens + zoom * 60_000);
  const opens = zoom === 0 ? dayOpens : end - zoom * 60_000;
  const closes = end;
  const pts = every.filter((q) => q.t >= opens - 60_000 && q.t <= closes);
  const lines: [string, number | null, string][] = [
    ["ref", Number(chart.reference_price), "floor-ref"],
    ["bid", chart.best_bid ? Number(chart.best_bid) : null, "floor-bid"],
    ["offer", chart.best_offer ? Number(chart.best_offer) : null, "floor-offer"],
  ];
  const values = [...pts.map((x) => x.p), ...lines.map((l) => l[1]).filter((v): v is number => v !== null)];
  let lo = Math.min(...values), hi = Math.max(...values);
  if (hi - lo < lo * 0.004) { lo *= 0.997; hi *= 1.003; }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const x = (t: number) => PAD.l + ((Math.min(Math.max(t, opens), closes) - opens) / (closes - opens)) * (W - PAD.l - PAD.r);
  const y = (p: number) => PAD.t + (1 - (p - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
  const path = pts.map((q, i) => `${i ? "L" : "M"}${x(q.t).toFixed(1)},${y(q.p).toFixed(1)}`).join(" ");
  const step = zoom === 0 ? 120 : zoom <= 5 ? 1 : zoom <= 15 ? 5 : zoom <= 30 ? 5 : 10;     // minutes between the marks
  const ticks: number[] = [];
  for (let t = Math.ceil(opens / (step * 60_000)) * step * 60_000; t <= closes; t += step * 60_000) ticks.push(t);
  const at = hover !== null ? pts[hover] : null;
  function move(e: React.PointerEvent<SVGSVGElement>) {
    if (!svg.current || pts.length === 0) return;
    const box = svg.current.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    let best = 0;
    pts.forEach((q, i) => { if (Math.abs(x(q.t) - px) < Math.abs(x(pts[best].t) - px)) best = i; });
    setHover(best);
  }
  const naira = (p: number) => formatNaira(String(Math.round(p)));
  return (
    <Panel title={`${chart.ticker} · ${chart.name}`} aside={head} className="floor-panel floor-chart">
      {!chart.today && <p className="muted small">No trade in {chart.ticker} yet today: showing {new Date(`${chart.session_date}T12:00:00+01:00`).toLocaleDateString("en-NG", { weekday: "long", day: "numeric", month: "short" })}.</p>}
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} className="floor-svg" role="img"
           aria-label={`${chart.ticker}, ${zoom ? `the last ${zoom} minutes` : "the whole trading day"}, a point a minute`}
           onPointerMove={move} onPointerLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}><line x1={x(t)} x2={x(t)} y1={PAD.t} y2={H - PAD.b} className="floor-grid" /><text x={x(t)} y={H - 6} className="floor-axis" textAnchor="middle">{lagosTime(new Date(t).toISOString())}</text></g>
        ))}
        {lines.map(([key, v, cls]) => v === null ? null : (
          <g key={key}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className={cls} />
            <text x={W - PAD.r + 4} y={y(v) + 4} className={`floor-axis ${cls}-text`}>{key === "ref" ? "open" : key} {naira(v)}</text>
          </g>
        ))}
        {pts.length > 1 && <path d={path} className="floor-line" />}
        {pts.map((q, i) => pts.length <= 1 || i === pts.length - 1 ? <circle key={i} cx={x(q.t)} cy={y(q.p)} r={4} className="floor-dot" /> : null)}
        {at && <g><line x1={x(at.t)} x2={x(at.t)} y1={PAD.t} y2={H - PAD.b} className="floor-cross" /><circle cx={x(at.t)} cy={y(at.p)} r={4} className="floor-dot" /></g>}
      </svg>
      <p className="small floor-readout mono" aria-live="polite">
        {at ? `${lagosTime(new Date(at.t).toISOString())} · ${naira(at.p)} · ${at.v.toLocaleString("en-NG")} shares`
            : every.length ? `Last ${chart.last_price ? formatNaira(chart.last_price) : "—"} · range today ${formatNaira(chart.lowest_today)} to ${formatNaira(chart.highest_today)}`
            : "No trades on this day yet."}{every.length > 0 && pts.length === 0 ? " None in this window: try a wider one." : ""}
      </p>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The trading floor
// ---------------------------------------------------------------------------

export function FloorWork({ onLoggedOut }: Props) {
  const page = useLoad(api.floor, "floor", onLoggedOut);
  useEvery(page.reload, 10_000);
  const d = page.data;
  const [picked, setPicked] = useState<string | null>(null);
  const tickerFallback = d?.positions[0]?.ticker ?? null;
  const [market, setMarket] = useState<string | null>(null);
  useEffect(() => {
    if (picked || tickerFallback) return;
    api.ticker().then((t) => setMarket(t.shares[0]?.ticker ?? null)).catch(() => undefined);
  }, [picked, tickerFallback]);
  const ticker = picked ?? tickerFallback ?? market;
  // Once the screen has a share, it keeps it until the player chooses another (selling out of a position must not move it).
  useEffect(() => { if (!picked && ticker) setPicked(ticker); }, [picked, ticker]);
  const [zoom, setZoom] = useState(60);
  const chart = useLoad(() => (ticker ? api.floorChart(ticker, 1) : Promise.resolve(null)), `floor-chart:${ticker}`, onLoggedOut);
  const [clock, setClock] = useState(() => Date.now());
  useEvery(useMemo(() => () => setClock(Date.now()), []), 20_000);
  const serverNow = d ? clock + (new Date(d.now).getTime() - Date.now()) : clock;
  useEvery(chart.reload, 15_000);

  const requests = useFloorRequests(onLoggedOut);
  const risk = useFloorRisk(onLoggedOut);
  const [riskFresh, setRiskFresh] = useState<FloorRisk | null>(null);
  const riskNow = riskFresh ?? risk.data;
  const tradedRef = useRef<() => void>(() => undefined);
  const onFloorDeal = useMemo(() => () => tradedRef.current(), []);
  if (page.loading && !d) return <Loading what="the trading floor" />;
  if (page.error || !d) return <Failed message={page.error ?? "Could not load the trading floor."} onRetry={page.reload} />;
  const traded = () => { page.reload(); chart.reload(); };
  tradedRef.current = traded;
  return (
    <>
      <PageHead title="Trading floor" sub={`Your own account: the market, the news, your positions and every trade, on one screen. The floor hour is every trading day at ${d.hour_at}.`} aside={d.market_state === "open" ? "market open" : d.market_state === "opening_auction" ? "opening auction" : "market closed"} />
      {d.floor_hour && <p className="floor-hour" role="status"><strong>The floor hour</strong> until {new Date(d.floor_hour.ends_at).toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" })}: the clients call twice as often, and the best banks and clients of the hour are named at the end.</p>}
      <StormBanner r={riskNow} />
      <Bar d={d} />
      <Tape d={d} />
      <div className="floor-grid-top">
        <MarketList chosen={ticker} onChoose={setPicked} onLoggedOut={onLoggedOut} />
        <NewsFeed notes={d.notes} onChoose={setPicked} onLoggedOut={onLoggedOut} />
        <Positions d={d} chosen={ticker} onChoose={setPicked} />
      </div>
      <MandatePanel f={requests} onLoggedOut={onLoggedOut} />
      <SwapPanel f={requests} onLoggedOut={onLoggedOut} />
      {ticker && (
        <div className="floor-grid-requests">
          <AskPanel f={requests} ticker={ticker} onTraded={onFloorDeal} onLoggedOut={onLoggedOut} />
          <DeskPanel f={requests} ticker={ticker} onLoggedOut={onLoggedOut} />
        </div>
      )}
      <AlertsPanel onLoggedOut={onLoggedOut} />
      <RiskPanel r={riskNow} onSaved={setRiskFresh} />
      <BankPanel onLoggedOut={onLoggedOut} />
      <WealthPanel onLoggedOut={onLoggedOut} />
      {ticker && (
        <div className="floor-grid-bottom">
          <ExchangeBox ticker={ticker} feeBps={d.fee_bps} chart={chart.data} onTraded={traded} onLoggedOut={onLoggedOut} />
          <Chart chart={chart.data} zoom={zoom} setZoom={setZoom} now={serverNow} />
        </div>
      )}
      <div className="floor-grid-requests">
        <ChatPanel f={requests} onLoggedOut={onLoggedOut} />
        <BlocksPanel f={requests} />
      </div>
      <FloorDeals f={requests} />
      <ScorePanel f={requests} />
    </>
  );
}

// ---------------------------------------------------------------------------
// The Auction House tab
// ---------------------------------------------------------------------------

function untilWords(ms: number): string {
  if (ms <= 0) return "ended";
  const m = Math.floor(ms / 60000), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (d > 0) return `${d}d ${h % 24}h`;
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m`;
}

function Lot({ a, now }: { a: AuctionLot; now: number }) {
  const open = a.status === "open";
  return (
    <tr className={a.you_lead ? "floor-on" : ""}>
      <td><span className="floor-kind">{a.kind_name}</span></td>
      <th scope="row"><a href={a.where}>{a.lot}</a></th>
      <td className="num mono">{a.price ? formatCompact(a.price) : <span className="muted">{formatCompact(a.start_price)} start</span>}</td>
      <td className="num mono muted">{a.fair ? formatCompact(a.fair) : "—"}</td>
      <td className="num">{a.bidders}</td>
      <td className="small">{open ? (a.lowest_price_met ? "Seller's lowest price met" : "Not yet at the seller's lowest price") : a.status === "sold" ? "Sold" : a.status === "unsold" ? "Unsold" : "Withdrawn"}</td>
      <td className="small">{a.your_status ? (a.you_lead ? <strong>You lead</strong> : `Your bid: ${a.your_status}`) : ""}</td>
      <td className="num mono">{open ? untilWords(new Date(a.ends_at).getTime() - now) : "—"}</td>
    </tr>
  );
}

export function AuctionHouseWork({ onLoggedOut }: Props) {
  const page = useLoad(api.auctionHouse, "auction-house", onLoggedOut);
  useEvery(page.reload, 20_000);
  const [kind, setKind] = useState<"all" | AuctionLot["kind"]>("all");
  if (page.loading && !page.data) return <Loading what="the Auction House" />;
  if (page.error || !page.data) return <Failed message={page.error ?? "Could not load the Auction House."} onRetry={page.reload} />;
  const now = new Date(page.data.now).getTime();
  const lots = page.data.auctions.filter((a) => kind === "all" || a.kind === kind);
  const open = lots.filter((a) => a.status === "open"), done = lots.filter((a) => a.status !== "open").slice(0, 15);
  const head = (
    <thead><tr>
      <th scope="col">Kind</th><th scope="col">Lot</th><th scope="col" className="num">Leading price</th><th scope="col" className="num" title="What it was worth when the auction opened">Worth</th>
      <th scope="col" className="num">Bidders</th><th scope="col">Seller's price</th><th scope="col">You</th><th scope="col" className="num">Ends in</th>
    </tr></thead>
  );
  return (
    <>
      <PageHead title="Auction House" sub="Every auction running in the game, in one place: property, newspapers and radio stations, and banks" aside={`${page.data.auctions.filter((a) => a.status === "open").length} open`} />
      <div className="floor-filter" role="group" aria-label="Show">
        {(["all", "property", "title", "bank"] as const).map((k) => (
          <button key={k} className={kind === k ? "on" : ""} aria-pressed={kind === k} onClick={() => setKind(k)}>{k === "all" ? "All" : k === "property" ? "Property" : k === "title" ? "Media titles" : "Banks"}</button>
        ))}
      </div>
      <Panel title="Open now" aside="choose a lot to bid where it is sold">
        {open.length === 0 ? <p className="muted small">No auction is open of this kind.</p> : (
          <div className="floor-scroll-x"><table className="dense floor-table">{head}<tbody>{open.map((a) => <Lot key={a.id} a={a} now={now} />)}</tbody></table></div>
        )}
      </Panel>
      {done.length > 0 && (
        <Panel title="Just settled" aside="the latest, from the last two days">
          <div className="floor-scroll-x"><table className="dense floor-table">{head}<tbody>{done.map((a) => <Lot key={a.id} a={a} now={now} />)}</tbody></table></div>
        </Panel>
      )}
      <p className="muted small">Each seller's lowest price stays secret: only whether the leading bid has reached it. Nobody's limit is shown but your own, and no bidder is named.</p>
    </>
  );
}
