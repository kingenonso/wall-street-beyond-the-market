// A player's working life: their build, their bank, their employer, their pay and their savings.

import { useState } from "react";
import { api, ApiError, type BuildCode, type Career, type Player } from "./api";
import { formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { LevelPanel, PayPanel, ProgressTracker } from "./Parts";
import { PensionFundsPanel } from "./Pensions";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void; onChanged: () => void };

function useAction(onDone: () => void) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await action(); onDone(); }
    catch (problem) { setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again."); }
    finally { setBusy(false); }
  }
  return { error, busy, run };
}

function BuildChoice({ career, act }: { career: Career; act: ReturnType<typeof useAction> }) {
  const changeAt = career.can_change_build_at ? new Date(career.can_change_build_at) : null;
  const locked = career.build !== null && changeAt !== null && changeAt.getTime() > Date.now();
  return (
    <Panel title={career.build ? "Your build" : "Step 1 · Choose your build"} aside="Your profession in the game">
      <div className="builds">
        {career.builds.map((build) => (
          <article key={build.code} className={build.code === career.build ? `build-card chosen accent-${build.accent}` : `build-card accent-${build.accent}`}>
            <h3>{build.name}</h3>
            <p className="small">{build.work}</p>
            <div className="small"><span className="muted">Earns:</span> {build.earns}</div>
            <div className="small"><span className="muted">Hired by:</span> {build.employer_words}.</div>
            <div className="small"><span className="muted">Cannot alone:</span> {build.cannot}</div>
            {build.code === career.build
              ? <div className="saved small">✓ Your build</div>
              : <button className="button-outline" disabled={act.busy || locked} onClick={() => act.run(() => api.chooseBuild(build.code as BuildCode))}>
                  {career.build ? `Change to ${build.name}` : `Choose ${build.name}`}
                </button>}
          </article>
        ))}
      </div>
      <p className="muted small">
        {career.later_builds.length > 0 && `${career.later_builds.join(", ")} open in the next stage. `}CEO cannot be chosen: it is earned by rising through another build.
        {career.build && changeAt && ` A build can be changed once in a real month${locked ? `: you can change from ${changeAt.toLocaleDateString("en-NG", { day: "numeric", month: "long" })}` : ""}. Each build keeps its own level, and changing means leaving your job.`}
      </p>
    </Panel>
  );
}

