import type { ReactNode } from "react";
import type { Player } from "./api";
import { formatCompact, formatLagosDate, formatLagosTime, MARKET_LABEL } from "./format";
import { ProfilePicture } from "./icons";
import { PriceTicker } from "./Ticker";
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
    <span className={`pill pill-${live.clock.closing_rush ? "opening_auction" : state}`}>
      <span className="pill-dot" aria-hidden="true" />
      {live.clock.closing_rush ? "Closing Rush" : MARKET_LABEL[state]}
    </span>
  );
}

function gameDate(live: LiveClock): string {
  const date = live.clock.game_date;
  return date ? `Year ${date.year} · Q${date.quarter} · Day ${date.day_of_quarter}` : "The world has not opened yet";
}

/** Zone 1 of the standard layout: the top bar. */
function TopBar({ player, live }: { player: Player; live: LiveClock | null }) {
  return (
    <header className="topbar">
      <a href="#/" className="plain-link"><Wordmark /></a>
      <div className="topbar-clock">
        {live && (
          <>
            <span className="muted">{gameDate(live)}</span>
            <span className="muted">{formatLagosDate(live.now)}</span>
            <span className="mono">{formatLagosTime(live.now)} Lagos</span>
          </>
        )}
        <MarketPill live={live} />
        {live && live.clock.test_weeks_ahead > 0 && (
          <span className="pill pill-test" title="This world has been fast-forwarded for testing">
            Test world · {live.clock.test_weeks_ahead} {live.clock.test_weeks_ahead === 1 ? "week" : "weeks"} ahead
          </span>
        )}
      </div>
      <div className="topbar-player">
        <div className="align-right">
          <div className="mono cash" title="Your cash">{formatCompact(player.cash.amount_kobo)}</div>
          <div className="muted small">
            {player.display_name}
            {player.build_name && <> · <a href="#/career" className="build-badge">{player.build_name} · Level {player.level}</a></>}
          </div>
        </div>
        <a href="#/profile" aria-label="Your profile picture" className="plain-link">
          <ProfilePicture icon={player.profile_icon} name={player.display_name} />
        </a>
      </div>
    </header>
  );
}

/** The sections of the player's screen. The build's own screen comes straight after the desk. */
function sectionsFor(player: Player) {
  return [
    { path: "", label: "My desk" },
    ...(player.build_name ? [{ path: "build", label: player.build_name }] : []),
    { path: "work", label: "Work" },
    { path: "market", label: "Market" },
    { path: "portfolio", label: "Portfolio" },
    { path: "news", label: "News" },
    { path: "companies", label: "Companies" },
    { path: "economy", label: "Economy" },
    { path: "career", label: "Career" },
    { path: "profile", label: "Profile" },
  ];
}

/** Zone 2: the sections menu. Only sections that exist are listed. */
function SectionsMenu({ player, current, onLogout }: { player: Player; current: string; onLogout: () => void }) {
  return (
    <nav className="sections" aria-label="Sections">
      {sectionsFor(player).map((section) => (
        <a
          key={section.path}
          href={`#/${section.path}`}
          className={section.path === current ? "section current" : "section"}
          aria-current={section.path === current ? "page" : undefined}
        >
          {section.label}
        </a>
      ))}
      <button className="section section-button" onClick={onLogout}>Log out</button>
    </nav>
  );
}

/**
 * The standard layout every screen uses (design document, section 18):
 * top bar, sections menu, work area and context rail.
 */
export function Shell({ player, live, current, onLogout, work, rail }: {
  player: Player;
  live: LiveClock | null;
  current: string;
  onLogout: () => void;
  work: ReactNode;
  rail: ReactNode;
}) {
  return (
    <div className="app" data-accent={player.accent ?? undefined}>
      <TopBar player={player} live={live} />
      <PriceTicker />
      <div className="shell">
        <SectionsMenu player={player} current={current} onLogout={onLogout} />
        <main className="work">{work}</main>
        <aside className="rail" aria-label="Context">{rail}</aside>
      </div>
    </div>
  );
}

export function Panel({ title, aside, children, className = "" }: {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || aside) && (
        <div className="panel-head">
          {title && <h2>{title}</h2>}
          {aside && <span className="muted small">{aside}</span>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="muted">Loading {what}…</p>;
}

export function Failed({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error" role="alert">
      {message} <button className="button-quiet" onClick={onRetry}>Try again</button>
    </div>
  );
}

/** A rise or fall, always with an arrow so it can be read without colour. */
export function Change({ bps }: { bps: number | null }) {
  if (bps === null) return <span className="muted">n/a</span>;
  const direction = bps > 0 ? "up" : bps < 0 ? "down" : "flat";
  const size = (Math.abs(bps) / 100).toFixed(1);
  const arrow = bps > 0 ? "▲" : bps < 0 ? "▼" : "–";
  return <span className={`mono change-${direction}`}>{arrow} {size}%</span>;
}

export function Rating({ value }: { value: string }) {
  const tier = ["AAA", "AA", "A"].includes(value) ? "strong" : ["BBB", "BB"].includes(value) ? "middle" : "weak";
  return <span className={`rating rating-${tier}`} title="Credit rating">{value}</span>;
}
