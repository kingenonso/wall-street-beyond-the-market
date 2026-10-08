// The empire as a working firm (private equity stage, part 1).
// Every build has a desk: duties that come round every quarter, marked from the empire's own figures.
// Requests go to the desk that must say yes, and never wait for ever. Members vote the big items and
// the empire's own rules. The Lawyer reads every paper before the head signs. The banker raises money,
// the Accountant closes the books, the Risk Manager sets limits, the Journalist briefs the head.
// The website only asks: the server knows the player's seat, and marks everything.

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, type Player } from "./api";
import { asKobo } from "./Empire";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { NumberTile } from "./Parts";
import { Failed, Loading, Panel } from "./Shell";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;
type Props = { player: Player; onLoggedOut: () => void; onChanged: () => void };
type Run = (method: "POST" | "PUT" | "DELETE", path: string, body?: unknown) => Promise<Any | null>;
type Act = { busy: boolean; error: string | null; notice: string | null; run: Run };

const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
const pct = (bps: number | null | undefined) => (bps === null || bps === undefined ? "—" : formatPercent(bps, 1));
const TABS = [
  ["desks", "Desks"], ["requests", "Requests and votes"], ["money", "Money"], ["people", "People"],
  ["work", "Work and events"], ["risk", "Risk"], ["board", "Board"],
] as const;
type Tab = (typeof TABS)[number][0];

async function call(method: string, path: string, body?: unknown): Promise<Any> {
  const response = await fetch(`/api${path}`, {
    method, credentials: "same-origin", headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d: Any) => d.msg).join(" ") : "Something went wrong.");
  }
  return data;
}

