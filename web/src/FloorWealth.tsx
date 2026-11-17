// Floor extras, slice 3 (owner, 17 November 2026: "Ok go ahead"): the wealth desk, inside the Trading floor tab. Rich
// computer clients come looking for someone to look after their money; asset managers pitch a fee, trade the client's own
// account within its limits, and are reviewed at every quarter's close. Every figure comes from the server.

import { useEffect, useState } from "react";
import { api, ApiError, type FloorWealth, type WealthClient, type WealthManaged } from "./api";
import { formatCompact } from "./format";
import { useLoad } from "./hooks";
import { Panel } from "./Shell";

const lagosTime = (iso: string) => new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", weekday: "short", hour: "2-digit", minute: "2-digit" });
const pct = (bps: number) => `${(bps / 100).toFixed(1)}%`;
const VERDICT: Record<string, string> = { adds: "added money", stays: "stayed", warns: "warned", leaves: "left" };

function useAct(setFresh: (w: FloorWealth) => void) {
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function act(run: () => Promise<FloorWealth>, done: string) {
    setBusy(true); setSaid(null);
    try { setFresh(await run()); setSaid(done); }
    catch (e) { setSaid(e instanceof ApiError ? e.message : "Could not reach the server."); }
    finally { setBusy(false); }
  }
  return { said, busy, act };
}

function Limits({ c }: { c: WealthClient }) {
  return (
    <p className="small muted">
      Wants {c.goal}: about {pct(c.goal_bps)} a year. At most {pct(c.most_shares_bps)} in shares, at least {pct(c.least_cash_bps)} in cash, and no fall
      of more than {pct(c.most_drop_bps)} from its high.{c.banned.length ? ` It will not hold: ${c.banned.join(", ").toLowerCase()}.` : ""}
    </p>
  );
}

function Seeking({ c, w, setFresh }: { c: NonNullable<FloorWealth["seeking"]>[number]; w: FloorWealth; setFresh: (w: FloorWealth) => void }) {
  const [fee, setFee] = useState(c.my_pitch ? String(c.my_pitch.fee_bps / 100) : "1");
  const [perf, setPerf] = useState(c.my_pitch ? String(c.my_pitch.perf_bps / 100) : "10");
  const { said, busy, act } = useAct(setFresh);
  return (
    <div className="wealth-client">
      <p className="small"><strong>{c.name}</strong> brings {formatCompact(c.amount)}. Choosing at {lagosTime(c.pitches_until)}; {c.rivals}{" "}
        {c.rivals === 1 ? "other manager has" : "other managers have"} pitched.</p>
      <Limits c={c} />
      {w.manager && (
        <div className="wealth-pitch">
          <label className="small">Yearly fee <input className="mono" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} />%</label>
          <label className="small">Share of the gain above its goal <input className="mono" inputMode="decimal" value={perf} onChange={(e) => setPerf(e.target.value)} />%</label>
          <button className="button-outline small" disabled={busy}
                  onClick={() => act(() => api.floorWealthPitch(c.id, Math.round(Number(fee) * 100), Math.round(Number(perf) * 100)), "Pitched.")}>
            {c.my_pitch ? "Change the pitch" : "Pitch"}
          </button>
          {said && <span className="small"> {said}</span>}
        </div>
      )}
    </div>
  );
}

