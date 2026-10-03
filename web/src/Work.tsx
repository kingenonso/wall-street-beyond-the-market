// Professional objectives: the work on offer, the work in hand and the work finished.
// The website only shows and asks. The server sets the terms, judges and pays.

import { useState } from "react";
import { api, ApiError, type Kobo, type Objective, type ObjectiveBoard, type ObjectiveField, type ObjectiveOffer, type Player, type Setting } from "./api";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { ProgressTracker, SkillTree, StateTag, progressWords } from "./Parts";
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
      <div className="scroll">
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
      {result.debrief.plain && <><div className="why-title">IN PLAIN WORDS</div><p>{result.debrief.plain}</p></>}
      {result.debrief.method && <><div className="why-title">THE PROFESSIONAL METHOD</div><p>{result.debrief.method}</p></>}
      {result.debrief.maths && <><div className="why-title">THE ARITHMETIC</div><p className="mono small">{result.debrief.maths}</p></>}
      <p className="muted small">Module: {objective.module} · {objective.setting_name.toLowerCase()}.</p>
      <ReportMarking what={{ objective_id: objective.id }} />
    </div>
  );
}

function ActiveCard({ objective, onChanged, onError }: { objective: Objective; onChanged: (finished?: number) => void; onError: (message: string) => void }) {
  const [typed, setTyped] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [sure, setSure] = useState(false);
  const terms = objective.terms;

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    try { await action(); onChanged(objective.id); }
    catch (problem) { onError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again."); }
    finally { setBusy(false); }
  }
  function handIn() {
    const answers = answersFrom(terms.fields, typed);
    if (typeof answers === "string") return onError(answers);
    void act(() => api.handIn(objective.id, answers));
  }

  return (
    <Panel title={objective.title} aside={<>{objective.module} · {formatNaira(objective.reward_kobo)} from {objective.payer}</>} className="objective">
      <div className="small"><span className={`tag tag-setting-${objective.setting}`}>{SETTING_MARK[objective.setting]} {objective.setting_name}</span>{terms.setting_note ? <span className="muted"> {terms.setting_note}</span> : null}</div>
      {terms.hand_in_by && <p className="small change-down">▼ Hand in by {new Date(terms.hand_in_by).toLocaleString("en-NG", { weekday: "short", hour: "2-digit", minute: "2-digit" })}. A late paper does not pass.</p>}
      <p>{terms.situation}</p>
      <div className="why-title">WHAT TO DO</div>
      <ul className="reasons">{terms.task.map((line) => <li key={line}>{line}</li>)}</ul>
      {terms.notes && terms.notes.length > 0 && <ul className="reasons">{terms.notes.map((line) => <li key={line}>{line}</li>)}</ul>}
      {terms.given.length > 0 && (
        <>
          <div className="why-title">FROM THE RECORDS{terms.client ? <> · <a href={`#/companies/${terms.client.ticker}`}>{terms.client.name}</a></> : null}</div>
          {terms.given.map((line) => (
            <div key={line.label} className="row">
              <span>{line.label}</span>
              <span className="mono">{line.kobo !== undefined ? `${inMillions(line.kobo)} m` : line.text}</span>
            </div>
          ))}
          {terms.given.some((line) => line.kobo !== undefined) && <p className="muted small">Figures are in millions of naira.</p>}
        </>
      )}
      <div className="row"><span className="muted">Passed when</span><span className="align-right">{terms.pass_when}</span></div>
      <div className="row"><span className="muted">Deadline</span><span className="align-right">{terms.deadline}</span></div>
      <div className="row"><span className="muted">Where it stands</span><span className="align-right">{progressWords(objective)}</span></div>

      {objective.can_hand_in && terms.fields.length > 0 && (
        <form className="hand-in" onSubmit={(event) => { event.preventDefault(); handIn(); }}>
          <div className="why-title">YOUR WORK</div>
          <div className="answers">
            {terms.fields.map((field) => (
              <AnswerField key={field.key} field={field} value={typed[field.key]} onChange={(value) => setTyped((was) => ({ ...was, [field.key]: value }))} />
            ))}
          </div>
          <div className="step-actions">
            <button className="button-primary" disabled={busy}>Hand it in</button>
            <span className="muted small">It can be handed in once. Check it first.</span>
          </div>
        </form>
      )}
      <div className="step-actions">
        {sure
          ? <span className="small">Giving it up counts as work not passed. <button className="button-quiet" disabled={busy} onClick={() => act(() => api.giveUp(objective.id))}>Yes, give it up</button> <button className="button-quiet" onClick={() => setSure(false)}>Keep it</button></span>
          : <button className="button-quiet" onClick={() => setSure(true)}>Give this work up</button>}
      </div>
    </Panel>
  );
}

