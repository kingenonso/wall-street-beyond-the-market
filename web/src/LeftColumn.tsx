import { useState, type PointerEvent } from "react";
import { api, type Indicator, type NewsItem, type Player, type Readout } from "./api";
import { useLoad } from "./hooks";
import { Change, Panel } from "./Shell";
import { formatCompact } from "./format";
import type { LiveClock } from "./useClock";

/**
 * The left column that never moves: three panels, on every page.
 *
 * Your money over time, the market's indicators, and the quotes and news you keep beside you. It sits at the
 * left edge of the screen the way the reference has it, and the sections live in the strip's menu instead, so
 * the column costs no navigation: it is the same column on the desk, on a company's page and in the courts.
 *
 * Everything in it is read from one small server answer (`/api/readout`), which is cheap on purpose: this
 * column is drawn on every screen, so it reads the quarter that has closed and the player's own recorded
 * closes, and computes no share prices. The tape across the top already carries the index and the prices, live.
 */
export function LeftColumn({ player, live, onLoggedOut }: {
  player: Player;
  live: LiveClock | null;
  onLoggedOut: () => void;
}) {
  // Read again when the game's day turns: a new close moves the chart, and a new quarter moves the indicators.
  const date = live?.clock.game_date;
  const readout = useLoad(api.readout, date ? `Y${date.year}Q${date.quarter}D${date.day_of_quarter}` : "waiting", onLoggedOut);
  return (
    <aside className="column" aria-label="Your money, the market and the news">
      <NetWorthPanel player={player} readout={readout.data} />
      <IndicatorsPanel readout={readout.data} />
      <QuotesNewsPanel readout={readout.data} onLoggedOut={onLoggedOut} />
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Your money over time
// ---------------------------------------------------------------------------

/** A round number at or above `value`, for the top of the scale. */
function niceCeil(value: number): number {
  if (value <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(value));
  return [1, 2, 2.5, 5, 10].map((m) => m * step).find((candidate) => candidate >= value) ?? 10 * step;
}

const PLOT = { width: 260, height: 132, left: 4, right: 62, top: 20, bottom: 20 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The month a recorded close fell in, from its date written the way the server writes it (2026-11-07). */
function monthOf(iso: string): string {
  const month = Number(iso.slice(5, 7));
  return MONTHS[month - 1] ?? "";
}

type Point = { label: string; value: number; bench: number | null };

/**
 * The player's own money, as a filled chart. It fills under the line, conventionally: the reference fills above
 * it, which puts the colour where the money is not, and every other chart in the game fills downward. The scale
 * runs down the right-hand edge, the name and the unit sit inside the plot, and the months run along the foot.
 */
function NetWorthPlot({ name, points }: { name: string; points: Point[] }) {
  const [at, setAt] = useState<number | null>(null);
  const W = PLOT.width, H = PLOT.height;
  const highest = Math.max(...points.map((p) => Math.max(p.value, p.bench ?? 0)));
  const lowest = Math.min(...points.map((p) => Math.min(p.value, p.bench ?? p.value)));
  // A record that moved only a little is drawn from just under its lowest point, so the two lines can be told apart;
  // one that swung by half or more is drawn from nought.
  const floor = lowest > highest * 0.5 ? Math.floor((lowest * 0.97) / niceCeil(highest / 20)) * niceCeil(highest / 20) : 0;
  const top = floor + niceCeil(highest - floor);
  const span = Math.max(1, points.length - 1);
  const x = (i: number) => PLOT.left + (i * (W - PLOT.left - PLOT.right)) / span;
  const y = (value: number) => PLOT.top + ((top - value) * (H - PLOT.top - PLOT.bottom)) / (top - floor || 1);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((n) => floor + (top - floor) * n);
  const line = points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ");
  // The BSX 50 beside it: the first figure, grown or shrunk exactly as the index was. Drawn only where the index has a close.
  const bench = points.map((p, i) => (p.bench === null ? null : `${x(i)},${y(p.bench)}`)).filter(Boolean).join(" ");
  const first = points[0], last = points[points.length - 1];
  // About three months along the foot, always including the last, and never two labels for one month.
  const every = Math.max(1, Math.floor(points.length / 3));
  const marks = points.map((p, i) => ({ ...p, i })).filter((p, i) => i === points.length - 1 || (p.i % every === 0 && points.length - 1 - p.i > every / 2));
  const shown = at === null ? null : points[at];

  function look(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const within = ((event.clientX - rect.left) / rect.width) * W;
    const found = Math.round(((within - PLOT.left) / (W - PLOT.left - PLOT.right)) * span);
    setAt(Math.min(points.length - 1, Math.max(0, found)));
  }

  return (
    <figure className="networth">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`${name}'s money, from ${naira(first.value)} on ${first.label} to ${naira(last.value)} on ${last.label}, over ${points.length} closes.`}
           onPointerMove={look} onPointerLeave={() => setAt(null)}>
        <text x={PLOT.left} y={12} className="plot-title">{name}, in naira</text>
        {bench && (
          <g className="plot-legend">
            <line x1={W - PLOT.right - 46} x2={W - PLOT.right - 34} y1={9} y2={9} className="plot-bench" />
            <text x={W - PLOT.right - 31} y={12} className="tick-label">BSX 50</text>
          </g>
        )}
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PLOT.left} x2={W - PLOT.right} y1={y(tick)} y2={y(tick)} className={tick === floor ? "axis-zero" : "grid-line"} />
            <text x={W - PLOT.right + 6} y={y(tick) + 3} className="tick-label">{formatCompact(Math.round(tick * 100).toString())}</text>
          </g>
        ))}
        <polygon className="plot-fill" points={`${PLOT.left},${y(floor)} ${line} ${x(points.length - 1)},${y(floor)}`} />
        {bench && <polyline className="plot-bench" points={bench} />}
        <polyline className="plot-line" points={line} />
        {/* The first and last months are anchored inward: a name centred on the plot's edge loses its first letter to
            the edge of the drawing, and "Mar" cut to "lar" is a month nobody can read. */}
        {marks.map((p) => (
          <text key={p.i} x={x(p.i)} y={H - 6} className="tick-label"
                textAnchor={p.i === 0 ? "start" : p.i === points.length - 1 ? "end" : "middle"}>
            {monthOf(p.label)}
          </text>
        ))}
        {at !== null && shown && (
          <g>
            <line x1={x(at)} x2={x(at)} y1={PLOT.top} y2={H - PLOT.bottom} className="crosshair" />
            <circle cx={x(at)} cy={y(shown.value)} r={3} className="plot-dot" />
            <text x={x(at)} y={y(shown.value) - 6} textAnchor={x(at) > W - PLOT.right - 40 ? "end" : "start"} className="plot-read">
              {formatCompact(Math.round(shown.value * 100).toString())}
              {shown.bench !== null ? ` · BSX 50 ${formatCompact(Math.round(shown.bench * 100).toString())}` : ""}
            </text>
          </g>
        )}
      </svg>
      <figcaption className="muted small">
        {shown ? `${shown.label}` : `Over ${points.length} closes, to the last bell`}
      </figcaption>
    </figure>
  );
}

