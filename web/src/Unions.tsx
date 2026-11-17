// Unions and strikes, part 1 (owner, 16 November 2026: "build"; the leaders are computer-run). Economy → Unions: the
// unions of each industry, the pay demands the public knows of, strikes under way, and the pay deals in force. A demand
// is shown only from its day. Every figure comes from the server.

import { useEffect } from "react";
import { api, type Player, type UnionDispute } from "./api";
import { useLoad } from "./hooks";
import { Band, BandCell, Failed, Loading, PageHead, Panel } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void };
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
        {d.offer_bps !== null && <> · the board offered {pct(d.offer_bps)}</>}
        {d.strike_days !== null && <> · strike of {d.strike_days} game days{striking && d.ends_day ? `, until day ${d.ends_day}` : ""}</>}
        {d.settled_bps !== null && <> · settled at {pct(d.settled_bps)}</>}
        <span className="muted"> · {d.city}, {d.quarter}</span>
      </p>
      {d.reasons.length > 0 && <ul className="small muted union-why">{d.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
    </div>
  );
}

export function UnionsWork({ onLoggedOut }: Props) {
  const page = useLoad(api.unions, "unions", onLoggedOut);
  const reload = page.reload;
  useEffect(() => {
    const id = window.setInterval(reload, 120_000);
    return () => window.clearInterval(id);
  }, [reload]);
  if (page.loading && !page.data) return <Loading what="the unions" />;
  if (page.error || !page.data) return <Failed message={page.error ?? "Could not load the unions."} onRetry={page.reload} />;
  const d = page.data;
  if (!d.ready) return <Panel title="Unions"><p className="small">Unions have not formed in this world yet.</p></Panel>;
  const open = d.open ?? [], past = d.past ?? [], deals = d.deals ?? [], rules = d.rules!;
  const striking = open.filter((x) => x.status_words === "on strike now").length;
  return (
    <>
      <PageHead title="Unions" sub="Every industry's workers, their pay demands and their strikes" aside={`${d.quarter} · day ${d.day}`} />
      <Band label="Labour now" columns={4}>
        <BandCell label="Prices against pay" value={d.squeeze_bps ? `prices ${pct(d.squeeze_bps)} ahead` : "pay keeping up"} note="over the last year" />
        <BandCell label="Demands open" value={open.length - striking} note={`${rules.notice_days} game days to answer`} />
        <BandCell label="On strike now" value={striking} note="sales lost every day" />
        <BandCell label="Pay deals in force" value={deals.length} note="above the going rate" />
      </Band>
      <Panel title="Disputes now" aside="shown from the day each is made public">
        {open.length === 0 ? <p className="muted small">No union has a demand open, and nobody is on strike.</p> : open.map((x) => <Dispute key={x.id} d={x} />)}
      </Panel>
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
            <tbody>{deals.map((x) => <tr key={x.ticker}><th scope="row">{x.company} <span className="mono small muted">{x.ticker}</span></th><td className="num mono">{pct(x.above_bps)}</td></tr>)}</tbody>
          </table>
        </Panel>
      )}
      <Panel title="Earlier disputes" aside="the last year">
        {past.length === 0 ? <p className="muted small">None yet.</p> : past.map((x) => <Dispute key={x.id} d={x} />)}
      </Panel>
    </>
  );
}
