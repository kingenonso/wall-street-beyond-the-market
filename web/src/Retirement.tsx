// Retirement, as a page of its own under Money.
//
// The owner's instruction of 9 November 2026 was that retirement should "go hard". It was already a
// rule in the engine — eight per cent of every salary, the employer's ten on top, six kinds of fund
// with their own weaknesses, an early pension that is smaller for good, one early withdrawal in a
// whole career — but it was three levels down inside Work › Career, below the payslips, and the only
// way to see where it was heading was to wait a decade. This page is the whole of it in one place,
// and the one thing it adds is a projection: what the pot becomes, and what it then pays.
//
// The projection is the server's figure, not this file's. Rule 1 of the working rules is that every
// important value is worked out in exactly one place, and this screen's job is to print it.

import { api, type Career, type Player } from "./api";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Failed, Loading, PageHead, Panel } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void; onChanged: () => void };

/** One bar that runs the whole way: the pot now, the pot at the end. Drawn from server figures only. */
function ProjectionBar({ now, then }: { now: string; then: string }) {
  const start = BigInt(now);
  const end = BigInt(then);
  // A pot that only grows makes the "now" mark a fraction of the bar. A pot that is projected to fall
  // (a fund that loses money) still shows its mark at the right-hand end rather than off the bar.
  const share = start > 0n && end > start ? Number((start * 1000n) / end) / 10 : 0;
  return (
    <div className="meter" role="img" aria-label={`Today the pot is ${formatNaira(now)}; at retirement it is projected to be ${formatNaira(then)}.`}>
      <div className="meter-fill meter-saved" style={{ width: `${Math.max(Math.min(share, 100), 2)}%` }} />
    </div>
  );
}

