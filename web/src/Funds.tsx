// Run Your Own Fund (the talent and funds stage, Part 2): open investment funds. Anybody puts money in or asks it back,
// dealt at the next closing bell's price; an Asset Manager of Level 20 launches one and runs it under the rules. The four
// funds Broad Street Asset Management runs are there from the start. The website only asks; the server decides.

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type FundManaging, type FundSheet, type FundStrategy, type FundSummary, type FundsPage, type FundAlert } from "./api";
import { AmountForm } from "./Empire";
import { BondOrderForm, ShareOrderForm } from "./TradeForm";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { NumberTile } from "./Parts";
import { Change, Failed, Loading, Panel } from "./Shell";
import { LineChart } from "./TrendChart";

const ORDER: FundStrategy[] = ["shares", "banks", "bonds", "balanced", "anything", "index"];
const unitNaira = (price: string) => `₦${(Number(price) / 1e8).toFixed(4)}`;
const units = (n: number) => n.toLocaleString("en-NG");
const day = (iso: string) => new Date(iso).toLocaleDateString("en-NG", { day: "numeric", month: "short", timeZone: "Africa/Lagos" });

export function Stars({ n }: { n: number | null }) {
  if (!n) return <span className="muted small" aria-label="not rated yet">not rated</span>;
  return <span className="fund-stars" aria-label={`${n} star${n > 1 ? "s" : ""} of 5`}>{"★".repeat(n)}<span className="fund-stars-off">{"★".repeat(5 - n)}</span></span>;
}

function Tags({ f }: { f: FundSummary }) {
  return (
    <>
      {f.computer && <span className="tag">computer-run</span>}
      {f.gated && <span className="tag tag-warn">▲ gated</span>}
      {f.run && <span className="tag tag-warn">▼ investors leaving</span>}
      {f.status === "closing" && <span className="tag tag-warn">closing</span>}
      {f.regulator_run && <span className="tag tag-warn">run by the regulator</span>}
    </>
  );
}

type Run = (path: string, body?: unknown) => Promise<boolean>;

