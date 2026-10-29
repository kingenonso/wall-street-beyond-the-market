import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  api, ApiError, type BoardPlayer, type ChallengeItem, type Firm, type FirmChallenges, type FirmInvitation, type Player, type TalentPage,
  type TalentRecord, type TalentView,
} from "./api";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { ProfilePicture } from "./icons";
import { NumberTile } from "./Parts";
import { Failed, Loading, Panel, Wordmark } from "./Shell";
import { LineChart } from "./TrendChart";

/** Proven Talent (the talent and funds stage, Part 1). A record worked out by the game from its own books, which
 * nobody can type in or change; badges earned from it; a page the player may share; firms' challenges; invitations from
 * firms. Only percentages and counts are shown, never anybody's money. */

const pct = (bps: number | null | undefined, sign = true) =>
  bps === null || bps === undefined ? "n/a" : `${sign && bps > 0 ? "+" : ""}${(bps / 100).toFixed(1)}%`;
const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric", timeZone: "Africa/Lagos" }) : "");
const when = (iso: string) => new Date(iso).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos" });
const problemWords = (problem: unknown) => (problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");

// ---------------------------------------------------------------------------
// The record itself (shared by the player's page, the shared page and the firms' view)
// ---------------------------------------------------------------------------

function Badges({ badges }: { badges: TalentView["badges"] }) {
  if (!badges.length) return <p className="muted small">No badges yet. They are earned from the record: beating the market, calls that turn out right, a clean audit record, coming through a bank crisis, firms' challenges won.</p>;
  return (
    <ul className="badge-list" aria-label="Badges">
      {badges.map((b) => (
        <li key={b.code} className="talent-badge" title={b.words}>
          <span aria-hidden="true">★</span> <span className="strong">{b.label}</span>
          <span className="muted small"> · {b.words} Earned {day(b.earned_at)}.</span>
        </li>
      ))}
    </ul>
  );
}

function Investing({ inv }: { inv: TalentRecord["investing"] }) {
  if (!inv.days_counted) {
    return <p className="muted small">No investing record yet: it starts once there is at least ₦100,000 to invest at two closing bells in a row. Each trading day's closing bell adds a day.</p>;
  }
  const step = Math.max(1, Math.ceil(inv.chart.length / 20));
  const points = inv.chart.filter((_, i) => i % step === 0 || i === inv.chart.length - 1)
    .map((p) => ({ label: new Date(p.day).toLocaleDateString("en-NG", { day: "numeric", month: "short", timeZone: "UTC" }), first: p.you_bps / 100, second: p.index_bps / 100 }));
  return (
    <>
      <div className="tiles">
        <NumberTile label="Return, money from outside taken out" value={pct(inv.total_bps)} note={`over ${inv.days_counted} trading days`} />
        <NumberTile label="Against the market index" value={pct(inv.versus_index_bps)} note={`the index: ${pct(inv.index_bps)}`} />
        <NumberTile label="Worst fall from a high" value={pct(inv.worst_fall_bps)} />
        <NumberTile label="Quarters beating the market" value={`${inv.quarters_beaten} of ${inv.quarters_counted}`} note={inv.best_streak ? `best run: ${inv.best_streak} in a row` : undefined} />
        <NumberTile label="A year, at this pace" value={pct(inv.annual_bps)} note={inv.swing_bps !== null ? `swings ${pct(inv.swing_bps, false)} a year` : undefined} />
        <NumberTile label="Return for each unit of risk" value={inv.risk_ratio === null ? "n/a" : inv.risk_ratio.toFixed(2)} note="a year's return ÷ a year's swings" />
      </div>
      {points.length >= 2 && <LineChart names={["You", "Market index"]} data={points} format={(v) => `${v.toFixed(0)}%`} />}
      {inv.quarters.length > 0 && (
        <div className="table-scroll">
          <table className="mini-table">
            <caption className="sr-only">Quarter by quarter against the market index</caption>
            <thead><tr><th scope="col">Quarter</th><th scope="col" className="num">You</th><th scope="col" className="num">Index</th><th scope="col">Beat it?</th></tr></thead>
            <tbody>
              {inv.quarters.map((q) => (
                <tr key={q.period}><td>{q.label}</td><td className="num mono">{pct(q.you_bps)}</td><td className="num mono">{pct(q.index_bps)}</td>
                  <td>{q.beat ? <span className="tag-good">✓ Yes</span> : <span className="tag">No</span>}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <div className="stat-row">
      {items.map(([label, value]) => <div key={label}><div className="lbl">{label}</div><div className="mono figure-small">{value}</div></div>)}
    </div>
  );
}

function Section({ name, rec, names }: { name: string; rec: Partial<TalentRecord>; names: Record<string, string> }) {
  const title = names[name] ?? name;
  if (name === "investing" && rec.investing) return <Panel title={title}><Investing inv={rec.investing} /></Panel>;
  if (name === "work" && rec.work) {
    return (
      <Panel title={title}>
        {rec.work.builds.length === 0 ? <p className="muted small">No career chosen yet.</p> : (
          <ul className="plain-list">
            {rec.work.builds.map((b) => (
              <li key={b.build} className="fact-row"><span className="strong">{b.name}</span>
                <span className="small">Level {b.level} · {b.rank} · work passed {b.passed}, failed {b.failed}</span></li>
            ))}
          </ul>
        )}
      </Panel>
    );
  }
  if (name === "calls" && rec.calls) {
    const c = rec.calls;
    return (
      <Panel title={title} aside="what was put in writing for an empire, checked later against what happened">
        <Facts items={[["Right", c.right], ["Wrong", c.wrong], ["Right, of those checked", c.right_bps === null ? "n/a" : pct(c.right_bps, false)]]} />
        {c.kinds.length > 0 && <p className="small muted">{c.kinds.map((k) => `${k.name}: ${k.right} right, ${k.wrong} wrong`).join(" · ")}</p>}
      </Panel>
    );
  }
  if (name === "audits" && rec.audits) {
    const a = rec.audits;
    return (
      <Panel title={title}>
        <Facts items={[["Audits filed", a.filed], ["Rightly named", a.rightly_named], ["Wrongly named", a.wrongly_named], ["Missed, proved later", a.missed_proved_later]]} />
      </Panel>
    );
  }
  if (name === "journalism" && rec.journalism) {
    const j = rec.journalism;
    return (
      <Panel title={title}>
        <Facts items={[["Published", j.published], ["Scoops", j.scoops], ["Leads that held up", j.leads_held], ["Leads proved false", j.leads_failed],
          ["Corrections", j.corrections], ["Credibility", j.credibility ?? "n/a"]]} />
      </Panel>
    );
  }
  if (name === "leadership" && rec.leadership) {
    const l = rec.leadership;
    return (
      <Panel title={title}>
        <Facts items={[["Decisions that turned out well", l.good], ["Turned out badly", l.bad]]} />
        <p className="small muted">{l.empires.length ? `Empires led: ${l.empires.join(", ")}` : "Has not led an empire."}</p>
      </Panel>
    );
  }
  if (name === "crisis" && rec.crisis) {
    const c = rec.crisis;
    return (
      <Panel title={title}>
        <Facts items={[["Crises lived through", c.crises_lived_through], ["Banks closed while saving there", c.banks_closed_with_savings],
          ["Pulled out in time", c.pulled_out_in_time], ["Savings lost", c.lost_savings ? "Yes" : "None"], ["Bank rescues won", c.rescues_won]]} />
      </Panel>
    );
  }
  if (name === "challenges" && rec.challenges) {
    const c = rec.challenges;
    return (
      <Panel title={title}>
        <Facts items={[["Entered", c.entered], ["Won", c.wins], ["In the top tenth", c.top_tenth]]} />
        {c.results.length > 0 && (
          <ul className="plain-list small">
            {c.results.map((r) => <li key={r.id}>{r.title} <span className="muted">· set by {r.firm} · {r.place ? `place ${r.place} of ${r.entrants}` : "not placed"}</span></li>)}
          </ul>
        )}
      </Panel>
    );
  }
  if (name === "conduct" && rec.conduct) {
    const c = rec.conduct;
    return (
      <Panel title={title} aside="always shown: it cannot be hidden" className={c.proved ? "panel-warn" : ""}>
        {c.proved === 0 ? <p className="small"><span className="tag-good">✓</span> No wrongdoing proved.</p> : (
          <ul className="plain-list small">{c.entries.map((e, i) => <li key={i}>{e.words} <span className="muted">· {day(e.at)}</span></li>)}</ul>
        )}
      </Panel>
    );
  }
  return null;
}

export function RecordView({ view }: { view: TalentView }) {
  return (
    <>
      <Panel>
        <div className="identity">
          <ProfilePicture icon={view.who.icon} name={view.who.name} size={56} />
          <div>
            <h1 className="h3-look">{view.who.name}</h1>
            {view.headline && <div>{view.headline}</div>}
            <div className="muted small">{view.who.build ? `${view.who.build} · ` : ""}playing since {day(view.who.since)}
              {view.worked_at ? ` · worked out ${when(view.worked_at)}` : ""}</div>
          </div>
        </div>
        <Badges badges={view.badges} />
        <p className="muted small">{view.how ?? "Worked out by the game from its own books: nobody, you included, can type in or change any of it. Only percentages and counts are shown, never how much money anybody has."}</p>
      </Panel>
      {view.sections.map((s) => <Section key={s} name={s} rec={view.record} names={view.names} />)}
    </>
  );
}

// ---------------------------------------------------------------------------
// The player's own page
// ---------------------------------------------------------------------------

type Tab = "record" | "challenges" | "invitations" | "sharing";
const TABS: [Tab, string][] = [["record", "My record"], ["challenges", "Firm challenges"], ["invitations", "Invitations"], ["sharing", "Sharing"]];

function useTalentRun(setPage: (p: TalentPage) => void, onLoggedOut: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(path: string, body: unknown, done: string) {
    setBusy(true); setError(null); setNotice(null);
    try {
      setPage(await api.talentPost(path, body));
      setNotice(done);
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setError(problemWords(problem));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}

export function TalentWork({ player, tab, onLoggedOut, onChanged }: { player: Player; tab?: string; onLoggedOut: () => void; onChanged: () => void }) {
  const loaded = useLoad(api.talent, "talent", onLoggedOut);
  const [page, setPage] = useState<TalentPage | null>(null);
  const [current, setCurrent] = useState<Tab>((TABS.find(([k]) => k === tab)?.[0]) ?? "record");
  useEffect(() => { if (loaded.data) setPage(loaded.data); }, [loaded.data]);
  const act = useTalentRun((p) => { setPage(p); onChanged(); }, onLoggedOut);
  if (loaded.loading && !page) return <Loading what="your record" />;
  if (loaded.error && !page) return <Failed message={loaded.error} onRetry={loaded.reload} />;
  if (!page) return null;
  const waiting = page.invitations.filter((i) => i.status === "sent").length;
  return (
    <>
      <div className="work-head">
        <h1>Proven Talent</h1>
        <span className="muted small">A record of what you have really done, worked out by the game. Firms can see it only if you let them.</span>
      </div>
      <div className="underline-tabs" role="tablist" aria-label="Proven Talent">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={current === key} className={current === key ? "active" : undefined}
                  onClick={() => { setCurrent(key); window.history.replaceState(null, "", `#/talent/${key}`); }}>
            {label}{key === "invitations" && waiting > 0 ? ` (${waiting})` : ""}
          </button>
        ))}
      </div>
      {act.notice && <p className="notice" role="status">{act.notice}</p>}
      {act.error && <p className="error" role="alert">{act.error}</p>}
      {current === "record" && <RecordView view={{ ...page, record: page.record, sections: [...page.sections, "conduct"] }} />}
      {current === "sharing" && <Sharing page={page} act={act} />}
      {current === "challenges" && <Challenges page={page} act={act} player={player} />}
      {current === "invitations" && <Invitations page={page} act={act} />}
    </>
  );
}

type Act = ReturnType<typeof useTalentRun>;

function Sharing({ page, act }: { page: TalentPage; act: Act }) {
  const s = page.settings;
  const [show, setShow] = useState<string[]>(s.show);
  const [headline, setHeadline] = useState(s.headline);
  const link = s.slug ? `${window.location.origin}${window.location.pathname}#/r/${s.slug}` : null;
  const [copied, setCopied] = useState(false);
  return (
    <>
      <Panel title="Share your record" aside={s.shared ? "shared" : "private"}>
        <p className="small">Your record is private until you share it. A shared record has its own address that only people you give it to will know.
          You choose which parts are shown. What you have been proved to have done wrong is always shown on a shared record: it cannot be hidden.</p>
        <div className="button-row">
          <button className={s.shared ? "button-quiet" : "button-primary"} disabled={act.busy}
                  onClick={() => act.run("/talent/share", { on: !s.shared }, s.shared ? "Your record is private again: the address no longer works." : "Your record is shared.")}>
            {s.shared ? "Stop sharing" : "Share my record"}
          </button>
          {s.shared && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("/talent/new-link", {}, "A new address: the old one no longer works.")}>Make a new address</button>}
        </div>
        {link && (
          <div className="fact-row">
            <span className="mono small" style={{ wordBreak: "break-all" }}>{link}</span>
            <span className="button-row">
              <button className="button-outline" onClick={() => { navigator.clipboard?.writeText(link).then(() => setCopied(true)).catch(() => undefined); }}>{copied ? "Copied" : "Copy"}</button>
              <a className="button-quiet" href={`#/r/${s.slug}`} target="_blank" rel="noreferrer">Open</a>
            </span>
          </div>
        )}
        <fieldset className="check-list">
          <legend className="small strong">Parts shown</legend>
          {page.sections.map((k) => (
            <label key={k} className="check-line small">
              <input type="checkbox" checked={show.includes(k)} onChange={(e) => setShow(e.target.checked ? [...show, k] : show.filter((x) => x !== k))} /> {page.names[k]}
            </label>
          ))}
          <label className="check-line small"><input type="checkbox" checked disabled /> {page.names.conduct} (always)</label>
        </fieldset>
        <button className="button-outline" disabled={act.busy} onClick={() => act.run("/talent/sections", { sections: show }, "Saved.")}>Save the parts shown</button>
      </Panel>
      <Panel title="The talent board" aside={s.on_board ? "firms can find you" : "not on the board"}>
        <p className="small">Firms an administrator has approved look for players on the board. They see the parts you share, and can send you an invitation to talk.
          Your contact details reach a firm only if you accept its invitation and type them in yourself.</p>
        <p className={s.board_ready ? "small" : "small muted"}>{s.board_words}</p>
        <label className="answer small">A line about you (shown on the board)
          <input type="text" maxLength={140} value={headline} onChange={(e) => setHeadline(e.target.value)} placeholder="e.g. Bank analyst: calm in a crisis" />
        </label>
        <div className="button-row">
          <button className={s.on_board ? "button-quiet" : "button-primary"} disabled={act.busy || (!s.on_board && !s.board_ready)}
                  onClick={() => act.run("/talent/board", { on: !s.on_board, headline }, s.on_board ? "You are off the board." : "You are on the board.")}>
            {s.on_board ? "Leave the board" : "Join the board"}
          </button>
          {s.on_board && <button className="button-outline" disabled={act.busy} onClick={() => act.run("/talent/board", { on: true, headline }, "Saved.")}>Save the line</button>}
        </div>
      </Panel>
    </>
  );
}

function Invitations({ page, act }: { page: TalentPage; act: Act }) {
  const [contact, setContact] = useState<Record<number, string>>({});
  if (!page.invitations.length) {
    return <Panel title="Invitations"><p className="muted small">No invitations yet. Firms can invite you if you are on the talent board, or if you finish near the top of one of their challenges and agreed to be seen.</p></Panel>;
  }
  return (
    <Panel title="Invitations from firms">
      {page.invitations.map((i) => (
        <div key={i.id} className="fact-row">
          <div>
            <div><span className="swatch" style={{ background: i.colour }} aria-hidden="true" /> <span className="strong">{i.firm}</span>
              {i.tagline && <span className="muted small"> · {i.tagline}</span>}</div>
            <p className="small">{i.message}</p>
            <div className="muted small">Sent {when(i.sent_at)}{i.challenge ? ` · after your challenge "${i.challenge}"` : ""}{i.website ? <> · <a href={i.website} target="_blank" rel="noreferrer noopener">{i.website}</a></> : null}</div>
            {i.status === "accepted" && <div className="small"><span className="tag-good">✓ Accepted</span> <span className="muted">You sent them: {i.contact}</span></div>}
            {i.status === "declined" && <div className="small muted">Declined.</div>}
          </div>
          {i.status === "sent" && (
            <div className="intel-actions">
              <label className="answer small">How they can reach you <input type="text" maxLength={300} value={contact[i.id] ?? ""} onChange={(e) => setContact({ ...contact, [i.id]: e.target.value })} placeholder="an email address" /></label>
              <button className="button-primary" disabled={act.busy || (contact[i.id] ?? "").trim().length < 5} onClick={() => act.run(`/talent/invitations/${i.id}`, { accept: true, contact: contact[i.id] }, `Accepted: ${i.firm} has your details.`)}>Accept</button>
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/talent/invitations/${i.id}`, { accept: false, contact: "" }, "Declined.")}>Decline</button>
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/talent/firms/${i.firm_id}/block`, {}, `${i.firm} can never invite you again.`)}>Block this firm</button>
            </div>
          )}
        </div>
      ))}
    </Panel>
  );
}

const PHASE: Record<ChallengeItem["phase"], string> = {
  waiting: "Starts soon", open: "Open", running: "Running: closed to new answers", scoring: "Being scored", scored: "Scored", cancelled: "Called off",
};

function Challenges({ page, act, player }: { page: TalentPage; act: Act; player: Player }) {
  if (!page.challenges.length) {
    return <Panel title="Firm challenges"><p className="muted small">No challenges are open just now. Firms set them: manage a paper portfolio, value a company, find the weakest bank, forecast a profit, or show your real record. Nothing a player wins is money, and no firm gets any advantage in the game.</p></Panel>;
  }
  return <>{page.challenges.map((c) => <ChallengeCard key={c.id} c={c} act={act} player={player} />)}</>;
}

function ChallengeCard({ c, act }: { c: ChallengeItem; act: Act; player: Player }) {
  const [seen, setSeen] = useState(true);
  const [amount, setAmount] = useState("");
  const [ticker, setTicker] = useState("");
  const [reasons, setReasons] = useState(c.mine?.answer_text ?? "");
  const [deal, setDeal] = useState({ ticker: "", quantity: "" });
  const mine = c.mine;
  const canJoin = !mine && (c.phase === "waiting" || c.phase === "open") && (c.kind !== "live" || c.phase === "waiting");
  const answering = !!mine && c.phase === "open" && ["valuation", "forecast", "weak_bank"].includes(c.kind);
  const dealing = !!mine && c.kind === "paper" && (c.phase === "open" || c.phase === "running");
  return (
    <Panel title={c.title} aside={<><span className="swatch" style={{ background: c.firm.colour }} aria-hidden="true" /> set by {c.firm.name}</>}>
      <p className="small"><span className="tag">{c.kind_name}</span> <span className={c.phase === "open" ? "tag-good" : "tag"}>{PHASE[c.phase]}</span>
        <span className="muted"> · {c.entrants} entrant{c.entrants === 1 ? "" : "s"} · starts {when(c.opens_at)} · answers close {when(c.locks_at)} · ends {when(c.ends_at)}</span></p>
      <p className="small">{c.kind_words}{c.company ? ` Company: ${c.company.name} (${c.company.ticker}).` : ""}{c.target_period ? ` Quarter: ${c.target_period}.` : ""}
        {c.kind === "paper" ? ` Paper cash: ${formatNaira(c.starting_cash)}.` : ""}</p>
      {c.brief && <p className="small muted">{c.brief}</p>}
      {canJoin && (
        <div className="button-row">
          <label className="check-line small"><input type="checkbox" checked={seen} onChange={(e) => setSeen(e.target.checked)} /> Let {c.firm.name} see my result and record if I finish in its top {c.top_shown}</label>
          <button className="button-primary" disabled={act.busy} onClick={() => act.run(`/challenges/${c.id}/join`, { seen_by_sponsor: seen }, "You have joined.")}>Join</button>
        </div>
      )}
      {mine && (
        <div className="small">
          <span className="tag-good">✓ Joined</span>{" "}
          <label className="check-line small"><input type="checkbox" checked={mine.seen_by_sponsor} disabled={act.busy}
            onChange={(e) => act.run(`/challenges/${c.id}/sponsor`, { on: e.target.checked }, e.target.checked ? `${c.firm.name} may see your result.` : `${c.firm.name} will not see your result.`)} /> {c.firm.name} may see my result</label>
          {mine.answered_at && <div className="muted">Your answer: {c.kind === "weak_bank" ? mine.answer_ticker : formatNaira(mine.answer ?? "0")}{c.kind === "valuation" ? " a share" : ""}</div>}
          {mine.score_words && <div className="strong">{mine.place ? `Place ${mine.place}. ` : ""}{mine.score_words}</div>}
        </div>
      )}
      {answering && (
        <div className="inline-form">
          {c.kind === "weak_bank"
            ? <label className="answer small">Bank (its three letters) <input type="text" maxLength={3} value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} /></label>
            : <label className="answer small">{c.kind === "valuation" ? "Your price for one share, ₦" : "Profit for the quarter, ₦"} <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>}
          <label className="answer small">Your reasons <textarea maxLength={1000} rows={3} value={reasons} onChange={(e) => setReasons(e.target.value)} /></label>
          <button className="button-outline" disabled={act.busy || (c.kind === "weak_bank" ? ticker.length !== 3 : amount.trim() === "")}
                  onClick={() => act.run(`/challenges/${c.id}/answer`, c.kind === "weak_bank" ? { ticker, reasons } : { amount_naira: Math.round(Number(amount)), reasons }, "Your answer is in. You can change it until answers close.")}>
            {mine?.answered_at ? "Change my answer" : "Send my answer"}
          </button>
        </div>
      )}
      {mine && c.kind === "paper" && (
        <>
          <p className="small">Paper cash {formatNaira(mine.cash ?? "0")} · worth now {formatNaira(mine.value ?? "0")} (started with {formatNaira(c.starting_cash)})</p>
          {(mine.holdings ?? []).length > 0 && (
            <ul className="plain-list small">{mine.holdings!.map((h) => <li key={h.ticker}>{h.quantity.toLocaleString("en-NG")} {h.ticker} at {formatNaira(h.price)}</li>)}</ul>
          )}
          {dealing && (
            <div className="inline-form">
              <label className="answer small">Share <input type="text" maxLength={3} value={deal.ticker} onChange={(e) => setDeal({ ...deal, ticker: e.target.value.toUpperCase() })} /></label>
              <label className="answer small">How many <input type="number" min={1} value={deal.quantity} onChange={(e) => setDeal({ ...deal, quantity: e.target.value })} /></label>
              {(["buy", "sell"] as const).map((side) => (
                <button key={side} className={side === "buy" ? "button-outline" : "button-quiet"} disabled={act.busy || deal.ticker.length !== 3 || !Number(deal.quantity)}
                        onClick={() => act.run(`/challenges/${c.id}/trade`, { ticker: deal.ticker, side, quantity: Math.round(Number(deal.quantity)) }, `Paper ${side === "buy" ? "bought" : "sold"} at the live price.`)}>
                  Paper {side}
                </button>
              ))}
            </div>
          )}
        </>
      )}
      {c.scoreboard.length > 0 && (
        <ol className="plain-list small" aria-label="Scoreboard">
          {c.scoreboard.map((s) => <li key={s.place}><span className="mono">{s.place}.</span> {s.name} <span className="muted">· {s.score_words}</span></li>)}
        </ol>
      )}
    </Panel>
  );
}

export function TalentRail({ player }: { player: Player }) {
  return (
    <Panel title="How the record works">
      <ul className="plain-list small">
        <li>Worked out after every closing bell from the game's own books. Nobody can type it in.</li>
        <li>Investing is measured with money from outside (salary, fees, gifts) taken out first, so earning more never looks like investing well.</li>
        <li>Trades between friends at odd prices are not counted as returns.</li>
        <li>Badges are earned, never bought. A firm gets no advantage in the game.</li>
      </ul>
      {(player.talent_waiting ?? 0) > 0 && <p className="small strong">{player.talent_waiting} invitation{player.talent_waiting === 1 ? "" : "s"} waiting.</p>}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// A shared record: open to anybody with its address, no login
// ---------------------------------------------------------------------------

export function SharedRecordPage({ slug }: { slug: string }) {
  const [view, setView] = useState<TalentView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.sharedRecord(slug).then(setView).catch((p) => setError(problemWords(p))); }, [slug]);
  return (
    <div className="public-page">
      <header className="public-head">
        <Wordmark />
        <span className="muted small">Proven Talent · a verified record</span>
        {view && <button className="button-quiet print-hide" onClick={() => window.print()}>Print or save as PDF</button>}
      </header>
      <main id="main" className="public-main">
        {error && <Panel><p className="error" role="alert">{error}</p></Panel>}
        {!view && !error && <p className="muted">Loading…</p>}
        {view && <RecordView view={view} />}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The firms' portal: its own login, no player powers
// ---------------------------------------------------------------------------

export function FirmPortal({ route }: { route: string[] }) {
  const [firm, setFirm] = useState<Firm | null | undefined>(undefined);
  useEffect(() => { api.firmMe().then(setFirm).catch(() => setFirm(null)); }, []);
  async function logout() { await api.firmLogout().catch(() => undefined); setFirm(null); }
  return (
    <div className="public-page">
      <header className="public-head">
        <Wordmark />
        <span className="muted small">Proven Talent · for firms</span>
        {firm && <span className="small"><span className="swatch" style={{ background: firm.colour }} aria-hidden="true" /> {firm.name} <button className="button-quiet" onClick={logout}>Log out</button></span>}
      </header>
      <main id="main" className="public-main">
        {firm === undefined && <p className="muted">Loading…</p>}
        {firm === null && <FirmAuth onIn={setFirm} />}
        {firm && firm.status !== "approved" && (
          <Panel title="Waiting for approval">
            <p className="small">Thank you. An administrator looks at every firm before it can see the talent board or set challenges. You will be able to use it as soon as {firm.name} is approved.</p>
          </Panel>
        )}
        {firm && firm.status === "approved" && <FirmDesk firm={firm} route={route} onLoggedOut={() => setFirm(null)} />}
      </main>
    </div>
  );
}

function FirmAuth({ onIn }: { onIn: (f: Firm) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [form, setForm] = useState({ name: "", email: "", password: "", contact_name: "", website: "", tagline: "", colour: "#2f6f9f" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      onIn(mode === "login" ? await api.firmLogin(form.email, form.password) : await api.firmSignup(form));
    } catch (p) { setError(problemWords(p)); } finally { setBusy(false); }
  }
  return (
    <Panel title={mode === "login" ? "Firm log in" : "Sign your firm up"}>
      <p className="small">Firms sponsor challenges and look for talent. A firm has no powers in the game: it cannot trade, own, vote or message players there, and no firm gets any advantage inside the world.
        Players' records are worked out by the game from its own books.</p>
      <form onSubmit={submit} className="stack-form">
        {mode === "signup" && <label className="answer">Firm's name <input required minLength={2} maxLength={80} value={form.name} onChange={set("name")} /></label>}
        <label className="answer">Email <input type="email" required value={form.email} onChange={set("email")} autoComplete="username" /></label>
        <label className="answer">Password <input type="password" required minLength={mode === "signup" ? 12 : 1} value={form.password} onChange={set("password")}
          autoComplete={mode === "signup" ? "new-password" : "current-password"} /></label>
        {mode === "signup" && (
          <>
            <label className="answer">Your name <input required minLength={2} maxLength={80} value={form.contact_name} onChange={set("contact_name")} /></label>
            <label className="answer">Website <input type="url" maxLength={200} value={form.website} onChange={set("website")} placeholder="https://" /></label>
            <label className="answer">One line about the firm <input maxLength={140} value={form.tagline} onChange={set("tagline")} /></label>
            <label className="answer">Colour <input type="color" value={form.colour} onChange={set("colour")} /></label>
          </>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="button-row">
          <button className="button-primary" disabled={busy}>{mode === "login" ? "Log in" : "Sign up"}</button>
          <button type="button" className="button-quiet" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); }}>
            {mode === "login" ? "New here? Sign your firm up" : "Already signed up? Log in"}</button>
        </div>
      </form>
    </Panel>
  );
}

const BUILD_CHOICES: [string, string][] = [["", "Any career"], ["asset_manager", "Asset Manager"], ["accountant", "Accountant"], ["investment_banker", "Investment Banker"],
  ["risk_manager", "Risk Manager"], ["lawyer", "Legal Counsel"], ["journalist", "Financial Journalist"]];

function FirmDesk({ firm, route, onLoggedOut }: { firm: Firm; route: string[]; onLoggedOut: () => void }) {
  const [tab, setTab] = useState<"board" | "challenges" | "invitations">("board");
  const viewing = route[1] === "record" ? route[2] : null;
  if (viewing) return <FirmRecord playerId={viewing} onLoggedOut={onLoggedOut} />;
  return (
    <>
      <div className="underline-tabs" role="tablist" aria-label="Firm">
        {([["board", "Talent board"], ["challenges", "Challenges"], ["invitations", "Invitations sent"]] as const).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "active" : undefined} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>
      {tab === "board" && <Board onLoggedOut={onLoggedOut} />}
      {tab === "challenges" && <FirmChallengesDesk firm={firm} onLoggedOut={onLoggedOut} />}
      {tab === "invitations" && <Sent onLoggedOut={onLoggedOut} />}
    </>
  );
}

function Board({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [q, setQ] = useState({ build: "", least_level: 0, sort: "versus_index" });
  const loaded = useLoad(() => api.firmBoard(q), `board-${q.build}-${q.least_level}-${q.sort}`, onLoggedOut);
  return (
    <Panel title="The talent board" aside="players who chose to be found">
      <div className="filter-row">
        <label className="small">Career <select className="filter-select" value={q.build} onChange={(e) => setQ({ ...q, build: e.target.value })}>
          {BUILD_CHOICES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="small">Level at least <select className="filter-select" value={q.least_level} onChange={(e) => setQ({ ...q, least_level: Number(e.target.value) })}>
          {[0, 10, 20, 40, 60, 80].map((n) => <option key={n} value={n}>{n || "any"}</option>)}</select></label>
        <label className="small">Sort by <select className="filter-select" value={q.sort} onChange={(e) => setQ({ ...q, sort: e.target.value })}>
          <option value="versus_index">Return against the market</option><option value="risk">Return for the risk taken</option>
          <option value="calls">Calls that turned out right</option><option value="badges">Badges</option><option value="wins">Challenges won</option></select></label>
      </div>
      {loaded.loading && <Loading what="the board" />}
      {loaded.error && <Failed message={loaded.error} onRetry={loaded.reload} />}
      {loaded.data && loaded.data.players.length === 0 && <p className="muted small">Nobody matches yet.</p>}
      {loaded.data && loaded.data.players.length > 0 && (
        <div className="table-scroll">
          <table className="mini-table">
            <caption className="sr-only">Players on the talent board</caption>
            <thead><tr><th scope="col">Player</th><th scope="col">Careers</th><th scope="col" className="num">Against the market</th><th scope="col" className="num">Worst fall</th>
              <th scope="col" className="num">Calls right</th><th scope="col" className="num">Badges</th><th scope="col">Conduct</th></tr></thead>
            <tbody>
              {loaded.data.players.map((p: BoardPlayer) => (
                <tr key={p.player_id}>
                  <td><a href={`#/firms/record/${p.player_id}`}>{p.name}</a><div className="muted small">{p.headline}</div></td>
                  <td className="small">{p.builds.map((b) => `${b.name} ${b.level}`).join(", ")}</td>
                  <td className="num mono">{pct(p.versus_index_bps)}</td><td className="num mono">{pct(p.worst_fall_bps)}</td>
                  <td className="num mono">{p.calls_right_bps === null ? "n/a" : pct(p.calls_right_bps, false)}</td><td className="num mono">{p.badges}</td>
                  <td className="small">{p.proved ? <span className="tag-bad">{p.proved} proved</span> : <span className="tag-good">✓ clean</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function FirmRecord({ playerId, onLoggedOut }: { playerId: string; onLoggedOut: () => void }) {
  const loaded = useLoad(() => api.firmRecord(playerId), `record-${playerId}`, onLoggedOut);
  const [message, setMessage] = useState("");
  const [state, setState] = useState<{ busy: boolean; error: string | null; done: string | null }>({ busy: false, error: null, done: null });
  async function invite() {
    setState({ busy: true, error: null, done: null });
    try { await api.firmInvite(playerId, message); setState({ busy: false, error: null, done: "Invitation sent." }); setMessage(""); loaded.reload(); }
    catch (p) { setState({ busy: false, error: problemWords(p), done: null }); }
  }
  return (
    <>
      <p><a href="#/firms">← Back to the board</a></p>
      {loaded.loading && <Loading what="the record" />}
      {loaded.error && <Panel><p className="error" role="alert">{loaded.error}</p></Panel>}
      {loaded.data && (
        <>
          <RecordView view={loaded.data} />
          <Panel title="Invite to talk">
            {loaded.data.invitations.map((i) => (
              <p key={i.id} className="small">Sent {when(i.sent_at)}: {i.status === "accepted" ? <>accepted · <span className="strong">{i.contact}</span></> : i.status}</p>
            ))}
            <label className="answer small">A short message (10 to 800 characters)
              <textarea rows={4} maxLength={800} value={message} onChange={(e) => setMessage(e.target.value)} /></label>
            {state.error && <p className="error" role="alert">{state.error}</p>}
            {state.done && <p className="notice" role="status">{state.done}</p>}
            <button className="button-primary" disabled={state.busy || message.trim().length < 10} onClick={invite}>Send the invitation</button>
            <p className="muted small">The player's contact details reach you only if they accept and type them in.</p>
          </Panel>
        </>
      )}
    </>
  );
}

function Sent({ onLoggedOut }: { onLoggedOut: () => void }) {
  const loaded = useLoad(api.firmInvitations, "firm-invitations", onLoggedOut);
  return (
    <Panel title="Invitations sent">
      {loaded.data && loaded.data.invitations.length === 0 && <p className="muted small">None yet.</p>}
      {loaded.data?.invitations.map((i: FirmInvitation) => (
        <div key={i.id} className="fact-row small">
          <span><span className="strong">{i.name}</span> <span className="muted">· {when(i.sent_at)}</span></span>
          <span>{i.status === "accepted" ? <>Accepted · <span className="strong">{i.contact}</span></> : i.status === "sent" ? "Waiting for an answer" : "Declined"}</span>
        </div>
      ))}
    </Panel>
  );
}

const toLagos = (local: string) => (local ? `${local}:00+01:00` : "");

function FirmChallengesDesk({ firm, onLoggedOut }: { firm: Firm; onLoggedOut: () => void }) {
  const loaded = useLoad(api.firmChallenges, "firm-challenges", onLoggedOut);
  const [data, setData] = useState<FirmChallenges | null>(null);
  useEffect(() => { if (loaded.data) setData(loaded.data); }, [loaded.data]);
  const [form, setForm] = useState({ kind: "paper", title: "", brief: "", ticker: "", starting_cash_naira: "5000000000", opens_at: "", locks_at: "", ends_at: "", top_shown: "10" });
  const [state, setState] = useState<{ busy: boolean; error: string | null; done: string | null }>({ busy: false, error: null, done: null });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  async function create(e: FormEvent) {
    e.preventDefault();
    setState({ busy: true, error: null, done: null });
    try {
      setData(await api.firmNewChallenge({
        kind: form.kind, title: form.title, brief: form.brief, ...(form.ticker ? { ticker: form.ticker } : {}),
        starting_cash_naira: Math.round(Number(form.starting_cash_naira)), opens_at: toLagos(form.opens_at), ends_at: toLagos(form.ends_at),
        ...(form.locks_at ? { locks_at: toLagos(form.locks_at) } : {}), top_shown: Math.round(Number(form.top_shown)),
      }));
      setState({ busy: false, error: null, done: "Your challenge is set. Players see it in Proven Talent." });
    } catch (p) { setState({ busy: false, error: problemWords(p), done: null }); }
  }
  async function cancel(id: number) {
    try { setData(await api.firmCancelChallenge(id)); } catch (p) { setState({ busy: false, error: problemWords(p), done: null }); }
  }
  const needsCompany = form.kind === "valuation" || form.kind === "forecast";
  return (
    <>
      <Panel title="Set a challenge" aside={`as ${firm.name}`}>
        <form onSubmit={create} className="stack-form">
          <label className="answer">Kind <select value={form.kind} onChange={set("kind")}>
            {Object.entries(data?.kinds ?? { paper: "Paper portfolio" }).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          {data && <p className="small muted">{data.kind_words[form.kind]}</p>}
          <label className="answer">Title <input required minLength={4} maxLength={90} value={form.title} onChange={set("title")} /></label>
          <label className="answer">Brief <textarea rows={3} maxLength={1200} value={form.brief} onChange={set("brief")} /></label>
          {needsCompany && <label className="answer">Company (three letters) <input required maxLength={3} value={form.ticker} onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })} /></label>}
          {form.kind === "paper" && <label className="answer">Paper cash for each entrant, ₦ <input type="number" min={1000000} max={100000000000} value={form.starting_cash_naira} onChange={set("starting_cash_naira")} /></label>}
          <label className="answer">Starts (Lagos time) <input type="datetime-local" required value={form.opens_at} onChange={set("opens_at")} /></label>
          {form.kind !== "live" && <label className="answer">Closes to new entrants and answers (optional) <input type="datetime-local" value={form.locks_at} onChange={set("locks_at")} /></label>}
          <label className="answer">Ends <input type="datetime-local" required value={form.ends_at} onChange={set("ends_at")} /></label>
          <label className="answer">How many of the best finishers you may see <input type="number" min={1} max={50} value={form.top_shown} onChange={set("top_shown")} /></label>
          {state.error && <p className="error" role="alert">{state.error}</p>}
          {state.done && <p className="notice" role="status">{state.done}</p>}
          <button className="button-primary" disabled={state.busy}>Set the challenge</button>
          <p className="muted small">Nothing a player wins is money, and your firm gets no advantage of any kind in the game. You see the best finishers who agreed to be seen.</p>
        </form>
      </Panel>
      {data?.challenges.map((c) => (
        <Panel key={c.id} title={c.title} aside={`${c.kind_name} · ${PHASE[c.phase]} · ${c.entrants} entrant${c.entrants === 1 ? "" : "s"}`}>
          <p className="small muted">Starts {when(c.opens_at)} · answers close {when(c.locks_at)} · ends {when(c.ends_at)}{c.company ? ` · ${c.company.name}` : ""}</p>
          {(c.phase === "waiting" || (c.entrants === 0 && c.phase !== "scored" && c.phase !== "cancelled")) && <button className="button-quiet" onClick={() => cancel(c.id)}>Call it off</button>}
          {(c.finishers ?? []).length > 0 && (
            <>
              <h3 className="small strong">Best finishers who agreed to be seen</h3>
              <ul className="plain-list small">
                {c.finishers!.map((f) => (
                  <li key={f.player_id}><span className="mono">{f.place}.</span> <a href={`#/firms/record/${f.player_id}`}>{f.name}</a> <span className="muted">· {f.score_words}{f.badges.length ? ` · ${f.badges.join(", ")}` : ""}</span>
                    {f.answer_text && <div className="muted">“{f.answer_text}”</div>}</li>
                ))}
              </ul>
            </>
          )}
          {c.scoreboard.length > 0 && <p className="small muted">Places: {c.scoreboard.slice(0, 10).map((s) => `${s.place}. ${s.name}`).join(" · ")}</p>}
        </Panel>
      ))}
    </>
  );
}
