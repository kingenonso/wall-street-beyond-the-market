import { useState } from "react";
import type { FiledReport } from "./api";
import { formatCompact } from "./format";

// Two series, checked for colour-blind separation and contrast against the panel colour.
const COLORS = ["#B88A30", "#8B7CF6"] as const;

export type TrendPoint = { label: string; first: number; second: number };

const W = 720, H = 250;
const PAD = { left: 64, right: 86, top: 14, bottom: 30 };

/** A round number at or above `value`, for the top of the scale. */
function niceCeil(value: number): number {
  if (value <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(value));
  return [1, 2, 2.5, 5, 10].map((m) => m * step).find((candidate) => candidate >= value) ?? 10 * step;
}

export const naira = (kobo: string) => Number(BigInt(kobo) / 100n);
const asKobo = (value: number) => (BigInt(Math.round(value)) * 100n).toString();

/** Sales and net profit by quarter, as filed. One scale, one unit (naira). */
export function TrendChart({ reports }: { reports: FiledReport[] }) {
  return (
    <LineChart
      names={["Sales", "Net profit"]}
      data={reports.map((r) => ({
        label: r.period_label,
        first: naira(r.figures.income_statement.revenue),
        second: naira(r.figures.income_statement.net_profit),
      }))}
    />
  );
}

/** Two amounts in naira over the same quarters, on one scale. */
export function LineChart({ names, data }: { names: [string, string]; data: TrendPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const SERIES = [
    { key: "first", label: names[0], color: COLORS[0] },
    { key: "second", label: names[1], color: COLORS[1] },
  ] as const;
  if (data.length < 2) return null;

  const top = niceCeil(Math.max(...data.map((d) => Math.max(d.first, d.second))));
  const lowest = Math.min(0, ...data.map((d) => Math.min(d.first, d.second)));
  const bottom = lowest < 0 ? -niceCeil(-lowest) : 0;
  const x = (i: number) => PAD.left + (i * (W - PAD.left - PAD.right)) / (data.length - 1);
  const y = (v: number) => PAD.top + ((top - v) * (H - PAD.top - PAD.bottom)) / (top - bottom);
  const ticks = [0, 1, 2, 3, 4].map((n) => bottom + ((top - bottom) * n) / 4);
  const band = (W - PAD.left - PAD.right) / (data.length - 1);

  return (
    <figure className="chart">
      <div className="legend" aria-hidden="true">
        {SERIES.map((s) => (
          <span key={s.key} className="legend-item">
            <span className="swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <div className="chart-frame">
        <svg viewBox={`0 0 ${W} ${H}`} role="img"
             aria-label={`${names[0]} and ${names[1]} by quarter, from ${data[0].label} to ${data[data.length - 1].label}. The same figures are in the table on this page.`}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "axis-zero" : "grid-line"} />
              <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" className="tick-label">{formatCompact(asKobo(tick))}</text>
            </g>
          ))}
          {data.map((d, i) => (
            <text key={d.label} x={x(i)} y={H - 8} textAnchor="middle" className="tick-label">
              {d.label.replace("Year ", "Y")}
            </text>
          ))}
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} className="crosshair" />}
          {SERIES.map((s) => (
            <g key={s.key}>
              <polyline fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"
                        points={data.map((d, i) => `${x(i)},${y(d[s.key])}`).join(" ")} />
              {data.map((d, i) => (
                <circle key={i} cx={x(i)} cy={y(d[s.key])} r={hover === i ? 5 : 4} fill={s.color} className="marker" />
              ))}
              <text x={W - PAD.right + 10} y={y(data[data.length - 1][s.key]) + 4} className="end-label">{s.label}</text>
            </g>
          ))}
          {/* Hover targets: a whole column each, far easier to hit than a dot. */}
          {data.map((_, i) => (
            <rect key={i} x={x(i) - band / 2} y={PAD.top} width={band} height={H - PAD.top - PAD.bottom} fill="transparent"
                  onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0}
                  aria-label={`${data[i].label}: ${names[0]} ${formatCompact(asKobo(data[i].first))}, ${names[1]} ${formatCompact(asKobo(data[i].second))}`} />
          ))}
        </svg>
        {hover !== null && (
          <div className="tooltip" style={{ left: `${(x(hover) / W) * 100}%` }} role="status">
            <div className="strong">{data[hover].label}</div>
            {SERIES.map((s) => (
              <div key={s.key} className="tooltip-row">
                <span><span className="swatch" style={{ background: s.color }} />{s.label}</span>
                <span className="mono">{formatCompact(asKobo(data[hover][s.key]))}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </figure>
  );
}
