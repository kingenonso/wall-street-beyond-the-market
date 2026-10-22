import { useState } from "react";
import { api, type BankAuction, type BankTrust, type CrisisRecord, type Player, type SavingsBank, type WatchSign } from "./api";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { Notices, useRun, Why } from "./Newsroom";
import { Failed, Loading, Panel } from "./Shell";
import { Term } from "./Term";

/** The crises stage, Part 1: the banks and how far each is trusted, the player's savings, the Crisis Watch, and the
 * record of every crisis. Never anybody else's savings; never a crisis's hidden weakness while it is open. */

const STATE_WORDS: Record<string, string> = { calm: "Calm", worried: "Savers worried", run: "A run", panic: "Panic", closed: "Closed" };
const stateTag = (s: string) => (s === "calm" ? "tag-good" : s === "worried" ? "tag" : "tag-bad");
const pct = (bps: number) => `${(bps / 100).toFixed(1).replace(/\.0$/, "")}%`;

function TrustBar({ score, state }: { score: number | null; state: string }) {
  const value = score ?? 0;
  return (
    <span className="trust-bar" role="img" aria-label={`Trust ${score ?? "not yet measured"} of 100: ${STATE_WORDS[state] ?? state}`}>
      <span className={`trust-fill trust-${state}`} style={{ width: `${value}%` }} />
    </span>
  );
}

function Days({ days }: { days: BankTrust["days"] }) {
  if (days.length < 2) return null;
  return (
    <span className="trust-days" aria-hidden="true">
      {days.map((d) => <span key={`${d.period}-${d.day}`} className={`trust-day trust-${d.state}`} style={{ height: `${Math.max(d.score, 4) / 4}px` }} />)}
    </span>
  );
}

type CrisisTab = "banks" | "savings" | "watch" | "crises";

export function CrisisWork({ player, tab: start, onLoggedOut }: { player: Player; tab?: string; onLoggedOut: () => void }) {
  const known: CrisisTab[] = ["banks", "savings", "watch", "crises"];
  const [tab, setTab] = useState<CrisisTab>(known.includes(start as CrisisTab) ? (start as CrisisTab) : "banks");
  const tabs: [CrisisTab, string][] = [["banks", "The banks"], ["savings", "Your savings"], ["watch", "Crisis Watch"], ["crises", "Crises on the record"]];
  function choose(next: CrisisTab) {
    setTab(next);
    window.history.replaceState(null, "", `#/crisis/${next}`);
  }
  return (
    <>
      <div className="page-head"><h1>Banks and crises</h1><span className="muted small">Every crisis grows out of real conditions, and can be explained</span></div>
      <div className="underline-tabs" role="tablist" aria-label="Banks and crises">
        {tabs.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : undefined} onClick={() => choose(key)}>{label}</button>)}
      </div>
      {tab === "banks" && <Banks player={player} onLoggedOut={onLoggedOut} />}
      {tab === "savings" && <Savings onLoggedOut={onLoggedOut} />}
      {tab === "watch" && <Watch onLoggedOut={onLoggedOut} />}
      {tab === "crises" && <Crises onLoggedOut={onLoggedOut} />}
    </>
  );
}

