// Professional objectives: the work on offer, the work in hand and the work finished.
// The website only shows and asks. The server sets the terms, judges and pays.

import { useState } from "react";
import { api, ApiError, type Kobo, type Objective, type ObjectiveBoard, type ObjectiveField, type ObjectiveOffer, type Player, type Setting, type Skill } from "./api";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { appendFigure, Calculator } from "./Calculator";
import { ProgressTracker, SkillTree, STATE_WORDS, progressWords } from "./Parts";
import { Failed, Loading, Panel } from "./Shell";

/** A company figure in millions of naira, to two places: what the work is done from. */
export function inMillions(kobo: Kobo): string {
  return (Number(BigInt(kobo)) / 1e8).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const UNIT: Record<string, string> = { millions: "₦ million", percent: "%", times: "times", ticker: "", naira: "₦", number: "" };

export function AnswerField({ field, value, onChange }: { field: ObjectiveField; value: any; onChange: (value: any) => void }) {
  if (field.kind === "choice") {
    return (
      <fieldset className="choice">
        <legend className="field-label">{field.label}</legend>
        {field.options.map((option) => (
          <label key={option.code} className={value === option.code ? "choice-option chosen" : "choice-option"}>
            <input type="radio" name={field.key} checked={value === option.code} onChange={() => onChange(option.code)} /> {option.label}
          </label>
        ))}
      </fieldset>
    );
  }
  if (field.kind === "classify") {
    const chosen: Record<string, string> = value ?? {};
    return (
      <div className="scroll" tabIndex={0}>
        <table>
          <caption className="field-label">{field.label}</caption>
          <thead><tr><th scope="col">Movement</th><th scope="col" className="num">₦ million</th><th scope="col">Heading</th></tr></thead>
          <tbody>
            {field.items.map((item) => (
              <tr key={item.key}>
                <th scope="row">{item.label}</th>
                <td className="num mono">{inMillions(item.kobo)}</td>
                <td>
                  <select aria-label={`Heading for: ${item.label}`} value={chosen[item.key] ?? ""}
                          onChange={(event) => onChange({ ...chosen, [item.key]: event.target.value })}>
                    <option value="">Choose…</option>
                    {field.options.map((option) => <option key={option.code} value={option.code}>{option.label}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <label className="answer">
      <span className="field-label">{field.label}</span>
      <span className="answer-box">
        <input type="text" inputMode={field.kind === "ticker" ? "text" : "decimal"} value={value ?? ""} maxLength={field.kind === "ticker" ? 3 : 18}
               onChange={(event) => onChange(field.kind === "ticker" ? event.target.value.toUpperCase() : event.target.value)} />
        <span className="muted small">{UNIT[field.kind]}</span>
      </span>
    </label>
  );
}

export function answersFrom(fields: ObjectiveField[], typed: Record<string, any>): Record<string, unknown> | string {
  const out: Record<string, unknown> = {};
  for (const field of fields) {
    const value = typed[field.key];
    if (field.kind === "classify") {
      if (!value || field.items.some((item) => !value[item.key])) return "Put every movement under a heading first.";
      out[field.key] = value;
    } else if (field.kind === "choice" || field.kind === "ticker") {
      if (!value) return field.kind === "choice" ? "Choose an answer first." : "Type the share's three-letter code.";
      out[field.key] = value;
    } else {
      const number = Number(String(value ?? "").replace(/,/g, "").trim());
      if (String(value ?? "").trim() === "" || !Number.isFinite(number)) return `Give a number for "${field.label}".`;
      out[field.key] = number;
    }
  }
  return out;
}

/** A player who believes the marking is wrong can say so, once. It is kept for the people who run the game. */
export function ReportMarking({ what }: { what: { objective_id?: number; case_id?: number } }) {
  const [open, setOpen] = useState(false);
  const [words, setWords] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (said) return <p className="small muted">{said}</p>;
  if (!open) return <button className="button-quiet" onClick={() => setOpen(true)}>I believe this marking is wrong</button>;
  return (
    <form className="stack-form" onSubmit={async (event) => {
      event.preventDefault();
      setBusy(true);
      try { setSaid((await api.reportMarking(what, words)).words); }
      catch (problem) { setSaid(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again."); }
      finally { setBusy(false); }
    }}>
      <label className="answer"><span className="field-label">What do you believe is wrong, and what should it be?</span>
        <textarea rows={3} maxLength={600} value={words} onChange={(event) => setWords(event.target.value)} /></label>
      <div className="step-actions">
        <button className="button-outline" disabled={busy || words.trim().length < 10}>Send the report</button>
        <span className="muted small">Every model answer is checked twice before it is used. A report is read by the people who run the game; nothing changes at once.</span>
      </div>
    </form>
  );
}

const SETTING_MARK: Record<Setting, string> = { solo: "①", empire: "②", live: "③" };

function Debrief({ objective }: { objective: Objective }) {
  const result = objective.result;
  if (!result) return null;
  const paid = BigInt(objective.paid_kobo);
  return (
    <div className="debrief">
      <p className="strong">{result.summary}</p>
      {result.milestones.length > 0 && (
        <ProgressTracker steps={result.milestones.map((m) => ({ label: m.label, done: m.earned, note: `${m.points} points` }))} />
      )}
      {objective.state === "passed" && (
        <p className="saved">
          ✓ Paid {formatNaira(objective.paid_kobo)} by {objective.payer}, and {objective.experience} experience.
          {result.payment_note ? ` ${result.payment_note}` : ""}
        </p>
      )}
      {objective.state !== "passed" && paid === 0n && (
        <p className="muted small">Nothing was paid. A piece of work not passed costs the reward and nothing else.</p>
      )}
      {result.debrief.plain && <><div className="why-title">In plain words</div><p>{result.debrief.plain}</p></>}
      {result.debrief.method && <><div className="why-title">The professional method</div><p>{result.debrief.method}</p></>}
      {result.debrief.maths && <><div className="why-title">The arithmetic</div><p className="mono small">{result.debrief.maths}</p></>}
      <p className="muted small">Module: {objective.module} · {objective.setting_name.toLowerCase()}.</p>
      <ReportMarking what={{ objective_id: objective.id }} />
    </div>
  );
}

const SETTING_WORDS: Record<Setting, string> = {
  solo: "Work you do alone, for a client or your employer. Passing it makes the module learned.",
  empire: "The same skill, done for your empire and paid by it. Passing it makes the module practised, and adds to the empire's league points.",
  live: "The weekend challenge: the same skill against the clock, open to everybody at once, from Friday 18:00 to Sunday 22:00 (Lagos). It pays and teaches one and a half times as much. Passing it makes the module proven.",
};

const SETTING_SHORT: Record<Setting, string> = { solo: "alone", empire: "for your empire", live: "weekend challenge" };
const UNIT_WORDS: Record<string, string> = { millions: "₦ million", percent: "%", times: "times (×)", naira: "₦", number: "", ticker: "" };

/** Three stars for a module: ★ passed alone, ★★ with your empire, ★★★ in a weekend challenge. */
export function Stars({ skill }: { skill?: Skill }) {
  const n = skill ? [skill.learned, skill.practised, skill.proven].filter(Boolean).length : 0;
  return <span className="stars" aria-label={`${n} of 3 stars in this module`}>{"★".repeat(n)}<span className="stars-empty">{"☆".repeat(3 - n)}</span></span>;
}

/** The long rules, kept behind a "?" so the page stays short. */
function Rules({ data }: { data: ObjectiveBoard }) {
  return (
    <Panel title="How work works">
      <ul className="reasons">
        <li>Each piece of work is practical work from one learning module. The server judges it against the game’s own records, and the named payer pays out of its own cash.</li>
        <li>Each module comes in three settings: <strong>{SETTING_MARK.solo} alone</strong> (passing makes it learned, ★), <strong>{SETTING_MARK.empire} for your empire</strong> (practised, ★★), and <strong>{SETTING_MARK.live} the weekend challenge</strong> (proven, ★★★). One setting of each module a quarter.</li>
        <li>You can hold {data.limit} pieces at once. The terms are fixed the moment you start.</li>
        <li>Work you prepare can be handed in once. Work in the market is judged on what you actually hold when the Closing Bell rings.</li>
        <li>A piece not passed costs its reward and nothing else. Five not passed in any ten opens a performance review.</li>
        <li>Afterwards you see the worked answer: plain words first, then the professional method, then the arithmetic.</li>
        <li>{SETTING_WORDS.live}</li>
      </ul>
    </Panel>
  );
}

function StatusTag({ kind, children }: { kind: "ready" | "progress" | "done" | "failed" | "locked"; children: React.ReactNode }) {
  const mark = { ready: "●", progress: "◐", done: "✓", failed: "✕", locked: "○" }[kind];
  return <span className={`status status-${kind}`}>{mark} {children}</span>;
}

function OfferCard({ offer, skill, canTake, onTake, busy }: { offer: ObjectiveOffer; skill?: Skill; canTake: boolean; onTake: () => void; busy: boolean }) {
  const [how, setHow] = useState(false);
  return (
    <article className="work-card">
      <div className="work-card-top">
        <StatusTag kind="ready">Ready · {SETTING_SHORT[offer.setting]}</StatusTag>
        <span className="mono strong">{formatNaira(offer.reward_kobo)}</span>
      </div>
      <h3>{offer.title}</h3>
      <div className="muted small">{offer.module} · {offer.experience} experience · <Stars skill={skill} /></div>
      {offer.practise_again && <div className="small change-down">▼ Your last attempt at this module was not passed. Practise it again.</div>}
      {how && (
        <div className="how-card" role="region" aria-label="How to do this">
          <p className="small">{offer.idea}</p>
          {offer.how && <p className="small"><strong>The method:</strong> {offer.how}</p>}
          {offer.pass_when && <p className="small muted">Passed when: {offer.pass_when}</p>}
          <p className="small muted">This is the method, not the answer. The worked answer comes after you hand in.</p>
        </div>
      )}
      <div className="work-card-actions">
        <button className="button-primary" disabled={!canTake || busy} onClick={onTake}>Start</button>
        <button className="button-quiet" aria-expanded={how} onClick={() => setHow(!how)}>How to do this</button>
      </div>
      {!canTake && <p className="muted small">You hold the most pieces at once. Finish one first.</p>}
    </article>
  );
}

export function WorkWork({ player, onLoggedOut, onChanged }: { player: Player; onLoggedOut: () => void; onChanged: () => void }) {
  const board = useLoad(api.objectives, "objectives", onLoggedOut);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [rules, setRules] = useState(false);
  const [setting, setSetting] = useState<Setting | "all">("all");
  const [track, setTrack] = useState<string>("");
  if (board.loading && !board.data) return <Loading what="your work" />;
  if (board.error || !board.data) return <Failed message={board.error ?? "Could not load your work."} onRetry={board.reload} />;
  const data = board.data;
  const changed = () => { setError(null); board.reload(); onChanged(); };
  const myTrack = track || data.tracks[0]?.track || "";
  const skillOf = new Map(data.skills.map((sk) => [`${sk.track}|${sk.module}`, sk]));
  const offers = data.offers.filter((o) => o.track === myTrack);
  const ready = offers.filter((o) => o.available && (setting === "all" || o.setting === setting));
  const later = offers.filter((o) => !o.available && o.setting === "solo");
  const weekend = data.weekend;
  const day = (iso: string) => new Date(iso).toLocaleString("en-NG", { weekday: "long", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos" });

  async function take(template: string) {
    setBusy(true); setError(null);
    try {
      const started = await api.takeWork(template);
      changed();
      if ("waiting" in started) { setNotice(started.words); return; }
      if (started.kind === "hand_in") window.location.hash = `#/work/${started.id}`;
    }
    catch (problem) { setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again."); }
    finally { setBusy(false); }
  }

  return (
    <>
      <div className="work-head">
        <h1>Work</h1>
        <span className="button-row">
          <span className="muted small">{data.active.length} of {data.limit} in hand</span>
          <button className="button-quiet" aria-expanded={rules} onClick={() => setRules(!rules)}>? How work works</button>
        </span>
      </div>
      {rules && <Rules data={data} />}
      {!player.build && (
        <Panel title="Choose a build first">
          <p>Work is given to a professional. <a href="#/career">Choose your build, your bank and your employer</a> and the work on offer appears here.</p>
        </Panel>
      )}
      {player.build && !data.ready && <Panel><p>{data.why} <a href="#/career">Go to your career</a>.</p></Panel>}
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="saved" role="status">{notice}</p>}

      {data.active.length > 0 && (
        <section aria-labelledby="in-progress">
          <h2 id="in-progress" className="lbl" style={{ marginBottom: 8 }}>In progress</h2>
          <div className="work-list">
            {data.active.map((o) => (
              <article key={o.id} className="work-card work-card-active">
                <div className="work-card-top">
                  <StatusTag kind="progress">In progress · due {o.terms.deadline}</StatusTag>
                  <span className="mono strong">{formatNaira(o.reward_kobo)}</span>
                </div>
                <h3>{o.title}</h3>
                <div className="muted small">{o.module} · {SETTING_SHORT[o.setting]} · {progressWords(o)}</div>
                <div className="work-card-actions"><a className="button-primary" href={`#/work/${o.id}`}>{o.kind === "hand_in" ? "Continue" : "Open"}</a></div>
              </article>
            ))}
          </div>
        </section>
      )}

      {data.offers.length > 0 && (
        <section aria-labelledby="ready-now">
          <div className="work-head" style={{ marginBottom: 8 }}>
            <h2 id="ready-now" className="lbl">Ready to start</h2>
            <span className="muted small">Only work you can start now</span>
          </div>
          {data.tracks.length > 1 && (
            <div className="filter-row" role="group" aria-label="Which syllabus map">
              {data.tracks.map((t) => <button key={t.track} className="filter-chip" aria-pressed={myTrack === t.track} onClick={() => setTrack(t.track)}>{t.name}</button>)}
            </div>
          )}
          <div className="filter-row" role="group" aria-label="Setting">
            <button className="filter-chip" aria-pressed={setting === "all"} onClick={() => setSetting("all")}>All</button>
            {(["solo", "empire", "live"] as Setting[]).map((code) => (
              <button key={code} className="filter-chip" aria-pressed={setting === code} onClick={() => setSetting(code)}>
                {SETTING_MARK[code]} {SETTING_SHORT[code]}{code === "live" ? (weekend.open ? " · ● open" : " · closed") : ""}
              </button>
            ))}
          </div>
          {setting === "live" && !weekend.open && <p className="muted small">○ The next weekend challenge opens on {day(weekend.opens)} (Lagos time).</p>}
          {setting === "empire" && data.in_empire && <p className="muted small">{data.empire_work.done} of {data.empire_work.most} pieces of empire work used this quarter.</p>}
          {ready.length === 0 ? <p className="muted small">Nothing in this setting can be started right now. {later.length > 0 ? "See what is coming up below." : ""}</p> : (
            <div className="work-list">
              {ready.map((offer) => (
                <OfferCard key={offer.template} offer={offer} skill={skillOf.get(`${offer.track}|${offer.module}`)} canTake={data.active.length < data.limit} busy={busy} onTake={() => take(offer.template)} />
              ))}
            </div>
          )}
        </section>
      )}

      {data.finished.length > 0 && (
        <Panel title="Done" aside="Open one to see the worked answer">
          {data.finished.map((objective) => (
            <div key={objective.id} className="definition">
              <button className="row row-button" onClick={() => setOpen(open === objective.id ? null : objective.id)} aria-expanded={open === objective.id}>
                <span>
                  {objective.state === "passed" ? <StatusTag kind="done">Done</StatusTag> : <StatusTag kind="failed">{STATE_WORDS[objective.state]}</StatusTag>}{" "}
                  <span className="strong">{objective.title}</span> <span className="muted small">{objective.module} · {SETTING_SHORT[objective.setting]}</span>
                </span>
                <span className="mono">{objective.result ? `${objective.result.score}/100 · ` : ""}{objective.state === "passed" ? `+ ${formatNaira(objective.paid_kobo)}` : "—"}</span>
              </button>
              {open === objective.id && <Debrief objective={objective} />}
            </div>
          ))}
        </Panel>
      )}

      {later.length > 0 && (
        <details className="panel">
          <summary className="strong" style={{ cursor: "pointer" }}>Coming up: {later.length} more {later.length === 1 ? "piece" : "pieces"} of work open as you grow <span className="muted">(show)</span></summary>
          <ul className="reasons" style={{ marginTop: 10 }}>
            {later.map((o) => <li key={o.template}><strong>{o.title}</strong> · {o.why_not}</li>)}
          </ul>
        </details>
      )}
    </>
  );
}

/** A unit check that never gives the answer away: it only says when a figure looks like it is in the wrong unit. */
export function unitWarning(field: ObjectiveField, typed: string, given: { kobo?: Kobo }[]): string | null {
  const v = Number(String(typed).replace(/,/g, "").trim());
  if (!typed || !Number.isFinite(v) || v === 0) return null;
  if (field.kind === "percent" && Math.abs(v) < 1 && String(typed).includes(".")) {
    return `▲ This answer is in percent. ${typed} means less than one percent. If you worked out a fraction, multiply it by 100.`;
  }
  if (field.kind === "millions") {
    const biggest = Math.max(0, ...given.filter((g) => g.kobo !== undefined).map((g) => Math.abs(Number(BigInt(g.kobo!)) / 1e8)));
    if (biggest > 0 && Math.abs(v) > biggest * 1000) return "▲ Figures here are in millions of naira. Your answer looks like it is in naira: divide by 1,000,000.";
  }
  if (field.kind === "times" && Math.abs(v) >= 100) return "▲ This answer is a number of times, such as 2.5. Did you write a percentage?";
  return null;
}

function objective_can_tour(board: ObjectiveBoard, id: number): boolean {
  const o = board.active.find((x) => x.id === id);
  return !!o && o.can_hand_in && o.terms.fields.length > 0;
}

const TOUR = [
  { at: "figures", text: "These are the company’s own figures, in millions of naira. Tap one and it goes into the calculator, so you never retype a number." },
  { at: "question", text: "One question at a time. The unit is beside the box. If an answer looks like the wrong unit, you are warned, but never told the answer." },
  { at: "calculator", text: "The calculator does the arithmetic. When the sum is right, put it straight into your answer." },
  { at: "hand-in", text: "Check your answers, then hand them in. It can be handed in once. Afterwards you see the worked answer." },
];

/** One piece of work, one question at a time, with the figures beside it and a calculator. */
export function WorkFocus({ id, player, onLoggedOut, onChanged, onPlayer }: {
  id: number; player: Player; onLoggedOut: () => void; onChanged: () => void; onPlayer: (player: Player) => void;
}) {
  const board = useLoad(api.objectives, "objectives", onLoggedOut);
  const [typed, setTyped] = useState<Record<string, any>>({});
  const [step, setStep] = useState(0);
  const [sum, setSum] = useState("");
  const [busy, setBusy] = useState(false);
  const [sure, setSure] = useState(false);
  const [giveUp, setGiveUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tour, setTour] = useState<number | null>(player.tour_done ? null : 0);
  const [howOpen, setHowOpen] = useState(!player.tour_done);
  const [rules, setRules] = useState(false);
  if (board.loading && !board.data) return <Loading what="your work" />;
  if (board.error || !board.data) return <Failed message={board.error ?? "Could not load your work."} onRetry={board.reload} />;
  const objective = board.data.active.find((o) => o.id === id) ?? board.data.finished.find((o) => o.id === id);
  if (!objective) return <Panel><p>This piece of work is not yours, or it has gone. <a href="#/work">Back to Work</a>.</p></Panel>;
  const terms = objective.terms;
  const fields = terms.fields;
  const field = fields[Math.min(step, Math.max(0, fields.length - 1))];
  const last = step >= fields.length - 1;
  const finishTour = () => { setTour(null); api.setSettings({ tour_done: true }).then(onPlayer).catch(() => undefined); };
  const at = tour !== null && objective_can_tour(board.data, id) ? TOUR[tour].at : null;

  async function handIn() {
    const answers = answersFrom(fields, typed);
    if (typeof answers === "string") { setError(answers); return; }
    setBusy(true); setError(null);
    try { await api.handIn(objective!.id, answers); board.reload(); onChanged(); setSure(false); }
    catch (problem) { setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again."); }
    finally { setBusy(false); }
  }

  if (objective.state !== "active") {
    return (
      <>
        <a href="#/work" className="small">← Back to Work</a>
        <Panel title={objective.title}><Debrief objective={objective} /></Panel>
      </>
    );
  }

  const unitOf = field && "kind" in field ? UNIT_WORDS[field.kind] ?? "" : "";
  const warning = field && field.kind !== "choice" && field.kind !== "classify" ? unitWarning(field, typed[field.key] ?? "", terms.given) : null;

  return (
    <div className="focus">
      <div className="focus-bar">
        <a href="#/work" className="button-quiet">← Back to Work</a>
        <div className="focus-title">
          <div className="strong">{objective.title}</div>
          <div className="muted small">{objective.module} · {formatNaira(objective.reward_kobo)} from {objective.payer} · due {terms.deadline}</div>
        </div>
        {fields.length > 0 && (
          <ol className="focus-dots" aria-label={`Question ${step + 1} of ${fields.length}`}>
            {fields.map((f, i) => (
              <li key={f.key}><button className={i === step ? "dot now" : typed[f.key] !== undefined && typed[f.key] !== "" ? "dot done" : "dot"}
                        aria-label={`Question ${i + 1}${i === step ? ", now" : typed[f.key] ? ", answered" : ""}`} onClick={() => setStep(i)} /></li>
            ))}
          </ol>
        )}
        <button className="button-quiet" aria-expanded={rules} onClick={() => setRules(!rules)}>? Rules</button>
      </div>
      {rules && <Rules data={board.data} />}
      {terms.hand_in_by && <p className="small change-down">▼ Hand in by {new Date(terms.hand_in_by).toLocaleString("en-NG", { weekday: "short", hour: "2-digit", minute: "2-digit" })}. A late paper does not pass.</p>}

      <div className="focus-grid">
        <section className={at === "figures" ? "panel tour-on" : "panel"} aria-labelledby="focus-figures">
          <div className="panel-head">
            <h2 id="focus-figures">{terms.client ? <a href={`#/companies/${terms.client.ticker}`}>{terms.client.name}</a> : "From the records"}</h2>
            <span className="muted small">₦ millions · tap a figure to use it</span>
          </div>
          {terms.given.length === 0 && <p className="muted small">This work is done in the market, not from figures.</p>}
          {terms.given.map((line) => line.kobo !== undefined ? (
            <button key={line.label} type="button" className="figure-button" onClick={() => setSum(appendFigure(sum, inMillions(line.kobo!).replace(/,/g, "")))}
                    aria-label={`${line.label}: ${inMillions(line.kobo)} million naira. Tap to use in the calculator.`}>
              <span>{line.label}</span><span className="mono">{inMillions(line.kobo)}</span>
            </button>
          ) : (
            <div key={line.label} className="row"><span>{line.label}</span><span>{line.text}</span></div>
          ))}
          <details className="why" style={{ marginTop: 12 }}>
            <summary>The situation and what to do</summary>
            <p className="small">{terms.situation}</p>
            <ul className="reasons">{terms.task.map((t) => <li key={t}>{t}</li>)}</ul>
            {terms.notes && <ul className="reasons">{terms.notes.map((t) => <li key={t}>{t}</li>)}</ul>}
            <p className="small muted">Passed when: {terms.pass_when}</p>
          </details>
        </section>

        <div className="focus-side">
          {objective.can_hand_in && field ? (
            <section className={at === "question" || at === "hand-in" ? "panel focus-question tour-on" : "panel focus-question"} aria-labelledby="focus-q">
              <div className="lbl">Question {step + 1} of {fields.length}</div>
              <h1 id="focus-q" className="focus-q">{field.label}</h1>
              <details className="how-card" open={howOpen} onToggle={(e) => setHowOpen((e.currentTarget as HTMLDetailsElement).open)}>
                <summary>How to do this</summary>
                <p className="small">{objective.idea}</p>
                {objective.how && <p className="small"><strong>The method:</strong> {objective.how}</p>}
                <p className="small muted">This is the method, not the answer. The worked answer comes after you hand in.</p>
              </details>
              {field.kind === "choice" || field.kind === "classify" ? (
                <AnswerField field={field} value={typed[field.key]} onChange={(v) => setTyped((was) => ({ ...was, [field.key]: v }))} />
              ) : (
                <div>
                  <label htmlFor={`answer-${field.key}`} className="field-label">Your answer</label>
                  <div className="unit-input">
                    {field.kind === "naira" && <span className="unit unit-before" aria-hidden="true">₦</span>}
                    <input id={`answer-${field.key}`} type="text" inputMode={field.kind === "ticker" ? "text" : "decimal"}
                           maxLength={field.kind === "ticker" ? 3 : 18} value={typed[field.key] ?? ""} aria-describedby={warning ? `warn-${field.key}` : undefined}
                           className={warning ? "warned" : undefined}
                           onChange={(e) => setTyped((was) => ({ ...was, [field.key]: field.kind === "ticker" ? e.target.value.toUpperCase() : e.target.value }))} />
                    {unitOf && field.kind !== "naira" && <span className="unit">{unitOf}</span>}
                  </div>
                  {warning && <p id={`warn-${field.key}`} role="status" className="unit-warning">{warning}</p>}
                </div>
              )}
              {error && <p className="error" role="alert">{error}</p>}
              <div className="step-actions">
                <span className="button-row">
                  {step > 0 && <button className="button-quiet" onClick={() => setStep(step - 1)}>← Back</button>}
                  {!last && <button className="button-primary" onClick={() => setStep(step + 1)}>Next question →</button>}
                  {last && !sure && <button className="button-primary" onClick={() => setSure(true)}>Hand it in</button>}
                </span>
              </div>
              {last && sure && (
                <div className="confirm">
                  <p className="small">Check your answers first: it can be handed in once.</p>
                  <ul className="reasons small">{fields.map((f) => <li key={f.key}>{f.label}: <span className="mono">{typeof typed[f.key] === "object" ? "chosen" : typed[f.key] || "— not answered"}</span></li>)}</ul>
                  <span className="button-row">
                    <button className="button-primary" disabled={busy} onClick={handIn}>{busy ? "Handing in…" : "Yes, hand it in"}</button>
                    <button className="button-quiet" onClick={() => setSure(false)}>Not yet</button>
                  </span>
                </div>
              )}
            </section>
          ) : (
            <Panel title="Where it stands">
              <p>{progressWords(objective)}</p>
              <p className="small muted">{terms.pass_when}</p>
              {objective.kind === "market" && <p className="small">This work is done by trading. <a href="#/market">Open the market</a>.</p>}
            </Panel>
          )}

          {fields.length > 0 && objective.can_hand_in && (
            <section className={at === "calculator" ? "panel tour-on" : "panel"} aria-labelledby="focus-calc">
              <h2 id="focus-calc" style={{ marginBottom: 10 }}>Calculator</h2>
              <Calculator text={sum} setText={setSum}
                          onUse={field && field.kind !== "choice" && field.kind !== "classify" && field.kind !== "ticker"
                            ? (v) => setTyped((was) => ({ ...was, [field.key]: String(Math.round(v * 100) / 100) }))
                            : undefined}
                          percent={field?.kind === "percent"} />
            </section>
          )}

          <div className="step-actions">
            {giveUp
              ? <span className="small">Giving it up counts as work not passed. <button className="button-quiet" disabled={busy} onClick={() => { setBusy(true); api.giveUp(objective.id).then(() => { board.reload(); onChanged(); window.location.hash = "#/work"; }).catch((p) => setError(p instanceof ApiError ? p.message : "Could not reach the server.")).finally(() => setBusy(false)); }}>Yes, give it up</button> <button className="button-quiet" onClick={() => setGiveUp(false)}>Keep it</button></span>
              : <button className="button-quiet" onClick={() => setGiveUp(true)}>Give this work up</button>}
          </div>
        </div>
      </div>

      {tour !== null && objective.can_hand_in && fields.length > 0 && (
        <div className="tour" role="region" aria-label={`First-time walkthrough, step ${tour + 1} of ${TOUR.length}`} aria-live="polite">
          <div className="lbl">First time · step {tour + 1} of {TOUR.length}</div>
          <p>{TOUR[tour].text}</p>
          <div className="button-row" style={{ justifyContent: "space-between" }}>
            <button className="button-quiet" onClick={finishTour}>Skip the tour</button>
            {tour < TOUR.length - 1
              ? <button className="button-primary" onClick={() => setTour(tour + 1)}>Next →</button>
              : <button className="button-primary" onClick={finishTour}>Got it</button>}
          </div>
        </div>
      )}
    </div>
  );
}

export function WorkRail({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const board = useLoad(api.objectives, `objectives-rail:${player.cash.amount_kobo}:${player.level}`, onLoggedOut);
  const data = board.data;
  return (
    <>
      {data && data.tracks.map((track) => {
        const skills = data.skills.filter((sk) => sk.track === track.track);
        const missing = skills.reduce((n, sk) => n + [sk.learned, sk.practised, sk.proven].filter((x) => !x).length, 0);
        return (
          <Panel key={track.track} title={`Your modules: ${track.name}`}>
            <p className="muted small">★ passed alone · ★★ with your empire · ★★★ in a weekend challenge</p>
            {skills.map((sk) => (
              <div key={sk.module} className="row">
                <span>{sk.open ? "" : "○ "}{sk.module}{!sk.open && <span className="muted small"> · Level {sk.level}</span>}</span>
                <Stars skill={sk} />
              </div>
            ))}
            <p className="small" style={{ marginTop: 8 }}>{missing === 0 ? "◆ Every module at ★★★." : <>◆ All at ★★★ opens your next rank case: <strong>{missing} {missing === 1 ? "star" : "stars"} to go.</strong></>}</p>
          </Panel>
        );
      })}
      {data && data.skills.length > 0 && (
        <details className="panel">
          <summary className="strong" style={{ cursor: "pointer" }}>The full syllabus map</summary>
          <div style={{ marginTop: 10 }}><SkillTree skills={data.skills} tracks={data.tracks} /></div>
        </details>
      )}
    </>
  );
}
