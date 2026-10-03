// The shared parts: built once, used on every build's screen (design document, section 18).
//   NumberTile        one figure with its change
//   ProgressTracker   numbered steps showing where a task stands
//   ObjectivesPanel   the work in hand, with milestones and deadlines
//   LevelPanel        level and experience
//   PayPanel          what the employer pays and what is taken from it
//   SkillTree         the learning modules of the build and how far the player has got
//   Wheel             the allocation wheel

import type { ReactNode } from "react";
import type { Career, Coverage, Kobo, Objective, ObjectiveBoard, Skill, Slice } from "./api";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { Change, Panel } from "./Shell";

export function NumberTile({ label, value, change, note }: { label: string; value: ReactNode; change?: number | null; note?: ReactNode }) {
  return (
    <div className="tile">
      <div className="muted small">{label}</div>
      <div className="figure-small mono">{value}</div>
      {change !== undefined && <div className="small"><Change bps={change} /></div>}
      {note && <div className="muted small">{note}</div>}
    </div>
  );
}

export type Step = { label: string; done: boolean; note?: string };

/** Numbered steps. The first step not yet done is the current one. */
export function ProgressTracker({ steps }: { steps: Step[] }) {
  const current = steps.findIndex((step) => !step.done);
  return (
    <ol className="tracker">
      {steps.map((step, index) => (
        <li key={step.label} className={step.done ? "tracker-step done" : index === current ? "tracker-step current" : "tracker-step"}
            aria-current={index === current ? "step" : undefined}>
          <span className="tracker-mark" aria-hidden="true">{step.done ? "✓" : index + 1}</span>
          <span>
            <span className="strong">{step.label}</span>
            {step.note && <span className="muted small"> · {step.note}</span>}
            <span className="sr-only">{step.done ? " (done)" : index === current ? " (do this next)" : " (not yet)"}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

export const STATE_WORDS: Record<Objective["state"], string> = {
  active: "In hand", passed: "Passed", failed: "Not passed", not_done: "Not done", withdrawn: "Given up",
};

export function StateTag({ state }: { state: Objective["state"] }) {
  const mark = state === "passed" ? "✓" : state === "active" ? "●" : "✕";
  return <span className={`tag tag-${state}`}>{mark} {STATE_WORDS[state]}</span>;
}

/** Where a piece of market work stands, in a few plain words, from what the server has recorded. */
export function progressWords(objective: Objective): string | null {
  const p = objective.progress as Record<string, any>;
  if (objective.kind === "hand_in") {
    return objective.submission ? "Handed in. The result comes when the quarter ends." : "Waiting for you to hand it in.";
  }
  if (objective.template === "am_value") {
    return p.pick ? `You named ${p.pick.ticker}. Hold it until the first Closing Bell after the results.` : "Name your share once you own it.";
  }
  if (objective.template === "am_rates") {
    if (!objective.submission) return "Hand in your call, then position your bonds.";
    return p.book_value ? `Your bonds at the last bell: ${formatNaira(String(p.book_value))}.` : "Call handed in. Your bonds are looked at at the last Closing Bell.";
  }
  if (objective.template === "am_beat") {
    return p.start ? `Measurement running: ${p.start.bells} of 7 Closing Bells.` : "The measurement starts at the next Closing Bell.";
  }
  if (objective.template === "am_idle") return `Held at ${p.bells ?? 0} Closing Bell${p.bells === 1 ? "" : "s"} so far.`;
  if (p.bells !== undefined) return `${p.run ?? 0} Closing Bell${p.run === 1 ? "" : "s"} in a row so far (${p.bells} seen).`;
  return "Looked at when the next Closing Bell rings.";
}

/** The work in hand, each with its deadline and who is paying. Used on every build's screen. */
export function ObjectivesPanel({ board, compact = false }: { board: ObjectiveBoard; compact?: boolean }) {
  return (
    <Panel title="Your objectives" aside={<a href="#/work">{board.active.length} of {board.limit} in hand · open</a>}>
      {board.active.length === 0 && (
        <p className="muted small">
          {board.ready ? "Nothing in hand. Take a piece of work on from the list of work on offer." : board.why}
        </p>
      )}
      {board.active.map((objective) => (
        <div key={objective.id} className="definition">
          <div className="row">
            <a href="#/work" className="strong">{objective.title}</a>
            <span className="mono">{formatNaira(objective.reward_kobo)}</span>
          </div>
          <div className="muted small">{objective.module} · paid by {objective.payer}</div>
          <div className="small">{progressWords(objective)}</div>
          {!compact && <div className="muted small">Deadline: {objective.terms.deadline}</div>}
        </div>
      ))}
    </Panel>
  );
}

export function LevelPanel({ career }: { career: NonNullable<Career["career"]> }) {
  const span = (career.next_level_at ?? career.experience) - career.level_floor;
  const done = career.experience - career.level_floor;
  const share = career.at_cap || span <= 0 ? 100 : Math.min(100, Math.round((done / span) * 100));
  return (
    <Panel title="Level" aside={career.track}>
      <div className="headline">
        <span className="figure mono">{career.level}</span>
        <span className="muted">{career.rank_name} {career.build_name} · {career.level_words}</span>
      </div>
      <div className="meter" role="img" aria-label={`${share}% of the way to the next level`}>
        <div className="meter-fill" style={{ width: `${share}%` }} />
      </div>
      <p className="muted small">
        {career.level >= career.top_level
          ? "Level 100: the top of the game."
          : career.at_cap
          ? <>Level {career.gate} is a gate. To go past it you need mastery across your modules and then a <a href="#/rank">rank case</a>. Experience you earn meanwhile is kept ({career.experience.toLocaleString("en-NG")} so far).</>
          : `${career.experience.toLocaleString("en-NG")} experience. Level ${career.level + 1} at ${career.next_level_at?.toLocaleString("en-NG")}. Experience comes only from work you pass.`}
      </p>
      {career.review && (
        <div className="warning" role="status">
          <div className="strong">Performance review open</div>
          <div className="small">{career.review.why} {career.review.how_to_recover}</div>
          <div className="small">So far: {career.review.passes} passed of {career.review.finished} finished.</div>
        </div>
      )}
    </Panel>
  );
}

export function PayPanel({ career }: { career: Career }) {
  const pay = career.pay;
  if (!pay) return null;
  const taken = [
    ["Income tax, to the Government", pay.tax_kobo],
    [`Living costs, to the households of ${career.job?.headquarters ?? "your city"}`, pay.living_costs_kobo],
    ["Your saving for retirement", pay.pension_yours_kobo],
  ] as [string, Kobo][];
  const payDay = career.next_pay_day ? new Date(career.next_pay_day) : null;
  return (
    <Panel title="Pay" aside={career.job ? `Paid by ${career.job.name}` : "No employer yet"}>
      <div className="row"><span>Salary for a quarter, before anything is taken</span><span className="mono">{formatNaira(pay.gross_kobo)}</span></div>
      {taken.map(([label, amount]) => (
        <div key={label} className="row"><span className="muted">{label}</span><span className="mono muted">− {formatNaira(amount)}</span></div>
      ))}
      <div className="row row-current"><span>Take-home pay</span><span className="mono">{formatNaira(pay.take_home_kobo)}</span></div>
      <div className="row"><span className="muted">Your employer also pays into your retirement savings</span><span className="mono muted">{formatNaira(pay.pension_employer_kobo)}</span></div>
      <p className="small">
        {!career.job ? "You are paid once you have an employer."
          : pay.worked_this_quarter ? "✓ You have finished work this quarter, so you will be paid on pay day."
          : "● No work finished yet this quarter. An employer pays a quarter's salary only to staff who finished at least one real piece of work in it: passed, or honestly attempted."}
      </p>
      {payDay && career.job && (
        <p className="muted small">
          Pay day is when the quarter ends: {payDay.toLocaleString("en-NG", { timeZone: "Africa/Lagos", weekday: "long", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} Lagos time.
          At the next level the salary is {formatNaira(pay.at_next_level_kobo)}.
        </p>
      )}
      {career.job && BigInt(career.job.owed_kobo) > 0n && (
        <p className="warning small">{career.job.name} still owes you {formatNaira(career.job.owed_kobo)} of salary. It is paid when the company has the cash.</p>
      )}
    </Panel>
  );
}

const STAGES: { key: "learned" | "practised" | "proven"; label: string; how: string }[] = [
  { key: "learned", label: "Learned", how: "passed on your own" },
  { key: "practised", label: "Practised", how: "passed with your empire" },
  { key: "proven", label: "Proven", how: "passed in a weekend challenge" },
];

/** The syllabus map: every learning module of a track, and which of its three stages are reached.
 *  With it, the coverage tracker: how much of the map has been worked through. */
export function SkillTree({ skills, tracks }: { skills: Skill[]; tracks: Coverage[] }) {
  return (
    <>
      {tracks.map((track) => (
        <Panel key={track.track} title={`${track.name}: syllabus map`} aside={`${track.mastered} of ${track.modules} modules proven`}>
          <div className="coverage" role="group" aria-label={`How much of the ${track.name} map you have worked through`}>
            {STAGES.map((stage) => (
              <div key={stage.key} className="coverage-line">
                <span className="small">{stage.label}</span>
                <div className="meter" role="img" aria-label={`${track[`${stage.key}_pct`]}% of modules ${stage.label.toLowerCase()}`}>
                  <div className={`meter-fill meter-${stage.key}`} style={{ width: `${track[`${stage.key}_pct`]}%` }} />
                </div>
                <span className="mono small">{track[`${stage.key}_pct`]}%</span>
              </div>
            ))}
          </div>
          <p className="muted small">Each module has three stages: learned (alone), practised (with your empire), proven (in a weekend challenge).</p>
          {skills.filter((skill) => skill.track === track.track).map((skill) => (
            <div key={skill.module} className="definition">
              <div className="row">
                <span className="strong">{skill.open ? "" : "🔒 "}{skill.module}</span>
                <span className="stage-pips" role="img" aria-label={STAGES.map((stage) => `${stage.label}: ${skill[stage.key] ? "yes" : "not yet"}`).join(", ")}>
                  {STAGES.map((stage, index) => (
                    <span key={stage.key} className={skill[stage.key] ? `pip pip-done pip-${stage.key}` : "pip"} title={`${stage.label}: ${stage.how}`}>
                      {skill[stage.key] ? "✓" : index + 1}
                    </span>
                  ))}
                </span>
              </div>
              <div className="muted small">{skill.idea}</div>
              <div className="small">
                {!skill.open ? <span className="muted">Opens at Level {skill.level}.</span>
                  : skill.proven && skill.practised && skill.learned ? <span className="change-up">▲ Proven.</span>
                  : <span className="muted">Next: {!skill.learned ? "pass it on your own" : !skill.practised ? "pass it with your empire" : "pass it in a weekend challenge"}.</span>}
              </div>
              {skill.practise_again && <div className="small change-down">▼ Last attempt was not passed. It is on offer again: practise it.</div>}
            </div>
          ))}
        </Panel>
      ))}
    </>
  );
}

// One colour for each kind of holding, always the same one. Checked for colour-blind separation
// and for contrast against the panel colour. Every slice is also named and given its figure in
// the list beside the wheel, so nothing depends on colour alone.
const WHEEL_COLORS: Record<string, string> = {
  "Shares": "#9085e9", "Government bonds": "#199e70", "Government bills": "#c98500", "Company bonds": "#d55181", "Cash": "#3987e5",
  "Government bonds and bills": "#199e70",
};

/** The allocation wheel: how what the player owns is divided. */
export function Wheel({ slices, total }: { slices: Slice[]; total: Kobo }) {
  const R = 54, r = 34, C = 64, GAP = 0.03;
  let angle = -Math.PI / 2;
  const arcs = slices.map((slice) => {
    const sweep = (slice.share_bps / 10000) * Math.PI * 2;
    const from = angle + (slices.length > 1 ? GAP / 2 : 0), to = angle + sweep - (slices.length > 1 ? GAP / 2 : 0);
    angle += sweep;
    const full = slices.length === 1;
    const point = (radius: number, at: number) => `${(C + radius * Math.cos(at)).toFixed(2)} ${(C + radius * Math.sin(at)).toFixed(2)}`;
    const large = to - from > Math.PI ? 1 : 0;
    const path = full
      ? `M ${C} ${C - R} A ${R} ${R} 0 1 1 ${C - 0.01} ${C - R} L ${C - 0.01} ${C - r} A ${r} ${r} 0 1 0 ${C} ${C - r} Z`
      : `M ${point(R, from)} A ${R} ${R} 0 ${large} 1 ${point(R, to)} L ${point(r, to)} A ${r} ${r} 0 ${large} 0 ${point(r, from)} Z`;
    return { slice, path, visible: to > from };
  });
  return (
    <div className="wheel">
      <svg viewBox="0 0 128 128" role="img" aria-label="How what you own is divided">
        {arcs.filter((arc) => arc.visible).map(({ slice, path }) => (
          <path key={slice.label} d={path} fill={WHEEL_COLORS[slice.label] ?? "#9085e9"}>
            <title>{`${slice.label}: ${formatNaira(slice.value_kobo)} (${formatPercent(slice.share_bps)})`}</title>
          </path>
        ))}
        <text x={C} y={C - 3} textAnchor="middle" className="wheel-total">{formatCompact(total)}</text>
        <text x={C} y={C + 11} textAnchor="middle" className="wheel-caption">in all</text>
      </svg>
      <div className="wheel-list">
        {slices.map((slice) => (
          <div key={slice.label} className="row">
            <span><span className="swatch" style={{ background: WHEEL_COLORS[slice.label] ?? "#9085e9" }} />{slice.label}</span>
            <span className="mono">{formatPercent(slice.share_bps)} <span className="muted">· {formatCompact(slice.value_kobo)}</span></span>
          </div>
        ))}
        {slices.length === 0 && <p className="muted small">You own nothing yet.</p>}
      </div>
    </div>
  );
}
