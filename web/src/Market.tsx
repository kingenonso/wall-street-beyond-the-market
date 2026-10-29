import { useState } from "react";
import { api, type MarketShare, type Watched } from "./api";
import { formatCompact, formatNaira, MARKET_LABEL } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";
import { AreaChart, Sparkline } from "./Charts";
import { Term } from "./Term";
import { ClosingBellPanel } from "./Bell";
import { BondsWork, CorporateWork, OwnershipWork } from "./Capital";
import { IndustriesWork } from "./Industries";
import { DerivativesWork, RiskWork } from "./Derivatives";
import { FundsWork } from "./Funds";

const shares = (count: number) => count.toLocaleString("en-NG");
const points = (level: number) => level.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-NG", { day: "numeric", month: "short", timeZone: "UTC" });


const TABS: [string, string][] = [
  ["", "Shares"], ["bonds", "Bonds and bills"], ["funds", "Funds"], ["derivatives", "Options and futures"], ["risk", "Risk"], ["offers", "Offers, votes and bids"],
  ["industries", "Industries"], ["owners", "Who owns what"],
];

/** The Market section: one place to trade, grouped by kind of asset. */
export function MarketWork({ tab = "", onLoggedOut, onChanged }: { tab?: string; onLoggedOut: () => void; onChanged: () => void }) {
  return (
    <>
      <div className="tabs tabs-inline" role="tablist" aria-label="The market, by kind of asset">
        {TABS.map(([path, label]) => (
          <a key={path} role="tab" aria-selected={tab === path} href={`#/market${path ? `/${path}` : ""}`}
             className={tab === path ? "tab active" : "tab"}>{label}</a>
        ))}
      </div>
      {/* Every market page has a main heading for screen readers; the shares page shows its own. */}
      {tab !== "" && <h1 className="sr-only">Market: {TABS.find(([path]) => path === tab)?.[1] ?? "the market"}</h1>}
      {tab === "bonds" ? <BondsWork onLoggedOut={onLoggedOut} onChanged={onChanged} />
        : tab === "funds" ? <FundsWork onLoggedOut={onLoggedOut} onChanged={onChanged} />
        : tab === "derivatives" ? <DerivativesWork onLoggedOut={onLoggedOut} onChanged={onChanged} />
        : tab === "risk" ? <RiskWork onLoggedOut={onLoggedOut} />
        : tab === "offers" ? <CorporateWork onLoggedOut={onLoggedOut} onChanged={onChanged} />
        : tab === "industries" ? <IndustriesWork onLoggedOut={onLoggedOut} />
        : tab === "owners" ? <OwnershipWork onLoggedOut={onLoggedOut} />
        : <SharesWork onLoggedOut={onLoggedOut} />}
    </>
  );
}

type SortKey = "ticker" | "name" | "price" | "change" | "value" | "volume";
const SORT_WORDS: Record<SortKey, string> = { ticker: "Code", name: "Company", price: "Price", change: "Today", value: "Whole company", volume: "Traded today" };

/** The index over a chosen stretch of trading days. One real week is one game quarter. */
const RANGES: [string, number][] = [["A week (one quarter)", 7], ["Four weeks (one year)", 28], ["Everything", 9999]];

/** The colour of a heat-map cell: green up, orange down, darker for a bigger move. The arrow carries it too. */
function heat(bps: number, traded: boolean): { background: string; color: string } {
  if (!traded || bps === 0) return { background: "var(--raised)", color: "var(--text)" };
  const strength = Math.min(1, Math.abs(bps) / 400);
  // The tint never goes past half, so the page's own text colour stays readable on every cell in both
  // modes (at least 4.5 to 1); the ▲ ▼ beside each move carries the direction as well as the colour.
  const mix = Math.round(12 + strength * 38);
  return { background: `color-mix(in srgb, ${bps > 0 ? "var(--up)" : "var(--down)"} ${mix}%, var(--panel))`, color: "var(--text)" };
}

function SharesWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const market = useLoad(api.market, "market", onLoggedOut);
  const watched = useLoad(api.watchlist, "watchlist", onLoggedOut);
  const [sort, setSort] = useState<{ key: SortKey; down: boolean }>({ key: "value", down: true });
  const [filter, setFilter] = useState<string>("all");
  const [range, setRange] = useState(28);
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  if (market.loading && !market.data) return <Loading what="the market" />;
  if (market.error) return <Failed message={market.error} onRetry={market.reload} />;
  if (!market.data) return null;
  const m = market.data;
  const watching = new Set((watched.data ?? []).map((w) => w.ticker));
  const sectors = [...new Set(m.shares.map((s) => s.sector))].sort();

  const value = (s: MarketShare): number | string =>
    sort.key === "ticker" ? s.ticker : sort.key === "name" ? s.name : sort.key === "price" ? Number(s.price_kobo)
      : sort.key === "change" ? (s.traded ? s.change_bps : -1e9) : sort.key === "volume" ? s.volume : Number(BigInt(s.market_value_kobo) / 100n);
  const shown = m.shares
    .filter((s) => filter === "all" ? true : filter === "watch" ? watching.has(s.ticker) : s.sector === filter)
    .sort((a, b) => {
      const x = value(a), y = value(b);
      const c = typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number);
      return sort.down ? -c : c;
    });
  const history = m.index_history.slice(-range);

  async function toggle(ticker: string) {
    setBusy(ticker);
    setProblem(null);
    try {
      await (watching.has(ticker) ? api.unwatch(ticker) : api.watch(ticker));
    } catch (failure) {
      setProblem(failure instanceof Error ? failure.message : "Could not reach the server.");
    }
    watched.reload();
    setBusy(null);
  }

  function header(key: SortKey, numeric = false) {
    const on = sort.key === key;
    return (
      <th scope="col" className={numeric ? "num" : undefined} aria-sort={on ? (sort.down ? "descending" : "ascending") : "none"}>
        <button className="sort-button" onClick={() => setSort({ key, down: on ? !sort.down : numeric })}>
          {SORT_WORDS[key]}{on ? (sort.down ? " ▼" : " ▲") : ""}
        </button>
      </th>
    );
  }

  return (
    <>
      <div className="work-head">
        <h1>Market</h1>
        <span className="muted small">
          Broad Street Exchange · {m.paused_until ? "Trading paused after a sharp fall" : MARKET_LABEL[m.market_state]}
        </span>
      </div>

      <Panel>
        <div className="panel-head">
          <div>
            <h2><Term word="BSX 50" /></h2>
            <div className="headline" style={{ margin: "4px 0 0" }}>
              <span className="mono figure">{points(m.index)}</span>
              <span className="small"><Change bps={m.index_change_bps} /> <span className="muted">today</span></span>
            </div>
          </div>
          <div className="range-buttons" role="group" aria-label="How far back">
            {RANGES.map(([label, days]) => <button key={days} aria-pressed={range === days} onClick={() => setRange(days)}>{label}</button>)}
          </div>
        </div>
        {history.length >= 2 ? (
          <AreaChart points={history.map((p) => ({ label: shortDate(p.session_date), value: p.level }))} format={points}
                     baseline={history[0].level} baselineLabel={`where it stood on ${shortDate(history[0].session_date)}`}
                     label={`The BSX 50 went from ${points(history[0].level)} on ${shortDate(history[0].session_date)} to ${points(history[history.length - 1].level)}.`} height={180} />
        ) : <p className="muted small">The chart appears after two days of trading.</p>}
        <div className="tiles" style={{ marginTop: 12, marginBottom: 0 }}>
          <div className="tile"><div className="muted small"><Term word="Market value">All companies are worth</Term></div><div className="mono figure-small">{formatCompact(m.market_value_kobo)}</div></div>
          <div className="tile"><div className="muted small">Shares traded today</div><div className="mono figure-small">{shares(m.volume)}</div><div className="small muted">in {shares(m.trades)} trades</div></div>
        </div>
      </Panel>

      <Panel title="Today at a glance: every share, by industry" aside="▲ up · ▼ down · stronger colour = bigger move">
        <div className="heat-grid">
          {sectors.map((sector) => {
            const inside = m.shares.filter((s) => s.sector === sector);
            return (
              <div key={sector} className="heat-group">
                <div className="small" style={{ color: "var(--text-2)", marginBottom: 6 }}>{sector}</div>
                <div className="heat-cells">
                  {inside.map((s) => (
                    <a key={s.ticker} href={`#/companies/${s.ticker}`} className="heat-cell" style={heat(s.change_bps, s.volume > 0)}
                       aria-label={`${s.name}: ${s.volume > 0 ? `${s.change_bps > 0 ? "up" : s.change_bps < 0 ? "down" : "unchanged"} ${(Math.abs(s.change_bps) / 100).toFixed(1)}% today` : "no trades yet today"}`}>
                      <span className="mono strong">{s.ticker}</span>
                      <span className="mono">{s.volume > 0 ? `${s.change_bps > 0 ? "▲" : s.change_bps < 0 ? "▼" : "–"}${(Math.abs(s.change_bps) / 100).toFixed(1)}%` : "–"}</span>
                    </a>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title={`All ${m.shares.length} shares`}>
        <div className="filter-row" role="group" aria-label="Show">
          <button className="filter-chip" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All</button>
          <button className="filter-chip" aria-pressed={filter === "watch"} onClick={() => setFilter("watch")}>★ My watchlist</button>
          <label className="filter-select">
            <span className="sr-only">Industry</span>
            <select value={sectors.includes(filter) ? filter : ""} onChange={(e) => setFilter(e.target.value || "all")}>
              <option value="">Industry…</option>
              {sectors.map((sec) => <option key={sec} value={sec}>{sec}</option>)}
            </select>
          </label>
        </div>
        {problem && <div className="error" role="alert">{problem}</div>}
        <div className="scroll" tabIndex={0}>
          <table className="dense">
            <thead>
              <tr>
                {header("ticker")}
                {header("name")}
                {header("price", true)}
                {header("change", true)}
                <th scope="col">Last 5 days</th>
                {header("volume", true)}
                {header("value", true)}
                <th scope="col"><Term word="Credit rating">Rating</Term></th>
                <th scope="col"><span className="sr-only">Watch</span></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => {
                const closes = s.closes.map(Number);
                return (
                  <tr key={s.ticker}>
                    <td className="mono strong"><a href={`#/companies/${s.ticker}`}>{s.ticker}</a></td>
                    <th scope="row">{s.name}<div className="muted small">{s.sector}</div></th>
                    <td className="num mono">{formatNaira(s.price_kobo)}{!s.traded && <div className="small muted">not yet traded</div>}</td>
                    <td className="num"><Change bps={s.volume > 0 ? s.change_bps : null} /></td>
                    <td><Sparkline values={closes} label={closes.length >= 2 ? `${s.name} over its last ${closes.length} trading days: ${closes[closes.length - 1] >= closes[0] ? "up" : "down"}` : undefined} /></td>
                    <td className="num mono">{shares(s.volume)}</td>
                    <td className="num mono">{formatCompact(s.market_value_kobo)}</td>
                    <td>{s.credit_rating && <Rating value={s.credit_rating} />}</td>
                    <td>
                      <button className="star-button" disabled={busy === s.ticker} aria-pressed={watching.has(s.ticker)}
                              aria-label={watching.has(s.ticker) ? `Stop watching ${s.name}` : `Watch ${s.name}`} onClick={() => toggle(s.ticker)}>
                        {watching.has(s.ticker) ? "★" : "☆"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {shown.length === 0 && <p className="muted small">Nothing here yet. {filter === "watch" ? "Press ☆ beside a company to watch it." : ""}</p>}
      </Panel>

      <ClosingBellPanel onLoggedOut={onLoggedOut} />
    </>
  );
}

/** Today's biggest rises and falls among shares that have traded. */
export function MoversPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data } = useLoad(api.market, "market", onLoggedOut);
  if (!data) return null;
  const traded = data.shares.filter((s) => s.volume > 0 && s.change_bps !== 0).sort((a, b) => b.change_bps - a.change_bps);
  if (traded.length === 0) return <Panel title="Biggest moves today"><p className="muted small">Nothing has moved yet today.</p></Panel>;
  const rows = [...traded.filter((s) => s.change_bps > 0).slice(0, 3), ...traded.filter((s) => s.change_bps < 0).slice(-3).reverse()];
  return (
    <Panel title="Biggest moves today">
      {rows.map((s) => (
        <a key={s.ticker} href={`#/companies/${s.ticker}`} className="row plain-link">
          <span><span className="mono strong">{s.ticker}</span> {s.name}</span>
          <Change bps={s.change_bps} />
        </a>
      ))}
    </Panel>
  );
}

/** A player's watched shares. Shown on the Market page and on the desk. */
export function WatchlistPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data } = useLoad(api.watchlist, "watchlist", onLoggedOut);
  return (
    <Panel title="Your watchlist" aside={data && data.length > 0 ? `${data.length} of 30` : undefined}>
      {(!data || data.length === 0) && (
        <p className="muted small">
          Nothing yet. Press "☆ Watch" beside a company on the Market page, or on its own page, to keep an eye on it here.
        </p>
      )}
      {(data ?? []).map((w: Watched) => (
        <div key={w.ticker} className={w.reached ? "row row-current" : "row"}>
          <span>
            <a href={`#/companies/${w.ticker}`}>{w.name}</a>
            {w.reached && (
              <div className="small">
                {w.reached === "above" ? "▲ Reached" : "▼ Fell to"} your price of{" "}
                {formatNaira((w.reached === "above" ? w.alert_above_kobo : w.alert_below_kobo) ?? "0")}
              </div>
            )}
          </span>
          <span className="mono">{formatNaira(w.price_kobo)} <Change bps={w.change_bps} /></span>
        </div>
      ))}
    </Panel>
  );
}

export function MarketRail({ onLoggedOut }: { onLoggedOut: () => void }) {
  return (
    <>
      <MoversPanel onLoggedOut={onLoggedOut} />
      <WatchlistPanel onLoggedOut={onLoggedOut} />
      <Panel>
        <details>
        <summary className="strong" style={{ cursor: "pointer" }}>? How the market works</summary>
        <ul className="reasons" style={{ marginTop: 10 }}>
          <li>Open a company to buy or sell its shares. Buyer and seller each pay 0.5% in fees, and half that in the Closing Rush (21:50 to 22:00).</li>
          <li>At 22:00 the Closing Bell names the day's winner, loser and boldest move.</li>
          <li>Bonds and bills are bought from and sold to the pension funds' bond desk. A Government bill pays interest on cash you are not using.</li>
          <li>Share offers, votes and takeover offers are announced when a quarter closes and settled when the next one closes.</li>
          <li>The market trades from 12:00 to 22:00 Lagos time. Orders placed at other times wait for the opening auction.</li>
          <li>A share cannot move more than a tenth in one day.</li>
          <li>Pension funds, small investors and founders trade too. Their buying and selling moves prices even when no player is trading.</li>
          <li>If the whole market falls 5% in a day, trading pauses for half an hour.</li>
        </ul>
        </details>
      </Panel>
    </>
  );
}
