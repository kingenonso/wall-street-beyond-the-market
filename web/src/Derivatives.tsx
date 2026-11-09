// Stage 9, Part B: options and futures, dealt with the market makers' desk at its two prices; every share's risk
// figures; and, for an empire, the hedging desk and the crash fund.

import { useState } from "react";
import { api, ApiError, type DerivativeOrder, type DerivativePosition, type DerivativesBoard, type FairExplained, type Series } from "./api";
import { asKobo } from "./Empire";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Failed, Loading, Panel } from "./Shell";
import { InstrumentsPanel, SwapsPanel } from "./Swaps";
import { Term } from "./Term";

const NAMES: Record<string, string> = { BSX50: "BSX 50", TOP30: "BSX Top 30", BANKS: "BSX Banks", OILGAS: "BSX Oil & Gas", OIL: "Oil", NAIRA: "Naira ($)",
  FARM: "Farm produce", METALS: "Metals", MATERIALS: "Building materials" };
/** The indexes contracts are written on (Part 3 added the Top 30, Banks and Oil & Gas): levels in hundredths of a point. */
const INDEX_UNDERLYINGS = ["BSX50", "TOP30", "BANKS", "OILGAS"];
const KIND: Record<string, string> = { call: "Call", put: "Put", future: "Future" };

export function useAct(reload: () => void, onLoggedOut: () => void, onChanged?: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(path: string, body: unknown, done: string) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const answer = await api.post(path, body);
      const result = answer.result as { waiting?: boolean } | null;
      setNotice(result && result.waiting ? "Above the limit the Risk Manager signed: it has gone to the head to decide." : done);
      reload();
      onChanged?.();
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}
export type Act = ReturnType<typeof useAct>;

function strikeText(s: Series): string {
  if (s.strike === null) return "—";
  return INDEX_UNDERLYINGS.includes(s.underlying) ? (s.strike / 100).toLocaleString("en-NG") : formatNaira(String(s.strike));
}

function spotText(s: Series): string {
  const v = Number(s.spot);
  if (INDEX_UNDERLYINGS.includes(s.underlying)) return (v / 100).toLocaleString("en-NG", { minimumFractionDigits: 2 });
  if (s.underlying === "OIL") return `$${(v / 100).toFixed(2)} a barrel`;
  if (s.underlying === "NAIRA") return `₦${(v / 100).toLocaleString("en-NG")} to $1`;
  if (["FARM", "METALS", "MATERIALS"].includes(s.underlying)) return (v / 100).toFixed(1);
  return formatNaira(s.spot);
}

function TradeRow({ s, act, forEmpire, hedge, open, onExplain }: { s: Series; act: Act; forEmpire: boolean; hedge: string; open: boolean; onExplain: (s: Series) => void }) {
  const [n, setN] = useState("1");
  const [limit, setLimit] = useState("");
  const count = Math.max(Math.floor(Number(n) || 0), 0);
  const limitKobo = limit.trim() === "" ? null : asKobo(limit);
  const body = (side: "long" | "short") => ({ side, contracts: count, for_empire: forEmpire, purpose: forEmpire && hedge ? hedge : null, limit_kobo: limitKobo });
  const done = (side: "long" | "short") => limitKobo ? `Order placed: what matches now is done, the rest waits until the bell.` : side === "long" ? `Bought ${count} ${s.name}.` : `${s.kind === "future" ? "Sold" : "Wrote"} ${count} ${s.name}.`;
  const bad = count < 1 || (limit.trim() !== "" && limitKobo === null);
  return (
    <tr>
      <th scope="row">{KIND[s.kind]}{s.kind !== "future" && <span className="muted small"> at {strikeText(s)}</span>}<div className="muted small">to {s.expiry}</div></th>
      <td className="num mono">{s.last_trade ? formatNaira(s.last_trade) : <span className="muted">—</span>}</td>
      <td className="num mono">{formatNaira(s.fair)} <button className="button-quiet small" onClick={() => onExplain(s)} aria-label={`Why ${s.name} is worth this`}>Why?</button></td>
      <td className="num mono">{formatNaira(s.bid)}{s.best_bid && <div className="muted small">waiting {formatNaira(s.best_bid)}</div>}</td>
      <td className="num mono">{formatNaira(s.ask)}{s.best_ask && <div className="muted small">waiting {formatNaira(s.best_ask)}</div>}</td>
      <td className="num mono small">{s.kind === "future" ? formatCompact(s.margin_long) : formatCompact(s.margin_short)}</td>
      <td>
        <span className="inline-form trade-cell">
          <input className="tiny-input" type="number" min={1} max={1000} aria-label={`Contracts of ${s.name}`} value={n} onChange={(e) => setN(e.target.value)} />
          <input className="tiny-input" type="text" inputMode="decimal" aria-label={`Limit price for ${s.name} (₦, blank for the best price now)`} placeholder="limit ₦" value={limit} onChange={(e) => setLimit(e.target.value)} />
          <button className="button-quiet" disabled={act.busy || !open || bad} onClick={() => act.run(`/derivatives/${s.id}/trade`, body("long"), done("long"))}>Buy</button>
          <button className="button-quiet" disabled={act.busy || !open || bad} onClick={() => act.run(`/derivatives/${s.id}/trade`, body("short"), done("short"))}>{s.kind === "future" ? "Sell" : "Write"}</button>
        </span>
      </td>
    </tr>
  );
}

