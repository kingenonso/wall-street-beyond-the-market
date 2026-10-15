// Stage 9: "What could happen?" — a Monte Carlo test of what a player (or their empire) holds, one share or one
// building, against 1,000 possible futures drawn from public figures only. The answer is a fan chart and a few
// plain numbers. One run a day is free; the server says what a further run costs.

import { useState } from "react";
import { api, ApiError, type WhatCouldHappen } from "./api";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { Panel } from "./Shell";

type What = "portfolio" | "empire" | "share" | "property";

const W = 640, H = 220, PAD = { left: 64, right: 16, top: 12, bottom: 28 };

/** The fan: the middle outcome as a line, the likely range (half of all futures) as a darker band, the wide range
 * (nine in ten) as a lighter one. Today's value is a dashed line, so a fall below it is easy to see. */
export function FanChart({ result }: { result: WhatCouldHappen }) {
  const n = (k: string) => Number(BigInt(k) / 100n);
  const start = n(result.start);
  const points = [{ day: 0, p5: start, p25: start, p50: start, p75: start, p95: start },
    ...result.fan.map((f) => ({ day: f.day, p5: n(f.p5), p25: n(f.p25), p50: n(f.p50), p75: n(f.p75), p95: n(f.p95) }))];
  const low = Math.min(...points.map((p) => p.p5)), high = Math.max(...points.map((p) => p.p95));
  const room = Math.max((high - low) * 0.08, Math.abs(high) * 0.01, 1);
  const top = high + room, bottom = low - room;
  const x = (d: number) => PAD.left + (d * (W - PAD.left - PAD.right)) / Math.max(result.days, 1);
  const y = (v: number) => PAD.top + ((top - v) * (H - PAD.top - PAD.bottom)) / (top - bottom);
  const band = (a: "p5" | "p25", b: "p95" | "p75") =>
    points.map((p, i) => `${i ? "L" : "M"}${x(p.day).toFixed(1)},${y(p[b]).toFixed(1)}`).join(" ")
    + " " + [...points].reverse().map((p) => `L${x(p.day).toFixed(1)},${y(p[a]).toFixed(1)}`).join(" ") + " Z";
  const ticks = [0, 1, 2, 3].map((i) => bottom + ((top - bottom) * i) / 3);
  const kobo = (v: number) => formatCompact(String(BigInt(Math.round(v)) * 100n));
  return (
    <figure className="chart fan">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Fan of ${result.paths} futures over ${result.days} trading days. Middle outcome ${formatNaira(result.median)}; nine in ten end between ${formatNaira(result.worst_likely)} and ${formatNaira(result.best_likely)}.`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="grid" />
            <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" className="axis">{kobo(t)}</text>
          </g>
        ))}
        <path d={band("p5", "p95")} className="fan-wide" />
        <path d={band("p25", "p75")} className="fan-likely" />
        <line x1={x(0)} x2={x(result.days)} y1={y(start)} y2={y(start)} className="fan-today" />
        <path d={points.map((p, i) => `${i ? "L" : "M"}${x(p.day).toFixed(1)},${y(p.p50).toFixed(1)}`).join(" ")} className="fan-middle" />
        <text x={x(0)} y={H - 8} className="axis">Today</text>
        <text x={x(result.days)} y={H - 8} textAnchor="end" className="axis">{result.days} trading days</text>
      </svg>
      <figcaption className="fan-key small">
        <span><span className="swatch fan-wide-swatch" aria-hidden="true" /> Nine futures in ten</span>
        <span><span className="swatch fan-likely-swatch" aria-hidden="true" /> Half of them</span>
        <span><span className="fan-line-swatch" aria-hidden="true">—</span> The middle one</span>
        <span><span className="fan-today-swatch" aria-hidden="true">- -</span> Today</span>
      </figcaption>
    </figure>
  );
}

export function WhatCouldHappenPanel({ what, ticker, propertyId, title = "What could happen?", onLoggedOut }: {
  what: What; ticker?: string; propertyId?: number; title?: string; onLoggedOut: () => void;
}) {
  const [horizon, setHorizon] = useState<"quarter" | "year">("quarter");
  const [result, setResult] = useState<WhatCouldHappen | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    setBusy(true); setError(null);
    try {
      const answer = await api.whatCouldHappen({ what, horizon, ticker, property_id: propertyId });
      setResult(answer.result);
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title={title} aside="1,000 possible futures, from public figures">
      <div className="inline-form">
        <label>Looking ahead
          <select value={horizon} onChange={(e) => setHorizon(e.target.value as "quarter" | "year")}>
            <option value="quarter">A quarter (7 trading days)</option>
            <option value="year">A game year (28 trading days)</option>
          </select>
        </label>
        <button className="button-outline" disabled={busy} onClick={run}>{busy ? "Working it out…" : "Run the test"}</button>
        <span className="muted small">One run a day is free; after that each costs ₦5,000.</span>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {result && (
        <>
          <p className="small"><strong>{result.title}</strong>{result.fee !== "0" ? ` · this run cost ${formatNaira(result.fee)}` : " · today's free run"}</p>
          <div className="tiles">
            <div className="tile"><div className="muted small">Today</div><div className="mono figure-small">{formatCompact(result.start)}</div></div>
            <div className="tile"><div className="muted small">The middle outcome</div><div className="mono figure-small">{formatCompact(result.median)}</div></div>
            <div className="tile"><div className="muted small">Chance of ending lower</div><div className="mono figure-small">{formatPercent(result.chance_of_loss_bps, 0)}</div></div>
            <div className="tile"><div className="muted small">Worst loss, one time in twenty</div><div className="mono figure-small change-down">▼ {formatCompact(result.value_at_risk)}</div></div>
            {result.chance_of_margin_call_bps !== null && (
              <div className="tile"><div className="muted small">Chance of a margin call</div><div className="mono figure-small">{formatPercent(result.chance_of_margin_call_bps, 0)}</div></div>
            )}
          </div>
          <FanChart result={result} />
          <details className="small">
            <summary>What the test assumes</summary>
            <ul>{result.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          </details>
        </>
      )}
    </Panel>
  );
}