function useRun(onChanged: () => void, reload: () => void): [Run, boolean, string | null, string | null] {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const run: Run = async (path, body) => {
    setBusy(true); setError(null); setDone(null);
    try { await api.fundAct(path, body); setDone("Done."); onChanged(); reload(); return true; }
    catch (problem) { setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again."); return false; }
    finally { setBusy(false); }
  };
  return [run, busy, error, done];
}

/** The Market section's Funds tab. */
export function FundsWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const page = useLoad(api.funds, "funds", onLoggedOut);
  const [open, setOpen] = useState<number | null>(null);
  const [run, busy, error] = useRun(onChanged, page.reload);
  if (page.error) return <Failed message={page.error} onRetry={page.reload} />;
  if (!page.data) return <Loading what="the funds" />;
  const data = page.data;
  if (open !== null) return <FundSheetView id={open} onBack={() => { setOpen(null); page.reload(); }} onLoggedOut={onLoggedOut} onChanged={onChanged} />;
  const byId = new Map(data.funds.map((f) => [f.id, f]));
  return (
    <>
      <Panel title="Investment funds" aside="money in and out at the next closing bell's price">
        <p className="small">
          A fund pools many people's money and a manager invests it. You buy <span className="strong">units</span>; a unit is worth the
          fund divided by its units. You never know the exact price you will deal at: it is the next closing bell's, so nobody can
          buy into a rise they have already seen. Coming in pays 0.25% above that price and leaving gets 0.25% below; the difference
          stays in the fund, so those who stay do not pay for those who come and go.
        </p>
        <Mine data={data} busy={busy} run={run} onOpen={setOpen} />
        {error && <p className="error" role="alert">{error}</p>}
      </Panel>
      {ORDER.map((key) => {
        const ids = data.tables[key] ?? [];
        if (!ids.length) return null;
        return (
          <Panel key={key} title={data.strategies[key]} aside={data.strategy_words[key]}>
            <div className="table-scroll">
              <table className="mini-table fund-table" tabIndex={0}>
                <caption className="sr-only">{data.strategies[key]} funds, best rated first</caption>
                <thead><tr><th scope="col">Fund</th><th scope="col">Stars</th><th scope="col" className="num">Today</th><th scope="col" className="num">Quarter</th>
                  <th scope="col" className="num">Year</th><th scope="col" className="num">Since launch</th><th scope="col" className="num">Fee</th>
                  <th scope="col" className="num">Size</th></tr></thead>
                <tbody>
                  {ids.map((id) => {
                    const f = byId.get(id)!;
                    return (
                      <tr key={id}>
                        <td><button className="link-button strong" onClick={() => setOpen(id)}>{f.name}</button>
                          <div className="muted small">{f.manager}{f.computer ? "" : ` · ${units(f.holders)} holder${f.holders === 1 ? "" : "s"}`} <Tags f={f} /></div></td>
                        <td><Stars n={f.stars} /></td>
                        <td className="num"><Change bps={f.day_bps} /></td>
                        <td className="num"><Change bps={f.quarter_bps} /></td>
                        <td className="num"><Change bps={f.year_bps} /></td>
                        <td className="num"><Change bps={f.since_bps} /></td>
                        <td className="num mono">{formatPercent(f.fee_bps, 2)}{f.perf_fee_bps ? <span className="muted small"> +{formatPercent(f.perf_fee_bps, 0)}</span> : null}</td>
                        <td className="num mono">{formatCompact(f.worth)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        );
      })}
      {data.managing && <ManagerDesk fund={data.managing} funds={data.funds} onLoggedOut={onLoggedOut} onChanged={onChanged} reload={page.reload} />}
      {data.can_launch && <LaunchForm data={data} onChanged={onChanged} reload={page.reload} />}
      {!data.can_launch && !data.managing && (
        <p className="muted small">An Asset Manager of Level {data.launch.level} may launch a fund of their own: registration {formatNaira(data.launch.registration)}, and at least {formatNaira(data.launch.seed)} of their own money in it.</p>
      )}
    </>
  );
}

function Mine({ data, busy, run, onOpen }: { data: FundsPage; busy: boolean; run: Run; onOpen: (id: number) => void }) {
  const { lines, waiting } = data.mine;
  if (!lines.length && !waiting.length) return <p className="muted small">You hold no funds yet. Open a fund below to put money in.</p>;
  return (
    <>
      <div className="why-title">YOUR FUNDS</div>
      {lines.map((l) => (
        <div key={`${l.whose}-${l.id}`} className="row">
          <span><button className="link-button strong" onClick={() => onOpen(l.id)}>{l.name}</button>{l.whose === "empire" && <span className="muted small"> · your empire's</span>}
            <span className="muted small"> · {units(l.units)} units at {unitNaira(l.unit_price)}{l.leaving ? ` · ${units(l.leaving)} asked back` : ""}</span></span>
          <span className="mono">{formatNaira(l.value)} <Change bps={l.day_bps} /></span>
        </div>
      ))}
      {waiting.map((w) => (
        <div key={w.id} className="row">
          <span className="small">{w.side === "in" ? `${formatNaira(w.amount)} into` : `${units(w.units)} units out of`} {w.fund} <span className="muted">· waiting for the bell</span></span>
          <button className="button-quiet" disabled={busy} onClick={() => run(`/orders/${w.id}/cancel`)}>Take back</button>
        </div>
      ))}
    </>
  );
}

function FundSheetView({ id, onBack, onLoggedOut, onChanged }: { id: number; onBack: () => void; onLoggedOut: () => void; onChanged: () => void }) {
  const sheet = useLoad(() => api.fund(id), `fund:${id}`, onLoggedOut);
  const [run, busy, error, done] = useRun(onChanged, sheet.reload);
  const [forEmpire, setForEmpire] = useState(false);
  if (sheet.error) return <Failed message={sheet.error} onRetry={sheet.reload} />;
  if (!sheet.data) return <Loading what="the factsheet" />;
  const f: FundSheet = sheet.data;
  const held = forEmpire && f.empire ? f.empire : f.mine;
  const open = f.status === "open" && !f.regulator_run;
  return (
    <>
      <button className="button-quiet" onClick={onBack}>← All funds</button>
      <Panel title={f.name} aside={<><Stars n={f.stars} /> <Tags f={f} /></>}>
        <p className="small">{f.strategy_name} · managed by <span className="strong">{f.manager}</span> · launched {f.launched_period}</p>
        {f.words && <p className="small muted">“{f.words}”</p>}
        <div className="tiles">
          <NumberTile label="A unit" value={unitNaira(f.unit_price)} change={f.day_bps} note="at the last closing bell" />
          <NumberTile label="Size of the fund" value={formatCompact(f.worth)} note={`${units(f.holders)} holder${f.holders === 1 ? "" : "s"}${f.computer ? " (the households, as one)" : ""}`} />
          <NumberTile label="Over a year" value={f.year_bps === null ? "n/a" : <Change bps={f.year_bps} />} note={`benchmark: ${f.benchmark}`} />
          <NumberTile label="Worst fall from a high" value={formatPercent(f.worst_fall_bps)} />
          <NumberTile label="Fees" value={`${formatPercent(f.fee_bps, 2)} a year`} note={f.perf_fee_bps ? `and ${formatPercent(f.perf_fee_bps, 0)} of gains above its best` : "no performance fee"} />
        </div>
        {f.chart.length >= 2 && (
          <LineChart names={["The fund", "Its benchmark"]} format={(v) => `${v.toFixed(1)}%`}
                     data={f.chart.map((p) => ({ label: day(p.day), first: p.fund_bps / 100, second: (p.bench_bps ?? 0) / 100 }))} />
        )}
        {f.merging && <p className="small strong">This fund merges into {f.merging.into} on {day(f.merging.takes_effect)}. You may ask for your money back before then.</p>}
      </Panel>
      <Panel title="Your money in this fund" aside={f.empire ? <label className="small"><input type="checkbox" checked={forEmpire} onChange={(e) => setForEmpire(e.target.checked)} disabled={!f.empire.head} /> for my empire{f.empire.head ? "" : " (only its head)"}</label> : undefined}>
        <div className="row"><span>{forEmpire ? "Your empire holds" : "You hold"} {units(held.units)} units{held.leaving ? `, ${units(held.leaving)} of them asked back` : ""}</span>
          <span className="mono strong">{formatNaira(held.value)}</span></div>
        {open && (
          <AmountForm label={`Put money in (the least for a new investor: ${formatNaira(f.least_in)})`} button="Put it in at the next bell" busy={busy}
                      onSubmit={(kobo) => run(`/${f.id}/invest`, { amount_naira: Math.floor(kobo / 100), for_empire: forEmpire })} />
        )}
        {held.units - held.leaving > 0 && (
          <div className="step-actions">
            <button className="button-outline" disabled={busy} onClick={() => run(`/${f.id}/leave`, { units: null, for_empire: forEmpire })}>Ask for all of it back at the next bell</button>
          </div>
        )}
        <button className="button-quiet" disabled={busy} onClick={() => run(`/${f.id}/follow`, { on: !f.following })}>{f.following ? "✓ Following: stop" : "Follow this fund (its news pops up)"}</button>
        {error && <p className="error" role="alert">{error}</p>}
        {done && <p className="small tag-good" role="status">{done}</p>}
        {f.orders.length > 0 && <div className="why-title">YOUR ORDERS</div>}
        {f.orders.map((o) => (
          <div key={o.id} className="row small"><span>{o.side === "in" ? `${formatNaira(o.amount)} in` : `${units(o.units)} units out`} · {o.status}{o.words ? ` · ${o.words}` : ""}</span>
            <span className="mono">{o.side === "out" && o.status !== "waiting" ? formatNaira(o.paid) : o.side === "in" && o.status === "dealt" ? `${units(o.units_done)} units` : ""}</span></div>
        ))}
      </Panel>
      <Panel title="What it held" aside="published one quarter late, as for every fund">
        {!f.holdings ? <p className="muted small">Nothing published yet: a fund's holdings appear a quarter after the quarter they are for.</p> : (
          <>
            <p className="small muted">At the end of {f.holdings.label} · cash {formatPercent(f.holdings.cash_bps)}</p>
            {f.holdings.lines.map((l) => <div key={l.ticker} className="row small"><span>{l.name ?? l.ticker}{l.name && <> <span className="ticker">{l.ticker}</span></>}</span><span className="mono">{formatPercent(l.weight_bps)}</span></div>)}
          </>
        )}
      </Panel>
      <Panel title="Quarter by quarter">
        {f.quarters.length === 0 ? <p className="muted small">Not yet a full quarter.</p> : (
          <div className="table-scroll">
            <table className="mini-table" tabIndex={0}>
              <caption className="sr-only">The fund's quarters</caption>
              <thead><tr><th scope="col">Quarter</th><th scope="col">Stars</th><th scope="col" className="num">Quarter</th><th scope="col" className="num">Year</th>
                <th scope="col" className="num">Benchmark</th><th scope="col" className="num">Return per unit of risk</th></tr></thead>
              <tbody>{f.quarters.map((q) => (
                <tr key={q.period}><td>{q.label}</td><td><Stars n={q.stars} /></td><td className="num"><Change bps={q.quarter_bps} /></td>
                  <td className="num"><Change bps={q.year_bps} /></td><td className="num"><Change bps={q.bench_bps} /></td>
                  <td className="num mono">{q.risk_ratio === null ? "n/a" : q.risk_ratio.toFixed(2)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel title="The rules it keeps">
        <ul className="plain-list small">{f.rules.map((r) => <li key={r}>{r}</li>)}</ul>
        {f.recent.length > 0 && <div className="why-title">LATELY</div>}
        {f.recent.map((r, i) => <div key={i} className="small"><span className="strong">{r.headline}</span> <span className="muted">· {day(r.at)}</span></div>)}
      </Panel>
    </>
  );
}

function LaunchForm({ data, onChanged, reload }: { data: FundsPage; onChanged: () => void; reload: () => void }) {
  const [run, busy, error] = useRun(onChanged, reload);
  const [name, setName] = useState("");
  const [strategy, setStrategy] = useState<FundStrategy>("shares");
  const [fee, setFee] = useState("100");
  const [perf, setPerf] = useState("0");
  const [least, setLeast] = useState("10000");
  const [seed, setSeed] = useState(String(Number(BigInt(data.launch.seed) / 100n)));
  const [words, setWords] = useState("");
  const [indexCode, setIndexCode] = useState(data.indexes[0]?.code ?? "");
  const [method, setMethod] = useState("full");
  const isIndex = strategy === "index";
  const chosenIndex = data.indexes.find((i) => i.code === indexCode);
  return (
    <Panel title="Launch a fund of your own" aside={`registration ${formatNaira(data.launch.registration)}`}>
      <form className="stack-form" onSubmit={(e) => {
        e.preventDefault();
        run("/launch", { name, strategy, fee_bps: Number(fee), perf_fee_bps: isIndex ? 0 : Number(perf), least_in_naira: Number(least), seed_naira: Number(seed), words,
          ...(isIndex ? { index_code: indexCode, method: chosenIndex?.kind === "bonds" ? "full" : method } : {}) });
      }}>
        <p className="small muted">
          You run one fund at a time and put in at least {formatNaira(data.launch.seed)} of your own money, which buys the first units at ₦1.
          While you run it you keep at least 1% of it (or all you put in). Fees can be lowered later, never raised.
        </p>
        <label className="answer"><span className="field-label">Name</span><span className="answer-box"><input type="text" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} /></span></label>
        <label className="answer"><span className="field-label">What it holds</span>
          <select value={strategy} onChange={(e) => setStrategy(e.target.value as FundStrategy)}>{ORDER.map((k) => <option key={k} value={k}>{data.strategies[k]}</option>)}</select></label>
        <p className="small muted">{data.strategy_words[strategy]}</p>
        {isIndex && (<>
          <label className="answer"><span className="field-label">The index it copies</span>
            <select value={indexCode} onChange={(e) => setIndexCode(e.target.value)}>{data.indexes.map((i) => <option key={i.code} value={i.code}>{i.name}</option>)}</select></label>
          {chosenIndex?.kind !== "bonds" && <label className="answer"><span className="field-label">How it copies</span>
            <select value={method} onChange={(e) => setMethod(e.target.value)}><option value="full">Every member, in proportion</option><option value="sample">Only the largest members, up to 80% of the index</option></select></label>}
        </>)}
        <label className="answer"><span className="field-label">Yearly fee, of the whole fund</span>
          <select value={isIndex && Number(fee) > 100 ? "100" : fee} onChange={(e) => setFee(e.target.value)}>{(isIndex ? [0, 10, 15, 20, 25, 35, 50, 75, 100] : [0, 25, 50, 75, 100, 125, 150, 175, 200]).map((b) => <option key={b} value={b}>{formatPercent(b, 2)}</option>)}</select></label>
        {!isIndex && <label className="answer"><span className="field-label">Performance fee, of gains above the fund's best</span>
          <select value={perf} onChange={(e) => setPerf(e.target.value)}>{[0, 500, 1000, 1500, 2000].map((b) => <option key={b} value={b}>{formatPercent(b, 0)}</option>)}</select></label>}
        <label className="answer"><span className="field-label">The least a new investor puts in (₦)</span><span className="answer-box"><input type="number" min={10000} value={least} onChange={(e) => setLeast(e.target.value)} /></span></label>
        <label className="answer"><span className="field-label">Your own money (₦)</span><span className="answer-box"><input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} /></span></label>
        <label className="answer"><span className="field-label">A line for investors (optional)</span><span className="answer-box"><input type="text" maxLength={400} value={words} onChange={(e) => setWords(e.target.value)} /></span></label>
        <button className="button-outline" disabled={busy || name.trim().length < 3}>Launch the fund</button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </Panel>
  );
}

function ManagerDesk({ fund, funds, onLoggedOut, onChanged, reload }: { fund: FundManaging; funds: FundSummary[]; onLoggedOut: () => void; onChanged: () => void; reload: () => void }) {
  const [run, busy, error, done] = useRun(onChanged, reload);
  const [into, setInto] = useState("");
  const others = funds.filter((f) => f.id !== fund.id && !f.computer && f.status === "open" && !f.regulator_run);
  const near = (bps: number, most: number) => (bps > most * 0.9 ? " change-down" : "");
  return (
    <Panel title={`The fund you run: ${fund.name}`} aside={<><Stars n={fund.stars} /> <Tags f={fund} /></>}>
      <div className="tiles">
        <NumberTile label="Worth now" value={formatCompact(fund.worth_now)} note={`a unit ${unitNaira(fund.unit_price)} at the last bell`} />
        <NumberTile label="Cash" value={<span className={fund.cash_bps < 500 ? "change-down" : ""}>{formatPercent(fund.cash_bps)}</span>} note="at least 5%" />
        <NumberTile label="Largest holding" value={<span className={near(fund.largest_bps, 1000)}>{formatPercent(fund.largest_bps)}</span>} note="at most 10%" />
        <NumberTile label="Shares · bonds" value={`${formatPercent(fund.shares_bps, 0)} · ${formatPercent(fund.bonds_bps, 0)}`} />
        <NumberTile label="Waiting at the bell" value={`${formatCompact(fund.waiting_in)} in`} note={`${units(fund.waiting_out_units)} units out`} />
      </div>
      {fund.leavers_waiting && <p className="small change-down">▼ Investors are waiting to be paid. The fund can sell, and can buy nothing until they are.{Number(fund.owed) > 0 ? ` It owes ${formatNaira(fund.owed)} on a short loan.` : ""}</p>}
      {fund.lines.map((h) => <div key={h.ticker} className="row small"><span>{h.ticker} shares</span><span className="mono">{units(h.shares)} · {formatCompact(h.value)}</span></div>)}
      {fund.bond_lines.map((b) => <div key={b.code} className="row small"><span>{b.name} <span className="ticker">{b.code}</span></span><span className="mono">{units(b.units)} · {formatCompact(b.value)}</span></div>)}
      {fund.orders.filter((o) => o.status === "open").map((o) => (
        <div key={o.id} className="row small"><span>{o.side === "buy" ? "Buying" : "Selling"} {units(o.remaining)} {o.ticker} · waiting</span>
          <button className="button-quiet" disabled={busy} onClick={() => run(`/manage/shares/${o.id}/cancel`)}>Cancel</button></div>
      ))}
      {fund.strategy !== "bonds" && (<>
        <div className="why-title">SHARES</div>
        <ShareOrderForm whose="The fund" busy={busy} held={fund.lines} fairDealing onLoggedOut={onLoggedOut} onPlace={(o) => run("/manage/shares", o)} />
      </>)}
      {fund.strategy !== "shares" && fund.strategy !== "banks" && (<>
        <div className="why-title">BONDS AND BILLS</div>
        <BondOrderForm whose="The fund" busy={busy} held={fund.bond_lines} onLoggedOut={onLoggedOut} onPlace={(o) => run("/manage/bonds", o)} />
      </>)}
      <div className="why-title">RUNNING THE FUND</div>
      <div className="step-actions">
        <button className="button-outline" disabled={busy} onClick={() => run("/manage/gate", { on: !fund.gated })}>{fund.gated ? "Lift the gate" : "Put up a gate (announced to everyone)"}</button>
        {fund.fee_bps > 0 && <button className="button-quiet" disabled={busy} onClick={() => run("/manage/fees", { fee_bps: Math.max(fund.fee_bps - 25, 0), perf_fee_bps: fund.perf_fee_bps })}>Lower the fee by 0.25%</button>}
        {fund.status === "open" && <button className="button-quiet" disabled={busy} onClick={() => run("/manage/close")}>Close the fund at the next bell</button>}
      </div>
      {fund.merges_waiting.map((m) => (
        <div key={m.id} className="row small"><span>{m.from_fund} asks to merge into your fund.</span>
          <span><button className="button-quiet" disabled={busy} onClick={() => run(`/manage/merges/${m.id}`, { accept: true })}>Agree</button>
            <button className="button-quiet" disabled={busy} onClick={() => run(`/manage/merges/${m.id}`, { accept: false })}>Refuse</button></span></div>
      ))}
      {fund.merge_out ? <p className="small">Merging into {fund.merge_out.into}: {fund.merge_out.status}.</p> : others.length > 0 && fund.status === "open" && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (into) run("/manage/merge", { into: Number(into) }); }}>
          <label className="small">Merge into <select value={into} onChange={(e) => setInto(e.target.value)}><option value="">choose a fund</option>{others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
          <button className="button-quiet" disabled={busy || !into}>Ask its manager</button>
        </form>
      )}
      <div className="definition shadow">
        <div className="why-title">THE SHADOW SIDE</div>
        <p className="small">
          You may sign for a cost that is not real, and the money comes to you. In the fund's books it reads "Custody and dealing
          costs". The regulator audits every fund's books each quarter. If it is proved, you repay it with a fine of half as much
          again, are struck off, and the regulator winds your fund down.
        </p>
        <AmountForm label={`Sign for a cost (limit ${formatNaira(fund.costs_limit)} a quarter, ${formatNaira(fund.costs_used)} used)`} button="Sign for it" busy={busy}
                    onSubmit={(kobo) => run("/manage/costs", { amount_naira: Math.floor(kobo / 100) })} />
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {done && <p className="small tag-good" role="status">{done}</p>}
    </Panel>
  );
}

function remembered(): number | null {
  try {
    const v = window.localStorage.getItem("wsbm-fund-alerts");
    return v === null ? null : Number(v);
  } catch {
    return null;
  }
}

/** A fund's news is not a page to visit: for the funds a player holds or follows (and, for a gate, a run or a manager struck
 * off, for everybody) it pops up. */
export function FundAlerts({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [shown, setShown] = useState<FundAlert[]>([]);
  const mark = useRef<number | null>(remembered());
  useEffect(() => {
    let stopped = false;
    function look() {
      api.fundAlerts(mark.current).then((found) => {
        if (stopped) return;
        mark.current = found.mark;
        if (found.alerts.length) setShown((now) => [...now, ...found.alerts.filter((i) => !now.some((x) => x.id === i.id))].slice(-3));
      }).catch((problem) => { if (problem instanceof ApiError && problem.status === 401) onLoggedOut(); });
    }
    look();
    const timer = window.setInterval(look, 60_000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [onLoggedOut]);
  if (shown.length === 0) return null;
  const a = shown[shown.length - 1];
  const close = () => {
    try {
      const before = Number(window.localStorage.getItem("wsbm-fund-alerts") ?? "0");
      window.localStorage.setItem("wsbm-fund-alerts", String(Math.max(before, ...shown.map((x) => x.id))));
    } catch { /* not remembered: fine */ }
    setShown((now) => now.slice(0, -1));
  };
  return (
    <div className="bank-alert-region fund-alert-region">
      <div className="bank-alert fund-alert" role="alertdialog" aria-labelledby={`fund-alert-${a.id}`}>
        <div className="bank-alert-tag">● FUNDS · {a.fund}</div>
        <div className="bank-alert-headline" id={`fund-alert-${a.id}`}>{a.headline}</div>
        <p className="small">{a.words}</p>
        <div className="bank-alert-actions">
          <a className="button-outline" href="#/market/funds" onClick={close}>See the funds</a>
          <button className="button-quiet" onClick={close}>Close{shown.length > 1 ? ` (${shown.length - 1} more)` : ""}</button>
        </div>
      </div>
    </div>
  );
}
