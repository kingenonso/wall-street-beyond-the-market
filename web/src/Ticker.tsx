import { useEffect, useState } from "react";
import { api, type Ticker } from "./api";
import { formatNaira, MARKET_LABEL } from "./format";
import type { LiveClock } from "./useClock";

/** The market's state: open, closed, or the Closing Rush, with a dot in its colour. */
export function MarketPill({ live }: { live: LiveClock | null }) {
  if (!live) return <span className="pill pill-closed">Connecting…</span>;
  const state = live.clock.market_state;
  return (
    <span className={`pill pill-${live.clock.closing_rush ? "opening_auction" : state}`} title={live.clock.closing_rush ? "Closing Rush" : MARKET_LABEL[state]}>
      <span className="pill-dot" aria-hidden="true" />
      <span className="pill-label">{live.clock.closing_rush ? "Closing Rush" : MARKET_LABEL[state]}</span>
    </span>
  );
}

/**
 * The tape row across the top of every screen. On its left it carries the game's date and the market's
 * state; then every share's price and today's move, which rolls. The prices are read again once a
 * minute. The roll stops while the pointer is on it, and does not roll at all for anybody who has asked
 * their device for less motion.
 */
export function PriceTicker({ live }: { live: LiveClock | null }) {
  const [data, setData] = useState<Ticker | null>(null);
  useEffect(() => {
    let cancelled = false;
    const read = () => api.ticker().then((fresh) => !cancelled && setData(fresh)).catch(() => undefined);
    read();
    const every = setInterval(read, 60_000);
    return () => { cancelled = true; clearInterval(every); };
  }, []);
  const date = live?.clock.game_date;
  const stamp = date ? `Y${date.year} · Q${date.quarter} · Day ${date.day_of_quarter}` : "Not open yet";
  const item = (s: Ticker["shares"][number], copy: number) => {
    const arrow = s.change_bps > 0 ? "▲" : s.change_bps < 0 ? "▼" : "–";
    const way = s.change_bps > 0 ? "up" : s.change_bps < 0 ? "down" : "flat";
    return (
      <a key={`${s.ticker}-${copy}`} href={`#/companies/${s.ticker}`} className="ticker-item" tabIndex={copy === 0 ? 0 : -1}
         aria-hidden={copy === 1 ? true : undefined}>
        <span className="mono strong">{s.ticker}</span>
        <span className="mono">{formatNaira(s.price_kobo)}</span>
        {s.traded_today
          ? <span className={`mono change-${way}`}>{arrow} {(Math.abs(s.change_bps) / 100).toFixed(1)}%</span>
          : <span className="muted small">no trades yet</span>}
      </a>
    );
  };
  const shares = data?.shares ?? [];
  const anyTrade = shares.some((s) => s.traded_today);
  const indexWay = (data?.index_change_bps ?? 0) > 0 ? "up" : (data?.index_change_bps ?? 0) < 0 ? "down" : "flat";
  return (
    <div className="ticker-bar" role="region" aria-label="The game's date and today's share prices">
      <div className="tape-date">
        <span className="mono strong" title="The game's date">{stamp}</span>
        <MarketPill live={live} />
      </div>
      {data && shares.length > 0 && (
        <>
          <a href="#/market" className="ticker-index">
            <span className="strong">BSX 50</span>
            <span className="mono">{data.index.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            {anyTrade ? (
              <span className={`mono change-${indexWay}`}>
                {data.index_change_bps > 0 ? "▲" : data.index_change_bps < 0 ? "▼" : "–"} {(Math.abs(data.index_change_bps) / 100).toFixed(1)}%
              </span>
            ) : <span className="muted small">no trades yet</span>}
            {data.closing_rush && <span className="pill pill-opening_auction">Closing Rush</span>}
          </a>
          <div className="ticker-window">
            {/* The list is written twice so that it can roll round without a gap. */}
            <div className="ticker-track" style={{ animationDuration: `${shares.length * 3}s` }}>
              {shares.map((s) => item(s, 0))}
              {shares.map((s) => item(s, 1))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