/** A whole naira figure, written the way the rest of the game writes money, for the chart's own words. */
function naira(value: number): string {
  return formatCompact(Math.round(value * 100).toString());
}

function NetWorthPanel({ player, readout }: { player: Player; readout: Readout | null }) {
  const points: Point[] = (readout?.net_worth ?? []).map((d) => ({
    label: d.session_date, value: Number(BigInt(d.total_kobo) / 100n),
    bench: d.index_kobo == null ? null : Number(BigInt(d.index_kobo) / 100n),
  }));
  const last = points.length ? points[points.length - 1].value : null;
  const own = readout?.net_worth_change_bps ?? null, index = readout?.index_change_bps ?? null;
  const pct = (bps: number) => `${bps > 0 ? "+" : bps < 0 ? "−" : ""}${(Math.abs(bps) / 100).toFixed(1)}%`;
  return (
    <Panel title="Net worth history" aside={last === null ? undefined : naira(last)}>
      {readout === null ? (
        <p className="muted small">Reading your record…</p>
      ) : points.length === 0 ? (
        <p className="muted small">Your first figure is written at tonight’s Closing Bell. Until then this panel stays empty rather than guessing.</p>
      ) : (
        <>
          <NetWorthPlot name={player.display_name} points={points} />
          {own !== null && index !== null && (
            <p className="small vs-index" title="Your figure counts everything that came in and went out, your pay and fees too, not only how your shares did.">
              <span>You <span className={`mono ${own > 0 ? "change-up" : own < 0 ? "change-down" : ""}`}>{pct(own)}</span></span>
              <span>BSX 50 <span className={`mono ${index > 0 ? "change-up" : index < 0 ? "change-down" : ""}`}>{pct(index)}</span></span>
              <span className={own > index ? "change-up" : own < index ? "change-down" : "muted"}>
                {own > index ? "ahead of the market" : own < index ? "behind the market" : "level with the market"}
              </span>
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The market's indicators
// ---------------------------------------------------------------------------

/**
 * One line of the readout: the name, then the figure with its move, then a bar whose length is the size of the
 * move against the biggest move in the panel. The name is never cut to a letter or an ellipsis — where it will
 * not fit across, it takes its own line and wraps, and the figure sits underneath it.
 */
/** The figure's own record as a small line: drawn from the server's numbers, never a figure of its own. */
export function Trend({ values, way }: { values: number[]; way: string }) {
  if (values.length < 2) return null;
  const low = Math.min(...values), high = Math.max(...values);
  const span = high - low || 1;
  const points = values.map((v, i) => `${((i * 60) / (values.length - 1)).toFixed(1)},${(20 - ((v - low) * 18) / span).toFixed(1)}`).join(" ");
  return <svg className={`trend trend-${way}`} viewBox="0 0 60 22" aria-hidden="true"><polyline points={points} /></svg>;
}

function IndicatorLine({ item }: { item: Indicator }) {
  const bps = item.change_bps;
  const way = bps === null || bps === 0 ? "flat" : bps > 0 ? "up" : "down";
  const arrow = bps === null || bps === 0 ? "–" : bps > 0 ? "▲" : "▼";
  const scaled = item.position_pct !== null && item.band_from_pct !== null && item.band_to_pct !== null;
  return (
    <div className="indicator">
      <div className="indicator-top">
        <div className="indicator-name">{item.name}</div>
        <Trend values={item.history ?? []} way={way} />
      </div>
      <div className="indicator-figure">
        <span className="mono indicator-value">{item.value}</span>
        {item.change === null
          ? <span className="muted small">no earlier figure</span>
          : <span className={`mono chip chip-${way}`}>{arrow} {item.change}</span>}
      </div>
      {scaled && (
        <div className="gauge" role="img"
             aria-label={`${item.name} stands at ${item.value}, on a scale from ${item.low} to ${item.high}. The shaded band is ${item.band_words}.`}>
          <div className="gauge-track">
            <span className="gauge-band" style={{ left: `${item.band_from_pct}%`, width: `${Math.max(2, item.band_to_pct! - item.band_from_pct!)}%` }} />
            <span className={`gauge-mark mark-${way}`} style={{ left: `${item.position_pct}%` }} />
          </div>
          <div className="gauge-ends mono"><span>{item.low}</span><span>{item.high}</span></div>
        </div>
      )}
      {item.means && <p className="indicator-means">{item.means}</p>}
    </div>
  );
}

function IndicatorsPanel({ readout }: { readout: Readout | null }) {
  const groups = readout?.groups ?? [];
  return (
    <Panel title="Market indicators" aside={readout?.period_label ?? undefined}>
      {readout === null ? (
        <p className="muted small">Reading the market…</p>
      ) : groups.length === 0 ? (
        <p className="muted small">No quarter has closed yet, so there is nothing to compare against. These figures appear when the first quarter does.</p>
      ) : (
        <>
          {groups.map((group) => (
            <div className="indicator-group" key={group.title}>
              <div className="group-label">{group.title}</div>
              <div className="indicators">
                {group.indicators.map((item) => <IndicatorLine key={item.name} item={item} />)}
              </div>
            </div>
          ))}
          <p className="muted small indicator-foot">Every move is {readout.since}. The shaded band on each scale is the figure&rsquo;s usual range.</p>
        </>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Quotes and news
// ---------------------------------------------------------------------------

/** The companies whose shares you hold, priced. It is loaded the first time the tab is opened, not before. */
function Quotes({ onLoggedOut }: { onLoggedOut: () => void }) {
  const list = useLoad(api.myHoldings, "column-holdings", onLoggedOut);
  const holdings = list.data ?? [];
  return (
    <div className="column-list">
      {list.data === null ? (
        <p className="muted small">Reading your holdings…</p>
      ) : holdings.length === 0 ? (
        <p className="muted small">You hold no shares yet. <a href="#/market">The market</a> is where you would start, and a company you hold keeps its prices here.</p>
      ) : (
        <ul>
          {holdings.map((h) => (
            <li key={h.ticker}>
              <a href={`#/companies/${h.ticker}`} className="mono strong">{h.ticker}</a>
              <span className="muted small">{h.shares.toLocaleString("en-NG")} shares</span>
              <span className="mono">{formatCompact(h.value_kobo)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** One headline, with the companies it names picked out in colour by how their price has moved since. */
function NewsLine({ item }: { item: NewsItem }) {
  return (
    <li className="news-line">
      <a href="#/news" className="news-line-head">{item.headline}</a>
      <div className="news-line-foot">
        <span className="muted small">{item.outlet} · {item.period_label}, day {item.day}</span>
        {item.tickers.map((ticker) => (
          <a key={ticker} href={`#/companies/${ticker}`} className="mono">
            {ticker} {item.moves[ticker] !== undefined && <Change bps={item.moves[ticker]} />}
          </a>
        ))}
      </div>
    </li>
  );
}

function News({ mine, onLoggedOut }: { mine: string[]; onLoggedOut: () => void }) {
  const list = useLoad(() => api.news({ limit: 40 }), "column-news", onLoggedOut);
  const [terms, setTerms] = useState("");
  const [onlyMine, setOnlyMine] = useState(false);
  const held = new Set(mine);
  const words = terms.split(",").map((word) => word.trim().toLowerCase()).filter(Boolean);
  const items = (list.data?.items ?? []).filter((item) => {
    if (onlyMine && !item.tickers.some((t) => held.has(t))) return false;
    if (words.length === 0) return true;
    const haystack = `${item.headline} ${item.outlet} ${item.tickers.join(" ")}`.toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
  return (
    <div className="column-list">
      <div className="news-search">
        <input value={terms} onChange={(e) => setTerms(e.target.value)} type="search" aria-label="Search the news"
               placeholder="Search the wire" title="Searches the headlines in this list. Separate terms with commas." />
        <button type="button" className="filter-chip" aria-pressed={onlyMine} onClick={() => setOnlyMine((on) => !on)}>My news</button>
      </div>
      {list.data === null ? (
        <p className="muted small">Reading the wire…</p>
      ) : items.length === 0 ? (
        <p className="muted small">{onlyMine ? "Nothing on the wire names a company you hold." : "No headline in this list matches those terms."}</p>
      ) : (
        <ul>{items.map((item) => <NewsLine key={`${item.period}-${item.day}-${item.headline}`} item={item} />)}</ul>
      )}
      <a className="news-more" href="#/news">The whole wire</a>
    </div>
  );
}

/**
 * The last panel of the column, with its two tabs at the foot: the quotes of what you hold, and the news.
 * The news tab carries the search field and the "My news" switch, and picks out the companies it names.
 */
function QuotesNewsPanel({ readout, onLoggedOut }: {
  readout: Readout | null;
  onLoggedOut: () => void;
}) {
  const [tab, setTab] = useState<"news" | "quotes">("news");
  // The quotes are read the first time somebody asks for them, and the news keeps its place while they look:
  // switching tabs must not throw away a search that was half typed.
  const [quotesSeen, setQuotesSeen] = useState(false);
  function choose(next: "news" | "quotes") {
    if (next === "quotes") setQuotesSeen(true);
    setTab(next);
  }
  return (
    <Panel title="Quotes and news">
      <div className="column-tabs" role="tablist" aria-label="Quotes or news">
        <button type="button" role="tab" aria-selected={tab === "news"} className={tab === "news" ? "current" : ""} onClick={() => choose("news")}>News</button>
        <button type="button" role="tab" aria-selected={tab === "quotes"} className={tab === "quotes" ? "current" : ""} onClick={() => choose("quotes")}>Quotes</button>
      </div>
      <div hidden={tab !== "news"}><News mine={readout?.my_tickers ?? []} onLoggedOut={onLoggedOut} /></div>
      {quotesSeen && <div hidden={tab !== "quotes"}><Quotes onLoggedOut={onLoggedOut} /></div>}
    </Panel>
  );
}
