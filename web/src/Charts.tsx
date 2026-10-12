// The redesign's charts and small pictures. Each is drawn as plain SVG, with words beside it
// (a label for screen readers, and the key figures in text), so nothing depends on colour alone.
//   Sparkline   a few days' prices as a small line
//   AreaChart   one series over time, with an optional baseline and trading volume
//   CompareChart two series started at 100, so the faster grower shows
//   DepthBars   who is waiting to buy and to sell, as bars
//   MixBar      how a whole splits into parts, with a legend

import { useId, useState, type ReactNode } from "react";

const UP = "var(--up)", DOWN = "var(--down)", FLAT = "var(--muted)";

export function wayOf(first: number, last: number): "up" | "down" | "flat" {
  return last > first ? "up" : last < first ? "down" : "flat";
}

/** A few closing prices as a small line, coloured by the direction over the whole run. */
export function Sparkline({ values, width = 90, height = 24, label }: { values: number[]; width?: number; height?: number; label?: string }) {
  if (values.length < 2) return <span className="muted small" aria-label={label}>–</span>;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const points = values.map((v, i) => `${((i * width) / (values.length - 1)).toFixed(1)},${(height - 2 - ((v - lo) / span) * (height - 4)).toFixed(1)}`).join(" ");
  const way = wayOf(values[0], values[values.length - 1]);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <polyline points={points} fill="none" stroke={way === "up" ? UP : way === "down" ? DOWN : FLAT} strokeWidth="1.5" />
    </svg>
  );
}

export type SeriesPoint = { label: string; value: number; volume?: number };

/** One series over time: a line with a light fill, an optional dashed baseline (yesterday's close,
 * or where a holding was bought), optional volume bars, and the value under the pointer. */