function Orders({ orders, act, forEmpire }: { orders: DerivativeOrder[]; act: Act; forEmpire: boolean }) {
  if (orders.length === 0) return null;
  return (
    <div className="scroll" tabIndex={0}>
      <table className="dense">
        <caption className="sr-only">Orders waiting</caption>
        <thead><tr><th scope="col">Waiting order</th><th scope="col">Side</th><th scope="col" className="num">Limit</th><th scope="col" className="num">Left of</th><th scope="col" className="num">Held for it</th><th scope="col"><span className="sr-only">Cancel</span></th></tr></thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <th scope="row" style={{ whiteSpace: "normal" }}>{o.name}</th>
              <td>{o.side === "buy" ? "▲ Buy" : "▼ Sell"}</td>
              <td className="num mono">{formatNaira(o.limit_price)}</td>
              <td className="num mono">{o.remaining} of {o.contracts}</td>
              <td className="num mono">{formatCompact(o.reserved)}</td>
              <td><button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/derivatives/orders/${o.id}/cancel`, { for_empire: forEmpire }, "Order cancelled; what was held is back.")}>Cancel</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Explained({ s, onClose, onLoggedOut }: { s: Series; onClose: () => void; onLoggedOut: () => void }) {
  const { data, error } = useLoad<FairExplained>(() => api.explainSeries(s.id), `explain:${s.id}`, onLoggedOut);
  const [depth, setDepth] = useState<"plain" | "method" | "maths">("plain");
  return (
    <Panel title={`Why ${s.name} is worth ${formatNaira(s.fair)}`} aside={<button className="button-quiet" onClick={onClose}>Close</button>}>
      <div className="filter-row" role="group" aria-label="How deep">
        {(["plain", "method", "maths"] as const).map((k) => <button key={k} className={depth === k ? "chip chip-on" : "chip"} aria-pressed={depth === k} onClick={() => setDepth(k)}>{k === "plain" ? "In plain words" : k === "method" ? "The method" : "The mathematics"}</button>)}
      </div>
      {error && <p className="error">{error}</p>}
      {data && <p className={depth === "maths" ? "mono small" : "small"}>{data[depth]}</p>}
      {data && <p className="muted small">The fair value is a guide. Prices are set by trades: {data.last_trade ? `the last one was at ${formatNaira(data.last_trade)}.` : "none yet in this contract."} The market makers deal a little either side of fair.</p>}
    </Panel>
  );
}

function Positions({ positions, act, forEmpire }: { positions: DerivativePosition[]; act: Act; forEmpire: boolean }) {
  const [more, setMore] = useState<Record<number, string>>({});
  if (positions.length === 0) return <p className="muted small">No open options or futures.</p>;
  return (
    <div className="scroll" tabIndex={0}>
      <table className="dense">
        <thead><tr><th scope="col">Contract</th><th scope="col">Side</th><th scope="col" className="num">Contracts</th><th scope="col" className="num">Opened at</th>
          <th scope="col" className="num">Now</th><th scope="col" className="num">Gain or loss</th><th scope="col" className="num">Margin held</th><th scope="col"><span className="sr-only">Close</span></th></tr></thead>
        <tbody>
          {positions.map((p) => {
            const up = BigInt(p.gain) >= 0n;
            return (
              <tr key={p.id}>
                <th scope="row" style={{ whiteSpace: "normal", minWidth: 150 }}>{p.name}{p.purpose && <div className="muted small">Hedge: {p.purpose}</div>}{p.margin_call && <div className="error small">▲ Margin call</div>}</th>
                <td>{p.side === "long" ? "Bought" : p.kind === "future" ? "Sold" : "Written"}</td>
                <td className="num mono">{p.contracts}</td>
                <td className="num mono">{formatNaira(p.entry_price)}</td>
                <td className="num mono">{formatNaira(p.price)}</td>
                <td className={`num mono ${up ? "change-up" : "change-down"}`}>{up ? "▲" : "▼"} {formatNaira(p.gain.replace("-", ""))}</td>
                <td className="num mono">{formatCompact(p.margin)}</td>
                <td>
                  <span className="inline-form trade-cell">
                    <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/derivatives/positions/${p.id}/close`, { for_empire: forEmpire }, "Closed with the desk.")}>Close</button>
                    {p.margin !== "0" && <>
                      <input className="tiny-input" type="text" inputMode="decimal" aria-label="More margin (₦)" placeholder="₦" value={more[p.id] ?? ""} onChange={(e) => setMore({ ...more, [p.id]: e.target.value })} />
                      <button className="button-quiet" disabled={act.busy || !asKobo(more[p.id] ?? "")} onClick={() => act.run(`/derivatives/positions/${p.id}/margin`, { amount_kobo: asKobo(more[p.id] ?? ""), for_empire: forEmpire }, "Margin added.")}>Add margin</button>
                    </>}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CrashFundPanel({ d, act }: { d: DerivativesBoard; act: Act }) {
  const e = d.empire!;
  const c = e.crash_fund;
  const [cover, setCover] = useState("");
  const canAsk = e.head || e.build === "risk_manager";
  return (
    <Panel title="The crash fund" aside={`${formatPercent(c.premium_bps, 0)} of the cover a quarter · pays when the BSX 50 falls ${formatPercent(c.trigger_bps, 0)} in a quarter`}>
      <div className="row small"><span>{e.name}'s cover</span><span className="mono">{c.cover === "0" ? "None" : formatNaira(c.cover)}</span></div>
      <div className="row small"><span>Paid in · paid out, all told</span><span className="mono">{formatCompact(c.paid_in)} · {formatCompact(c.paid_out)}</span></div>
      <div className="row small"><span>In the fund now (every member's premiums)</span><span className="mono">{formatCompact(c.fund)}</span></div>
      {canAsk && (
        <form className="inline-form" onSubmit={(ev) => { ev.preventDefault(); const k = cover === "0" ? 0 : asKobo(cover); if (k !== null) act.run("/empire/crash-fund", { cover_kobo: k }, e.head ? "Cover set." : "Asked. The head decides."); }}>
          <label className="answer">Cover (₦; 0 to leave)<input type="text" inputMode="decimal" value={cover} onChange={(ev) => setCover(ev.target.value)} /></label>
          <button className="button-outline" disabled={act.busy || (cover !== "0" && !asKobo(cover))}>{e.head ? "Set the cover" : "Ask the head"}</button>
        </form>
      )}
      {c.history.length > 0 && (
        <p className="muted small">Recent quarters: {c.history.map((h) => `${h.label} ${h.change_bps >= 0 ? "▲" : "▼"} ${formatPercent(Math.abs(h.change_bps), 1)}${h.triggered ? " (paid out)" : ""}`).join(" · ")}</p>
      )}
      <p className="muted small">Cover is at most half of what the empire is worth. If the fund cannot pay everyone in full after a crash, it shares out what it has. A premium not paid lets the cover lapse.</p>
    </Panel>
  );
}

export function DerivativesWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged?: () => void }) {
  const [underlying, setUnderlying] = useState("BSX50");
  const { data: d, error, loading, reload } = useLoad(() => api.derivatives(underlying), `derivatives:${underlying}`, onLoggedOut);
  const act = useAct(reload, onLoggedOut, onChanged);
  const [forEmpire, setForEmpire] = useState(false);
  const [hedge, setHedge] = useState("");
  const [explain, setExplain] = useState<Series | null>(null);
  if (loading && !d) return <Loading what="options and futures" />;
  if (error && !d) return <Failed message={error} onRetry={reload} />;
  if (!d) return null;
  const shown = d.series.filter((s) => s.underlying === underlying);
  const futures = shown.filter((s) => s.kind === "future");
  const options = shown.filter((s) => s.kind !== "future");
  const first = shown[0];
  const choices = ["BSX50", ...["TOP30", "BANKS", "OILGAS"].filter((u) => d.underlyings.includes(u)), "OIL", "NAIRA", "FARM", "METALS", "MATERIALS",
    ...d.underlyings.filter((u) => !(u in NAMES))];
  return (
    <>
      <div className="work-head">
        <div>
          <h1>Options and futures</h1>
          <span className="muted small">Bought and sold through the clearing house: orders match each other first, then the market makers. Settled in cash.</span>
        </div>
        {!d.open && <span className="tag tag-waiting">The desk deals while the market is open</span>}
      </div>
      {act.error && <p className="error" role="alert">{act.error}</p>}
      {act.notice && <p className="saved" role="status">{act.notice}</p>}
      <p className="small">
        A <Term word="Call option">call</Term> pays what the price ends above its strike; a <Term word="Put option">put</Term> what it ends below. Buying one costs only its price.
        Writing (selling) one brings in its price but needs margin: 20% of what it is on, plus its own value. A <Term word="Future">future</Term> gains or loses with the price, one for one,
        and is settled every night at the Closing Bell against 15% margin. A margin call not met by the next bell closes the position.
        Every trade pays a fee of 0.05% of what it is on; a tenth of it goes to the clearing house's <Term word="Default fund">default fund</Term>{" "}
        (now <span className="mono">{formatCompact(d.default_fund)}</span>), which pays the winners when a loser cannot. Whoever it covers owes the fund.
        Buying options opens at Level {d.unlock.options_level}; futures, writing options and swaps at Level {d.unlock.advanced_level} with your build's risk module learned.
        Give a limit price to wait for a better price until the bell; leave it blank to deal at the best price now.
      </p>
      {d.empire?.acts && (
        <div className="inline-form">
          <label className="check-line"><input type="checkbox" checked={forEmpire} onChange={(e) => setForEmpire(e.target.checked)} /> Trade for {d.empire.name}</label>
          {forEmpire && <label className="answer">What it protects (a hedge, scored when it ends)<input type="text" maxLength={120} value={hedge} onChange={(e) => setHedge(e.target.value)} placeholder="for example: our bank shares against a fall" /></label>}
          {forEmpire && <span className="muted small">Committed {formatCompact(d.empire.committed)} of the ₦{d.empire.limit_naira.toLocaleString("en-NG")} the Risk Manager allows; above it, the head decides.</span>}
        </div>
      )}
      <div className="filter-row" role="group" aria-label="What the contracts are on">
        {choices.map((u) => <button key={u} className={underlying === u ? "chip chip-on" : "chip"} aria-pressed={underlying === u} onClick={() => setUnderlying(u)}>{NAMES[u] ?? u}</button>)}
      </div>
      {first && <p className="small">{NAMES[underlying] ?? underlying} now: <span className="mono">{spotText(first)}</span> · one contract is on <span className="mono">{formatNaira(first.value)}</span></p>}
      {futures.length > 0 && (
        <Panel title="Futures">
          <div className="scroll" tabIndex={0}>
            <table className="dense">
              <thead><tr><th scope="col">Contract</th><th scope="col" className="num">Last trade</th><th scope="col" className="num">Fair value</th><th scope="col" className="num">You can sell at</th><th scope="col" className="num">You can buy at</th><th scope="col" className="num">Margin a contract</th><th scope="col">Trade</th></tr></thead>
              <tbody>{futures.map((s) => <TradeRow key={s.id} s={s} act={act} forEmpire={forEmpire} hedge={hedge} open={d.open} onExplain={setExplain} />)}</tbody>
            </table>
          </div>
        </Panel>
      )}
      {options.length > 0 && (
        <Panel title="Options" aside="a contract is on 100 shares, or ₦100 a point of the BSX 50">
          <div className="scroll" tabIndex={0}>
            <table className="dense">
              <thead><tr><th scope="col">Option</th><th scope="col" className="num">Last trade</th><th scope="col" className="num">Fair value</th><th scope="col" className="num">You can sell at</th><th scope="col" className="num">You can buy at</th><th scope="col" className="num">Margin to write</th><th scope="col">Trade</th></tr></thead>
              <tbody>{options.map((s) => <TradeRow key={s.id} s={s} act={act} forEmpire={forEmpire} hedge={hedge} open={d.open} onExplain={setExplain} />)}</tbody>
            </table>
          </div>
        </Panel>
      )}
      {explain && <Explained s={explain} onClose={() => setExplain(null)} onLoggedOut={onLoggedOut} />}
      {shown.length === 0 && <p className="muted">Options on single shares are offered on the BSX 50's fifty members: choose one from a company's page, or type its code below.</p>}
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const v = (e.currentTarget.elements.namedItem("code") as HTMLInputElement).value.trim().toUpperCase(); if (v) setUnderlying(v); }}>
        <label>A share's options (its code)<input name="code" className="small-input" type="text" maxLength={12} /></label>
        <button className="button-quiet">Show</button>
      </form>
      <Panel title="Your options and futures"><Positions positions={d.mine} act={act} forEmpire={false} /><Orders orders={d.my_orders} act={act} forEmpire={false} /></Panel>
      {d.empire?.acts && <Panel title={`${d.empire.name}'s options and futures`}><Positions positions={d.empire.positions} act={act} forEmpire /><Orders orders={d.empire.orders} act={act} forEmpire /></Panel>}
      {d.empire && <CrashFundPanel d={d} act={act} />}
      <SwapsPanel onLoggedOut={onLoggedOut} onChanged={onChanged} />
      <InstrumentsPanel onLoggedOut={onLoggedOut} onChanged={onChanged} />
    </>
  );
}

