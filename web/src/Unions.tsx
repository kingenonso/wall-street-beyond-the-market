// Unions and strikes, part 1 (owner, 16 November 2026: "build"; the leaders are computer-run). No tab of its own (owner,
// 17 November 2026): the Labour section of the Economy page, and a union panel on each company's page. A demand is shown
// only from its day. Every figure comes from the server.

import { useEffect, useState } from "react";
import { api, ApiError, type UnionDispute, type UnionsPage, type UnionTable } from "./api";
import { formatCompact } from "./format";
import { useLoad } from "./hooks";
import { Band, BandCell, Panel } from "./Shell";

const pct = (bps: number) => `${(bps / 100).toFixed(1).replace(/\.0$/, "")}%`;
const temper = (bps: number) => (bps >= 7000 ? "quick to strike" : bps >= 5000 ? "firm" : bps >= 4000 ? "steady" : "patient");

function Dispute({ d }: { d: UnionDispute }) {
  const striking = d.status_words === "on strike now";
  return (
    <div className={`union-row ${striking ? "union-strike" : ""}`}>
      <div className="union-row-head">
        <strong>{d.company}</strong> <span className="mono small muted">{d.ticker}</span>
        <span className={`union-status small ${striking ? "change-down strong" : ""}`}>{d.status_words}</span>
      </div>
      <p className="small">
        The {d.union} asks {pct(d.demand_bps)} more pay
        {d.status === "open" && d.days_left !== null && <> · the board must answer within {d.days_left === 0 ? "the day" : `${d.days_left} game day${d.days_left === 1 ? "" : "s"}`} (day {d.deadline_day})</>}
        {d.offer_bps !== null && <> · {d.answer === "board" || d.answer === null ? "the board offered" : d.answer === "none" ? "no answer came" : "the offer was"} {d.answer === "none" ? "" : pct(d.offer_bps)}</>}
        {d.strike_days !== null && <> · strike of {d.strike_days} game days{striking && d.ends_day ? `, until day ${d.ends_day}` : ""}</>}
        {d.settled_bps !== null && <> · settled at {pct(d.settled_bps)}</>}
        {d.answer && d.answer !== "board" && d.status !== "open" && <> · {ANSWER_WORDS[d.answer]}</>}
        {d.mediator && <> · a mediator {d.mediator_worked === null ? "is at work" : d.mediator_worked ? "helped" : "could not help"}</>}
        <span className="muted"> · {d.city}, {d.quarter}</span>
      </p>
      {d.reasons.length > 0 && <ul className="small muted union-why">{d.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
    </div>
  );
}

/** Economy page: the Labour section. */
export function LabourPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const page = useLoad(api.unions, "unions", onLoggedOut);
  const reload = page.reload;
  useEffect(() => {
    const id = window.setInterval(reload, 120_000);
    return () => window.clearInterval(id);
  }, [reload]);
  const d = page.data;
  if (!d || !d.ready) return null;
  const open = d.open ?? [], past = d.past ?? [], deals = d.deals ?? [], rules = d.rules!;
  const striking = open.filter((x) => x.status_words === "on strike now").length;
  return (
    <section id="labour" className="labour">
      <h2 className="season-head">Labour: unions and strikes <span className="small muted">{d.quarter} · day {d.day}</span></h2>
      <Band label="Labour now" columns={4}>
        <BandCell label="Prices against pay" value={d.squeeze_bps ? `prices ${pct(d.squeeze_bps)} ahead` : "pay keeping up"} note="over the last year" />
        <BandCell label="Demands open" value={open.length - striking} note={`${rules.notice_days} game days to answer`} />
        <BandCell label="On strike now" value={striking} note="sales lost every day" />
        <BandCell label="Pay deals in force" value={deals.length} note="above the going rate" />
      </Band>
      <Panel title="Disputes now" aside="shown from the day each is made public">
        {open.length === 0 ? <p className="muted small">No union has a demand open, and nobody is on strike.</p> : open.map((x) => <Dispute key={x.id} d={x} />)}
      </Panel>
      <details className="labour-more">
        <summary>The unions, the pay deals in force, earlier disputes, and how it works</summary>
        <Panel title="How it works" aside="the leaders are run by the computer">
          <ul className="small">
            <li><strong>Why staff get angry.</strong> At each quarter's close the staff of every listed company weigh up the quarter: prices rising faster than pay, profits well up while pay stood still, jobs cut, a dividend paid while pay fell behind. A pay deal calms them, and so does a recent strike: nobody is paid while they are out. The leader's temper scales it all.</li>
            <li><strong>The demand.</strong> An angry enough workforce asks for a rise of {pct(rules.demand_bps[0])} to {pct(rules.demand_bps[1])}. It is made public on a day in the coming quarter, and the board has {rules.notice_days} game days to answer.</li>
            <li><strong>The answer.</strong> The board weighs a year of the higher wage bill against what a strike would cost it, and agrees, offers less, or refuses. A calm leader takes half the demand; the most militant only the full rise.</li>
            <li><strong>The strike.</strong> {rules.strike_days[0]} to {rules.strike_days[1]} game days of lost sales, shown in the quarter's results. It ends in a deal halfway between the demand and the offer.</li>
            <li><strong>The deal.</strong> The company pays above the going rate; the going rate closes {pct(rules.catch_up_bps)} of the gap each quarter.</li>
          </ul>
        </Panel>
        <Panel title="The unions" aside="one for each industry outside banking and insurance">
          <table className="dense">
            <thead><tr><th scope="col">Union</th><th scope="col">Industry</th><th scope="col">Leader</th><th scope="col">Temper</th><th scope="col" className="num">Disputes</th><th scope="col" className="num">Strikes</th><th scope="col" className="num">Days out</th></tr></thead>
            <tbody>{(d.unions ?? []).map((u) => (
              <tr key={u.name}><th scope="row">{u.name}</th><td>{u.industry}</td><td>{u.leader}</td><td>{temper(u.militancy_bps)}</td>
                <td className="num">{u.disputes}</td><td className="num">{u.strikes}</td><td className="num">{u.strike_days}</td></tr>
            ))}</tbody>
          </table>
        </Panel>
        {deals.length > 0 && (
          <Panel title="Pay deals in force" aside="how far above the going rate">
            <table className="dense">
              <thead><tr><th scope="col">Company</th><th scope="col" className="num">Above the going rate</th></tr></thead>
              <tbody>{deals.map((x) => <tr key={x.ticker}><th scope="row"><a href={`#/companies/${x.ticker}`}>{x.company}</a> <span className="mono small muted">{x.ticker}</span></th><td className="num mono">{pct(x.above_bps)}</td></tr>)}</tbody>
            </table>
          </Panel>
        )}
        <Panel title="Earlier disputes" aside="the last year">
          {past.length === 0 ? <p className="muted small">None yet.</p> : past.map((x) => <Dispute key={x.id} d={x} />)}
        </Panel>
      </details>
    </section>
  );
}

const ANSWER_WORDS: Record<string, string> = {
  agree: "the head agreed", offer: "the head offered less", refuse: "the head refused", none: "nobody answered in time", board: "the board answered",
};

/** Part 2: the empire at the table. The head answers; members advise; the numbers come from the server. */
function Table({ d, t, run, busy }: { d: UnionDispute; t: UnionTable; run: (ask: () => Promise<UnionsPage>, words?: (p: UnionsPage) => string) => void; busy: boolean }) {
  const [offer, setOffer] = useState(String(Math.round(t.risk.fair_bps / 100) || Math.round(d.demand_bps / 200)));
  const [advice, setAdvice] = useState<"agree" | "offer" | "refuse">("offer");
  const [note, setNote] = useState("");
  const offerBps = Math.round(Number(offer) * 100);
  const offerOk = Number.isFinite(offerBps) && offerBps > 0 && offerBps < d.demand_bps;
  const r = t.risk, b = t.banker, a = t.asset;
  return (
    <div className="union-table">
      <h3 className="small">At the table: {t.is_head ? "you answer for the empire" : "the head answers; you can advise"}</h3>
      <div className="union-views">
        <div>
          <p className="small strong">Risk Manager's view: the trade-off</p>
          <ul className="small">
            <li>A strike of {r.days[0]}, {r.days[1]} or {r.days[2]} game days would cost about {formatCompact(r.strike_short)}, {formatCompact(r.strike_middle)} or {formatCompact(r.strike_long)} in lost profit.</li>
            <li>The full {pct(d.demand_bps)} costs about {formatCompact(r.rise_two_years)} in wages over two years (a deal fades as the going rate catches up).</li>
            <li>The rise that costs the same as a middle-length strike: about {pct(r.fair_bps)}, or {formatCompact(r.fair_two_years)} over two years.</li>
          </ul>
        </div>
        <div>
          <p className="small strong">Investment Banker's view: what it does to the company</p>
          <ul className="small">
            <li>The company is valued at about {formatCompact(b.value)}; last quarter's profit was {formatCompact(b.profit_quarter)}.</li>
            {b.strike_share_bps !== null && <li>A middle-length strike takes about {pct(b.strike_share_bps)} of that value in lost profit, and shows in the quarter's results a buyer will read.</li>}
          </ul>
        </div>
        <div>
          <p className="small strong">Asset Manager's view: the staff and the union</p>
          <ul className="small">
            <li>It pays {a.pay_vs_going_bps === 0 ? "the going rate" : `${pct(Math.abs(a.pay_vs_going_bps))} ${a.pay_vs_going_bps > 0 ? "above" : "below"} the going rate`}{a.morale_bps !== null ? `; staff morale ${Math.round(a.morale_bps / 100)} out of 100` : ""}.</li>
            <li>This union is {temper(a.temper_bps)}: {a.union_disputes} dispute{a.union_disputes === 1 ? "" : "s"} and {a.union_strikes} strike{a.union_strikes === 1 ? "" : "s"} in the last year.</li>
            {a.stake_cost && <li>The empire paid {formatCompact(a.stake_cost)} for its stake.</li>}
          </ul>
        </div>
      </div>
      {t.advice.length > 0 && (
        <div className="small">
          <p className="strong">Advice on record</p>
          <ul>{t.advice.map((x, i) => <li key={i}>{x.name} ({x.build}): {x.advice === "offer" && x.offer_bps ? `offer ${pct(x.offer_bps)}` : x.advice}{x.note ? `. "${x.note}"` : ""}</li>)}</ul>
        </div>
      )}
      {t.is_head ? (
        <div className="union-answer">
          <button disabled={busy} onClick={() => run(() => api.unionAnswer(d.id, "agree"), () => `You agreed to ${pct(d.demand_bps)}.`)}>Agree to {pct(d.demand_bps)}</button>
          <span className="union-offer">
            <input className="mono" inputMode="decimal" aria-label="Your offer, in percent" value={offer} onChange={(e) => setOffer(e.target.value)} />%
            <button disabled={busy || !offerOk} onClick={() => run(() => api.unionAnswer(d.id, "offer", offerBps), (p) => answerWords(p, d.id))}>Offer {offerOk ? pct(offerBps) : "less"}</button>
          </span>
          <button className="button-outline" disabled={busy} onClick={() => run(() => api.unionAnswer(d.id, "refuse"), (p) => answerWords(p, d.id))}>Refuse</button>
          <button className="button-outline small" disabled={busy || !t.can_more_time} onClick={() => run(() => api.unionMoreTime(d.id))}>
            {t.more_time === "granted" ? "More time given" : t.more_time === "refused" ? "More time refused" : "Ask for more time"}</button>
          <button className="button-outline small" disabled={busy || !!t.mediator_fee} onClick={() => run(() => api.unionMediator(d.id), () => "A mediator is at work. Whether it helped shows when the union answers.")}>
            {t.mediator_fee ? `Mediator hired (${formatCompact(t.mediator_fee)})` : `Hire a mediator (${formatCompact(t.mediator_quote)})`}</button>
          <p className="small muted">If nobody answers by day {d.deadline_day}, the staff take it as a no and walk out.</p>
        </div>
      ) : (
        <div className="union-answer">
          <select aria-label="Your advice" value={advice} onChange={(e) => setAdvice(e.target.value as "agree" | "offer" | "refuse")}>
            <option value="agree">Agree</option><option value="offer">Offer less</option><option value="refuse">Refuse</option>
          </select>
          {advice === "offer" && <span className="union-offer"><input className="mono" inputMode="decimal" aria-label="Offer, in percent" value={offer} onChange={(e) => setOffer(e.target.value)} />%</span>}
          <input className="union-note" maxLength={300} placeholder="A short note for the head (optional)" aria-label="A note for the head" value={note} onChange={(e) => setNote(e.target.value)} />
          <button disabled={busy || (advice === "offer" && !offerOk)} onClick={() => run(() => api.unionAdvise(d.id, advice, advice === "offer" ? offerBps : null, note), () => "Your advice is on record for the head.")}>Advise the head</button>
        </div>
      )}
    </div>
  );
}

function answerWords(p: UnionsPage, id: number): string {
  const d = [...(p.company?.now ?? []), ...(p.company?.past ?? [])].find((x) => x.id === id);
  if (!d) return "Answered.";
  if (d.status === "agreed") return `The union took ${pct(d.settled_bps ?? 0)}. No strike.`;
  return `The union walked out, for about ${d.strike_days} game days.`;
}

/** A company's page: its union, any dispute now, and its pay deal; for the controlling empire, the table. */
export function CompanyUnionPanel({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const page = useLoad(() => api.unions(ticker), `unions:${ticker}`, onLoggedOut);
  const [fresh, setFresh] = useState<UnionsPage | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ ok: boolean; words: string } | null>(null);
  const c = (fresh ?? page.data)?.company;
  if (!c) return null;
  async function run(ask: () => Promise<UnionsPage>, words?: (p: UnionsPage) => string) {
    setBusy(true); setSaid(null);
    try {
      const p = await ask(); setFresh(p);
      const r = p as UnionsPage & { result?: { words?: string } };
      setSaid({ ok: true, words: words ? words(p) : r.result?.words ?? "Done." });
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setSaid({ ok: false, words: problem instanceof ApiError ? problem.message : "Could not reach the server." });
    } finally { setBusy(false); }
  }
  return (
    <Panel title="Its union" aside={<a href="#/economy">All unions</a>}>
      <p className="small"><strong>{c.union}</strong>, led by {c.leader} ({temper(c.militancy_bps)}).
        {c.above_bps > 0 ? ` A pay deal has it paying ${pct(c.above_bps)} above the going rate.` : ""}
        {c.empire ? ` ${c.empire} controls it, so its head answers the union.` : " Its board answers the union."}</p>
      {said && <p className={`small ${said.ok ? "" : "change-down"}`} role={said.ok ? "status" : "alert"}>{said.words}</p>}
      {c.now.length > 0 ? c.now.map((x) => (
        <div key={x.id}>
          <Dispute d={x} />
          {x.table && <Table d={x} t={x.table} run={run} busy={busy} />}
        </div>
      )) : <p className="muted small">No demand open and nobody on strike.</p>}
      {c.past.length > 0 && <p className="small muted">Earlier: {c.past.map((x) => `${x.quarter} ${x.status_words}${x.settled_bps !== null ? ` at ${pct(x.settled_bps)}` : ""}${x.answer && x.answer !== "board" ? ` (${ANSWER_WORDS[x.answer]})` : ""}`).join(" · ")}</p>}
    </Panel>
  );
}
