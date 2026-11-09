// Rank cases and the CEO rank (design document, sections 6 and 9).
// A career stops at Levels 20, 40, 60 and 80 until that level's rank case is passed. The website
// only shows and asks: the server makes the case from the live world, marks it and moves the rank.

import { useState } from "react";
import { api, ApiError, type Player, type RankCase, type RankTrack, type Ranks } from "./api";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { ProgressTracker, StateTag } from "./Parts";
import { Failed, Loading, Panel } from "./Shell";
import { AnswerField, answersFrom, inMillions, ReportMarking } from "./Work";

const moment = (iso: string) => new Date(iso).toLocaleString("en-NG", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function Requirements({ track }: { track: RankTrack }) {
  const steps = [
    ...(track.track === "ceo" ? [] : [{ label: `Reach Level ${track.gate}`, done: track.at_gate, note: `you are at Level ${track.level}` }]),
    ...track.needs.map((need) => ({
      label: `${need.need} modules ${need.words}`, done: need.met,
      note: need.met ? `${need.have} done` : `${need.have} done · still to do: ${need.missing.slice(0, 3).join(", ")}${need.missing.length > 3 ? "…" : ""}`,
    })),
    { label: "Pass the rank case", done: track.ceo?.case_passed ?? false, note: `${track.pass_mark} marks in the hundred` },
    ...(track.ceo ? [
      { label: `Reach Level ${track.ceo.level.need} in your build`, done: track.ceo.level.met, note: `you are at Level ${track.ceo.level.have}` },
      { label: `Hold a reputation of ${track.ceo.reputation.need}`, done: track.ceo.reputation.met, note: `yours is ${track.ceo.reputation.have}` },
    ] : []),
  ];
  return <ProgressTracker steps={steps} />;
}

function TrackPanel({ track, busy, onBegin, hours, retryDays }: { track: RankTrack; busy: boolean; onBegin: () => void; hours: number; retryDays: number }) {
  const [sure, setSure] = useState(false);
  const ceo = track.track === "ceo";
  if (track.gate === null) {
    return <Panel title={`${track.name}: every rank case passed`} aside={track.rank_name}><p className="saved">✓ {track.why_not}</p></Panel>;
  }
  return (
    <Panel title={ceo ? "The CEO rank" : `${track.name}: ${track.title}`} aside={ceo ? (track.ceo?.earned ? "★ Earned" : "Leadership track") : `Now: ${track.rank_name}`}>
      <p className="small">
        {ceo
          ? "An empire is led by an Acting Head, with capped powers, until its head has earned the CEO rank. Any member who holds it can also be voted in as head by the empire. It needs three things: Level 60 in your own build, the CEO rank case, and a reputation of 75."
          : `Work alone carries a career to Level ${track.gate}. Going past it takes mastery across your build's modules and then one large piece of practical work: a rank case. Experience you earn while you wait at the gate is kept, and counts the moment you pass.`}
      </p>
      <Requirements track={track} />
      {!track.ceo?.case_passed && (
        <>
          <div className="why-title">The case</div>
          <p className="small">{track.what}. It has {track.parts.length} parts ({track.parts.join(", ").toLowerCase()}), all made from the world as it stands at the moment you begin, so no two cases are alike.</p>
          <div className="row"><span className="muted">Fee, paid when you begin</span><span className="mono">{track.fee_kobo ? formatNaira(track.fee_kobo) : "—"}</span></div>
          <div className="row"><span className="muted">To pass</span><span>{track.pass_mark} marks in the hundred, across the result and the working</span></div>
          <div className="row"><span className="muted">Time allowed</span><span>{hours} real hours, and never past the end of the quarter</span></div>
          <p className="muted small">The fee is paid into the prize pool: it leaves your pocket and the economy, and is not returned. A case that is not passed can be sat again after {retryDays} real days, on a fresh case.</p>
          {track.can_begin ? (
            <div className="step-actions">
              {sure
                ? <span className="small">The fee of {formatNaira(track.fee_kobo!)} is taken now. <button className="button-primary" disabled={busy} onClick={onBegin}>Yes, begin the case</button> <button className="button-quiet" onClick={() => setSure(false)}>Not yet</button></span>
                : <button className="button-primary" disabled={busy} onClick={() => setSure(true)}>Begin the rank case</button>}
            </div>
          ) : <p className="small muted">○ {track.why_not}</p>}
        </>
      )}
      {track.ceo?.earned && <p className="saved">✓ You hold the CEO rank{track.ceo.since ? `, since ${moment(track.ceo.since)}` : ""}.</p>}
    </Panel>
  );
}

function CaseInHand({ rankCase, busy, onHandIn, onError }: {
  rankCase: RankCase; busy: boolean; onHandIn: (answers: Record<string, Record<string, unknown>>) => void; onError: (message: string) => void;
}) {
  const [typed, setTyped] = useState<Record<string, Record<string, any>>>({});
  const [sure, setSure] = useState(false);
  function handIn() {
    const out: Record<string, Record<string, unknown>> = {};
    for (const part of rankCase.parts) {
      const answers = answersFrom(part.terms.fields, typed[part.template] ?? {});
      if (typeof answers === "string") { setSure(false); return onError(`${part.title}: ${answers}`); }
      out[part.template] = answers;
    }
    onHandIn(out);
  }
  return (
    <Panel title={`Rank case in hand: ${rankCase.title}`} aside={`Hand in by ${moment(rankCase.due_at)}`} className="objective">
      <p className="small">
        {rankCase.company ? <>The case is about <a href={`#/companies/${rankCase.company.ticker}`}>{rankCase.company.name} ({rankCase.company.ticker})</a>. </> : null}
        Every part is handed in together, once. {rankCase.pass_mark} marks in the hundred pass it; every figure in every part carries marks.
      </p>
      {rankCase.parts.map((part, index) => (
        <div key={part.template} className="case-part">
          <h3>Part {index + 1} of {rankCase.parts.length}: {part.title} <span className="muted small">· {part.module}</span></h3>
          <p>{part.terms.situation}</p>
          <ul className="reasons">{part.terms.task.map((line) => <li key={line}>{line}</li>)}</ul>
          {part.terms.given.length > 0 && (
            <>
              <div className="why-title">From the records</div>
              {part.terms.given.map((line) => (
                <div key={line.label} className="row"><span>{line.label}</span><span className="mono">{line.kobo !== undefined ? `${inMillions(line.kobo)} m` : line.text}</span></div>
              ))}
            </>
          )}
          <div className="why-title">Your work</div>
          <div className="answers">
            {part.terms.fields.map((field) => (
              <AnswerField key={field.key} field={field} value={typed[part.template]?.[field.key]}
                           onChange={(value) => setTyped((was) => ({ ...was, [part.template]: { ...was[part.template], [field.key]: value } }))} />
            ))}
          </div>
        </div>
      ))}
      <div className="step-actions">
        {sure
          ? <span className="small">It can be handed in once. <button className="button-primary" disabled={busy} onClick={handIn}>Yes, hand the whole case in</button> <button className="button-quiet" onClick={() => setSure(false)}>Check it again</button></span>
          : <button className="button-primary" disabled={busy} onClick={() => setSure(true)}>Hand the case in</button>}
        <span className="muted small">Figures in the records are in millions of naira.</span>
      </div>
    </Panel>
  );
}

function PastCase({ rankCase }: { rankCase: RankCase }) {
  const [open, setOpen] = useState(false);
  const result = rankCase.result;
  return (
    <div className="definition">
      <button className="row row-button" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span><StateTag state={rankCase.state} /> <span className="strong">{rankCase.track_name}, Level {rankCase.gate}</span> <span className="muted small">{rankCase.judged_at ? moment(rankCase.judged_at) : ""}</span></span>
        <span className="mono">{result ? `${result.score} of 100` : "—"}</span>
      </button>
      {open && result && (
        <div className="debrief">
          <p className="strong">{result.summary}</p>
          {result.held_back && <p className="muted small">○ {result.held_back}</p>}
          {result.parts.map((part) => (
            <div key={part.template} className="case-part">
              <h3>{part.title} <span className="muted small">· {part.module} · {part.score} of 100</span></h3>
              <p className="small">{part.summary}</p>
              <ProgressTracker steps={part.milestones.map((m) => ({ label: m.label, done: m.earned, note: `${m.points} points` }))} />
              {part.debrief.plain && <><div className="why-title">In plain words</div><p>{part.debrief.plain}</p></>}
              {part.debrief.method && <><div className="why-title">The professional method</div><p>{part.debrief.method}</p></>}
              {part.debrief.maths && <><div className="why-title">The arithmetic</div><p className="mono small">{part.debrief.maths}</p></>}
            </div>
          ))}
          <ReportMarking what={{ case_id: rankCase.id }} />
        </div>
      )}
    </div>
  );
}

export function RankWork({ player, onLoggedOut, onChanged }: { player: Player; onLoggedOut: () => void; onChanged: () => void }) {
  const loaded = useLoad(api.ranks, `ranks:${player.id}`, onLoggedOut);
  const [fresh, setFresh] = useState<Ranks | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const data = fresh ?? loaded.data;
  if (loaded.loading && !data) return <Loading what="your rank" />;
  if (!data) return <Failed message={loaded.error ?? "Could not load your rank."} onRetry={loaded.reload} />;

  async function run(action: () => Promise<Ranks>) {
    setBusy(true); setError(null);
    try { setFresh(await action()); onChanged(); }
    catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
    } finally { setBusy(false); }
  }

  return (
    <>
      <div className="work-head">
        <h1>Rank</h1>
        <span className="muted small">Levels 20, 40, 60 and 80 are gates. Each opens with a rank case.</span>
      </div>
      {!player.build && <Panel title="Choose a build first"><p>A rank belongs to a build. <a href="#/career">Choose yours on the Career page</a>.</p></Panel>}
      {error && <p className="error" role="alert">{error}</p>}
      {data.active && <CaseInHand rankCase={data.active} busy={busy} onError={setError} onHandIn={(answers) => run(() => api.handInCase(data.active!.id, answers))} />}
      {data.tracks.map((track) => <TrackPanel key={track.track} track={track} busy={busy} hours={data.hours} retryDays={data.retry_days} onBegin={() => run(() => api.beginCase(track.track))} />)}
      {data.past.length > 0 && (
        <Panel title="Past cases" aside="Open one to see why">
          {data.past.map((past) => <PastCase key={past.id} rankCase={past} />)}
        </Panel>
      )}
    </>
  );
}