export function RiskWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.shareRisk, "share-risk", onLoggedOut);
  const [sort, setSort] = useState<"ticker" | "vol" | "beta" | "short">("vol");
  if (loading && !data) return <Loading what="the risk figures" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const rows = [...data.shares].sort((a, b) => sort === "ticker" ? a.ticker.localeCompare(b.ticker)
    : sort === "vol" ? (b.volatility_bps ?? 0) - (a.volatility_bps ?? 0) : sort === "beta" ? (b.beta ?? 0) - (a.beta ?? 0) : b.short_interest_bps - a.short_interest_bps);
  return (
    <>
    <div className="work-head">
      <div>
        <h1>Risk</h1>
        <div className="work-sub">
          How far each share swings, and how much it moves with the market
          <span className="dot-sep"> · </span>from its last 60 trading days; a game year is {data.year_sessions} trading days
        </div>
      </div>
    </div>
    <Panel title="Every share’s risk">
      <p className="small"><Term word="Volatility">Swing</Term>: how far the price moves in a year, on a typical reckoning. <Term word="Beta">Beta</Term>: how much it moves with the BSX 50 (1 = with it, above 1 more, below 1 less). Short interest: shares lent to short sellers, as a share of all shares. A share with too short a record is given the usual figures, marked "usual".</p>
      <div className="filter-row" role="group" aria-label="Sort by">
        {(["vol", "beta", "short", "ticker"] as const).map((k) => <button key={k} className={sort === k ? "chip chip-on" : "chip"} aria-pressed={sort === k} onClick={() => setSort(k)}>{k === "vol" ? "Swing" : k === "beta" ? "Beta" : k === "short" ? "Short interest" : "Code"}</button>)}
      </div>
      <div className="scroll" tabIndex={0}>
        <table className="dense">
          <thead><tr><th scope="col">Share</th><th scope="col" className="num">Swing a year</th><th scope="col" className="num">Beta</th><th scope="col" className="num">Short interest</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker}>
                <th scope="row"><a href={`#/companies/${r.ticker}`} style={{ textDecoration: "underline" }}>{r.ticker}</a> <span className="muted small">{r.name}</span></th>
                <td className="num mono">{r.volatility_bps === null ? "—" : formatPercent(r.volatility_bps, 0)}{!r.enough && <span className="muted small"> usual</span>}</td>
                <td className="num mono">{r.beta === null ? "—" : r.beta.toFixed(2)}</td>
                <td className="num mono">{formatPercent(r.short_interest_bps, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
    </>
  );
}