export function RetirementWork({ player, onLoggedOut, onChanged }: Props) {
  const career = useLoad(api.career, `retirement:${player.build}`, onLoggedOut);
  if (career.loading && !career.data) return <Loading what="your retirement savings" />;
  if (career.error || !career.data) return <Failed message={career.error ?? "Could not load your retirement savings."} onRetry={career.reload} />;

  const data: Career = career.data;
  const savings = data.retirement;
  const after = () => { career.reload(); onChanged(); };

  if (!savings) {
    return (
      <>
        <PageHead title="Retirement" sub="Money set aside for you out of every salary" />
        <Panel title="You have no retirement savings yet">
          <p className="small">
            Retirement saving begins with your first salary. Eight per cent is taken from your pay before tax and
            your employer adds ten per cent on top; neither part is yours to spend until you retire. Find an employer
            and the pot opens itself. <a href="#/career">Look for work on your career page</a>.
          </p>
        </Panel>
      </>
    );
  }

  const projection = savings.projection;
  const paid = savings.entries.reduce(
    (total, entry) => ({ you: total.you + BigInt(entry.paid_in_by_you_kobo), employer: total.employer + BigInt(entry.paid_in_by_employer_kobo) }),
    { you: 0n, employer: 0n });

  return (
    <>
      <PageHead title="Retirement" sub="Money set aside for you out of every salary. It is not cash: it cannot be spent or traded."
                aside={<span className="mono">{formatNaira(savings.value_kobo)}</span>} />

      <section className="band band-4" aria-label="Your retirement savings">
        <div className="band-cell">
          <div className="band-label">Your pot</div>
          <div className="band-value">{formatCompact(savings.value_kobo)}</div>
          <div className="band-note">{savings.managed_by ? `looked after by ${savings.managed_by}, a fund run by a player` : "with the pension funds, in your name"}</div>
        </div>
        <div className="band-cell">
          <div className="band-label">{savings.retired ? "Paid to you each quarter" : "Projected when it opens"}</div>
          <div className="band-value">{savings.retired ? formatPercent(savings.pension_bps ?? savings.full_pension_bps, 1) : projection ? formatCompact(projection.value_then_kobo) : "—"}</div>
          <div className="band-note">{savings.retired ? "of the pot, every quarter, for as long as it lasts" : "an estimate: see what it assumes"}</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Quarters of work behind you</div>
          <div className="band-value">{savings.quarters_worked.toLocaleString("en-NG")}</div>
          <div className="band-note">only quarters you were paid a salary for count</div>
        </div>
        <div className="band-cell">
          <div className="band-label">The mark employers look for</div>
          <div className={`band-value ${savings.sound_finances ? "change-up" : "muted"}`}>{savings.sound_finances ? "✓ Sound finances" : "Not yet"}</div>
          <div className="band-note">savings worth two quarters of your salary</div>
        </div>
      </section>

      {savings.retired ? (
        <Panel title="Your pension is being paid" aside={`${formatPercent(savings.pension_bps ?? savings.full_pension_bps, 1)} a quarter`}>
          <p className="small">
            It is paid out of the pot every quarter, by the pension funds, straight into your own account. You may keep
            working; what you earn keeps adding to the pot, and so the pension keeps being paid on a larger figure.
          </p>
        </Panel>
      ) : (
        <Panel title="Where this is heading" aside={projection ? `${projection.quarters} quarters to go` : "not yet projected"}>
          {projection ? (
            <>
              <div className="headline">
                <span className="figure-small mono">{formatNaira(projection.value_now_kobo)}</span>
                <span className="muted small">today · grows to</span>
                <span className="figure-small mono">{formatNaira(projection.value_then_kobo)}</span>
                <span className="muted small">on the day it can be drawn</span>
              </div>
              <ProjectionBar now={projection.value_now_kobo} then={projection.value_then_kobo} />
              <div className="row small">
                <span>And then it pays each quarter</span>
                <span className="mono">
                  {formatNaira(projection.pension_a_quarter_kobo)} on a full pension · {formatNaira(projection.early_pension_a_quarter_kobo)} on an early one
                </span>
              </div>
              <div className="why-title">What this estimate assumes, and it is only an estimate</div>
              <ul className="small">
                {projection.assumptions.map((line) => <li key={line}>{line}</li>)}
              </ul>
              <p className="muted small">
                Two of those will be wrong: nobody's salary stays flat for {projection.quarters} quarters, and no fund
                earns the same thing every quarter. Take it as the shape of the thing rather than a promise.
              </p>
            </>
          ) : (
            <p className="small">
              There is no estimate to give yet: the pension funds have not reported what they earned, so there is
              nothing honest to build one from. It will appear after the first quarter closes.
            </p>
          )}
        </Panel>
      )}

      <Panel title="The fund that looks after it" aside={savings.can_change ? "you may move it once a game year" : "moved this game year"}>
        <p className="small">
          Every fund mixes shares, bonds and cash in its own way, and each one's weakness is written beside it. A change
          takes effect from the next quarter. No fund is safe from a bad quarter.
        </p>
        {savings.funds.map((fund) => (
          <div key={fund.code} className={fund.code === savings.fund && !savings.managed_by ? "definition row-chosen" : "definition"}>
            <div className="row">
              <span className="strong">
                {fund.code === savings.fund && !savings.managed_by ? "✓ " : ""}{fund.name}
              </span>
              <span>
                {fund.last_return_bps !== null && <span className="small">last quarter {formatPercent(fund.last_return_bps, 2)} </span>}
                {fund.code !== savings.fund && !savings.managed_by && (
                  <button className="button-quiet" disabled={!savings.can_change}
                          onClick={() => api.chooseFund(fund.code).then(after).catch(() => undefined)}>Move here</button>
                )}
              </span>
            </div>
            <div className="muted small">
              {fund.shares_bps / 100}% shares, {fund.bonds_bps / 100}% bonds{fund.cash_bps ? `, ${fund.cash_bps / 100}% cash` : ""} · {fund.who_for}
            </div>
            <div className="small"><span className="change-up">▲ {fund.good}.</span> <span className="change-down">▼ {fund.bad}.</span></div>
            {fund.best_bps !== null && fund.worst_bps !== null && (
              <div className="muted small">
                Best quarter {formatPercent(fund.best_bps, 2)} · worst quarter {formatPercent(fund.worst_bps, 2)}
                {fund.year_bps !== null && <> · over the last game year {formatPercent(fund.year_bps, 2)}</>}
                {fund.year_after_prices_bps !== null && <> · after rising prices {formatPercent(fund.year_after_prices_bps, 2)}</>}
              </div>
            )}
          </div>
        ))}
      </Panel>

      <Panel title="Save more, and be rewarded for it" aside={`up to ${savings.most_extra_bps / 100}% extra`}>
        <p className="small">
          What you save extra is taken before income tax, so you pay less tax; your employer matches it, naira for
          naira, up to {savings.match_most_bps / 100}% of your salary; and it brings the "sound finances" mark closer,
          which employers look for.
        </p>
        <div className="row">
          <span>Extra saving from each salary</span>
          <span>
            {[0, 500, 1000, 1500, 2000].filter((bps) => bps <= savings.most_extra_bps).map((bps) => (
              <button key={bps} className={savings.extra_bps === bps ? "button-outline" : "button-quiet"} aria-pressed={savings.extra_bps === bps}
                      onClick={() => api.setExtraSaving(bps).then(after).catch(() => undefined)}>{bps / 100}%</button>
            ))}
          </span>
        </div>
        {data.pay && savings.extra_bps > 0 && (
          <div className="muted small">
            At your level: {formatNaira(data.pay.extra_saving_kobo)} extra saved each quarter, and {formatNaira(data.pay.employer_match_kobo)} added by your employer.
          </div>
        )}
      </Panel>

      <Panel title="When you may draw it" aside={savings.retired ? "being drawn" : `${savings.quarters_to_go} quarters at most`}>
        <p className="small">
          <strong>Full pension</strong> ({formatPercent(savings.full_pension_bps, 1)} of the pot each quarter): at Level{" "}
          {savings.retirement_level}, or after forty quarters of work (forty real weeks), whichever comes first.
          {savings.can_retire ? " You may begin it now." : savings.retires_label ? ` For you that is ${savings.retires_label}: ${savings.quarters_to_go} quarters to go.` : " Only quarters you were paid a salary for count."}
        </p>
        <p className="small">
          <strong>Early pension</strong> ({formatPercent(savings.early_pension_bps, 1)} each quarter, smaller for good): at Level{" "}
          {savings.early_level}, or after twenty quarters of work.
          {savings.can_retire_early ? " You may begin it now." : !savings.can_retire && savings.early_label ? ` For you that is ${savings.early_label}: ${savings.early_quarters_to_go} quarters to go.` : ""}
          {" "}Either way the pension is paid every quarter, and you may keep working. Retiring early is the real
          trade-off: money sooner, less of it.
        </p>
        {!savings.retired && savings.can_retire && (
          <button className="button-primary" onClick={() => api.beginPension(false).then(after).catch(() => undefined)}>Begin my full pension</button>
        )}
        {!savings.retired && savings.can_retire_early && (
          <button className="button-outline" onClick={() => api.beginPension(true).then(after).catch(() => undefined)}>
            Begin an early pension ({formatPercent(savings.early_pension_bps, 1)})
          </button>
        )}
        <div className="why-title">The one early withdrawal</div>
        <p className="small">
          Once in a whole career you may take out up to {savings.early_withdrawal_most_bps / 100}% of the pot to found an
          empire. It is the only money that ever comes out early{savings.early_withdrawal_used ? ", and you have used it" : ", and you have not used it"}.
        </p>
      </Panel>

      <Panel title="Where it came from, quarter by quarter" aside={paid.you + paid.employer > 0n ? `${formatCompact((paid.you + paid.employer).toString())} paid in over the last ${savings.entries.length} quarters` : undefined}>
        {savings.entries.length === 0 ? (
          <p className="small">Nothing has been paid in yet. Your first salary opens the record.</p>
        ) : (
          <div className="scroll" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th scope="col">Quarter</th><th scope="col" className="num">Opening</th><th scope="col" className="num">You paid in</th>
                  <th scope="col" className="num">Employer paid in</th><th scope="col" className="num">The fund earned</th>
                  <th scope="col" className="num">Pension paid</th><th scope="col" className="num">Closing</th>
                </tr>
              </thead>
              <tbody>
                {savings.entries.map((entry) => (
                  <tr key={entry.period_label}>
                    <th scope="row">{entry.period_label} <span className="muted small">{entry.fund === "managed" ? "player-run fund" : entry.fund}</span></th>
                    <td className="num mono">{formatNaira(entry.opening_kobo)}</td>
                    <td className="num mono">{formatNaira(entry.paid_in_by_you_kobo)}</td>
                    <td className="num mono">{formatNaira(entry.paid_in_by_employer_kobo)}</td>
                    <td className={entry.growth_kobo.startsWith("-") ? "num mono change-down" : "num mono"}>
                      {entry.growth_kobo.startsWith("-") ? "▼ " : ""}{formatNaira(entry.growth_kobo.replace("-", ""))}
                    </td>
                    <td className="num mono">{BigInt(entry.paid_out_kobo) > 0n ? formatNaira(entry.paid_out_kobo) : "—"}</td>
                    <td className="num mono strong">{formatNaira(entry.closing_kobo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

/** One line on the career page pointing at this screen, so there is only ever one version of the truth. */
export function RetirementLine({ career }: { career: Career }) {
  const savings = career.retirement;
  if (!savings) return null;
  return (
    <Panel title="Retirement savings" aside={<a href="#/retirement">Open the retirement page</a>}>
      <div className="row">
        <span>Your pot, in a fund that is {savings.retired ? "paying your pension" : "locked until you retire"}</span>
        <span className="mono">{formatNaira(savings.value_kobo)}</span>
      </div>
      {savings.projection && !savings.retired && (
        <p className="muted small">
          Projected to be {formatCompact(savings.projection.value_then_kobo)} when it opens, which would pay about{" "}
          {formatNaira(savings.projection.pension_a_quarter_kobo)} a quarter.
        </p>
      )}
    </Panel>
  );
}
