import { useEffect, useState } from "react";
import { api, type Ticker } from "./api";
import { formatNaira } from "./format";

/**
 * The price ticker across the top of every screen: every share's price and today's move.
 * It reads the prices again once a minute. It stops moving while the pointer is on it, and
 * does not move at all for anybody who has asked their device for less motion.
 */
export function PriceTicker() {
  const [data, setData] = useState<Ticker | null>(null);
  useEffect(() => {
    let cancelled = false;
    const read = () => api.ticker().then((fresh) => !cancelled && setData(fresh)).catch(() => undefined);
    read();
    const every = setInterval(read, 60_000);
    return () => { cancelled = true; clearInterval(every); };
  }, []);
  if (!data || data.shares.length === 0) return null;
  const item = (s: Ticker["shares"][number], copy: number) => {
    const arrow = s.change_bps > 0 ? "▲" : s.change_bps < 0 ? "▼" : "–";
    const way = s.change_bps > 0 ? "up" : s.change_bps < 0 ? "down" : "flat";
    return (
      <a key={`${s.ticker}-${copy}`} href={`#/companies/${s.ticker}`} className="ticker-item" tabIndex={copy === 0 ? 0 : -1}
         aria-hidden={copy === 1 ? true : undefined}>
        <span className="mono strong">{s.ticker}</span>
        <span className="mono">{formatNaira(s.price_kobo)}</span>
        <span className={`mono change-${way}`}>{arrow} {(Math.abs(s.change_bps) / 100).toFixed(1)}%</span>
      </a>
    );
  };
  const indexWay = data.index_change_bps > 0 ? "up" : data.index_change_bps < 0 ? "down" : "flat";
  return (
    <div className="ticker-bar" role="region" aria-label="Share prices">
      <a href="#/market" className="ticker-index">
        <span className="strong">BSX 50</span>
        <span className="mono">{data.index.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        <span className={`mono change-${indexWay}`}>
          {data.index_change_bps > 0 ? "▲" : data.index_change_bps < 0 ? "▼" : "–"} {(Math.abs(data.index_change_bps) / 100).toFixed(1)}%
        </span>
        {data.closing_rush && <span className="pill pill-opening_auction">Closing Rush</span>}
      </a>
      <div className="ticker-window">
        {/* The list is written twice so that it can roll round without a gap. */}
        <div className="ticker-track" style={{ animationDuration: `${data.shares.length * 3}s` }}>
          {data.shares.map((s) => item(s, 0))}
          {data.shares.map((s) => item(s, 1))}
        </div>
      </div>
    </div>
  );
}
