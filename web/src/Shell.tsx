import { useEffect, useRef, useState, type FocusEvent, type ReactNode } from "react";
import { api, type NewsAlert, type NewsAlertMark, type Player } from "./api";
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
function TopBar({ player, live, onLogout, onPlayer }: {
  player: Player; live: LiveClock | null; onLogout: () => void; onPlayer?: (player: Player) => void;
}) {
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
        <ProfileMenu player={player} onLogout={onLogout} onPlayer={onPlayer} />
      </div>
    </header>
  );
}

/**
 * The profile picture in the top right opens a small menu: the player's profile, their rank,
 * their messages, the news pop-ups switch, and logging out. A dot on the picture says something
 * is waiting (a rank case, or a message not yet read).
 */
function ProfileMenu({ player, onLogout, onPlayer }: { player: Player; onLogout: () => void; onPlayer?: (player: Player) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const first = useRef<HTMLAnchorElement>(null);
  const waiting = player.rank_waiting || player.unread_messages > 0;
  useEffect(() => {
    if (!open) return;
    first.current?.focus();
    const away = (event: MouseEvent) => { if (box.current && !box.current.contains(event.target as Node)) setOpen(false); };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); button.current?.focus(); }
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", key); };
  }, [open]);
  // Tabbing out of the menu closes it.
  function leave(event: FocusEvent) {
    if (box.current && !box.current.contains(event.relatedTarget as Node | null)) setOpen(false);
  }
  function toggleNews() {
    api.setNewsAlerts(!player.news_alerts).then((p) => onPlayer?.(p)).catch(() => undefined);
  }
  const close = () => setOpen(false);
  return (
    <div className="profile-menu" ref={box} onBlur={leave}>
      <button
        ref={button}
        className="profile-button"
        aria-expanded={open}
        aria-controls="profile-dropdown"
        aria-label={waiting ? "Your menu (something is waiting)" : "Your menu"}
        onClick={() => setOpen(!open)}
      >
        <ProfilePicture icon={player.profile_icon} name={player.display_name} />
        {waiting && <span className="waiting-dot" aria-hidden="true" />}
      </button>
      {open && (
        <nav className="profile-dropdown" id="profile-dropdown" aria-label="Your menu">
          <div className="profile-dropdown-head">
            <span className="strong">{player.display_name}</span>
            {player.build_name && <span className="muted small">{player.build_name} · Level {player.level}</span>}
          </div>
          <a ref={first} href="#/profile" onClick={close}>Profile</a>
          {player.build_name && (
            <a href="#/rank" onClick={close}>
              Rank
              {player.rank_waiting && <span className="menu-flag">◆ a case is waiting</span>}
            </a>
          )}
          <a href="#/messages" onClick={close}>
            Messages
            {player.unread_messages > 0 && <span className="count" aria-label={`${player.unread_messages} unread`}>{player.unread_messages}</span>}
          </a>
          <button aria-pressed={player.news_alerts} onClick={toggleNews}>
            News pop-ups <span className="muted small">{player.news_alerts ? "● On" : "○ Off"}</span>
          </button>
          <button onClick={() => { close(); onLogout(); }}>Log out</button>
        </nav>
      )}
    </div>
  );
}

/**
 * Quiet news pop-ups: a short headline at the bottom of the screen for every new story, which fades
 * on its own after a few seconds. No sound, never in the way of the work, and the player can turn
 * them off from the menu under their picture or from the pop-up itself.
 */