function OfferRow({ offer, canTake, onTake, busy }: { offer: ObjectiveOffer; canTake: boolean; onTake: () => void; busy: boolean }) {
  return (
    <div className="definition">
      <div className="row">
        <span className="strong">{offer.title} <span className="ticker">{offer.kind === "hand_in" ? "prepare and hand in" : "act in the market"}</span></span>
        <span className="mono">{formatNaira(offer.reward_kobo)} · {offer.experience} exp</span>
      </div>
      <div className="muted small">{offer.module} · {offer.idea}</div>
      {offer.available ? (
        <>
          <p className="small">{offer.situation}</p>
          <div className="small"><span className="muted">Passed when:</span> {offer.pass_when}</div>
          <div className="small"><span className="muted">Paid by:</span> {offer.payer}{offer.setting === "empire" ? " (your empire, out of its own cash)" : offer.client ? <> (the client, <a href={`#/companies/${offer.client.ticker}`}>{offer.client.ticker}</a>)</> : " (your employer, as performance pay)"}</div>
          {offer.practise_again && <div className="small change-down">▼ Your last attempt at this module was not passed. Practise it again.</div>}
          <div className="step-actions">
            <button className="button-outline" disabled={!canTake || busy} onClick={onTake}>Take this work on</button>
            {!canTake && <span className="muted small">You have three pieces of work in hand. Finish one first.</span>}
          </div>
        </>
      ) : <div className="small muted">○ {offer.why_not}</div>}
    </div>
  );
}

const SETTING_WORDS: Record<Setting, string> = {
  solo: "Work you do alone, for a client or your employer. Passing it makes the module learned.",
  empire: "The same skill, done for your empire and paid by it. Passing it makes the module practised, and adds to the empire's league points.",
  live: "The same skill against the clock, in a challenge open to everybody at once. It pays and teaches one and a half times as much. Passing it makes the module proven.",
};