function useFirm(onLoggedOut: () => void, onChanged: () => void) {
  const [data, setData] = useState<Any>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const me = useRef(Math.random());
  async function load() {
    try { setData(await call("GET", "/firm")); setLoadError(null); } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) onLoggedOut();
      setLoadError(problem instanceof ApiError ? problem.message : "Could not reach the server.");
    }
  }
  useEffect(() => {
    load();
    const heard = (event: Event) => { if ((event as CustomEvent).detail !== me.current) load(); };
    window.addEventListener("firm-changed", heard);
    return () => window.removeEventListener("firm-changed", heard);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const run: Run = async (method, path, body) => {
    setBusy(true); setError(null); setNotice(null);
    try {
      const answer = await call(method, path, body);
      setData(answer); onChanged();
      window.dispatchEvent(new CustomEvent("firm-changed", { detail: me.current }));
      setNotice("Done.");
      return answer;
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
      return null;
    } finally { setBusy(false); }
  };
  return { data, loadError, reload: load, act: { busy, error, notice, run } as Act };
}

// ---------------------------------------------------------------------------
// Small parts
// ---------------------------------------------------------------------------

function Money({ kobo, compact = false }: { kobo: string | null | undefined; compact?: boolean }) {
  if (kobo === null || kobo === undefined) return <span className="muted">—</span>;
  return <span className="mono">{compact ? formatCompact(kobo) : formatNaira(kobo)}</span>;
}

function Arrow({ up }: { up: boolean | null }) {
  if (up === null) return null;
  return <span className={up ? "change-up" : "change-down"} aria-label={up ? "good" : "bad"}>{up ? "▲" : "▼"} </span>;
}

function Reason({ placeholder, button, busy, onSubmit, optional = false }: {
  placeholder: string; button: string; busy: boolean; onSubmit: (words: string) => void; optional?: boolean;
}) {
  const [words, setWords] = useState("");
  return (
    <form className="inline-form" onSubmit={(e: FormEvent) => { e.preventDefault(); onSubmit(words); setWords(""); }}>
      <input type="text" maxLength={400} placeholder={placeholder} value={words} onChange={(e) => setWords(e.target.value)} />
      <button className="button-outline" disabled={busy || (!optional && words.trim().length === 0)}>{button}</button>
    </form>
  );
}

function SeatPicker({ roster, value, onChange, build, label = "Member", exceptYou = false }: {
  roster: Any[]; value: string; onChange: (v: string) => void; build?: string; label?: string; exceptYou?: boolean;
}) {
  const choices = roster.filter((r) => (!build || r.build === build) && !(exceptYou && r.you));
  return (
    <label className="answer"><span className="field-label">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose…</option>
        {choices.map((r) => <option key={r.seat_id} value={r.seat_id}>{r.name} · {r.build_name}{r.is_head ? " (head)" : ""}</option>)}
      </select>
    </label>
  );
}

function Fact({ fact }: { fact: Any }) {
  const value = fact.kind === "money" ? <Money kobo={fact.value} /> : fact.kind === "percent" ? <span className="mono">{pct(Number(fact.value))}</span>
    : fact.kind === "number" ? <span className="mono">{Number(fact.value).toLocaleString("en-NG")}</span> : <span>{String(fact.value)}</span>;
  return <div className="row"><span className="small">{fact.label}</span>{value}</div>;
}

// ---------------------------------------------------------------------------
// A duty: open it, answer it, hand it in
// ---------------------------------------------------------------------------

function DutyForm({ duty, act }: { duty: Any; act: Act }) {
  const [answers, setAnswers] = useState<Record<string, Any>>({});
  const [result, setResult] = useState<Any>(null);
  const terms = duty.terms;
  if (!terms) return null;
  const set = (key: string, value: Any) => setAnswers({ ...answers, [key]: value });
  async function submit(event: FormEvent) {
    event.preventDefault();
    const out: Record<string, Any> = {};
    for (const ask of terms.asks) {
      const value = answers[ask.key];
      if (ask.kind === "money") { const k = asKobo(String(value ?? "")); out[ask.key] = k ?? (String(value ?? "").trim() === "0" ? 0 : null); }
      else if (ask.kind === "number") out[ask.key] = Number(String(value ?? "").replace(/,/g, ""));
      else if (ask.kind === "percent") out[ask.key] = Number(String(value ?? "").replace("%", ""));
      else out[ask.key] = value ?? (ask.kind === "pick" ? [] : "");
    }
    const done = await act.run("POST", `/firm/duties/${duty.id}/hand-in`, { answers: out });
    if (done) setResult(done.result);
  }
  return (
    <form className="duty-form" onSubmit={submit}>
      <p>{terms.brief}</p>
      {terms.given.length > 0 && <div className="facts">{terms.given.map((fact: Any, i: number) => <Fact key={i} fact={fact} />)}</div>}
      {terms.asks.map((ask: Any) => (
        <label key={ask.key} className="answer">
          <span className="field-label">{ask.label}</span>
          {ask.kind === "choice" ? (
            <select value={answers[ask.key] ?? ""} onChange={(e) => set(ask.key, e.target.value)}>
              <option value="">Choose…</option>
              {ask.choices.map((c: string) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : ask.kind === "pick" ? (
            <span className="picks">
              {ask.choices.map((c: string) => {
                const picked: string[] = answers[ask.key] ?? [];
                return (
                  <label key={c} className="pick">
                    <input type="checkbox" checked={picked.includes(c)}
                      onChange={(e) => set(ask.key, e.target.checked ? [...picked, c] : picked.filter((p) => p !== c))} /> {c}
                  </label>
                );
              })}
              {ask.count && <span className="muted small">Pick {ask.count}.</span>}
            </span>
          ) : ask.kind === "text" ? (
            <textarea maxLength={ask.most} rows={3} value={answers[ask.key] ?? ""} onChange={(e) => set(ask.key, e.target.value)} />
          ) : (
            <span className="answer-box">
              {ask.kind === "money" && <span className="muted small">₦</span>}
              <input type="text" inputMode="decimal" value={answers[ask.key] ?? ""} onChange={(e) => set(ask.key, e.target.value)} />
              {ask.kind === "percent" && <span className="muted small">%</span>}
            </span>
          )}
        </label>
      ))}
      <button className="button-primary" disabled={act.busy}>Hand in</button>
      {result && <DutyResult result={result} />}
    </form>
  );
}

function DutyResult({ result }: { result: Any }) {
  return (
    <div className="debrief">
      <p className="strong">Marked {result.score} out of 100 · {result.experience} experience</p>
      {(result.result?.lines ?? []).map((line: Any, i: number) => (
        <div key={i} className="row"><span><Arrow up={line.right} />{line.label}</span><span className="muted small">{line.right ? "right" : `right answer: ${line.answer}`}</span></div>
      ))}
      {result.result?.words && <p className="muted small">{result.result.words}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The tabs
// ---------------------------------------------------------------------------

function Desks({ f, act }: { f: Any; act: Act }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      <p className="muted small">Each desk's duties for {f.period_label ?? "this quarter"}. A duty nobody does is done by the staff where there are staff
        (scored {f.duties.staff_score}), or missed: a missed duty costs a league point. Well done means {f.duties.pass_mark} or more.</p>
      {f.duties.desks.map((desk: Any) => (
        <Panel key={desk.build} title={desk.name} aside={desk.yours ? "Your desk" : desk.staffed ? "Staff on the desk" : desk.empty ? "Nobody on the desk" : ""}
          className={desk.yours ? "panel-yours" : ""}>
          <div className="row"><span className="small muted">Lead</span><span className="small">{desk.lead ?? "—"}{desk.you_lead ? " (you)" : ""}</span></div>
          <div className="row"><span className="small muted">Members</span><span className="small">{desk.members.map((m: Any) => m.name).join(", ") || "—"}</span></div>
          {desk.duties.map((duty: Any) => (
            <div key={duty.id} className="duty">
              <div className="row">
                <span><span className={`tag tag-${duty.status}`}>{duty.status === "due" ? "To do" : duty.status === "done" ? "Done" : "Missed"}</span> {duty.title}</span>
                <span className="small muted">{duty.score !== null ? `${duty.score}/100` : ""} {duty.done_by ? `· ${duty.done_by}` : duty.given_to ? `· given to ${duty.given_to}` : ""}</span>
              </div>
              <p className="muted small">{duty.why}</p>
              {duty.yours && !duty.opened && (
                <button className="button-outline" disabled={act.busy} onClick={async () => { if (await act.run("POST", `/firm/duties/${duty.id}/open`)) setOpen(duty.id); }}>Open it</button>
              )}
              {duty.opened && (open === duty.id || duty.terms) && <DutyForm duty={duty} act={act} />}
              {duty.can_assign && desk.members.length > 1 && (
                <label className="answer"><span className="field-label">Give it to</span>
                  <select defaultValue="" onChange={(e) => act.run("PUT", `/firm/duties/${duty.id}/given-to`, { seat_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">Anybody on the desk</option>
                    {desk.members.map((m: Any) => <option key={m.seat_id} value={m.seat_id}>{m.name}</option>)}
                  </select>
                </label>
              )}
            </div>
          ))}
          {desk.scorecards.length > 0 && (
            <div className="scorecards">
              <span className="field-label">Scorecards</span>
              {desk.scorecards.map((card: Any) => (
                <div key={card.period} className="row small"><span>Quarter {card.period}</span>
                  <span className="mono">{card.score}/100 · {card.done} done, {card.by_staff} by staff, {card.missed} missed{card.budget !== "0" && card.budget ? ` · spent ${formatCompact(card.spent)} of ${formatCompact(card.budget)}` : ""}</span></div>
              ))}
            </div>
          )}
        </Panel>
      ))}
    </>
  );
}

function Requests({ f, act }: { f: Any; act: Act }) {
  const a = f.approvals;
  return (
    <>
      <Panel title="Waiting for you" aside={`A request passes to the head after ${a.hours} hours, to the deputy after two days, and lapses after three`}>
        {a.to_decide.length === 0 && <p className="muted">Nothing is waiting for your decision.</p>}
        {a.to_decide.map((r: Any) => (
          <div key={r.id} className="request">
            <div className="row"><span className="strong">{r.title}</span><span className="small muted">asked by {r.asked_by} · {when(r.asked_at)} · you decide as {r.you_decide_as}</span></div>
            <RequestDetail r={r} />
            <Reason placeholder={r.needs_reason ? "Your reason (kept on the record)" : "Your reason (needed to refuse)"} button="Approve" busy={act.busy} optional={!r.needs_reason}
              onSubmit={(reason) => act.run("PUT", `/firm/requests/${r.id}`, { approve: true, reason })} />
            <Reason placeholder="Why you refuse (kept on the record)" button="Refuse" busy={act.busy}
              onSubmit={(reason) => act.run("PUT", `/firm/requests/${r.id}`, { approve: false, reason })} />
          </div>
        ))}
      </Panel>
      {a.can_overrule.length > 0 && (
        <Panel title="Refusals you may overrule" aside="An overrule goes on your record for good">
          {a.can_overrule.map((r: Any) => (
            <div key={r.id} className="request">
              <div className="row"><span className="strong">{r.title}</span><span className="small muted">refused by the {r.desk_name}: “{r.reason}”</span></div>
              <Reason placeholder="Why you overrule them" button="Overrule" busy={act.busy} onSubmit={(reason) => act.run("POST", `/firm/requests/${r.id}/overrule`, { reason })} />
            </div>
          ))}
        </Panel>
      )}
      {a.asked.length > 0 && (
        <Panel title="What you asked for">
          {a.asked.map((r: Any) => <div key={r.id} className="row small"><span>{r.title}</span><span className={`tag tag-${r.status}`}>{r.status}{r.reason ? `: ${r.reason}` : ""}</span></div>)}
        </Panel>
      )}
      <Papers f={f} act={act} />
      <Votes f={f} act={act} />
    </>
  );
}

function RequestDetail({ r }: { r: Any }) {
  const d = r.detail ?? {};
  if (d.terms) {
    return (
      <div className="facts">
        <div className="row small"><span>Owned now</span><Money kobo={d.owned} compact /></div>
        <div className="row small"><span>Owed now, and after</span><span><Money kobo={d.owed_now} compact /> → <Money kobo={d.owed_after} compact /></span></div>
        {d.gearing_after_bps !== null && <div className="row small"><span>Owed as a share of owned, after</span><span className="mono">{pct(d.gearing_after_bps)} (the most is {pct(d.most_bps)})</span></div>}
        {d.interest_a_quarter !== "0" && <div className="row small"><span>Interest a quarter</span><Money kobo={d.interest_a_quarter} /></div>}
      </div>
    );
  }
  if (d.heading) {
    return (
      <div className="facts">
        <div className="row small"><span>It goes into the books as</span><span>{d.heading}: {d.description}</span></div>
        <div className="row small"><span>For the desk</span><span>{d.desk}{d.budget !== null ? ` · budget ${formatCompact(d.budget)}, spent ${formatCompact(d.spent)}` : " · no budget set"}</span></div>
      </div>
    );
  }
  if (d.why) return <ul className="small">{d.why.map((w: string) => <li key={w}>{w}</li>)}</ul>;
  return null;
}

function Papers({ f, act }: { f: Any; act: Act }) {
  const papers = f.papers.papers;
  if (papers.length === 0) return null;
  return (
    <Panel title="Papers" aside={f.papers.strike_cost}>
      {papers.map((p: Any) => <Paper key={p.id} p={p} act={act} />)}
    </Panel>
  );
}

function Paper({ p, act }: { p: Any; act: Act }) {
  const [struck, setStruck] = useState<string[]>([]);
  const read = p.status !== "draft";
  return (
    <div className="paper">
      <div className="row"><span className="strong">{p.title}</span><span className={`tag tag-${p.status}`}>{p.status}{p.by_staff ? " (read by the staff)" : ""}</span></div>
      <ol className="clauses">
        {p.clauses.map((c: Any) => (
          <li key={c.code} className={read && c.trap ? "clause-trap" : ""}>
            {p.yours_to_read && (
              <label><input type="checkbox" checked={struck.includes(c.code)} onChange={(e) => setStruck(e.target.checked ? [...struck, c.code] : struck.filter((s) => s !== c.code))} /> Strike out </label>)}
            {c.words}
            {read && <div className="small muted">{c.struck ? "Struck out. " : ""}{c.plain}</div>}
          </li>
        ))}
      </ol>
      {p.yours_to_read && <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/firm/papers/${p.id}`, { struck })}>Done reading</button>}
      {read && <p className="small">{p.kept_traps === 0 ? "▲ Every trap was struck out." : `▼ ${p.kept_traps} trap(s) left in, and in force.`} {p.wrongly_struck ? `▼ ${p.wrongly_struck} fair clause(s) struck out.` : ""}</p>}
    </div>
  );
}

const PROPOSALS: Record<string, { fields: [string, string, "money" | "bps" | "naira" | "choice" | "id", string[]?][] }> = {
  dividend: { fields: [["amount_kobo", "The payout", "money"]] },
  treasury: { fields: [["cash_least_bps", "Cash at least (%)", "bps"], ["shares_most_bps", "Shares at most (%)", "bps"]] },
  risk_appetite: { fields: [["worst_year_bps", "The most to lose in a bad year (%)", "bps"]] },
  constitution: { fields: [["big_votes", "Big votes carried by", "choice", ["majority", "two_thirds"]],
    ["member_signing_naira", "A member's signing limit (₦)", "naira"], ["leaver_units", "A leaving partner's units", "choice", ["keep", "buy_back"]]] },
  conduct: { fields: [["theft", "A proved theft", "choice", ["head_decides", "always_punish"]], ["missed_duty_fine_naira", "Fine for a missed duty (₦)", "naira"]] },
  pension_plan: { fields: [["fund_id", "The fund's number", "id"]] },
};

function Votes({ f, act }: { f: Any; act: Act }) {
  const r = f.resolutions;
  const [kind, setKind] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  async function propose(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, Any> = { kind };
    for (const [key, , type] of PROPOSALS[kind].fields) {
      const v = values[key];
      if (v === undefined || v === "") continue;
      body[key] = type === "money" ? asKobo(v) : type === "bps" ? Math.round(Number(v) * 100) : type === "choice" ? v : Number(v.replace(/,/g, ""));
    }
    if (await act.run("POST", "/firm/votes", body)) { setKind(""); setValues({}); }
  }
  return (
    <Panel title="Votes" aside={r.open ? "Carried as soon as enough members say yes; on a tie, the head's vote decides" : "Run by the computer: its members do not vote"}>
      {r.votes.length === 0 && <p className="muted">No votes yet.</p>}
      {r.votes.map((v: Any) => (
        <div key={v.id} className="vote">
          <div className="row"><span className="strong">{v.title}</span><span className={`tag tag-${v.status}`}>{v.status}</span></div>
          <div className="row small"><span>{v.kind_name} · put by {v.proposer}{v.status === "open" ? ` · closes ${when(v.closes_at)}` : ""}</span>
            <span className="mono">{v.for} for · {v.against} against{v.voters ? ` · ${v.voters} may vote` : ""}</span></div>
          {v.outcome && <p className="small muted">{v.outcome}</p>}
          {v.status === "open" && !v.about_you && (
            <div className="inline-form">
              <button className={v.your_vote === true ? "button-primary" : "button-outline"} disabled={act.busy} onClick={() => act.run("PUT", `/firm/votes/${v.id}`, { yes: true })}>▲ For</button>
              <button className={v.your_vote === false ? "button-primary" : "button-outline"} disabled={act.busy} onClick={() => act.run("PUT", `/firm/votes/${v.id}`, { yes: false })}>▼ Against</button>
              {v.yours && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/firm/votes/${v.id}`)}>Withdraw</button>}
            </div>
          )}
          {v.about_you && v.status === "open" && <p className="small muted">This vote is about you: you do not vote on it.</p>}
        </div>
      ))}
      {r.can_propose.length > 0 && (
        <form className="propose" onSubmit={propose}>
          <label className="answer"><span className="field-label">Put to the vote</span>
            <select value={kind} onChange={(e) => { setKind(e.target.value); setValues({}); }}>
              <option value="">Choose…</option>
              {r.can_propose.map((p: Any) => <option key={p.kind} value={p.kind}>{p.name}</option>)}
            </select>
          </label>
          {kind && PROPOSALS[kind].fields.map(([key, label, type, choices]) => (
            <label key={key} className="answer"><span className="field-label">{label}</span>
              {type === "choice" ? (
                <select value={values[key] ?? ""} onChange={(e) => setValues({ ...values, [key]: e.target.value })}>
                  <option value="">Leave as it is</option>{choices!.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
                </select>
              ) : <input type="text" inputMode="decimal" value={values[key] ?? ""} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />}
            </label>
          ))}
          {kind && <button className="button-primary" disabled={act.busy}>Put it to the vote</button>}
        </form>
      )}
    </Panel>
  );
}

function MoneyTab({ f, act }: { f: Any; act: Act }) {
  const m = f.money;
  const [kind, setKind] = useState("loan");
  const [amount, setAmount] = useState("");
  const [quarters, setQuarters] = useState("4");
  const [budgets, setBudgets] = useState<Record<string, string>>({});
  const [trainee, setTrainee] = useState("");
  const [trainingCost, setTrainingCost] = useState("");
  const [pool, setPool] = useState<Record<string, string>>({});
  return (
    <>
      <div className="tiles">
        <NumberTile label="Everything it owns" value={formatCompact(m.owned)} />
        <NumberTile label="Everything it owes" value={formatCompact(m.owed)} note={`may borrow ${formatCompact(m.borrow_room)} more`} />
        {m.unit_price && <NumberTile label="One unit of the empire" value={formatNaira(m.unit_price)} note="what each partner's share is counted in" />}
        <NumberTile label="Room for a dividend" value={formatCompact(m.dividend_room)} note="half of last quarter's profit" />
      </div>
      <Panel title="The treasury policy" aside="Voted by the members; the Asset Manager must stay inside it">
        <div className="row"><span>Cash (the safe pot)</span><span className="mono">{pct(m.mix.cash_bps)} · at least {pct(m.policy.cash_least_bps)}</span></div>
        <div className="row"><span>Bonds and bills (the main pot)</span><span className="mono">{pct(m.mix.bonds_bps)}</span></div>
        <div className="row"><span>Shares (the growth pot)</span><span className="mono">{pct(m.mix.shares_bps)} · at most {pct(m.policy.shares_most_bps)}</span></div>
        {m.breaches.length > 0 ? m.breaches.map((b: string) => <p key={b} className="change-down small">▼ The policy is broken: {b}.</p>) : <p className="change-up small">▲ Inside the policy.</p>}
        {m.risk_appetite && <p className="small muted">Risk appetite: the empire accepts losing up to {pct(m.risk_appetite.worst_year_bps)} in a bad year.</p>}
      </Panel>
      <Panel title="What the empire owes" aside={`A bank lends at the Central Bank's rate + ${pct(m.limits.loan_spread_bps)}; a bond at + ${pct(m.limits.bond_spread_bps)}`}>
        {m.debts.length === 0 && <p className="muted">Nothing.</p>}
        {m.debts.map((d: Any) => (
          <div key={d.id} className="debt">
            <div className="row"><span className="strong">{d.kind === "loan" ? "Loan" : "Bond"} from {d.lender}</span><span className={`tag tag-${d.status}`}>{d.status}</span></div>
            <div className="row small"><span>Owed · rate · due</span><span className="mono">{formatCompact(d.outstanding)} · {pct(d.rate_bps)} a year · {d.due}</span></div>
            <div className="row small"><span>Interest a quarter</span><Money kobo={d.interest_a_quarter} /></div>
            {d.traps.map((t: string) => <p key={t} className="small change-down">▼ In force: {t}</p>)}
            {d.broken.map((b: string) => <p key={b} className="small change-down">▼ Broken now: {b}</p>)}
            {f.is_head && d.status !== "defaulted" && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("POST", `/firm/debts/${d.id}/repayment`)}>Repay it now</button>}
          </div>
        ))}
        {m.can_design && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(amount); if (k) act.run("POST", "/firm/raisings", { kind, amount_kobo: k, quarters: kind === "stake" ? 0 : Number(quarters) }); }}>
            <label className="answer"><span className="field-label">Raise money by</span>
              <select value={kind} onChange={(e) => setKind(e.target.value)}><option value="loan">a bank loan</option><option value="bond">a bond, sold to the pension funds</option><option value="stake">selling a stake in the empire</option></select></label>
            <label className="answer"><span className="field-label">How much (₦)</span><input type="text" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
            {kind !== "stake" && <label className="answer"><span className="field-label">Over</span><select value={quarters} onChange={(e) => setQuarters(e.target.value)}>{m.limits.terms.map((t: number) => <option key={t} value={t}>{t} quarters</option>)}</select></label>}
            <button className="button-primary" disabled={act.busy || !asKobo(amount)}>Design it</button>
            <span className="muted small">It goes to the Accountant, then the Risk Manager; the Lawyer reads the paper; the head signs.</span>
          </form>
        )}
      </Panel>
      <Panel title="Budgets this quarter" aside={`Any cost above ${formatNaira(m.expense_threshold)} waits for the Accountant`}>
        {m.budgets.map((b: Any) => (
          <div key={b.desk} className="row">
            <span>{b.name}</span>
            <span className="mono">{b.budget ? <><Arrow up={BigInt(b.spent) <= BigInt(b.budget)} />{formatCompact(b.spent)} of {formatCompact(b.budget)}</> : <>{formatCompact(b.spent)} · no budget</>}</span>
            {m.can_set_budgets && <input className="small-input" type="text" inputMode="decimal" placeholder="₦" value={budgets[b.desk] ?? ""} onChange={(e) => setBudgets({ ...budgets, [b.desk]: e.target.value })} />}
          </div>
        ))}
        {m.can_set_budgets && (
          <button className="button-primary" disabled={act.busy || Object.values(budgets).every((v) => !v)} onClick={() => {
            const out: Record<string, number> = {};
            for (const [desk, text] of Object.entries(budgets)) { if (text.trim() === "0") out[desk] = 0; else { const k = asKobo(text); if (k) out[desk] = k; } }
            act.run("PUT", "/firm/budgets", { budgets: out });
          }}>Set the budgets</button>
        )}
      </Panel>
      <Panel title="Training" aside="A genuine cost: a member learns, and it counts against your desk's budget">
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(trainingCost); if (k) act.run("POST", "/firm/training", { amount_kobo: k, seat_id: trainee ? Number(trainee) : null }); }}>
          <SeatPicker roster={f.roster} value={trainee} onChange={setTrainee} label="For" />
          <label className="answer"><span className="field-label">Cost (₦)</span><input type="text" inputMode="decimal" value={trainingCost} onChange={(e) => setTrainingCost(e.target.value)} /></label>
          <button className="button-outline" disabled={act.busy || !asKobo(trainingCost)}>Sign for it</button>
        </form>
      </Panel>
      {m.can_propose_bonuses && (
        <Panel title="The quarter's bonus pool" aside="You propose; the head approves">
          {f.roster.filter((r: Any) => !r.is_head).map((r: Any) => (
            <div key={r.seat_id} className="row"><span>{r.name} · {r.build_name}</span>
              <input className="small-input" type="text" inputMode="decimal" placeholder="₦" value={pool[r.seat_id] ?? ""} onChange={(e) => setPool({ ...pool, [r.seat_id]: e.target.value })} /></div>
          ))}
          <button className="button-primary" disabled={act.busy} onClick={() => {
            const shares: Record<string, number> = {};
            for (const [seat, text] of Object.entries(pool)) { const k = asKobo(text); if (k) shares[seat] = k; }
            act.run("POST", "/firm/bonus-pool", { shares });
          }}>Propose it to the head</button>
        </Panel>
      )}
      {m.accounts.length > 0 && (
        <Panel title="The empire's accounts" aside="Closed as each quarter closes, and kept for good">
          <table className="table">
            <thead><tr><th>Quarter</th><th>Start</th><th>Close</th><th>Capital in</th><th>Paid out</th><th>Costs</th><th>Profit</th></tr></thead>
            <tbody>{m.accounts.map((a: Any) => (
              <tr key={a.period}><td>{a.label}</td><td className="mono">{formatCompact(a.opening)}</td><td className="mono">{formatCompact(a.closing)}</td>
                <td className="mono">{formatCompact(a.capital_in)}</td><td className="mono">{formatCompact(a.paid_out)}</td><td className="mono">{formatCompact(a.total_costs)}</td>
                <td className="mono"><Arrow up={!a.profit.startsWith("-")} />{formatCompact(a.profit)}</td></tr>))}</tbody>
          </table>
        </Panel>
      )}
      {m.partners.length > 0 && (
        <Panel title="The partners" aside="Who owns the empire, in units">
          {m.partners.map((p: Any, i: number) => (
            <div key={i} className="row"><span>{p.name}{p.you ? " (you)" : ""}</span><span className="mono">{Number(p.units).toLocaleString("en-NG")} units · {pct(p.share_bps)} · {formatCompact(p.value)}</span></div>
          ))}
          {m.stake_offer && <p className="small">A stake offer is open: {formatCompact(m.stake_offer.raised)} of {formatCompact(m.stake_offer.wanted)} put in, until {when(m.stake_offer.closes_at)}.</p>}
        </Panel>
      )}
    </>
  );
}

