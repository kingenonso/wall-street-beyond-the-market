import type { Player } from "./api";
import { formatLagosDate, formatLagosTime, formatMoney, MARKET_LABEL } from "./format";
import type { LiveClock } from "./useClock";

export function Wordmark() {
  return (
    <div className="wordmark" aria-label="Wall Street: Beyond the Market">
      <span className="wordmark-main">WALL STREET</span>
      <span className="wordmark-sub">BEYOND THE MARKET</span>
    </div>
  );
}

export function MarketPill({ live }: { live: LiveClock | null }) {
  if (!live) return <span className="pill pill-closed">Connecting…</span>;
  const state = live.clock.market_state;
  return (
    <span className={`pill pill-${state}`}>
      <span className="pill-dot" aria-hidden="true" />
      {MARKET_LABEL[state]}
    </span>
  );
}

export function TopBar({ player, live, onLogout }: { player: Player; live: LiveClock | null; onLogout: () => void }) {
  return (
    <header className="topbar">
      <Wordmark />
      <div className="topbar-clock">
        {live && (
          <>
            <span>{formatLagosDate(live.now)}</span>
            <span className="mono">{formatLagosTime(live.now)}</span>
            <span className="muted">Lagos</span>
          </>
        )}
        <MarketPill live={live} />
      </div>
      <div className="topbar-player">
        <div className="avatar" aria-hidden="true">{player.display_name.charAt(0).toUpperCase()}</div>
        <div>
          <div className="mono cash">{formatMoney(player.cash, true)}</div>
          <div className="muted small">{player.display_name}</div>
        </div>
        <button className="button-quiet" onClick={onLogout}>Log out</button>
      </div>
    </header>
  );
}