export function RankRail({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const loaded = useLoad(api.ranks, `ranks-rail:${player.id}:${player.level}`, onLoggedOut);
  const own = loaded.data?.tracks[0];
  return (
    <>
      <Panel title="The road to Level 100">
        <ol className="road">
          {[["Associate", "Levels 1 to 20"], ["Professional", "Levels 21 to 40"], ["Senior", "Levels 41 to 60"], ["Principal", "Levels 61 to 80"], ["Master", "Levels 81 to 100"]].map(([name, levels], index) => (
            <li key={name} className={own && own.rank === index ? "road-step current" : own && own.rank > index ? "road-step done" : "road-step"}
                aria-current={own && own.rank === index ? "step" : undefined}>
              <span className="tracker-mark" aria-hidden="true">{own && own.rank > index ? "✓" : index + 1}</span>
              <span><span className="strong">{name}</span> <span className="muted small">· {levels}{index < 4 ? ` · rank case at Level ${(index + 1) * 20}` : ""}</span></span>
            </li>
          ))}
        </ol>
        <p className="muted small">Retirement opens at Level 50. Work done after each rank case teaches more: experience is doubled after the first, trebled after the second, and so on.</p>
      </Panel>
      <Panel title="The three stages of a module">
        <ul className="reasons">
          <li><span className="strong">Learned:</span> you passed its work on your own.</li>
          <li><span className="strong">Practised:</span> you passed its work with your empire.</li>
          <li><span className="strong">Proven:</span> you passed it in a weekend challenge (Friday 18:00 to Sunday 22:00, Lagos time). When live events are built, they will count here too.</li>
        </ul>
        <p className="small"><a href="#/work">Go to your work</a> to see every module and its stage.</p>
      </Panel>
    </>
  );
}