function BankChoice({ career, act, onLoggedOut }: { career: Career; act: ReturnType<typeof useAction>; onLoggedOut: () => void }) {
  const banks = useLoad(api.banks, `banks:${career.bank?.ticker ?? ""}`, onLoggedOut);
  return (
    <Panel title={career.bank ? "Your bank" : "Step 2 · Choose your bank"} aside="Where your salary is paid">
      <p className="small">
        Your bank pays interest each quarter on the least cash you kept with it through the whole quarter, so money put in
        for a day earns nothing, and the quarter you join in is not counted. A weaker bank pays more to keep its customers.
        You can move once a quarter.
      </p>
      <div className="scroll">
        <table>
          <thead><tr><th scope="col">Bank</th><th scope="col">Head office</th><th scope="col">Credit rating</th><th scope="col" className="num">Pays on savings, a year</th><th scope="col"></th></tr></thead>
          <tbody>
            {(banks.data ?? []).map((bank) => (
              <tr key={bank.ticker} className={bank.yours ? "row-chosen" : undefined}>
                <th scope="row"><a href={`#/companies/${bank.ticker}`}>{bank.name}</a></th>
                <td>{bank.headquarters}</td>
                <td>{bank.rating ? <Rating value={bank.rating} /> : "—"}</td>
                <td className="num mono">{formatPercent(bank.savings_rate_bps, 2)}</td>
                <td className="num">
                  {bank.yours ? <span className="saved small">✓ Your bank</span>
                    : <button className="button-quiet" disabled={act.busy || (career.bank !== null && !career.bank.can_move)}
                              onClick={() => act.run(() => api.chooseBank(bank.ticker))}>{career.bank ? "Move here" : "Choose"}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {career.bank && !career.bank.can_move && <p className="muted small">You joined {career.bank.name} this quarter. You can move after the quarter ends.</p>}
    </Panel>
  );
}

function EmployerChoice({ career, act, onLoggedOut }: { career: Career; act: ReturnType<typeof useAction>; onLoggedOut: () => void }) {
  const openings = useLoad(api.employers, `employers:${career.build}:${career.job?.ticker ?? ""}`, onLoggedOut);
  const [all, setAll] = useState(false);
  const rows = openings.data ?? [];
  const shown = all ? rows : rows.filter((row) => row.yours || row.places_left > 0).slice(0, 12);
  return (
    <Panel title={career.job ? "Your employer" : "Step 3 · Find an employer"} aside={`${rows.length} companies hire your build`}>
      <p className="small">
        A new professional starts in a salaried job. The pay is the same wherever you go, so choose by the company: one that is
        behind on its bills may pay you late.
      </p>
      <div className="scroll">
        <table>
          <thead><tr><th scope="col">Company</th><th scope="col">Industry</th><th scope="col">Head office</th><th scope="col">Rating</th><th scope="col" className="num">Places</th><th scope="col"></th></tr></thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.ticker} className={row.yours ? "row-chosen" : undefined}>
                <th scope="row"><a href={`#/companies/${row.ticker}`}>{row.name}</a>{row.behind_on_bills && <span className="small change-down"> ▼ behind on its bills</span>}</th>
                <td>{row.sector}</td>
                <td>{row.headquarters}</td>
                <td>{row.rating ? <Rating value={row.rating} /> : "—"}</td>
                <td className="num mono">{row.places_left}</td>
                <td className="num">
                  {row.yours ? <span className="saved small">✓ Your employer</span>
                    : <button className="button-quiet" disabled={act.busy || row.places_left === 0 || !career.bank || (career.job !== null && !career.job.can_move)}
                              onClick={() => act.run(() => api.takeJob(row.ticker))}>{career.job ? "Move here" : "Join"}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > shown.length && <button className="button-quiet" onClick={() => setAll(true)}>Show all {rows.length}</button>}
      {!career.bank && <p className="muted small">Choose your bank first: your employer needs to know where to pay you.</p>}
      {career.job && !career.job.can_move && <p className="muted small">You started at {career.job.name} this quarter. You can move after the quarter ends.</p>}
      {career.job && (
        <div className="step-actions">
          <button className="button-quiet" disabled={act.busy} onClick={() => act.run(api.leaveJob)}>Resign from {career.job.name}</button>
          <span className="muted small">Pay for the quarter in hand is lost if you resign before pay day.</span>
        </div>
      )}
    </Panel>
  );
}

function Payslips({ career }: { career: Career }) {
  if (career.payslips.length === 0) return null;
  return (
    <Panel title="Payslips" aside="One for each quarter">
      <div className="scroll">
        <table>
          <thead><tr><th scope="col">Quarter</th><th scope="col">Employer</th><th scope="col" className="num">Salary</th><th scope="col" className="num">Tax</th><th scope="col" className="num">Living costs</th><th scope="col" className="num">Saved</th><th scope="col" className="num">Take-home</th></tr></thead>
          <tbody>
            {career.payslips.map((slip) => (
              <tr key={slip.period_label}>
                <th scope="row">{slip.period_label}<div className="muted small">Level {slip.level}{slip.note ? ` · ${slip.note}` : ""}</div></th>
                <td>{slip.employer}</td>
                <td className="num mono">{formatNaira(slip.gross_kobo)}</td>
                <td className="num mono">{formatNaira(slip.tax_kobo)}</td>
                <td className="num mono">{formatNaira(slip.living_costs_kobo)}</td>
                <td className="num mono">{formatNaira(slip.pension_yours_kobo)}</td>
                <td className="num mono strong">{formatNaira(slip.paid_kobo)}{BigInt(slip.owed_kobo) > 0n && <div className="small change-down">owed {formatNaira(slip.owed_kobo)}</div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function Retirement({ career, act }: { career: Career; act: ReturnType<typeof useAction> }) {
  const savings = career.retirement;
  if (!savings) return null;
  const pay = career.pay;
  return (
    <Panel title="Retirement savings" aside={savings.retired ? "Your pension is being paid" : "Locked until retirement"}>
      <div className="headline"><span className="figure-small mono">{formatNaira(savings.value_kobo)}</span>
        <span className="muted small">{savings.managed_by ? `with ${savings.managed_by}, a fund run by a player` : "with the pension funds, in your name"}</span>
        {savings.sound_finances && <span className="tag tag-passed">✓ Sound finances</span>}
      </div>
      <p className="small">
        Part of every salary is saved for you and your employer adds more. You choose the kind of fund that looks after it.
        It can be changed once in a game year, and a change takes effect from the next quarter. It is not cash: it cannot be
        spent or traded. No fund is safe from a bad quarter: each one's weakness is written beside it.
      </p>
      {savings.funds.map((fund) => (
        <div key={fund.code} className={fund.code === savings.fund && !savings.managed_by ? "definition row-chosen" : "definition"}>
          <div className="row">
            <span className="strong">{fund.code === savings.fund && !savings.managed_by ? "✓ " : ""}{fund.name}</span>
            <span>
              {fund.last_return_bps !== null && <span className="small">last quarter <Change bps={fund.last_return_bps} /> </span>}
              {fund.code !== savings.fund && !savings.managed_by && <button className="button-quiet" disabled={act.busy || !savings.can_change} onClick={() => act.run(() => api.chooseFund(fund.code))}>Move here</button>}
            </span>
          </div>
          <div className="muted small">
            {fund.shares_bps / 100}% shares, {fund.bonds_bps / 100}% bonds{fund.cash_bps ? `, ${fund.cash_bps / 100}% cash` : ""} · {fund.who_for}
          </div>
          <div className="small"><span className="change-up">▲ {fund.good}.</span> <span className="change-down">▼ {fund.bad}.</span></div>
          {fund.best_bps !== null && fund.worst_bps !== null && (
            <div className="muted small">
              Best quarter <Change bps={fund.best_bps} /> · worst quarter <Change bps={fund.worst_bps} />
              {fund.year_bps !== null && <> · over the last game year <Change bps={fund.year_bps} /></>}
              {fund.year_after_prices_bps !== null && <> · after rising prices <Change bps={fund.year_after_prices_bps} /></>}
            </div>
          )}
        </div>
      ))}

      <div className="why-title">SAVE MORE, AND BE REWARDED FOR IT</div>
      <p className="small">
        You may save up to {savings.most_extra_bps / 100}% of your salary on top of the usual amount. What you save extra is taken
        before income tax, so you pay less tax; your employer matches it, naira for naira, up to {savings.match_most_bps / 100}% of
        your salary; and savings worth two quarters of salary earn the "sound finances" mark, which employers look for.
        Your one early withdrawal (up to half) may be used to found an empire{savings.early_withdrawal_used ? ": you have used it" : ""}.
      </p>
      <div className="row">
        <span>Extra saving from each salary</span>
        <span>
          {[0, 500, 1000, 1500, 2000].filter((bps) => bps <= savings.most_extra_bps).map((bps) => (
            <button key={bps} className={savings.extra_bps === bps ? "button-outline" : "button-quiet"} disabled={act.busy} aria-pressed={savings.extra_bps === bps}
                    onClick={() => act.run(() => api.setExtraSaving(bps))}>{bps / 100}%</button>
          ))}
        </span>
      </div>
      {pay && savings.extra_bps > 0 && (
        <div className="muted small">At your level: {formatNaira(pay.extra_saving_kobo)} extra saved each quarter, and {formatNaira(pay.employer_match_kobo)} added by your employer.</div>
      )}

      <div className="why-title">WHEN IS RETIREMENT?</div>
      {savings.retired ? (
        <p className="small">✓ Your pension is paid every quarter: a fortieth of your savings each time. You may keep working.</p>
      ) : (
        <>
          <p className="small">
            At Level {savings.retirement_level}, or after ten game years of work (forty quarters), whichever comes first.
            {savings.can_retire ? " You may begin your pension now." : savings.retires_label ? ` For you that is ${savings.retires_label}: ${savings.quarters_to_go} quarters to go.` : " The count begins with your first job."}
            {" "}From then a pension is paid to you every quarter, and you may keep working.
          </p>
          {savings.can_retire && <button className="button-outline" disabled={act.busy} onClick={() => act.run(api.beginPension)}>Begin my pension</button>}
        </>
      )}

      {savings.entries.length > 0 && (
        <div className="scroll">
          <table>
            <thead><tr><th scope="col">Quarter</th><th scope="col" className="num">You paid in</th><th scope="col" className="num">Employer paid in</th><th scope="col" className="num">The fund earned</th><th scope="col" className="num">Pension paid</th><th scope="col" className="num">Savings</th></tr></thead>
            <tbody>
              {savings.entries.map((entry) => (
                <tr key={entry.period_label}>
                  <th scope="row">{entry.period_label} <span className="muted small">{entry.fund === "managed" ? "player-run fund" : entry.fund}</span></th>
                  <td className="num mono">{formatNaira(entry.paid_in_by_you_kobo)}</td>
                  <td className="num mono">{formatNaira(entry.paid_in_by_employer_kobo)}</td>
                  <td className={entry.growth_kobo.startsWith("-") ? "num mono change-down" : "num mono"}>{entry.growth_kobo.startsWith("-") ? "▼ " : ""}{formatNaira(entry.growth_kobo.replace("-", ""))}</td>
                  <td className="num mono">{BigInt(entry.paid_out_kobo) > 0n ? formatNaira(entry.paid_out_kobo) : "—"}</td>
                  <td className="num mono strong">{formatNaira(entry.closing_kobo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

export function CareerWork({ player, onLoggedOut, onChanged }: Props) {
  const career = useLoad(api.career, `career:${player.build}:${player.employer}`, onLoggedOut);
  const act = useAction(() => { career.reload(); onChanged(); });
  if (career.loading && !career.data) return <Loading what="your career" />;
  if (career.error || !career.data) return <Failed message={career.error ?? "Could not load your career."} onRetry={career.reload} />;
  const data = career.data;
  const settled = data.build !== null && data.bank !== null && data.job !== null;
  return (
    <>
      <div className="work-head">
        <h1>{settled ? "Your career" : "Start your career"}</h1>
        <span className="muted small">{data.career ? `${data.career.build_name} · Level ${data.career.level}` : "Three steps"}</span>
      </div>
      {!settled && (
        <Panel>
          <ProgressTracker steps={[
            { label: "Choose your build", done: data.build !== null, note: data.career?.build_name },
            { label: "Choose your bank", done: data.bank !== null, note: data.bank?.name },
            { label: "Find an employer", done: data.job !== null, note: data.job?.name },
            { label: "Take on your first piece of work", done: false, note: "on the Work page" },
          ]} />
        </Panel>
      )}
      {act.error && <p className="error" role="alert">{act.error}</p>}
      {settled && <p className="saved" role="status">✓ You work for {data.job?.name} and bank with {data.bank?.name}. <a href="#/work">See the work on offer</a>.</p>}
      {!settled && (
        <>
          <BuildChoice career={data} act={act} />
          {data.build && <BankChoice career={data} act={act} onLoggedOut={onLoggedOut} />}
          {data.build && <EmployerChoice career={data} act={act} onLoggedOut={onLoggedOut} />}
        </>
      )}
      <Payslips career={data} />
      <Retirement career={data} act={act} />
      {data.build && <PensionFundsPanel player={player} onLoggedOut={onLoggedOut} onChanged={() => { career.reload(); onChanged(); }} />}
      {data.interest.length > 0 && (
        <Panel title="Interest from your bank">
          {data.interest.map((line) => (
            <div key={line.period_label} className="row">
              <span>{line.period_label} · {line.bank} <span className="muted small">on {formatNaira(line.lowest_balance_kobo)} at {formatPercent(line.rate_bps, 2)} a year</span></span>
              <span className="mono change-up">+ {formatNaira(line.amount_kobo)}</span>
            </div>
          ))}
        </Panel>
      )}
      {settled && (
        <>
          <EmployerChoice career={data} act={act} onLoggedOut={onLoggedOut} />
          <BankChoice career={data} act={act} onLoggedOut={onLoggedOut} />
          <BuildChoice career={data} act={act} />
        </>
      )}
    </>
  );
}

export function CareerRail({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const career = useLoad(api.career, `career-rail:${player.build}:${player.employer}:${player.level}`, onLoggedOut);
  const data = career.data;
  if (!data) return null;
  return (
    <>
      {data.career && <LevelPanel career={data.career} />}
      <PayPanel career={data} />
      <Panel title="Standing">
        <div className="row"><span>Reputation</span><span className="mono">{data.reputation} of 100</span></div>
        <p className="muted small">Everybody starts at 50. Each piece of work passed adds to it. Level, reputation and wealth are kept apart: none can be bought with another.</p>
      </Panel>
      {data.events.length > 0 && (
        <Panel title="Your record">
          {data.events.slice(0, 8).map((event, index) => (
            <div key={index} className="news-line">
              <div className="small muted">{new Date(event.at).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" })}</div>
              <div className="small">{event.words}</div>
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}
