// Floor extras, slice 1 (owner, 17 November 2026: "build"): the flash storm banner and the risk engine, inside the
// Trading floor tab. Every figure comes from the server.

import { useEffect, useState } from "react";
import { api, ApiError, type FloorRisk, type FloorUsage } from "./api";
import { formatCompact } from "./format";
import { useLoad } from "./hooks";
import { Panel } from "./Shell";

const lagosTime = (iso: string) => new Date(iso).toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" });
const pct = (bps: number) => `${Math.round(bps / 100)}%`;

export function useFloorRisk(onLoggedOut: () => void) {
  const page = useLoad(api.floorRisk, "floor-risk", onLoggedOut);
  const reload = page.reload;
  useEffect(() => {
    const id = window.setInterval(reload, 15_000);
    return () => window.clearInterval(id);
  }, [reload]);
  return page;
}

/** The storm: a banner across the floor while it lasts. */
export function StormBanner({ r }: { r: FloorRisk | null }) {
  if (!r?.storm) return null;
  return (
    <p className="floor-storm" role="alert">
      <strong>Flash storm until {lagosTime(r.storm.ends_at)}.</strong> {r.storm.reason} The clients are calling every open desk, four times as
      often and three times as big, mostly in {r.storm.ticker}. The best banks and clients of the storm earn their empires league points.
    </p>
  );
}

function Meter({ label, used, words }: { label: string; used: number; words: string }) {
  return (
    <div className="risk-meter">
      <span className="small">{label}</span>
      <div className="risk-bar" role="img" aria-label={`${label}: ${pct(used)} of the limit used`}>
        <span className={used >= 10000 ? "risk-over" : used >= 7500 ? "risk-near" : ""} style={{ width: `${Math.min(used, 10000) / 100}%` }} />
      </div>
      <span className="small mono">{words}</span>
    </div>
  );
}

function Usage({ u }: { u: FloorUsage }) {
  const loss = BigInt(u.day_pnl) < 0n ? (-BigInt(u.day_pnl)).toString() : "0";
  return (
    <>
      {u.frozen && <p className="small change-down strong">Frozen for the rest of the trading day: it lost {formatCompact(u.frozen_loss!)} on today's Floor deals.</p>}
      <Meter label="Today's loss" used={u.loss_used_bps} words={`${formatCompact(loss)} of ${formatCompact(u.limits.day_loss_most)}`} />
      <Meter label="Most in one share" used={u.name_used_bps}
             words={u.biggest ? `${formatCompact(u.biggest.worth)} ${u.biggest.shares > 0 ? "long" : "short"} ${u.biggest.ticker} of ${formatCompact(u.limits.name_most)}` : `nothing held, of ${formatCompact(u.limits.name_most)}`} />
      <p className="small muted">Largest single deal: {formatCompact(u.limits.deal_most)}. Today's Floor deals, marked to the market now: {formatCompact(u.day_pnl)}.
        {u.limits.set_by ? ` Limits set by ${u.limits.set_by}.` : " The Floor's own limits."}</p>
    </>
  );
}

function SetLimits({ id, u, base, factor, onSaved }: { id: string; u: FloorUsage; base: NonNullable<FloorRisk["base"]>; factor: number; onSaved: (r: FloorRisk) => void }) {
  const naira = (k: string) => String(Number(BigInt(k) / 100n));
  const [deal, setDeal] = useState(naira(u.limits.deal_most));
  const [name, setName] = useState(naira(u.limits.name_most));
  const [loss, setLoss] = useState(naira(u.limits.day_loss_most));
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const n = (v: string) => Math.round(Number(v.replace(/[,\s]/g, "")) * 100);
  async function save() {
    setBusy(true); setSaid(null);
    try { onSaved(await api.floorLimits(id, n(deal), n(name), n(loss))); setSaid("Saved."); }
    catch (e) { setSaid(e instanceof ApiError ? e.message : "Could not reach the server."); }
    finally { setBusy(false); }
  }
  return (
    <div className="risk-set">
      <label className="small">One deal ₦<input className="mono" inputMode="numeric" value={deal} onChange={(e) => setDeal(e.target.value)} /></label>
      <label className="small">One share ₦<input className="mono" inputMode="numeric" value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="small">Day's loss ₦<input className="mono" inputMode="numeric" value={loss} onChange={(e) => setLoss(e.target.value)} /></label>
      <button className="button-outline small" disabled={busy} onClick={save}>Set limits</button>
      {said && <span className="small">{said}</span>}
      <span className="small muted">Up to {factor}× the Floor's own: {formatCompact(base.deal_most)}, {formatCompact(base.name_most)}, {formatCompact(base.day_loss_most)}.</span>
    </div>
  );
}

/** The risk engine: a banker's own limits, and for a Risk Manager or a head, every banker in the empire. */
export function RiskPanel({ r, onSaved }: { r: FloorRisk | null; onSaved: (r: FloorRisk) => void }) {
  if (!r?.ready || (!r.mine && !r.team?.length)) return null;
  return (
    <Panel title="Risk engine" aside="limits on every bank's desk">
      {r.mine && <><p className="small strong">Your desk</p><Usage u={r.mine} /></>}
      {r.team && r.team.length > 0 && (
        <>
          <p className="small strong">Your empire's bankers</p>
          {r.team.map((b) => (
            <div key={b.player_id} className="risk-team">
              <p className="small strong">{b.name}</p>
              <Usage u={b} />
              <SetLimits id={b.player_id} u={b} base={r.base!} factor={r.most_factor!} onSaved={onSaved} />
            </div>
          ))}
        </>
      )}
      <p className="small muted">A price that would break the one-deal or one-share limit is refused. A day's loss past the limit freezes the desk until the
        next trading day, and the Floor is told. The empire's Risk Manager (or head) sets the limits; a banker with no empire works to the Floor's own.</p>
    </Panel>
  );
}