function Offers({ data, busy, onTake }: { data: ObjectiveBoard; busy: boolean; onTake: (template: string) => void }) {
  const [setting, setSetting] = useState<Setting>("solo");
  const [track, setTrack] = useState(data.tracks[0]?.track ?? "");
  const offers = data.offers.filter((offer) => offer.setting === setting && offer.track === track);
  const weekend = data.weekend;
  const day = (iso: string) => new Date(iso).toLocaleString("en-NG", { weekday: "long", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos" });
  return (
    <Panel title="Work on offer" aside="Each piece can be taken once a quarter, in each setting">
      <p className="muted small">
        No question papers here. Each piece is practical work from one learning module, and each module's work comes in three
        settings. The server judges the result against the game's own records, and the named payer pays out of its own cash.
      </p>
      {data.tracks.length > 1 && (
        <div className="choice" role="group" aria-label="Which syllabus map">
          {data.tracks.map((t) => <button key={t.track} type="button" aria-pressed={track === t.track} onClick={() => setTrack(t.track)}>{t.name}</button>)}
        </div>
      )}
      <div className="choice" role="group" aria-label="Setting">
        {(["solo", "empire", "live"] as Setting[]).map((code) => (
          <button key={code} type="button" aria-pressed={setting === code} onClick={() => setSetting(code)}>
            {SETTING_MARK[code]} {data.settings[code]}{code === "live" ? (weekend.open ? " · ● open now" : " · closed") : ""}
          </button>
        ))}
      </div>
      <p className="small">{SETTING_WORDS[setting]}</p>
      {setting === "live" && (
        <p className={weekend.open ? "saved" : "muted small"}>
          {weekend.open ? `● The weekend challenge is open until ${day(weekend.closes)} (Lagos time). Each piece must be handed in within ${weekend.hours} hours of taking it on.`
            : `○ The next weekend challenge opens on ${day(weekend.opens)} and closes on ${day(weekend.closes)} (Lagos time).`}
        </p>
      )}
      {setting === "empire" && data.in_empire && <p className="muted small">{data.empire_work.done} of {data.empire_work.most} pieces of empire work used this quarter.</p>}
      {offers.map((offer) => (
        <OfferRow key={offer.template} offer={offer} canTake={data.active.length < data.limit} busy={busy} onTake={() => onTake(offer.template)} />
      ))}
    </Panel>
  );
}

export function WorkWork({ player, onLoggedOut, onChanged }: { player: Player; onLoggedOut: () => void; onChanged: () => void }) {
  const board = useLoad(api.objectives, "objectives", onLoggedOut);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  if (board.loading && !board.data) return <Loading what="your work" />;
  if (board.error || !board.data) return <Failed message={board.error ?? "Could not load your work."} onRetry={board.reload} />;
  const data = board.data;
  const changed = (finished?: number) => { setError(null); if (finished) setOpen(finished); board.reload(); onChanged(); };

  async function take(template: string) {
    setBusy(true); setError(null);
    try { await api.takeWork(template); changed(); }
    catch (problem) { setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again."); }
    finally { setBusy(false); }
  }

  return (
    <>
      <div className="work-head">
        <h1>Your work</h1>
        <span className="muted small">{data.active.length} of {data.limit} in hand · {data.coverage.learned} of {data.coverage.modules} modules learned · <a href="#/rank">Rank</a></span>
      </div>
      {!player.build && (
        <Panel title="Choose a build first">
          <p>Work is given to a professional. <a href="#/career">Choose your build, your bank and your employer</a> and the work on offer appears here.</p>
        </Panel>
      )}
      {player.build && !data.ready && <Panel><p>{data.why} <a href="#/career">Go to your career</a>.</p></Panel>}
      {error && <p className="error" role="alert">{error}</p>}

      {data.active.map((objective) => <ActiveCard key={objective.id} objective={objective} onChanged={changed} onError={setError} />)}

      {data.offers.length > 0 && <Offers data={data} busy={busy} onTake={take} />}

      {data.finished.length > 0 && (
        <Panel title="Finished work" aside="Open one to see why">
          {data.finished.map((objective) => (
            <div key={objective.id} className="definition">
              <button className="row row-button" onClick={() => setOpen(open === objective.id ? null : objective.id)} aria-expanded={open === objective.id}>
                <span><StateTag state={objective.state} /> <span className="strong">{objective.title}</span> <span className="muted small">{objective.module} · {SETTING_MARK[objective.setting]} {objective.setting_name.toLowerCase()}</span></span>
                <span className="mono">{objective.state === "passed" ? `+ ${formatNaira(objective.paid_kobo)}` : "—"}</span>
              </button>
              {open === objective.id && <Debrief objective={objective} />}
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}

export function WorkRail({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const board = useLoad(api.objectives, `objectives-rail:${player.cash.amount_kobo}:${player.level}`, onLoggedOut);
  return (
    <>
      {board.data && board.data.skills.length > 0 && (
        <SkillTree skills={board.data.skills} tracks={board.data.tracks} />
      )}
      <Panel title="How work is judged">
        <ul className="reasons">
          <li>The terms are fixed the moment you take a piece of work on.</li>
          <li>Each setting draws its own client and its own numbers, so the same answers never fit twice.</li>
          <li>Work you prepare can be handed in once. Work in the market is judged on what you actually hold when the Closing Bell rings.</li>
          <li>A piece of work not passed costs its reward and nothing else.</li>
          <li>Five not passed in any ten opens a performance review. You are told why and how to recover.</li>
          <li>Afterwards you are shown why: plain words first, then the professional method, then the arithmetic.</li>
        </ul>
      </Panel>
    </>
  );
}
