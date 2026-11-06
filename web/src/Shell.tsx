import { useEffect, useRef, useState, type FocusEvent, type ReactNode } from "react";
import { api, type NewsAlert, type NewsAlertMark, type Player } from "./api";
import { CommandBar } from "./CommandBar";
import { formatLagosDate, formatLagosTime, formatNaira, MARKET_LABEL } from "./format";
import { ProfilePicture } from "./icons";
import { PriceTicker } from "./Ticker";
import { play } from "./sound";
import type { LiveClock } from "./useClock";
import { BankAlerts } from "./Crisis";
import { FundAlerts } from "./Funds";
import { EtfAlerts } from "./Etfs";
import { FxAlerts } from "./Currencies";

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
    <span className={`pill pill-${live.clock.closing_rush ? "opening_auction" : state}`} title={live.clock.closing_rush ? "Closing Rush" : MARKET_LABEL[state]}>
      <span className="pill-dot" aria-hidden="true" />
      <span className="pill-label">{live.clock.closing_rush ? "Closing Rush" : MARKET_LABEL[state]}</span>
    </span>
  );
}

/** The volume: it follows the finger at once, and is saved once the player stops moving it. A late answer never undoes a newer choice. */
function VolumeSlider({ player, onPlayer }: { player: Player; onPlayer?: (player: Player) => void }) {
  const [value, setValue] = useState(player.sound_volume);
  const sent = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => { setValue(player.sound_volume); }, [player.sound_volume]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  function move(next: number) {
    setValue(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const mine = ++sent.current;
      api.setSettings({ sound_volume: next }).then((p) => { if (mine === sent.current) onPlayer?.(p); }).catch(() => undefined);
    }, 400);
  }
  return (
    <label className="menu-volume">
      <span>Volume</span>
      <input type="range" min={0} max={100} step={10} value={value} disabled={!player.sound_on}
             onChange={(e) => move(Number(e.target.value))} aria-valuetext={`${value} out of 100`} />
    </label>
  );
}

/** Zone 1 of the standard layout: the top bar. */
function TopBar({ player, live, onLogout, onPlayer }: {
  player: Player; live: LiveClock | null; onLogout: () => void; onPlayer?: (player: Player) => void;
}) {
  return (
    <header className="topbar">
      <a href="#/" className="plain-link topbar-mark"><Wordmark /></a>
      <CommandBar player={player} />
      {/* One row: the game's date and the Lagos time, the market's state. The full date is in the tooltip. */}
      <div className="topbar-clock">
        {live && (
          <span className="mono topbar-date" title={`${formatLagosDate(live.now)} · ${formatLagosTime(live.now)} Lagos`}>
            {shortGameDate(live)}<span className="muted topbar-time"> · {formatLagosTime(live.now).slice(0, 5)} Lagos</span>
          </span>
        )}
        <MarketPill live={live} />
        {live && live.clock.test_weeks_ahead > 0 && (
          <span className="pill pill-test" title={`A test world, fast-forwarded ${live.clock.test_weeks_ahead} ${live.clock.test_weeks_ahead === 1 ? "week" : "weeks"}`}>
            Test +{live.clock.test_weeks_ahead}w
          </span>
        )}
      </div>
      {/* The player: cash, and the picture that opens their menu (their name, build, sound and settings are inside it). */}
      <div className="topbar-player">
        <div className="mono cash" title="Your cash">{formatNaira(player.cash.amount_kobo)}</div>
        <a href="#/search" className="icon-button phone-only" aria-label="Search or jump to">
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        </a>
        <ProfileMenu player={player} onLogout={onLogout} onPlayer={onPlayer} />
      </div>
    </header>
  );
}