function Managed({ c, setFresh }: { c: WealthManaged; setFresh: (w: FloorWealth) => void }) {
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("1000");
  const [price, setPrice] = useState("");
  const { said, busy, act } = useAct(setFresh);
  const over = (v: number, most: number) => (v > most ? "change-down strong" : "");
  return (
    <div className="wealth-client">
      <p className="small"><strong>{c.name}</strong>: {formatCompact(c.worth)}, {c.quarter_bps >= 0 ? "up" : "down"} {pct(Math.abs(c.quarter_bps))} this quarter.
        Satisfaction {pct(c.satisfaction_bps)}. Your fee: {pct(c.fee_bps)} a year and {pct(c.perf_bps)} of the gain above its goal.</p>
      <p className="small">
        <span className={over(c.shares_bps, c.most_shares_bps)}>Shares {pct(c.shares_bps)} of at most {pct(c.most_shares_bps)}</span>;{" "}
        <span className={c.cash_bps < c.least_cash_bps ? "change-down strong" : ""}>cash {pct(c.cash_bps)} of at least {pct(c.least_cash_bps)}</span>;{" "}
        <span className={over(c.fall_bps, c.most_drop_bps)}>fall from its high {pct(c.fall_bps)} of at most {pct(c.most_drop_bps)}</span>.
      </p>
      <Limits c={c} />
      {c.lines.length > 0 && <p className="small mono">{c.lines.map((l) => `${l.ticker} ${l.shares.toLocaleString("en-NG")} (${formatCompact(l.value)})`).join(", ")}</p>}
      <div className="wealth-pitch">
        <select value={side} onChange={(e) => setSide(e.target.value as "buy" | "sell")}><option value="buy">Buy</option><option value="sell">Sell</option></select>
        <input className="mono wealth-ticker" placeholder="Code" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} maxLength={3} />
        <input className="mono" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} aria-label="Shares" />
        <label className="small">at ₦<input className="mono" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
        <button className="button-outline small" disabled={busy || ticker.length !== 3}
                onClick={() => act(() => api.floorWealthTrade(c.id, ticker, side, Math.round(Number(qty)), Math.round(Number(price) * 100)), "Order placed for the client.")}>
          Place for the client
        </button>
      </div>
      {c.orders.map((o) => (
        <p key={o.id} className="small">Waiting: {o.side} {o.remaining.toLocaleString("en-NG")} {o.ticker} at {formatCompact(o.limit_price)}{" "}
          <button className="button-outline small" disabled={busy} onClick={() => act(() => api.floorWealthCancel(c.id, o.id), "Cancelled.")}>Cancel</button></p>
      ))}
      {c.breaches.map((b, i) => <p key={i} className="small change-down">Limit broken: {b.words}</p>)}
      {c.reviews.map((r) => (
        <p key={r.period} className="small muted">Review: {pct(r.return_bps)} after fees against a fair {pct(r.benchmark_bps)}, {r.breaches} limits broken,
          fees {formatCompact(r.fee)}{BigInt(r.perf_fee) > 0n ? ` and ${formatCompact(r.perf_fee)} for the gain` : ""}. It {VERDICT[r.verdict]}. {r.words}</p>
      ))}
      <button className="button-outline small" disabled={busy} onClick={() => act(() => api.floorWealthHandBack(c.id), "Handed back.")}>Hand the client back</button>
      {said && <span className="small"> {said}</span>}
    </div>
  );
}

/** The wealth desk: clients looking for a manager, and for an asset manager, the clients they look after. */
export function WealthPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const page = useLoad(api.floorWealth, "floor-wealth", onLoggedOut);
  const reload = page.reload;
  useEffect(() => {
    const id = window.setInterval(reload, 15_000);
    return () => window.clearInterval(id);
  }, [reload]);
  const [fresh, setFresh] = useState<FloorWealth | null>(null);
  useEffect(() => setFresh(null), [page.data]);
  const w = fresh ?? page.data;
  if (!w?.ready || (!w.manager && !w.seeking?.length)) return null;
  return (
    <Panel title="Wealth desk" aside="clients looking for someone to look after their money">
      {w.manager && w.record && (
        <p className="small">Your record: {w.record.kept} {w.record.kept === 1 ? "client" : "clients"} now (at most {w.most_clients}), {w.record.left} lost,
          {w.record.satisfaction_bps !== null ? ` satisfaction ${pct(w.record.satisfaction_bps)} at ${w.record.reviews} reviews` : " no reviews yet"}.
          Clients weigh this against your fee.</p>
      )}
      {(w.clients ?? []).map((c) => <Managed key={c.id} c={c} setFresh={setFresh} />)}
      <p className="small strong">Looking for a manager</p>
      {!w.seeking?.length && <p className="small muted">No client is looking just now. They arrive from time to time while the market is open.</p>}
      {(w.seeking ?? []).map((c) => <Seeking key={c.id} c={c} w={w} setFresh={setFresh} />)}
      {(w.gone ?? []).length > 0 && <p className="small muted">Clients lost: {w.gone!.map((g) => `${g.name} (${g.left_why})`).join("; ")}.</p>}
      <p className="small muted">The client's money sits in its own account, which you trade at prices you name. Its limits are looked at through the day: each
        break costs its satisfaction, and three in a quarter and it leaves with its money. At every quarter's close it pays your fees and judges the quarter
        against a fair benchmark, then adds money, stays, warns or leaves. Fees are at most {pct(w.most_fee_bps ?? 0)} a year and {pct(w.most_perf_bps ?? 0)} of
        the gain above its goal.</p>
    </Panel>
  );
}