function Banks({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.crisis, "crisis", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [limit, setLimit] = useState<Record<number, string>>({});
  if (loading && !data) return <Loading what="the banks" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const isHead = !!player.empire && !player.empire.forming && player.empire.is_head;
  return (
    <>
      <Notices act={act} />
      {data.blanket && (
        <p className="notice" role="status">The Government has promised that every saving at every bank is safe, whatever its size, until calm returns.</p>
      )}
      <Panel title="Trust in the banks" aside={`all banks together: ${data.national} of 100`}>
        {data.banks.length === 0 && <p className="muted">Trust is measured from the first game day of the quarter.</p>}
        {data.banks.map((b) => (
          <div key={b.ticker} className="fact-row bank-row">
            <div>
              <div className="strong">{b.name} <span className="muted small">· {b.ticker} · {b.headquarters}</span></div>
              <div className="small">
                <TrustBar score={b.trust} state={b.state} />{" "}
                <span className={stateTag(b.state)}>{STATE_WORDS[b.state] ?? b.state}</span>
                {b.trust !== null && <span className="muted"> · {b.trust} of 100{b.change ? ` (${b.change > 0 ? "+" : ""}${b.change} on its last day)` : ""}</span>}
                <Days days={b.days} />
              </div>
              {b.parts.length > 0 && (
                <div className="small muted">What moves it: {b.parts.map((p) => `${p.name} ${p.points > 0 ? "+" : ""}${p.points}`).join(" · ")}</div>
              )}
              {b.resolution && <div className="small">{b.resolution.words}</div>}
            </div>
          </div>
        ))}
        <p className="muted small">Trust moves each game day part of the way towards where its public signals put it. Below 45, the biggest savers
          start to leave; below 35, a run; below 20, panic. Banks still trusted take in what frightened savers draw out.</p>
      </Panel>
      {data.auctions.length > 0 && (
        <Panel title="Banks at the Auction House" aside="your top price stays secret">
          {data.auctions.map((a: BankAuction) => (
            <div key={a.id} className="fact-row">
              <div>
                <div className="strong">{a.bank.name} <span className="muted small">· {a.kind === "rescue" ? "closed: new money wanted" : "public stake for sale"}</span></div>
                <div className="small muted">{a.status === "open" ? `Ends ${new Date(a.ends_at).toLocaleString("en-NG", { timeZone: "Africa/Lagos" })}` : a.status}
                  {" · "}{a.price ? `leading bid ${formatNaira(a.price)}` : `lowest bid ${formatNaira(a.start_price)}`}
                  {a.lowest_price_met ? " · lowest price met" : ""} · {a.bidders} bidder{a.bidders === 1 ? "" : "s"}
                  {a.you_lead ? " · you lead" : a.your_status ? ` · your bid: ${a.your_status}` : ""}{a.empire_leads ? " · your empire leads" : ""}</div>
                {a.kind === "rescue" && <div className="small muted">The price is new money paid into the bank itself. The winner owns 95% of it; its old owners keep 5%.</div>}
              </div>
              {a.status === "open" && (
                <div className="intel-actions">
                  <label className="answer small">Your top price ₦<input type="number" min={1} value={limit[a.id] ?? ""} onChange={(e) => setLimit({ ...limit, [a.id]: e.target.value })} /></label>
                  <button className="button-outline" disabled={act.busy || !Number(limit[a.id])} onClick={() => act.run(() => api.post(`/auctions/${a.id}/bid`, { limit_kobo: Math.round(Number(limit[a.id]) * 100) }), "Your bid stands.")}>Bid</button>
                  {isHead && <button className="button-quiet" disabled={act.busy || !Number(limit[a.id])} onClick={() => act.run(() => api.post(`/empire/auctions/${a.id}/bid`, { limit_kobo: Math.round(Number(limit[a.id]) * 100) }), "The empire's bid stands.")}>Bid for my empire</button>}
                </div>
              )}
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}

function Savings({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.savings, "savings", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [amount, setAmount] = useState<Record<string, string>>({});
  const [forEmpire, setForEmpire] = useState(false);
  if (loading && !data) return <Loading what="your savings" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const head = !!data.empire?.head;
  const move = (b: SavingsBank, way: "in" | "out") =>
    act.run(() => api.post(`/savings/${b.ticker}/${way}`, { amount_naira: Math.round(Number(amount[b.ticker] ?? 0)), for_empire: head && forEmpire }),
      way === "in" ? `Put into savings at ${b.name}.` : `Taken out of savings at ${b.name}.`);
  return (
    <>
      <Notices act={act} />
      <Panel title="Savings at the banks" aside={`cash in hand ${formatNaira(data.cash)}`}>
        {head && (
          <label className="small answer"><input type="checkbox" checked={forEmpire} onChange={(e) => setForEmpire(e.target.checked)} /> For {data.empire?.name}
            {" "}(its cash {formatNaira(data.empire?.cash ?? "0")})</label>
        )}
        {data.banks.filter((b) => b.takes_savings).map((b) => (
          <div key={b.ticker} className="fact-row">
            <div>
              <div className="strong">{b.name} <span className="muted small">· {b.ticker}{b.rating ? ` · rated ${b.rating}` : ""}</span></div>
              <div className="small">
                <TrustBar score={b.trust} state={b.state} /> <span className={stateTag(b.state)}>{STATE_WORDS[b.state] ?? b.state}</span>
                <span className="muted"> · savings pay {pct(b.savings_rate_bps)} a year</span>
              </div>
              <div className="small muted">Yours: {formatNaira(b.mine)} ({formatNaira(b.mine_guaranteed)} guaranteed)
                {b.empire !== null && <> · the empire's: {formatNaira(b.empire)} ({formatNaira(b.empire_guaranteed ?? "0")} guaranteed)</>}</div>
            </div>
            {!b.closed && (
              <div className="intel-actions">
                <label className="answer small">₦<input type="number" min={10000} value={amount[b.ticker] ?? ""} onChange={(e) => setAmount({ ...amount, [b.ticker]: e.target.value })} aria-label={`Amount for ${b.name}`} /></label>
                <button className="button-outline" disabled={act.busy || !Number(amount[b.ticker])} onClick={() => move(b, "in")}>Put in</button>
                <button className="button-quiet" disabled={act.busy || !Number(amount[b.ticker])} onClick={() => move(b, "out")}>Take out</button>
                {(BigInt(b.mine) > 0n || (head && forEmpire && BigInt(b.empire ?? "0") > 0n)) && (
                  <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post(`/savings/${b.ticker}/out`, { amount_naira: 0, everything: true, for_empire: head && forEmpire }), `Took everything out of ${b.name}.`)}>Take it all out</button>
                )}
              </div>
            )}
          </div>
        ))}
        <p className="muted small">Savings pay more than cash in hand, on the least you keep through the whole quarter. But they are a claim on the bank:
          if it fails, only the first {formatNaira(data.guarantee)} at each bank is <Term word="Deposit guarantee">guaranteed</Term>
          {data.blanket ? " (for now the Government guarantees every saving in full)" : ""}. Above that, savers bear their share of its losses.</p>
      </Panel>
      {data.interest.length > 0 && (
        <Panel title="Interest paid on your savings">
          {data.interest.map((i) => (
            <div key={`${i.period}-${i.bank}`} className="fact-row small"><span>Q{i.period} · {i.bank}</span><span>{formatNaira(i.amount)} on {formatNaira(i.lowest)} at {pct(i.rate_bps)}</span></div>
          ))}
        </Panel>
      )}
    </>
  );
}

function Sign({ s }: { s: WatchSign }) {
  return (
    <div className="fact-row">
      <div>
        <div className="strong">{s.name} <span className={s.level === "green" ? "tag-good" : s.level === "amber" ? "tag" : "tag-bad"}>{s.level}</span></div>
        <div className="small muted">{s.words}</div>
      </div>
      <span className="watch-history" aria-label={`The last readings: ${s.history.map((h) => h.level).join(", ")}`}>
        {s.history.map((h) => <span key={h.period} className={`watch-dot watch-${h.level}`} />)}
      </span>
    </div>
  );
}

function Watch({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.crisis, "crisis", onLoggedOut);
  if (loading && !data) return <Loading what="the Crisis Watch" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <Panel title="The Crisis Watch" aside={data.watch.label ? `read at the close of ${data.watch.label}` : "read at each close"}>
      {data.watch.signs.length === 0 && <p className="muted">The first reading comes at the next quarter's close.</p>}
      {data.watch.signs.map((s) => <Sign key={s.sign} s={s} />)}
      <p className="muted small">A sign turning red changes nothing by itself. Most warnings never become a crisis: strong banks, a good
        policy response or good decisions by players can stop one.</p>
    </Panel>
  );
}

const PHASES = ["Warning", "Trigger", "Spread", "Crisis", "Recovery"];

function Timeline({ c }: { c: CrisisRecord }) {
  return (
    <ol className="phases" aria-label="Its phases">
      {PHASES.map((p) => {
        const reached = c.steps.filter((s) => s.phase === p);
        return (
          <li key={p} className={reached.length ? "phase-on" : "phase-off"}>
            <span className="strong small">{p}</span>
            {reached.map((s) => <div key={s.step} className="small muted">{s.name}: {s.words} <span className="muted">(day {s.day})</span></div>)}
          </li>
        );
      })}
    </ol>
  );
}

function Crises({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.crisis, "crisis", onLoggedOut);
  if (loading && !data) return <Loading what="the record" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      {data.crises.length === 0 && <Panel title="Crises on the record"><p className="muted">None yet. Most warning signs fade away.</p></Panel>}
      {data.crises.map((c) => (
        <Panel key={c.id} title={c.title} aside={c.status === "open" ? `now: ${c.phase}, ${c.step_name.toLowerCase()}` : c.status === "faded" ? "faded away" : "in the history books"}>
          {c.banks.length > 0 && <p className="small muted">Banks touched: {c.banks.join(", ")}</p>}
          <Timeline c={c} />
          {c.report && (
            <div className="crisis-report">
              <h3 className="small strong">The Crisis Report</h3>
              <p className="small">{c.report.summary}</p>
              <p className="small"><span className="strong">What made it possible:</span> {c.report.weakness}</p>
              <p className="small"><span className="strong">What stopped it:</span> {c.report.stopped_by.join("; ") || "nothing was needed"}</p>
              {c.report.hit.length > 0 && <p className="small"><span className="strong">Hit:</span> {c.report.hit.map((h) => `${h.bank} (trust fell to ${h.lowest_trust ?? "?"}${h.closed ? ", closed" : ""})`).join(", ")}</p>}
              {c.report.came_through.length > 0 && <p className="small"><span className="strong">Came through:</span> {c.report.came_through.map((h) => h.bank).join(", ")}</p>}
              <p className="small muted">{c.report.lesson}{c.report.long_weakness ? " Its recovery took longer than two quarters: a long weakness." : ""}</p>
            </div>
          )}
          <Why keyName={`crisis:${c.id}`} />
        </Panel>
      ))}
    </>
  );
}

export function CrisisRail() {
  return (
    <Panel title="How a crisis grows">
      <ul className="reasons small">
        <li>A crisis is never dropped on players. It grows from a <strong>hidden weakness</strong>, through warning signs, a local event, the response of the banks and the Government, spread and a tipping point.</li>
        <li>Each bank's <strong>trust</strong> is made of public signals: its owners' funds, bad loans, cash, rating, savers leaving, the news, its share price and trouble at other banks.</li>
        <li>The Central Bank lends to a sound bank in a run. A bank that cannot pay is closed: savers above the guarantee bear their share, and the Auction House finds it new money.</li>
        <li>Pulling your own money out is allowed, even if it starts a run. Spreading a false story to start one is a crime, kept for the courts.</li>
      </ul>
    </Panel>
  );
}