function shortGameDate(live: LiveClock): string {
  const date = live.clock.game_date;
  return date ? `Y${date.year} · Q${date.quarter} · Day ${date.day_of_quarter}` : "Not open yet";
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
  const waiting = player.rank_waiting || player.unread_messages > 0 || (player.talent_waiting ?? 0) > 0;
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
  function change(settings: Parameters<typeof api.setSettings>[0]) {
    api.setSettings(settings).then((p) => onPlayer?.(p)).catch(() => undefined);
  }
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
          <a href="#/talent" onClick={close}>
            Proven Talent
            {(player.talent_waiting ?? 0) > 0 && <span className="menu-flag">◆ {player.talent_waiting === 1 ? "an invitation" : `${player.talent_waiting} invitations`} waiting</span>}
          </a>
          <a href="#/messages" onClick={close}>
            Messages
            {player.unread_messages > 0 && <span className="count" aria-label={`${player.unread_messages} unread`}>{player.unread_messages}</span>}
          </a>
          <button aria-pressed={player.news_alerts} onClick={toggleNews}>
            News pop-ups <span className="muted small">{player.news_alerts ? "● On" : "○ Off"}</span>
          </button>
          <button aria-pressed={player.sound_on} onClick={() => change({ sound_on: !player.sound_on })}>
            Sound <span className="muted small">{player.sound_on ? "● On" : "○ Off"}</span>
          </button>
          <VolumeSlider player={player} onPlayer={onPlayer} />
          <button aria-pressed={player.theme === "light"} onClick={() => change({ theme: player.theme === "light" ? "dark" : "light" })}>
            Light mode <span className="muted small">{player.theme === "light" ? "● On" : "○ Off"}</span>
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

export type Section = { path: string; label: string; count?: number; countWords?: string; tabs?: { path: string; label: string }[] };

/** The sections of the player's screen: seven, each a group of pages shown as tabs along the top of the page (owner, 29
 * October 2026: the sidebar stays short; a new feature goes inside a section, under the picture's menu, or pops up). */
export function sectionsFor(player: Player): Section[] {
  return [
    { path: "", label: "My desk" },
    { path: "work", label: "Work", count: player.work_in_hand, countWords: "in hand",
      tabs: [...(player.build_name ? [{ path: "build", label: `${player.build_name} desk` }] : []), { path: "work", label: "Work in hand" },
             { path: "career", label: "Career and levels" }] },
    // One section for the empire: its overview, desks, requests, deals, companies and War Room are tabs inside it.
    { path: "empire", label: player.empire ? "Empire" : "Empires", ...(player.empire && !player.empire.forming ? { count: player.empire.waiting, countWords: "waiting" } : {}) },
    { path: "market", label: "Markets", tabs: [{ path: "market", label: "Trade shares" }, { path: "companies", label: "Companies" }, { path: "property", label: "Property" }] },
    { path: "portfolio", label: "Money", ...((player.margin_calls ?? 0) > 0 ? { count: player.margin_calls, countWords: "margin calls" } : {}),
      tabs: [{ path: "portfolio", label: "Portfolio and savings" }, { path: "borrow", label: "Borrow" }, { path: "currencies", label: "Currencies" }] },
    { path: "news", label: "News", tabs: [{ path: "news", label: "News" }, { path: "intel", label: "Intelligence" }] },
    { path: "economy", label: "Economy", tabs: [{ path: "economy", label: "The economy" }, { path: "charities", label: "Charities" }] },
  ];
}

/** The section a page belongs to. */
export function sectionOf(player: Player, current: string): Section | undefined {
  return sectionsFor(player).find((s) => s.path === current || (s.tabs ?? []).some((t) => t.path === current));
}

/** Along the top of a page that shares its section with others: the section's pages, as links. */
function SectionTabs({ player, current }: { player: Player; current: string }) {
  const section = sectionOf(player, current);
  if (!section?.tabs || section.tabs.length < 2) return null;
  return (
    <nav className="section-tabs" aria-label={`${section.label}: its pages`}>
      {section.tabs.map((t) => (
        <a key={t.path} href={`#/${t.path}`} className={t.path === current ? "section-tab current" : "section-tab"}
           aria-current={t.path === current ? "page" : undefined}>{t.label}</a>
      ))}
    </nav>
  );
}

/** Zone 2: the sections menu. Only sections that exist are listed. On a phone it becomes the bar at the bottom. */
function SectionsMenu({ player, current }: { player: Player; current: string }) {
  const here = sectionOf(player, current)?.path;
  return (
    <nav className="sections" aria-label="Sections">
      {sectionsFor(player).map((section) => (
        <a
          key={section.path}
          href={`#/${section.path}`}
          className={section.path === here ? "section current" : "section"}
          aria-current={section.path === here ? (section.path === current ? "page" : "true") : undefined}
        >
          {section.label}
          {(section.count ?? 0) > 0 && <span className="count" aria-label={`${section.count} ${section.countWords}`}>{section.count}</span>}
        </a>
      ))}
      {player.empire && (
        <a href="#/empire" className="empire-badge plain-link">
          <span className="strong">{player.empire.name}</span>
          <span className="muted small">{player.empire.forming ? "being founded" : player.empire.place ? `place ${player.empire.place} in the league` : ""}</span>
        </a>
      )}
    </nav>
  );
}

const BAR_ICONS: Record<string, ReactNode> = {
  "": <path d="M3 11l9-7 9 7v9H3z" />,
  market: <path d="M3 17l6-6 4 4 8-8" />,
  work: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 9h8M8 13h8M8 17h5" /></>,
  empire: <><path d="M4 21V9l8-5 8 5v12" /><path d="M9 21v-6h6v6" /></>,
  more: <><circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" /></>,
};

/** On a phone: the five places a player goes most, along the bottom of the screen. The rest are under More. */
function BottomBar({ player, current }: { player: Player; current: string }) {
  const all = sectionsFor(player);
  const pick = (path: string) => all.find((s) => s.path === path)!;
  const items = [pick(""), pick("market"), pick("work"), pick("empire")].map((s) => ({ ...s, label: s.path === "" ? "Desk" : s.label }));
  const here = sectionOf(player, current)?.path ?? current;
  const inMore = !["", "market", "work", "empire"].includes(here);
  return (
    <nav className="bottom-bar" aria-label="Sections">
      {items.map((s) => (
        <a key={s.path} href={`#/${s.path}`} className={s.path === here ? "bar-item current" : "bar-item"} aria-current={s.path === here ? "page" : undefined}>
          <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">{BAR_ICONS[s.path]}</svg>
          <span>{s.label}</span>
          {(s.count ?? 0) > 0 && <span className="bar-count" aria-label={`${s.count} ${s.countWords}`}>{s.count}</span>}
        </a>
      ))}
      <a href="#/more" className={inMore ? "bar-item current" : "bar-item"} aria-current={current === "more" ? "page" : undefined}>
        <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">{BAR_ICONS.more}</svg>
        <span>More</span>
        {(player.unread_messages > 0 || player.rank_waiting) && <span className="bar-dot" role="img" aria-label="something is waiting" />}
      </a>
    </nav>
  );
}

/** On a phone, everything that is not on the bottom bar, and the player's own settings. */
export function MoreWork({ player, onPlayer, onLogout }: { player: Player; onPlayer?: (player: Player) => void; onLogout: () => void }) {
  const change = (settings: Parameters<typeof api.setSettings>[0]) => api.setSettings(settings).then((p) => onPlayer?.(p)).catch(() => undefined);
  const rest = sectionsFor(player).filter((s) => !["", "market", "work", "empire"].includes(s.path));
  return (
    <>
      <h1>More</h1>
      <Panel title="Sections">
        <nav aria-label="More sections" className="more-list">
          {rest.map((s) => <a key={s.path} href={`#/${s.path}`}>{s.label}<span aria-hidden="true">›</span></a>)}
          <a href="#/messages">Messages {player.unread_messages > 0 ? <span className="count" aria-label={`${player.unread_messages} unread`}>{player.unread_messages}</span> : <span aria-hidden="true">›</span>}</a>
          {player.build_name && <a href="#/rank">Rank {player.rank_waiting ? <span className="menu-flag">◆ a case is waiting</span> : <span aria-hidden="true">›</span>}</a>}
          <a href="#/talent">Proven Talent {(player.talent_waiting ?? 0) > 0 ? <span className="menu-flag">◆ an invitation is waiting</span> : <span aria-hidden="true">›</span>}</a>
          <a href="#/profile">Profile<span aria-hidden="true">›</span></a>
        </nav>
      </Panel>
      <Panel title="Your settings">
        <div className="more-list">
          <button aria-pressed={player.news_alerts} onClick={() => api.setNewsAlerts(!player.news_alerts).then((p) => onPlayer?.(p)).catch(() => undefined)}>News pop-ups <span className="muted small">{player.news_alerts ? "● On" : "○ Off"}</span></button>
          <button aria-pressed={player.sound_on} onClick={() => change({ sound_on: !player.sound_on })}>Sound <span className="muted small">{player.sound_on ? "● On" : "○ Off"}</span></button>
          <VolumeSlider player={player} onPlayer={onPlayer} />
          <button aria-pressed={player.theme === "light"} onClick={() => change({ theme: player.theme === "light" ? "dark" : "light" })}>Light mode <span className="muted small">{player.theme === "light" ? "● On" : "○ Off"}</span></button>
          <button onClick={onLogout}>Log out</button>
        </div>
      </Panel>
    </>
  );
}

/** On a phone, the search icon opens the command bar on its own page. */
export function SearchWork({ player }: { player: Player }) {
  return (
    <>
      <h1>Search</h1>
      <Panel><CommandBar player={player} /><p className="muted small" style={{ marginTop: 10 }}>Type a company’s code or name, a page, or what you want to do.</p></Panel>
    </>
  );
}

/**
 * The standard layout every screen uses (design document, section 18):
 * top bar, sections menu, work area and context rail.
 */
export function Shell({ player, live, current, onLogout, onPlayer, work, rail, accent, wide = false }: {
  player: Player;
  /** No context rail: the work area takes the whole width (the focused work screen). */
  wide?: boolean;
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
  // The Closing Bell rings (if the player has sound on) when the market closes while they are here.
  const state = live?.clock.market_state;
  const was = useRef(state);
  // Every row of tabs in the game: the left and right arrow keys move to the next tab and open it.
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft" && event.key !== "Home" && event.key !== "End") return;
      const tab = (event.target as HTMLElement | null)?.closest?.('[role="tab"]') as HTMLElement | null;
      const list = tab?.closest('[role="tablist"]');
      if (!tab || !list) return;
      const tabs = Array.from(list.querySelectorAll<HTMLElement>('[role="tab"]')).filter((t) => !(t as HTMLButtonElement).disabled);
      const at = tabs.indexOf(tab);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
        : (at + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      event.preventDefault();
      tabs[next].focus();
      tabs[next].click();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  useEffect(() => {
    if (was.current === "open" && state === "closed") play("bell");
    was.current = state;
  }, [state]);
  return (
    <div className="app" data-accent={accent ?? player.accent ?? undefined}>
      <a href="#main" className="skip-link" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to the page</a>
      <TopBar player={player} live={live} onLogout={onLogout} onPlayer={onPlayer} />
      <PriceTicker />
      <div className={wide ? "shell shell-wide" : "shell"}>
        <SectionsMenu player={player} current={current} />
        <main className="work" id="main" tabIndex={-1}><SectionTabs player={player} current={current} />{work}</main>
        {!wide && <aside className="rail" aria-label="Context">{rail}</aside>}
      </div>
      <BottomBar player={player} current={current} />
      <NewsToasts player={player} onPlayer={onPlayer} />
      <BankAlerts onLoggedOut={onLogout} />
      <FundAlerts onLoggedOut={onLogout} />
      <EtfAlerts onLoggedOut={onLogout} />
      <FxAlerts onLoggedOut={onLogout} />
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

/** A gain or a loss in naira, with an arrow so that it reads without colour. */
export function Gain({ kobo }: { kobo: string }) {
  const value = BigInt(kobo);
  if (value === 0n) return <span className="mono muted">₦0</span>;
  const up = value > 0n;
  return <span className={`mono change-${up ? "up" : "down"}`}>{up ? "▲" : "▼"} {formatNaira((up ? value : -value).toString())}</span>;
}

export function Rating({ value }: { value: string }) {
  const tier = ["AAA", "AA", "A"].includes(value) ? "strong" : ["BBB", "BB"].includes(value) ? "middle" : "weak";
  return <span className={`rating rating-${tier}`} title="Credit rating">{value}</span>;
}