function NewsToasts({ player, onPlayer }: { player: Player; onPlayer?: (player: Player) => void }) {
  const [shown, setShown] = useState<{ key: number; item: NewsAlert; more: number } | null>(null);
  const mark = useRef<NewsAlertMark | null>(null);
  const queue = useRef<{ item: NewsAlert; more: number }[]>([]);
  const counter = useRef(0);
  const on = player.news_alerts;

  useEffect(() => {
    let stopped = false;
    function look() {
      api.newsAlerts(mark.current).then((found) => {
        if (stopped) return;
        mark.current = found.mark;
        if (!on) return;
        // Oldest first, so the newest is the last one seen.
        const fresh = [...found.items].reverse().map((item, i) => ({ item, more: i === found.items.length - 1 ? found.more : 0 }));
        queue.current = [...queue.current, ...fresh].slice(-3);
      }).catch(() => undefined);
    }
    look();
    const timer = window.setInterval(look, 60_000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [on]);

  const showing = useRef(false);
  showing.current = shown !== null;
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (showing.current || queue.current.length === 0) return;
      const next = queue.current.shift()!;
      counter.current += 1;
      showing.current = true;
      setShown({ key: counter.current, ...next });
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  // It stays while the pointer or the keyboard is on it, and fades seven seconds after.
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (!shown || held) return;
    const timer = window.setTimeout(() => setShown(null), 7000);
    return () => window.clearTimeout(timer);
  }, [shown, held]);

  // The live region is always there, so screen readers announce what is put into it.
  return (
    <div className="news-toast-region" role="status" aria-live="polite">
      {shown && on && (
    <div className="news-toast" key={shown.key}
         onMouseEnter={() => setHeld(true)} onMouseLeave={() => setHeld(false)}
         onFocus={() => setHeld(true)} onBlur={() => setHeld(false)}>
      <a href="#/news" className="plain-link news-toast-text" onClick={() => { setHeld(false); setShown(null); }}>
        <span className="news-toast-outlet">{shown.item.important ? "▲ " : ""}{shown.item.outlet}</span>
        <span className="news-toast-headline">{shown.item.headline}</span>
        {shown.more > 0 && <span className="muted small"> and {shown.more} more</span>}
      </a>
      <button className="news-toast-button" aria-label="Close" title="Close" onClick={() => { setHeld(false); setShown(null); }}>×</button>
      <button
        className="news-toast-button small"
        title="Turn news pop-ups off (you can turn them on again from the menu under your picture)"
        onClick={() => { setHeld(false); setShown(null); api.setNewsAlerts(false).then((p) => onPlayer?.(p)).catch(() => undefined); }}
      >Mute</button>
    </div>
      )}
    </div>
  );
}

/** The sections of the player's screen. The build's own screen comes straight after the desk. */
function sectionsFor(player: Player) {
  return [
    { path: "", label: "My desk" },
    ...(player.build_name ? [{ path: "build", label: player.build_name }] : []),
    { path: "work", label: "Work" },
    // One section for the empire: its overview, desks, requests, deals, companies and War Room are tabs inside it.
    { path: "empire", label: player.empire ? "Empire" : "Empires", ...(player.empire && !player.empire.forming ? { count: player.empire.waiting } : {}) },
    { path: "market", label: "Market" },
    { path: "portfolio", label: "Portfolio" },
    { path: "news", label: "News" },
    { path: "companies", label: "Companies" },
    { path: "economy", label: "Economy" },
    { path: "career", label: "Career" },
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
          {"count" in section && (section.count ?? 0) > 0 && <span className="count" aria-label={`${section.count} waiting`}>{section.count}</span>}
        </a>
      ))}
      {player.empire && (
        <a href="#/empire" className="empire-badge plain-link">
          <span className="strong">{player.empire.name}</span>
          <span className="muted small">{player.empire.forming ? "being founded" : player.empire.place ? `place ${player.empire.place} in the league` : ""}</span>
        </a>
      )}
      <button className="section section-button" onClick={onLogout}>Log out</button>
    </nav>
  );
}

/**
 * The standard layout every screen uses (design document, section 18):
 * top bar, sections menu, work area and context rail.
 */
export function Shell({ player, live, current, onLogout, onPlayer, work, rail, accent }: {
  player: Player;
  /** Called with the player as the server now sees them, after a change made from the top bar. */
  onPlayer?: (player: Player) => void;
  live: LiveClock | null;
  /** The accent of the screen being shown, when it is not the player's own build's (the head's screen is gold; the War Room is neutral). */
  accent?: string;
  current: string;
  onLogout: () => void;
  work: ReactNode;
  rail: ReactNode;
}) {
  return (
    <div className="app" data-accent={accent ?? player.accent ?? undefined}>
      <TopBar player={player} live={live} onLogout={onLogout} onPlayer={onPlayer} />
      <PriceTicker />
      <div className="shell">
        <SectionsMenu player={player} current={current} onLogout={onLogout} />
        <main className="work">{work}</main>
        <aside className="rail" aria-label="Context">{rail}</aside>
      </div>
      <NewsToasts player={player} onPlayer={onPlayer} />
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