function People({ f, act }: { f: Any; act: Act }) {
  const p = f.people;
  const [seat, setSeat] = useState("");
  const [notice, setNotice] = useState("14");
  const [bonusShare, setBonusShare] = useState("0");
  const [nonCompete, setNonCompete] = useState("0");
  const [apprentice, setApprentice] = useState("");
  const [target, setTarget] = useState("");
  const [offer, setOffer] = useState("");
  const [title, setTitle] = useState({ seat: "", title: "deputy" });
  const [strategy, setStrategy] = useState({ choice: "grow", growth: "10", payout: "", tasks: "2" });
  const mine = f.roster.find((r: Any) => r.you);
  return (
    <>
      {p.approaches.map((o: Any) => (
        <Panel key={o.id} title={`${o.from} wants you`} aside={`A bonus of ${formatNaira(o.bonus)} to join them`}>
          {o.words && <p>“{o.words}”</p>}
          {o.matched && <p className="change-up">▲ Your empire offers {formatNaira(o.matched)} to stay.</p>}
          {o.may_go_at && <p className="small muted">Your empire may match until {when(o.may_go_at)}. You may stay now, or go after that.</p>}
          <div className="inline-form">
            <button className="button-outline" disabled={act.busy} onClick={() => act.run("PUT", `/firm/approaches/${o.id}`, { go: false })}>Stay</button>
            <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/firm/approaches/${o.id}`, { go: true })}>Go</button>
          </div>
        </Panel>
      ))}
      {p.to_match.map((o: Any) => (
        <Panel key={o.id} title={`${o.from} has approached ${o.member}`} aside={`They offer ${formatNaira(o.bonus)}`}>
          <p className="small muted">You may offer a bonus to keep them until {when(o.match_by)}.</p>
          <MatchForm id={o.id} act={act} />
        </Panel>
      ))}
      <Panel title="Contracts" aside="The Lawyer drafts; the head offers; the member signs. Enforced by the game">
        {p.contracts.length === 0 && <p className="muted">No contracts yet.</p>}
        {p.contracts.map((c: Any) => (
          <div key={c.id} className="row"><span>{c.name}</span>
            <span className="small">{c.notice_days} days' notice · {pct(c.bonus_bps)} of the desk's pool · {c.non_compete ? `may not join the rival for ${c.non_compete} quarter(s)` : "no non-compete"} · <span className={`tag tag-${c.status}`}>{c.status}</span></span>
            {c.to_offer && (
              <span className="inline-form">
                <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/firm/contracts/${c.id}/offer`, { sign: true })}>Offer it</button>
                <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/firm/contracts/${c.id}/offer`, { sign: false })}>Tear it up</button>
              </span>)}
            {c.yours && c.status === "offered" && (
              <span className="inline-form">
                <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/firm/contracts/${c.id}`, { sign: true })}>Sign</button>
                <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/firm/contracts/${c.id}`, { sign: false })}>Turn down</button>
              </span>)}
          </div>
        ))}
        {p.can_draft && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/firm/contracts", { seat_id: Number(seat), notice_days: Number(notice), bonus_bps: Math.round(Number(bonusShare) * 100), non_compete: Number(nonCompete) }); }}>
            <SeatPicker roster={f.roster.filter((r: Any) => !r.is_head)} value={seat} onChange={setSeat} exceptYou />
            <label className="answer"><span className="field-label">Notice (days)</span><input type="number" min={0} max={p.rules.notice_most} value={notice} onChange={(e) => setNotice(e.target.value)} /></label>
            <label className="answer"><span className="field-label">Share of the desk's pool (%)</span><input type="number" min={0} max={20} value={bonusShare} onChange={(e) => setBonusShare(e.target.value)} /></label>
            <label className="answer"><span className="field-label">Non-compete (quarters)</span><select value={nonCompete} onChange={(e) => setNonCompete(e.target.value)}><option>0</option><option>1</option><option>2</option></select></label>
            <button className="button-primary" disabled={act.busy || !seat}>Draft and offer it</button>
          </form>
        )}
      </Panel>
      <Panel title="Apprentices" aside={`A mentor is ${p.rules.apprentice_gap} levels above; both gain when the apprentice does well`}>
        {p.apprentices.map((a: Any, i: number) => <div key={i} className="row"><span>{a.mentor} mentors {a.apprentice}</span><span className="small">{a.build}</span></div>)}
        {p.apprentices.length === 0 && <p className="muted">None yet.</p>}
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/firm/apprentices", { seat_id: Number(apprentice) }); }}>
          <SeatPicker roster={f.roster} value={apprentice} onChange={setApprentice} build={mine?.build} label="Take on as your apprentice" exceptYou />
          <button className="button-outline" disabled={act.busy || !apprentice}>Take them on</button>
          {p.apprentices.some((a: Any) => a.you) && <button type="button" className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", "/firm/apprentices")}>End your apprenticeship</button>}
        </form>
      </Panel>
      <Panel title="The empire's rules" aside="Changed only by the members' vote">
        <div className="row"><span>Big votes carried by</span><span>{String(p.constitution.big_votes).replace("_", " ")}</span></div>
        <div className="row"><span>A member's signing limit</span><span>{p.constitution.member_signing_naira ? formatNaira(String(p.constitution.member_signing_naira * 100)) : "as the head sets it"}</span></div>
        <div className="row"><span>A leaving partner's units</span><span>{p.constitution.leaver_units === "buy_back" ? "bought back by the empire" : "kept"}</span></div>
        <div className="row"><span>A proved theft</span><span>{p.conduct.theft === "always_punish" ? "always punished" : "the head decides"}</span></div>
        <div className="row"><span>A missed duty</span><span>{p.conduct.missed_duty_fine_naira ? `a fine of ${formatNaira(String(p.conduct.missed_duty_fine_naira * 100))}` : "no fine"}</span></div>
      </Panel>
      {f.is_head && (
        <>
          <Panel title="Titles" aside="A deputy decides what waits too long for you, and leads if you go">
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("PUT", "/firm/titles", { seat_id: Number(title.seat), title: title.title }); }}>
              <SeatPicker roster={f.roster} value={title.seat} onChange={(v) => setTitle({ ...title, seat: v })} exceptYou />
              <label className="answer"><span className="field-label">As</span><select value={title.title} onChange={(e) => setTitle({ ...title, title: e.target.value })}><option value="deputy">deputy head</option><option value="lead">lead of their desk</option></select></label>
              <button className="button-outline" disabled={act.busy || !title.seat}>Name them</button>
            </form>
          </Panel>
          <Panel title="The year's strategy" aside="Set once a year; you are judged against your own targets">
            {p.strategy ? (
              <>
                <p className="strong">{p.strategy.words}</p>
                <p className="small">Targets: worth up {pct(p.strategy.targets.growth_bps)}, {formatNaira(p.strategy.targets.payout)} paid to partners, {p.strategy.targets.tasks} tasks finished.</p>
                {p.strategy.result && <p className="small">Result: {p.strategy.result.hit} of 3 targets met.</p>}
              </>
            ) : (
              <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("PUT", "/firm/strategy", { choice: strategy.choice, growth_bps: Math.round(Number(strategy.growth) * 100), payout_kobo: asKobo(strategy.payout) ?? 0, tasks: Number(strategy.tasks) }); }}>
                <label className="answer"><span className="field-label">Direction</span><select value={strategy.choice} onChange={(e) => setStrategy({ ...strategy, choice: e.target.value })}>
                  {Object.entries(p.strategies).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}</select></label>
                <label className="answer"><span className="field-label">Worth up by (%)</span><input type="text" value={strategy.growth} onChange={(e) => setStrategy({ ...strategy, growth: e.target.value })} /></label>
                <label className="answer"><span className="field-label">Dividends (₦)</span><input type="text" value={strategy.payout} onChange={(e) => setStrategy({ ...strategy, payout: e.target.value })} /></label>
                <label className="answer"><span className="field-label">Tasks</span><input type="number" min={0} max={12} value={strategy.tasks} onChange={(e) => setStrategy({ ...strategy, tasks: e.target.value })} /></label>
                <button className="button-primary" disabled={act.busy}>Set it</button>
              </form>
            )}
          </Panel>
          <Panel title="Approach a member of another empire" aside="Their empire has two days to match; a member under contract costs a transfer fee">
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(offer); if (k) act.run("POST", "/firm/approaches", { seat_id: Number(target), bonus_kobo: k }); }}>
              <label className="answer"><span className="field-label">Who</span><select value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">Choose…</option>{p.elsewhere.map((o: Any) => <option key={o.seat_id} value={o.seat_id}>{o.name} · {o.build_name} · {o.empire}</option>)}</select></label>
              <label className="answer"><span className="field-label">Bonus (₦)</span><input type="text" value={offer} onChange={(e) => setOffer(e.target.value)} /></label>
              <button className="button-outline" disabled={act.busy || !target || !asKobo(offer)}>Make the offer</button>
            </form>
            {p.our_approaches.map((o: Any) => <div key={o.id} className="row small"><span>{o.member}: {formatNaira(o.bonus)}</span><button className="button-quiet" onClick={() => act.run("DELETE", `/firm/approaches/${o.id}`)}>Withdraw</button></div>)}
          </Panel>
        </>
      )}
    </>
  );
}

function MatchForm({ id, act }: { id: number; act: Act }) {
  const [text, setText] = useState("");
  return (
    <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(text); if (k) act.run("PUT", `/firm/approaches/${id}/match`, { bonus_kobo: k }); }}>
      <label className="answer"><span className="field-label">Bonus to stay (₦)</span><input type="text" value={text} onChange={(e) => setText(e.target.value)} /></label>
      <button className="button-primary" disabled={act.busy || !asKobo(text)}>Match</button>
    </form>
  );
}

function WorkTab({ f, act }: { f: Any; act: Act }) {
  const w = f.work;
  const [kind, setKind] = useState("investment");
  const [priority, setPriority] = useState("2");
  const [cover, setCover] = useState({ kind: "holding_collapse", insurer: "", amount: "" });
  return (
    <>
      {w.events.map((h: Any) => <Event key={h.id} h={h} act={act} />)}
      <Panel title="Tasks" aside={`${w.open} of ${w.most} in hand · one of each kind a quarter`}>
        {w.tasks.length === 0 && <p className="muted">No tasks in hand.</p>}
        {w.tasks.map((t: Any) => (
          <div key={t.id} className="task">
            <div className="row"><span className="strong">{t.kind_name}{t.company ? `: ${t.company} (${t.ticker})` : ""}</span>
              <span className="small">priority {t.priority} · <span className={`tag tag-${t.status}`}>{t.status}</span>{t.decision ? ` · the head chose to ${t.decision}` : ""}</span></div>
            {f.is_head && t.status === "open" && (
              <select className="small-input" value={t.priority} onChange={(e) => act.run("PUT", `/firm/tasks/${t.id}/priority`, { priority: Number(e.target.value) })}>
                <option value={1}>Priority 1</option><option value={2}>Priority 2</option><option value={3}>Priority 3</option></select>)}
            <ol className="steps">
              {t.steps.map((s: Any) => (
                <li key={s.id} className={`step step-${s.status}`}>
                  <span>{s.status === "done" ? "▲" : s.status === "current" ? "▶" : "·"} {s.name}: {s.what}</span>
                  <span className="small muted"> {s.done_by ? `done by ${s.done_by}` : s.given_to ? `given to ${s.given_to}` : ""}</span>
                  {s.can_assign && s.status !== "done" && (
                    <select className="small-input" defaultValue="" onChange={(e) => act.run("PUT", `/firm/steps/${s.id}/given-to`, { seat_id: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">Anybody on the desk</option>
                      {f.roster.filter((r: Any) => r.build === s.build).map((r: Any) => <option key={r.seat_id} value={r.seat_id}>{r.name}</option>)}
                    </select>)}
                  {s.decide_defence && <DefenceForm id={s.id} act={act} />}
                </li>
              ))}
            </ol>
          </div>
        ))}
        {w.can_start && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/firm/tasks", { kind, priority: Number(priority) }); }}>
            <label className="answer"><span className="field-label">Start a task</span><select value={kind} onChange={(e) => setKind(e.target.value)}>
              {w.kinds.map((k: Any) => <option key={k.kind} value={k.kind} disabled={k.started}>{k.name}{k.started ? " (started this quarter)" : ""}</option>)}</select></label>
            <label className="answer"><span className="field-label">Priority</span><select value={priority} onChange={(e) => setPriority(e.target.value)}><option>1</option><option>2</option><option>3</option></select></label>
            <button className="button-primary" disabled={act.busy}>Start it</button>
          </form>
        )}
      </Panel>
      {w.shortlist && (
        <Panel title="The banker's shortlist" aside="Pick one: the next investment is on it, and the banker's choice is judged against the market">
          <p>“{w.shortlist.reason}”</p>
          {w.shortlist.targets.map((t: Any) => (
            <div key={t.id} className="row"><span>{t.name} ({t.ticker})</span>
              {f.is_head && <button className="button-outline" disabled={act.busy} onClick={() => act.run("PUT", `/firm/shortlists/${w.shortlist.id}`, { company_id: t.id })}>Pick it</button>}</div>
          ))}
        </Panel>
      )}
      <Panel title="The rival" aside="Quarter by quarter: who earned more league points">
        {w.rivalry ? (
          <>
            <p className="strong">{w.rivalry.rival}: won {w.rivalry.won}, lost {w.rivalry.lost}, drawn {w.rivalry.drawn}</p>
            {w.rivalry.quarters.slice(0, 6).map((q: Any) => <div key={q.label} className="row small"><span>{q.label}</span><span className="mono"><Arrow up={q.ours === q.theirs ? null : q.ours > q.theirs} />{q.ours} to {q.theirs}</span></div>)}
          </>
        ) : <p className="muted">A rival is named at the next Closing Bell.</p>}
        {f.is_head && w.rivals.length > 0 && (
          <label className="answer"><span className="field-label">Choose another rival</span>
            <select defaultValue="" onChange={(e) => e.target.value && act.run("PUT", "/firm/rival", { empire_id: Number(e.target.value) })}>
              <option value="">Choose…</option>{w.rivals.map((r: Any) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
        )}
      </Panel>
      <Panel title="Insurance" aside={`Bought for ${w.cover.quarters} quarters; the insurer pays claims from its own cash`}>
        {w.cover.running.map((c: Any) => <div key={c.kind} className="row"><span>{c.name} · {c.insurer}</span><span className="mono">{formatCompact(c.cover)} cover · {formatCompact(c.claimed)} claimed · until {c.until}</span></div>)}
        {w.cover.running.length === 0 && <p className="muted">No cover running.</p>}
        {f.your_build === "risk_manager" && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(cover.amount); if (k) act.run("POST", "/firm/cover", { kind: cover.kind, insurer_id: cover.insurer, cover_kobo: k }); }}>
            <label className="answer"><span className="field-label">Against</span><select value={cover.kind} onChange={(e) => setCover({ ...cover, kind: e.target.value })}>
              {w.cover.kinds.map((k: Any) => <option key={k.kind} value={k.kind}>{k.name} ({pct(k.premium_bps)} a quarter)</option>)}</select></label>
            <label className="answer"><span className="field-label">From</span><select value={cover.insurer} onChange={(e) => setCover({ ...cover, insurer: e.target.value })}>
              <option value="">Choose…</option>{w.cover.insurers.map((i: Any) => <option key={i.id} value={i.id}>{i.name} (cash {formatCompact(i.cash)})</option>)}</select></label>
            <label className="answer"><span className="field-label">Cover (₦, up to {formatCompact(w.cover.most)})</span><input type="text" value={cover.amount} onChange={(e) => setCover({ ...cover, amount: e.target.value })} /></label>
            <button className="button-outline" disabled={act.busy || !cover.insurer || !asKobo(cover.amount)}>Buy it</button>
          </form>
        )}
      </Panel>
    </>
  );
}

function DefenceForm({ id, act }: { id: number; act: Act }) {
  const [choice, setChoice] = useState("hold");
  return (
    <span className="inline-form">
      <select value={choice} onChange={(e) => setChoice(e.target.value)}><option value="hold">Hold the shares</option><option value="sell">Sell them</option></select>
      <Reason placeholder="Your reason (on your record)" button="Decide" busy={act.busy} onSubmit={(reason) => act.run("PUT", `/firm/steps/${id}/defence`, { choice, reason })} />
    </span>
  );
}

function Event({ h, act }: { h: Any; act: Act }) {
  const [amount, setAmount] = useState("");
  const open = h.status === "open";
  return (
    <Panel title={h.title} aside={open ? `Answer by ${when(h.due_at)}` : `Scored ${h.score} out of 100`} className={open ? "panel-urgent" : ""}>
      <p>{h.body}</p>
      {h.desks.map((d: Any) => (
        <div key={d.desk} className="row">
          <span className="small"><span className="strong">{d.name}:</span> {d.prompt}</span>
          <span className="small">
            {d.answered ? <>answered by {d.by}{d.choice ? `: ${d.choice}` : ""}{d.right !== null && d.right !== undefined ? ` · right answer: ${d.right}` : ""}</> : open ? "waiting" : "no answer"}
          </span>
          {d.yours && (d.amount ? (
            <span className="inline-form">
              <input type="text" inputMode="decimal" placeholder="₦" value={amount} onChange={(e) => setAmount(e.target.value)} />
              <button className="button-primary" disabled={act.busy || !asKobo(amount)} onClick={() => act.run("POST", `/firm/events/${h.id}`, { desk: d.desk, choice: asKobo(amount) })}>Answer</button>
            </span>
          ) : (
            <span className="inline-form">{d.choices.map((c: string) => (
              <button key={c} className="button-outline" disabled={act.busy} onClick={() => act.run("POST", `/firm/events/${h.id}`, { desk: d.desk, choice: c })}>{c.replace(/_/g, " ")}</button>))}</span>
          ))}
        </div>
      ))}
      {h.outcome && <p className="small muted">{h.outcome}</p>}
    </Panel>
  );
}

function RiskTab({ f, act }: { f: Any; act: Act }) {
  const r = f.risk;
  const [limit, setLimit] = useState("");
  const [freeze, setFreeze] = useState({ seat: "", reason: "" });
  const n = r.now;
  return (
    <>
      {r.you_frozen && <p className="error">The Risk Manager has frozen your trading for the empire.</p>}
      <div className="tiles">
        <NumberTile label="Worth (owned less owed)" value={formatCompact(n.worth)} change={n.since_close_bps} note="since the last close" />
        <NumberTile label="Largest holding" value={n.biggest ? `${n.biggest} · ${pct(n.biggest_bps)}` : "—"} />
        <NumberTile label="Largest industry" value={n.biggest_sector ? `${n.biggest_sector} · ${pct(n.biggest_sector_bps)}` : "—"} />
        <NumberTile label="Owed as a share of owned" value={pct(n.gearing_bps)} note={n.cash_cover !== null ? `cash covers ${n.cash_cover} quarters of interest` : "nothing owed"} />
      </div>
      {n.breaches.map((b: string) => <p key={b} className="change-down">▼ The treasury policy is broken: {b}.</p>)}
      <Panel title="The risk report at every Closing Bell" aside="Kept for good">
        <table className="table"><thead><tr><th>Day</th><th>Worth</th><th>Largest holding</th><th>Owed / owned</th><th>Policy</th></tr></thead>
          <tbody>{r.reports.map((d: Any) => (
            <tr key={d.day}><td>{d.day}</td><td className="mono">{formatCompact(d.worth)}</td><td>{d.biggest ? `${d.biggest} ${pct(d.biggest_bps)}` : "—"}</td><td className="mono">{pct(d.gearing_bps)}</td>
              <td>{d.breaches.length ? "▼ broken" : "▲ kept"}</td></tr>))}</tbody></table>
      </Panel>
      <Panel title="Limits" aside="A trade above the limit, into a new industry, or against the policy, waits for the Risk Manager">
        <div className="row"><span>The most one trade may be without approval</span><span className="mono">{r.trade_limit_naira ? formatNaira(String(r.trade_limit_naira * 100)) : "no limit set"}</span></div>
        {r.frozen.length > 0 && <div className="row"><span>Frozen</span><span>{r.frozen.join(", ")}</span></div>}
        {r.you_set_limits && (
          <>
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const v = Number(limit.replace(/,/g, "")); act.run("PUT", "/firm/trade-limit", { limit_naira: v > 0 ? v : null }); }}>
              <label className="answer"><span className="field-label">Limit (₦, blank for none)</span><input type="text" value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
              <button className="button-outline" disabled={act.busy}>Set it</button>
            </form>
          </>
        )}
        {(r.you_set_limits || f.is_head) && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const frozen = !r.frozen_seats.includes(Number(freeze.seat)); act.run("PUT", "/firm/freeze", { seat_id: Number(freeze.seat), frozen, reason: freeze.reason }); }}>
            <SeatPicker roster={f.roster.filter((x: Any) => !x.is_head && x.build === "asset_manager")} value={freeze.seat} onChange={(v) => setFreeze({ ...freeze, seat: v })} label="Asset Manager" />
            <input type="text" placeholder="Your reason (on the record)" value={freeze.reason} onChange={(e) => setFreeze({ ...freeze, reason: e.target.value })} />
            <button className="button-outline" disabled={act.busy || !freeze.seat || !freeze.reason}>{r.frozen_seats.includes(Number(freeze.seat)) ? "Lift the freeze" : "Freeze their trading"}</button>
          </form>
        )}
      </Panel>
    </>
  );
}

function Board({ f }: { f: Any }) {
  const b = f.board;
  return (
    <>
      <Panel title="This quarter's plan" aside={b.plan_at ? `set ${when(b.plan_at)}` : "the head sets it at the board meeting"}>
        {b.plan ? (
          <>
            <p className="strong">Priorities: {b.plan.priorities.join(", ")}</p>
            {b.plan.focus && <p className="small">The desk that needs the most attention: {b.plan.focus}</p>}
            <p>{b.plan.plan}</p>
          </>
        ) : <p className="muted">No plan was set for this quarter.</p>}
      </Panel>
      <Panel title="The desks' reports" aside="Last quarter and this">
        {b.reports.map((r: Any, i: number) => (
          <div key={i} className="report">
            <div className="row small"><span><span className="strong">{r.desk}:</span> {r.title}</span><span className="mono">{r.status === "missed" ? "▼ missed" : `${r.score}/100`}{r.by ? ` · ${r.by}` : ""}</span></div>
            {r.text && Object.values(r.text).map((t: Any, j: number) => <p key={j} className="small">{String(t)}</p>)}
          </div>
        ))}
        {b.reports.length === 0 && <p className="muted">Nothing reported yet.</p>}
      </Panel>
      {b.big_votes.length > 0 && <Panel title="Open votes"><ul>{b.big_votes.map((v: Any) => <li key={v.id}>{v.title}: {v.for} for, {v.against} against</li>)}</ul></Panel>}
    </>
  );
}

// ---------------------------------------------------------------------------
// The screen
// ---------------------------------------------------------------------------

function needsYou(f: Any): { tag: string; title: string; tab: Tab }[] {
  const out: { tag: string; title: string; tab: Tab }[] = [];
  for (const h of f.work.events) for (const d of h.desks) if (d.yours) out.push({ tag: "EVENT", title: `${h.title}: answer for the ${d.name}`, tab: "work" });
  for (const r of f.approvals.to_decide) out.push({ tag: "REQUEST", title: r.title, tab: "requests" });
  for (const p of f.papers.papers) if (p.yours_to_read) out.push({ tag: "PAPER", title: `Read: ${p.title}`, tab: "requests" });
  for (const v of f.resolutions.votes) if (v.status === "open" && v.your_vote === null && !v.about_you) out.push({ tag: "VOTE", title: v.title, tab: "requests" });
  for (const o of f.people.approaches) out.push({ tag: "OFFER", title: `${o.from} wants you`, tab: "people" });
  for (const o of f.people.to_match) out.push({ tag: "MATCH", title: `${o.from} has approached ${o.member}`, tab: "people" });
  for (const c of f.people.contracts) if (c.yours && c.status === "offered") out.push({ tag: "CONTRACT", title: "A contract is waiting for your signature", tab: "people" });
  for (const d of f.duties.desks) for (const duty of d.duties) if (duty.yours) out.push({ tag: "DUTY", title: duty.title, tab: "desks" });
  return out;
}

export function FirmWork({ player, onLoggedOut, onChanged }: Props) {
  const { data, loadError, reload, act } = useFirm(onLoggedOut, onChanged);
  const [tab, setTab] = useState<Tab>("desks");
  if (!data && !loadError) return <Loading what="the firm" />;
  if (!data) return <Failed message={loadError ?? "Could not load the firm."} onRetry={reload} />;
  const f = data.firm;
  if (!f) {
    return (
      <Panel title="The firm">
        <p className="muted">The firm is the work inside an open empire. Take a seat in one first: see <a href="#/empire">Empires</a>.</p>
        <StakeOffers offers={data.stake_offers} act={act} />
        <Bookkeeping b={data.bookkeeping} act={act} />
      </Panel>
    );
  }
  const cards = needsYou(f);
  return (
    <>
      <div className="work-head">
        <h1>{f.name}: the firm</h1>
        <span className="muted small">{f.is_head ? "You are the head" : f.is_deputy ? "You are the deputy head" : `Your desk: ${f.roster.find((r: Any) => r.you)?.build_name ?? ""}`}{f.deputy && !f.is_deputy ? ` · deputy: ${f.deputy}` : ""}</span>
      </div>
      {act.error && <p className="error" role="alert">{act.error}</p>}
      {act.notice && <p className="saved" role="status">{act.notice}</p>}
      <section aria-label="Needs you now">
        {cards.length === 0 ? <p className="muted">Nothing in the firm is waiting on you.</p> : (
          <div className="queue">
            {cards.slice(0, 4).map((card, index) => (
              <button key={index} className={index === 0 ? "card card-first" : "card"} onClick={() => setTab(card.tab)}>
                <div className="card-top"><span className="card-tag">{card.tag}</span></div>
                <h3>{card.title}</h3>
              </button>
            ))}
          </div>
        )}
      </section>
      <div className="tabs tabs-inline" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "tab active" : "tab"} onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>
      {tab === "desks" && <Desks f={f} act={act} />}
      {tab === "requests" && <Requests f={f} act={act} />}
      {tab === "money" && <MoneyTab f={f} act={act} />}
      {tab === "people" && <People f={f} act={act} />}
      {tab === "work" && <WorkTab f={f} act={act} />}
      {tab === "risk" && <RiskTab f={f} act={act} />}
      {tab === "board" && <Board f={f} />}
      {tab === "people" && <Bookkeeping b={data.bookkeeping} act={act} />}
      <span hidden>{player.id}</span>
    </>
  );
}

function Bookkeeping({ b, act }: { b: Any; act: Act }) {
  const [key, setKey] = useState("");
  const [fee, setFee] = useState("");
  const [answers, setAnswers] = useState<Record<number, { net: string; biggest: string; note: string }>>({});
  if (!b) return null;
  const open = b.mine.find((m: Any) => m.status === "open");
  return (
    <Panel title="Bookkeeping" aside={`An Accountant looks at your money for the quarter just closed. From a seat in an empire, ${pct(b.empire_share_bps)} of the fee is the firm's`}>
      {b.mine.map((m: Any) => (
        <div key={m.id} className="report">
          <div className="row small"><span>{m.who} · quarter {m.period} · fee {formatNaira(m.fee)}</span><span className={`tag tag-${m.status}`}>{m.status}</span></div>
          {m.status === "done" && m.report.answers && (
            <div className="facts">
              <div className="row small"><span>Your cash changed by</span><Money kobo={String(m.report.answers.net)} /></div>
              <div className="row small"><span>The largest kind of payment out</span><span>{m.report.answers.biggest}</span></div>
              <div className="row small"><span>Marked</span><span className="mono">{m.report.score}/100</span></div>
              {m.report.note && <p className="small">“{m.report.note}”</p>}
              {m.rating === null && <span className="inline-form">{[1, 2, 3, 4, 5].map((n) => <button key={n} className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/bookkeeping/${m.id}/rating`, { stars: n })}>{"★".repeat(n)}</button>)}</span>}
            </div>
          )}
          {m.status === "open" && !m.opened && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/bookkeeping/${m.id}`)}>Cancel</button>}
        </div>
      ))}
      {!open && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(fee); if (k) act.run("POST", "/bookkeeping", { adviser_key: key, fee_kobo: k }); }}>
          <label className="answer"><span className="field-label">Hire</span><select value={key} onChange={(e) => setKey(e.target.value)}>
            <option value="">Choose an Accountant…</option>
            {b.advisers.map((a: Any) => <option key={a.key} value={a.key}>{a.name} · reputation {a.reputation}{a.stars !== null ? ` · ${a.stars}★` : ""}</option>)}</select></label>
          <label className="answer"><span className="field-label">Fee (₦{formatNaira(b.fee_least).slice(1)} to {formatNaira(b.fee_most)})</span><input type="text" value={fee} onChange={(e) => setFee(e.target.value)} /></label>
          <button className="button-outline" disabled={act.busy || !key || !asKobo(fee)}>Hire them</button>
        </form>
      )}
      {b.clients.length > 0 && <p className="field-label">Your clients</p>}
      {b.clients.map((c: Any) => {
        const a = answers[c.id] ?? { net: "", biggest: "", note: "" };
        return (
          <div key={c.id} className="report">
            <div className="row small"><span>{c.who} · fee {formatNaira(c.fee)}</span><span className={`tag tag-${c.status}`}>{c.status}</span></div>
            {c.status === "open" && !c.opened && <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", `/bookkeeping/${c.id}/open`)}>Open their figures</button>}
            {c.status === "open" && c.opened && (
              <form className="duty-form" onSubmit={(e) => { e.preventDefault(); const sign = a.net.trim().startsWith("-") ? -1 : 1; const k = asKobo(a.net.replace("-", "")) ?? 0;
                act.run("POST", `/bookkeeping/${c.id}/report`, { net_kobo: sign * k, biggest: a.biggest, note: a.note }); }}>
                <div className="facts">{c.report.given.map((g: Any) => <div key={g.label} className="row small"><span>{g.label}</span><span className="mono">in {formatNaira(g.in)} · out {formatNaira(g.out)}</span></div>)}</div>
                <label className="answer"><span className="field-label">Net change in their cash (₦, minus if it fell)</span><input type="text" value={a.net} onChange={(e) => setAnswers({ ...answers, [c.id]: { ...a, net: e.target.value } })} /></label>
                <label className="answer"><span className="field-label">The largest kind of payment out</span><select value={a.biggest} onChange={(e) => setAnswers({ ...answers, [c.id]: { ...a, biggest: e.target.value } })}>
                  <option value="">Choose…</option>{c.report.choices.map((x: string) => <option key={x}>{x}</option>)}</select></label>
                <label className="answer"><span className="field-label">A note to the client</span><textarea rows={2} maxLength={400} value={a.note} onChange={(e) => setAnswers({ ...answers, [c.id]: { ...a, note: e.target.value } })} /></label>
                <button className="button-primary" disabled={act.busy || !a.biggest}>Deliver the report</button>
              </form>
            )}
          </div>
        );
      })}
    </Panel>
  );
}

