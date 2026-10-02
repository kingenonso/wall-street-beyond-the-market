import { useState } from "react";
import { api, type MarketShare, type Watched } from "./api";
import { formatCompact, formatNaira, MARKET_LABEL } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";
import { SingleLine } from "./TrendChart";
import { ClosingBellPanel } from "./Bell";
import { BondsWork, CorporateWork, OwnershipWork } from "./Capital";
import { IndustriesWork } from "./Industries";

const shares = (count: number) => count.toLocaleString("en-NG");
const points = (level: number) => level.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-NG", { day: "numeric", month: "short", timeZone: "UTC" });

type Order = "name" | "change" | "value" | "volume";

const TABS: [string, string][] = [
  ["", "Shares"], ["bonds", "Bonds and bills"], ["offers", "Offers, votes and bids"], ["industries", "Industries"], ["owners", "Who owns what"],
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
      {tab === "bonds" ? <BondsWork onLoggedOut={onLoggedOut} onChanged={onChanged} />
        : tab === "offers" ? <CorporateWork onLoggedOut={onLoggedOut} onChanged={onChanged} />
        : tab === "industries" ? <IndustriesWork onLoggedOut={onLoggedOut} />
        : tab === "owners" ? <OwnershipWork onLoggedOut={onLoggedOut} />
        : <SharesWork onLoggedOut={onLoggedOut} />}
    </>
  );
}

function SharesWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const market = useLoad(api.market, "market", onLoggedOut);
  const watched = useLoad(api.watchlist, "watchlist", onLoggedOut);
  const [order, setOrder] = useState<Order>("value");
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  if (market.loading && !market.data) return <Loading what="the market" />;
  if (market.error) return <Failed message={market.error} onRetry={market.reload} />;
  if (!market.data) return null;
  const m = market.data;
  const watching = new Set((watched.data ?? []).map((w) => w.ticker));

  const sorted = [...m.shares].sort((a: MarketShare, b: MarketShare) =>
    order === "name" ? a.name.localeCompare(b.name)
      : order === "change" ? b.change_bps - a.change_bps
      : order === "volume" ? b.volume - a.volume
      : Number(BigInt(b.market_value_kobo) - BigInt(a.market_value_kobo)));

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

  return (
    <>
      <div className="work-head">
        <h1>The market</h1>
        <span className="muted small">
          Broad Street Exchange · {m.paused_until ? "Trading paused after a sharp fall" : MARKET_LABEL[m.market_state]}
        </span>
      </div>

      <ClosingBellPanel onLoggedOut={onLoggedOut} />

      <Panel title="BSX 50 index" aside="All fifty companies, each counted by its size">
        <div className="tiles">
          <div className="tile">
            <div className="muted small">BSX 50</div>
            <div className="mono figure-small">{points(m.index)}</div>
            <div className="small"><Change bps={m.index_change_bps} /> <span className="muted">today</span></div>
          </div>
          <div className="tile">
            <div className="muted small">All companies are worth</div>
            <div className="mono figure-small">{formatCompact(m.market_value_kobo)}</div>
            <div className="small muted">at today's prices</div>
          </div>
          <div className="tile">
            <div className="muted small">Shares traded today</div>
            <div className="mono figure-small">{shares(m.volume)}</div>
            <div className="small muted">in {shares(m.trades)} trades</div>
          </div>
        </div>
        {m.index_history.length >= 2 ? (
          <SingleLine name="BSX 50" format={points}
                      data={m.index_history.map((p) => ({ label: shortDate(p.session_date), value: p.level }))} />
        ) : (
          <p className="muted small">The chart appears after two days of trading.</p>
        )}
        <p className="muted small">
          The index stood at 1,000 when each share was first listed. It rises when companies' share prices rise, and a large
          company moves it more than a small one. New shares a company issues do not move it: only prices do.
        </p>
      </Panel>

      <Panel title="All shares" aside={
        <span className="sort">
          Sort by{" "}
          {(["value", "change", "volume", "name"] as Order[]).map((key) => (
            <button key={key} className={order === key ? "link-button current" : "link-button"} onClick={() => setOrder(key)}>
              {{ value: "size", change: "today's move", volume: "shares traded", name: "name" }[key]}
            </button>
          ))}
        </span>
      }>
        {problem && <div className="error" role="alert">{problem}</div>}
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col" className="num">Price</th>
                <th scope="col" className="num">Today</th>
                <th scope="col" className="num">Shares traded</th>
                <th scope="col" className="num">Whole company</th>
                <th scope="col">Rating</th>
                <th scope="col" aria-label="Watch" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((s) => (
                <tr key={s.ticker}>
                  <th scope="row">
                    <a href={`#/companies/${s.ticker}`}>{s.name}</a> <span className="ticker mono">{s.ticker}</span>
                    <div className="small muted">{s.sector}</div>
                  </th>
                  <td className="num mono">{formatNaira(s.price_kobo)}{!s.traded && <div className="small muted">not yet traded</div>}</td>
                  <td className="num"><Change bps={s.traded ? s.change_bps : null} /></td>
                  <td className="num mono">{shares(s.volume)}</td>
                  <td className="num mono">{formatCompact(s.market_value_kobo)}</td>
                  <td>{s.credit_rating && <Rating value={s.credit_rating} />}</td>
                  <td>
                    <button className="button-quiet" disabled={busy === s.ticker} aria-pressed={watching.has(s.ticker)}
                            onClick={() => toggle(s.ticker)}>
                      {watching.has(s.ticker) ? "★ Watching" : "☆ Watch"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
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
      <WatchlistPanel onLoggedOut={onLoggedOut} />
      <Panel title="How the market works">
        <ul className="reasons">
          <li>Open a company to buy or sell its shares. Buyer and seller each pay 0.5% in fees, and half that in the Closing Rush (21:50 to 22:00).</li>
          <li>At 22:00 the Closing Bell names the day's winner, loser and boldest move.</li>
          <li>Bonds and bills are bought from and sold to the pension funds' bond desk. A Government bill pays interest on cash you are not using.</li>
          <li>Share offers, votes and takeover offers are announced when a quarter closes and settled when the next one closes.</li>
          <li>The market trades from 12:00 to 22:00 Lagos time. Orders placed at other times wait for the opening auction.</li>
          <li>A share cannot move more than a tenth in one day.</li>
          <li>Pension funds, small investors and founders trade too. Their buying and selling moves prices even when no player is trading.</li>
          <li>If the whole market falls 5% in a day, trading pauses for half an hour.</li>
        </ul>
      </Panel>
    </>
  );
}