export function AreaChart({ points, label, format, baseline, baselineLabel, height = 220, color }: {
  points: SeriesPoint[];
  /** What the chart shows, in words, for screen readers. */
  label: string;
  format: (value: number) => string;
  baseline?: number;
  baselineLabel?: string;
  height?: number;
  color?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return <p className="muted small">Not enough trading yet to draw a chart.</p>;
  const W = 800, H = height, top = 10, volH = points.some((p) => p.volume) ? 40 : 0, bottom = H - volH - 6;
  const values = points.map((p) => p.value).concat(baseline !== undefined ? [baseline] : []);
  let lo = Math.min(...values), hi = Math.max(...values);
  const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.02 || 1;
  lo -= pad; hi += pad;
  const x = (i: number) => (i * W) / (points.length - 1);
  const y = (v: number) => top + ((hi - v) * (bottom - top)) / (hi - lo);
  const line = "M" + points.map((p, i) => `${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" L");
  const way = wayOf(baseline ?? points[0].value, points[points.length - 1].value);
  const stroke = color ?? (way === "up" ? UP : way === "down" ? DOWN : FLAT);
  const maxVol = Math.max(1, ...points.map((p) => p.volume ?? 0));
  const shown = hover ?? points.length - 1;
  return (
    <figure className="area-chart" style={{ margin: 0 }}>
      <div className="area-chart-readout small">
        <span className="muted">{points[shown].label}</span>{" "}
        <span className="mono strong">{format(points[shown].value)}</span>
        {points[shown].volume !== undefined && <span className="muted"> · {points[shown].volume!.toLocaleString("en-NG")} traded</span>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label} style={{ width: "100%", height, display: "block" }}
           onMouseLeave={() => setHover(null)}
           onMouseMove={(e) => {
             const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
             setHover(Math.max(0, Math.min(points.length - 1, Math.round(((e.clientX - box.left) / box.width) * (points.length - 1)))));
           }}>
        {[0.25, 0.5, 0.75].map((f) => <line key={f} x1={0} x2={W} y1={top + (bottom - top) * f} y2={top + (bottom - top) * f} stroke="var(--border)" vectorEffect="non-scaling-stroke" />)}
        {baseline !== undefined && <line x1={0} x2={W} y1={y(baseline)} y2={y(baseline)} stroke="var(--muted)" strokeDasharray="5 5" vectorEffect="non-scaling-stroke" />}
        <path d={`${line} L${W} ${bottom} L0 ${bottom} Z`} fill={stroke} fillOpacity="0.10" />
        <path d={line} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {volH > 0 && points.map((p, i) => {
          const h = ((p.volume ?? 0) / maxVol) * (volH - 4);
          const w = Math.max(2, W / points.length - 3);
          return <rect key={i} x={Math.min(W - w, Math.max(0, x(i) - w / 2))} y={H - h} width={w} height={h} fill="var(--border-strong)" />;
        })}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={top} y2={H} stroke="var(--muted)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
      </svg>
      <figcaption className="mono muted small area-chart-axis">
        <span>{points[0].label}</span>
        {baseline !== undefined && baselineLabel && <span>dashed line: {baselineLabel}</span>}
        <span>{points[points.length - 1].label}</span>
      </figcaption>
    </figure>
  );
}

/** Two series started at 100, so the one that grew faster sits higher. */
export function CompareChart({ first, second, labels, names, height = 170 }: {
  first: number[]; second: number[]; labels: [string, string]; names: [string, string]; height?: number;
}) {
  if (first.length < 2 || second.length < 2) return <p className="muted small">The comparison starts after two Closing Bells.</p>;
  const a = first.map((v) => (v / first[0]) * 100), b = second.map((v) => (v / second[0]) * 100);
  const all = a.concat(b);
  const lo = Math.min(...all) - 0.5, hi = Math.max(...all) + 0.5, W = 800, H = height;
  const path = (vals: number[]) => "M" + vals.map((v, i) => `${((i * W) / (vals.length - 1)).toFixed(1)} ${(4 + ((hi - v) * (H - 8)) / (hi - lo)).toFixed(1)}`).join(" L");
  const lastA = a[a.length - 1], lastB = b[b.length - 1];
  return (
    <figure style={{ margin: 0 }}>
      <ul className="legend-list">
        <li><svg aria-hidden="true" width="18" height="4"><rect width="18" height="3" fill="var(--gold)" /></svg> {names[0]}: <span className="mono">{lastA.toFixed(1)}</span></li>
        <li><svg aria-hidden="true" width="18" height="4"><line x1="0" y1="2" x2="18" y2="2" stroke="var(--muted)" strokeWidth="2" strokeDasharray="4 3" /></svg> {names[1]}: <span className="mono">{lastB.toFixed(1)}</span></li>
      </ul>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" style={{ width: "100%", height, display: "block" }}
           aria-label={`${names[0]} ${lastA >= 100 ? "rose" : "fell"} to ${lastA.toFixed(1)}; ${names[1]} ${lastB >= 100 ? "rose" : "fell"} to ${lastB.toFixed(1)}, both from 100`}>
        <path d={path(b)} fill="none" stroke="var(--muted)" strokeWidth="2" strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />
        <path d={path(a)} fill="none" stroke="var(--gold)" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <figcaption className="mono muted small area-chart-axis"><span>{labels[0]}</span><span>{labels[1]}</span></figcaption>
    </figure>
  );
}

export type Level = { price: string; quantity: number };

/** Who is waiting to trade: sellers asking (above) and buyers offering (below), as bars. */
export function DepthBars({ sellers, buyers, format }: { sellers: Level[]; buyers: Level[]; format: (price: string) => string }) {
  const max = Math.max(1, ...sellers.map((l) => l.quantity), ...buyers.map((l) => l.quantity));
  const row = (l: Level, side: "sell" | "buy") => (
    <div key={`${side}-${l.price}`} className="depth-row">
      <span className={`mono ${side === "sell" ? "change-down" : "change-up"}`}>{side === "sell" ? "▼" : "▲"} {format(l.price)}</span>
      <span className="depth-track" aria-hidden="true"><span className={`depth-bar depth-${side}`} style={{ width: `${Math.max(2, (l.quantity / max) * 100)}%` }} /></span>
      <span className="mono muted">{l.quantity.toLocaleString("en-NG")}</span>
    </div>
  );
  if (sellers.length === 0 && buyers.length === 0) return <p className="muted small">Nobody is waiting to buy or sell this share right now.</p>;
  const bestSell = sellers.length ? Number(sellers[0].price) : null, bestBuy = buyers.length ? Number(buyers[0].price) : null;
  return (
    <div className="depth" role="group" aria-label="Who is waiting to trade">
      {[...sellers].reverse().map((l) => row(l, "sell"))}
      <div className="depth-gap mono small">
        {bestSell !== null && bestBuy !== null ? `Gap between best seller and best buyer: ${format(String(bestSell - bestBuy))}` : "Only one side is waiting"}
      </div>
      {buyers.map((l) => row(l, "buy"))}
      <div className="muted small" style={{ marginTop: 6 }}>▼ sellers asking · ▲ buyers offering · bar length = number of shares</div>
    </div>
  );
}

export type MixPart = { label: string; value: number; color: string; note?: ReactNode };

/** How a whole splits into parts: one bar, and a legend with each part's share in words. */
export function MixBar({ parts, label }: { parts: MixPart[]; label: string }) {
  const total = parts.reduce((sum, p) => sum + Math.max(0, p.value), 0) || 1;
  const id = useId();
  return (
    <div>
      <div className="mix-bar" role="img" aria-labelledby={id}>
        {parts.filter((p) => p.value > 0).map((p) => <span key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />)}
      </div>
      <ul className="legend-list" id={id} aria-label={label}>
        {parts.map((p) => (
          <li key={p.label}>
            <svg aria-hidden="true" width="10" height="10"><rect width="10" height="10" rx="2" fill={p.color} /></svg> {p.label}{" "}
            <span className="mono">{p.note} · {Math.round((Math.max(0, p.value) / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