function StakeOffers({ offers, act }: { offers: Any[]; act: Act }) {
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  if (!offers || offers.length === 0) return null;
  return (
    <Panel title="Stakes on offer" aside="Put money into an empire for units, at the offer's price">
      {offers.map((o: Any) => (
        <div key={o.id} className="row">
          <span>{o.empire}: {formatCompact(o.raised)} of {formatCompact(o.wanted)} · a unit {formatNaira(o.unit_price)} · until {when(o.closes_at)}</span>
          <span className="inline-form">
            <input className="small-input" type="text" placeholder="₦" value={amounts[o.id] ?? ""} onChange={(e) => setAmounts({ ...amounts, [o.id]: e.target.value })} />
            <button className="button-outline" disabled={act.busy || !asKobo(amounts[o.id] ?? "")} onClick={() => act.run("POST", `/stake-offers/${o.id}`, { amount_kobo: asKobo(amounts[o.id] ?? "") })}>Buy</button>
          </span>
        </div>
      ))}
    </Panel>
  );
}

export function FirmRail({ onLoggedOut, onChanged }: Props) {
  const { data, act } = useFirm(onLoggedOut, onChanged);
  if (!data?.firm) return data ? <StakeOffers offers={data.stake_offers} act={act} /> : null;
  const f = data.firm;
  const card = f.people.scorecard;
  const record = f.record;
  return (
    <>
      {card?.record && (
        <Panel title="The head's scorecard" aside="Public">
          <div className="row"><span>Worth over the last quarters</span><span className="mono">{card.worth_change_bps !== null ? <><Arrow up={card.worth_change_bps >= 0} />{pct(card.worth_change_bps)}</> : "—"}</span></div>
          <div className="row"><span>Members kept</span><span className="mono">{card.members_kept} of {card.members_ever}</span></div>
          <div className="row"><span>Thefts proved</span><span className="mono">{card.thefts_proved}</span></div>
          <div className="row"><span>Overrules on the record</span><span className="mono">{card.record.overrules}</span></div>
          <div className="row"><span>Turned out well / badly</span><span className="mono">▲ {card.record.good} · ▼ {card.record.bad}</span></div>
        </Panel>
      )}
      <Panel title="Your record" aside="What you signed, and how it turned out">
        <div className="row"><span>Right / wrong</span><span className="mono">▲ {record.right} · ▼ {record.wrong}</span></div>
        {record.latest.slice(0, 6).map((o: Any, i: number) => (
          <div key={i} className="news-line"><div className="small">{o.name}: {o.subject}</div>
            <div className="small muted">{o.outcome ? `${o.outcome === "right" ? "▲ right" : o.outcome === "wrong" ? "▼ wrong" : "not checked"}${o.outcome_words ? `: ${o.outcome_words}` : ""}` : "waiting to be checked"}</div></div>
        ))}
      </Panel>
      {f.work.rivalry && <Panel title="Against the rival"><p>{f.work.rivalry.rival}: won {f.work.rivalry.won}, lost {f.work.rivalry.lost}</p></Panel>}
      <StakeOffers offers={data.stake_offers} act={act} />
    </>
  );
}
