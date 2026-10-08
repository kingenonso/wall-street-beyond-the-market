// The screens of the other four builds, and the screen of the head of an empire (design document,
// section 18). Each uses the same four zones as every other screen, in its own accent colour:
//   Investment Banker (purple)   deals open in the market; one company against the companies like it
//   Risk Manager (orange)        what could be lost, by kind, city and industry; stress tests
//   Legal Counsel (red)                 matters in hand; who controls a company and who is paid first
//   Financial Journalist (blue)            the newsroom, investigations, the indicators, the publishing pipeline
//   Head of an empire (gold)     what the empire is worth and holds; what waits for the head's decision

import { useState } from "react";
import {
  api, ApiError, type BankerDesk, type EmpireRoom, type Objective, type Player,
} from "./api";
import { BuildRail, NeedsYouNow, urgent } from "./BuildDesk";
import { Chat } from "./Empire";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { WatchlistPanel } from "./Market";
import { Story } from "./News";
import { NumberTile, ProgressTracker, StateTag, Wheel } from "./Parts";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";
import { SingleLine } from "./TrendChart";

type Props = { player: Player; onLoggedOut: () => void; onChanged: () => void };
const times = (value: number | null) => (value === null ? "n/a" : `${value.toLocaleString("en-NG", { maximumFractionDigits: 1 })}×`);
const lost = (kobo: string | undefined) => (kobo === undefined ? "n/a" : `▼ ${formatCompact(kobo)}`);

function CompanyPicker({ value, companies, onChange }: { value: string; companies: { ticker: string; name: string; sector: string }[]; onChange: (ticker: string) => void }) {
  return (
    <label className="answer">
      <span className="field-label">Company</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {companies.map((c) => <option key={c.ticker} value={c.ticker}>{c.name} ({c.ticker}) · {c.sector}</option>)}
      </select>
    </label>
  );
}

function Matters({ objectives, empty }: { objectives: Objective[]; empty: string }) {
  if (objectives.length === 0) return <p className="muted small">{empty} <a href="#/work">See the work on offer</a>.</p>;
  return (
    <>
      {objectives.map((o) => (
        <div key={o.id} className="row">
          <span><StateTag state={o.state} /> <a href="#/work">{o.title}</a>{o.terms.client && <span className="muted small"> · {o.terms.client.name}</span>}
            {o.state === "active" && <span className="muted small"> · {o.terms.deadline}</span>}</span>
          <span className="mono">{o.state === "passed" ? `+ ${formatNaira(o.paid_kobo)}` : o.state === "active" ? formatNaira(o.reward_kobo) : "—"}</span>
        </div>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Investment Banker
// ---------------------------------------------------------------------------

const MULTIPLES: { key: keyof BankerDesk["multiples"]; label: string; plain: string }[] = [
  { key: "earnings", label: "Price ÷ a year's profit", plain: "How many years of today's profit the market is paying for." },
  { key: "book", label: "Price ÷ owners' money", plain: "What the market pays for each naira the owners have in the business." },
  { key: "ebitda", label: "Whole business ÷ a year's EBITDA", plain: "Shares plus debt less cash, against profit before interest, tax and wear." },
];

export function InvestmentBankerWork({ player, onLoggedOut }: Props) {
  const [ticker, setTicker] = useState<string | undefined>(undefined);
  const desk = useLoad(() => api.bankerDesk(ticker), `banker:${ticker ?? ""}`, onLoggedOut);
  const board = useLoad(api.objectives, "banker-objectives", onLoggedOut);
  const career = useLoad(api.career, "banker-career", onLoggedOut);
  if (desk.loading && !desk.data) return <Loading what="the deal desk" />;
  if (desk.error || !desk.data) return <Failed message={desk.error ?? "Could not load the deal desk."} onRetry={desk.reload} />;
  const d = desk.data;
  const mine = [...(board.data?.active ?? []), ...(board.data?.finished ?? [])];
  const implied = MULTIPLES.map((m) => d.implied_kobo[m.key]).filter((v): v is string => v !== null).map((v) => Number(BigInt(v)));
  const low = implied.length ? Math.min(...implied) : null;
  const high = implied.length ? Math.max(...implied) : null;
  const price = Number(BigInt(d.price_kobo));
  return (
    <>
      <NeedsYouNow cards={urgent(board.data, career.data, player)} />
      <Panel title="Deal pipeline" aside="Every deal open in the market, by stage">
        {d.pipeline.length === 0 && <p className="muted small">No takeover, share sale or vote is open at the moment. Deals are proposed as quarters close.</p>}
        {d.pipeline.map((deal, index) => (
          <div key={index} className="definition">
            <div className="row">
              <span><span className="card-tag">{deal.kind.toUpperCase()}</span> <span className="strong">{deal.title}</span></span>
              <span className={deal.open ? "tag tag-active" : "tag"}>{deal.open ? "● " : ""}{deal.stage}</span>
            </div>
            <div className="muted small">{deal.price_kobo ? `${formatNaira(deal.price_kobo)} a share · ` : ""}{deal.deadline}. {deal.words} <a href="#/market/offers">Open it</a> · <button className="link-button" onClick={() => setTicker(deal.ticker)}>Analyse {deal.ticker}</button></div>
          </div>
        ))}
      </Panel>

      <Panel title="Company analysis" aside={d.is_employer ? "Your employer" : `${d.sector} · ${d.headquarters}`}>
        <CompanyPicker value={d.ticker} companies={d.companies} onChange={setTicker} />
        <div className="tiles">
          <NumberTile label="Share price" value={formatNaira(d.price_kobo)} change={d.change_bps} note="today" />
          <NumberTile label="Value of all its shares" value={formatCompact(d.market_value_kobo)} note={`${d.shares_in_issue.toLocaleString("en-NG")} shares`} />
          <NumberTile label={`Profit, ${d.period_label}`} value={formatCompact(d.net_profit_kobo)} note={`on sales of ${formatCompact(d.revenue_kobo)}`} />
          <NumberTile label="Credit rating" value={<Rating value={d.rating} />} note={<a href={`#/companies/${d.ticker}`}>Company page</a>} />
        </div>
        <div className="scroll">
          <table>
            <thead><tr><th scope="col">Valuation multiple</th><th scope="col" className="num">{d.ticker}</th><th scope="col" className="num">Companies like it (middle)</th><th scope="col" className="num">Price that would imply</th></tr></thead>
            <tbody>
              {MULTIPLES.map((m) => (
                <tr key={m.key}>
                  <th scope="row">{m.label}<div className="muted small">{m.plain}</div></th>
                  <td className="num mono">{times(d.multiples[m.key])}</td>
                  <td className="num mono">{times(d.peer_median[m.key])}</td>
                  <td className="num mono">{d.implied_kobo[m.key] ? formatNaira(d.implied_kobo[m.key]!) : "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Valuation workspace" aside="What the companies like it say it is worth">
        {low === null || high === null ? <p className="muted small">There is not enough to go on: it makes no profit, or there is no company like it to compare with.</p> : (
          <>
            <p className="small">
              Priced like the companies in its industry, one {d.ticker} share would be worth between <span className="mono strong">{formatNaira(String(low))}</span> and{" "}
              <span className="mono strong">{formatNaira(String(high))}</span>. It trades at <span className="mono strong">{formatNaira(d.price_kobo)}</span>:{" "}
              {price < low ? <span className="change-up">▲ below the range. Either the market knows something the multiples do not, or it is cheap.</span>
                : price > high ? <span className="change-down">▼ above the range. The market expects it to do better than companies like it.</span>
                : "inside the range."}
            </p>
            <div className="range" role="img" aria-label={`Range ${formatNaira(String(low))} to ${formatNaira(String(high))}; price ${formatNaira(d.price_kobo)}`}>
              {(() => {
                const from = Math.min(low, price) * 0.9, to = Math.max(high, price) * 1.1;
                const at = (v: number) => `${((v - from) / (to - from)) * 100}%`;
                return (<>
                  <div className="range-band" style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})` }} />
                  <div className="range-mark" style={{ left: at(price) }}><span className="mono small">▼ price</span></div>
                </>);
              })()}
            </div>
            <p className="muted small">A multiple is a comparison, not a valuation: a company that is growing faster, or owes less, deserves a higher one. The full worked valuation (profits to come, brought back to today) is on the company's page.</p>
          </>
        )}
      </Panel>

      <Panel title="Comparable companies" aside={d.sector}>
        <div className="scroll">
          <table>
            <thead><tr><th scope="col">Company</th><th scope="col">Rating</th><th scope="col" className="num">Value</th><th scope="col" className="num">÷ profit</th><th scope="col" className="num">÷ owners' money</th><th scope="col" className="num">÷ EBITDA</th></tr></thead>
            <tbody>
              {d.peers.map((peer) => (
                <tr key={peer.ticker} className={peer.this ? "row-chosen" : undefined}>
                  <th scope="row">{peer.this ? peer.name : <button className="link-button" onClick={() => setTicker(peer.ticker)}>{peer.name}</button>} <span className="ticker">{peer.ticker}</span></th>
                  <td><Rating value={peer.rating} /></td>
                  <td className="num mono">{formatCompact(peer.market_value_kobo)}</td>
                  <td className="num mono">{times(peer.multiples.earnings)}</td>
                  <td className="num mono">{times(peer.multiples.book)}</td>
                  <td className="num mono">{times(peer.multiples.ebitda)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Due-diligence checklist" aside={`${d.diligence.filter((item) => item.ok).length} of ${d.diligence.length} clear`}>
        {d.diligence.map((item) => (
          <div key={item.label} className="row">
            <span>{item.ok ? <span className="change-up">✓</span> : <span className="change-down">✕</span>} {item.label}</span>
            <span className="muted small">{item.words}</span>
          </div>
        ))}
        <p className="muted small">Counterparties, deal documents, and deals a player arranges for a fee arrive with the stage that lets players found and run companies.</p>
      </Panel>

      <Panel title="Tasks and deadlines" aside={<a href="#/work">All your work</a>}>
        <Matters objectives={mine} empty="No deal work yet." />
      </Panel>
    </>
  );
}

export function InvestmentBankerRail({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  return (<><BuildRail player={player} onLoggedOut={onLoggedOut} /><WatchlistPanel onLoggedOut={onLoggedOut} /></>);
}

// ---------------------------------------------------------------------------
// Risk Manager
// ---------------------------------------------------------------------------

const LEVEL = { low: "● Low", medium: "◆ Medium", high: "▲ High" } as const;

export function RiskManagerWork({ player, onLoggedOut }: Props) {
  const [book, setBook] = useState<"auto" | "own">("auto");
  const desk = useLoad(() => api.riskDesk(book), `risk:${book}:${player.cash.amount_kobo}`, onLoggedOut);
  const board = useLoad(api.objectives, "risk-objectives", onLoggedOut);
  const career = useLoad(api.career, "risk-career", onLoggedOut);
  if (desk.loading && !desk.data) return <Loading what="the risk desk" />;
  if (desk.error || !desk.data) return <Failed message={desk.error ?? "Could not load the risk desk."} onRetry={desk.reload} />;
  const d = desk.data;
  const worstLoss = d.scenarios.reduce((most, s) => (BigInt(s.loss_kobo) > most ? BigInt(s.loss_kobo) : most), 0n);
  return (
    <>
      <NeedsYouNow cards={urgent(board.data, career.data, player)} />
      <Panel title="Risk exposure" aside={d.book_name}>
        {d.in_empire && (
          <div className="tabs tabs-inline" role="tablist">
            <button role="tab" aria-selected={d.book === "empire"} className={d.book === "empire" ? "tab active" : "tab"} onClick={() => setBook("auto")}>The empire's book</button>
            <button role="tab" aria-selected={d.book === "own"} className={d.book === "own" ? "tab active" : "tab"} onClick={() => setBook("own")}>Your own</button>
          </div>
        )}
        <div className="tiles">
          <NumberTile label="Total exposure" value={formatCompact(d.at_risk_kobo)} note={`of ${formatCompact(d.total_kobo)} in all: shares and company bonds`} />
          <NumberTile label="Value-at-risk, one day" value={lost(d.var_kobo)} note={d.var_bps === null ? `needs 10 Closing Bells (${d.days_of_history} so far)` : `${formatPercent(d.var_bps, 2)} of the shares`} />
          <NumberTile label="Expected shortfall" value={lost(d.shortfall_kobo)} note={d.shortfall_bps === null ? "needs 10 Closing Bells" : "the average of the worst days"} />
          <NumberTile label="Largest fall on record" value={lost(d.worst_kobo)} note={d.worst_bps === null ? "needs 10 Closing Bells" : `a day of ${formatPercent(d.worst_bps, 2)}`} />
        </div>
        <details className="why">
          <summary>Why these figures?</summary>
          <p className="small">
            Value-at-risk is the loss not expected to be exceeded on a normal day: on 19 trading days in 20, going by how the
            BSX 50 has moved, the shares held would not have lost more than this. It says nothing about the 20th day. Expected
            shortfall is the average loss on those worst days. Both look backwards: a market that has been calm looks safe
            until the day it is not.
          </p>
        </details>
      </Panel>

      <Panel title="Risk by category">
        <div className="two-columns">
          <div><div className="why-title">BY KIND</div><Wheel slices={d.categories} total={d.total_kobo} /></div>
          <div>
            <div className="why-title">SHARES BY INDUSTRY</div>
            {d.sectors.length === 0 && <p className="muted small">No shares are held.</p>}
            {d.sectors.slice(0, 6).map((row) => (
              <div key={row.label} className="bar-row">
                <div className="row"><span>{row.label}</span><span className="mono">{formatPercent(row.share_bps)} <span className="muted">· {formatCompact(row.value_kobo)}</span></span></div>
                <div className="meter"><div className="meter-fill" style={{ width: `${row.share_bps / 100}%` }} /></div>
              </div>
            ))}
            <div className="why-title">SHARES BY CITY</div>
            {d.cities.map((row) => (
              <div key={row.label} className="bar-row">
                <div className="row"><span>{row.label}</span><span className="mono">{formatPercent(row.share_bps)} <span className="muted">· {formatCompact(row.value_kobo)}</span></span></div>
                <div className="meter"><div className="meter-fill" style={{ width: `${row.share_bps / 100}%` }} /></div>
              </div>
            ))}
          </div>
        </div>
      </Panel>

      <Panel title="Top exposures" aside="Largest first">
        {d.exposures.length === 0 && <p className="muted small">Nothing is held but cash.</p>}
        {d.exposures.length > 0 && (
          <div className="scroll">
            <table>
              <thead><tr><th scope="col">Exposure</th><th scope="col">Rating</th><th scope="col">Risk level</th><th scope="col" className="num">Value</th><th scope="col" className="num">Of the book</th></tr></thead>
              <tbody>
                {d.exposures.map((row) => (
                  <tr key={row.name + row.what}>
                    <th scope="row">{row.name} <span className="muted small">{row.what}</span></th>
                    <td>{row.rating ? <Rating value={row.rating} /> : <span className="muted small">the Government</span>}</td>
                    <td className={row.level === "high" ? "change-down" : row.level === "low" ? "change-up" : undefined}>{LEVEL[row.level]}</td>
                    <td className="num mono">{formatCompact(row.value_kobo)}</td>
                    <td className="num mono">{formatPercent(row.share_bps)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Stress tests" aside="What each would cost this book today">
        {d.scenarios.map((scenario) => (
          <div key={scenario.name} className="bar-row">
            <div className="row"><span className="strong">{scenario.name}</span><span className="mono change-down">▼ {formatCompact(scenario.loss_kobo)}</span></div>
            <div className="meter"><div className="meter-fill meter-loss" style={{ width: `${worstLoss > 0n ? Number((BigInt(scenario.loss_kobo) * 100n) / worstLoss) : 0}%` }} /></div>
            <div className="muted small">{scenario.words}</div>
          </div>
        ))}
      </Panel>

      <Panel title="Liquidity" aside="Could a sudden bill be met without selling?">
        <div className="row"><span>Cash</span><span className="mono">{formatCompact(d.cash_kobo)} <span className="muted">· {formatPercent(d.cash_share_bps)} of the book</span></span></div>
        <div className="row"><span>Government bonds and bills (sold to the desk in a day)</span><span className="mono">{formatCompact(d.categories.find((c) => c.label === "Government bonds and bills")?.value_kobo ?? "0")}</span></div>
        {d.staff_pay_kobo && <div className="row"><span>The staff's pay each quarter</span><span className="mono">{formatCompact(d.staff_pay_kobo)} <span className="muted">· cash covers {d.quarters_of_staff_pay} quarters</span></span></div>}
      </Panel>

      <Panel title="Alerts and monitoring">
        {d.alerts.length === 0 && <p className="small">✓ Nothing on this book breaks a rule of thumb today.</p>}
        <ul className="reasons">{d.alerts.map((alert) => <li key={alert} className="change-down">▲ {alert}</li>)}</ul>
        <p className="muted small">Derivatives, hedges and insurance cover arrive in a later stage. Until then risk is managed by what is held and how much.</p>
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------------------
// Legal Counsel
// ---------------------------------------------------------------------------

export function LawyerWork({ player, onLoggedOut }: Props) {
  const [ticker, setTicker] = useState<string | undefined>(undefined);
  const desk = useLoad(() => api.lawyerDesk(ticker), `lawyer:${ticker ?? ""}`, onLoggedOut);
  const board = useLoad(api.objectives, "lawyer-objectives", onLoggedOut);
  const career = useLoad(api.career, "lawyer-career", onLoggedOut);
  const empire = useLoad(api.empires, `lawyer-empire:${player.empire?.name ?? ""}`, onLoggedOut);
  if (desk.loading && !desk.data) return <Loading what="the case files" />;
  if (desk.error || !desk.data) return <Failed message={desk.error ?? "Could not load the case files."} onRetry={desk.reload} />;
  const d = desk.data;
  const mine = [...(board.data?.active ?? []), ...(board.data?.finished ?? [])];
  const room = empire.data?.room ?? null;
  return (
    <>
      <NeedsYouNow cards={urgent(board.data, career.data, player)} />
      <Panel title="Active legal matters" aside={<a href="#/work">All your work</a>}>
        <Matters objectives={mine} empty="No matters in hand." />
      </Panel>

      <Panel title="Contract management" aside={room ? room.name : "Needs a seat in an empire"}>
        {!room && <p className="muted small">A Legal Counsel with a seat in an empire drafts its pacts with other empires. <a href="#/empire">See the empires</a>.</p>}
        {room && room.pacts.length === 0 && <p className="muted small">{room.name} has no pacts. Draft one in the <a href="#/empire">War Room</a>.</p>}
        {room?.pacts.map((pact) => (
          <div key={pact.id} className="row">
            <span>With {pact.with} <span className="muted small">· {pact.kind}</span></span>
            <span className="small">{pact.status}{!pact.legal && <span className="change-down"> · unlawful</span>}{pact.exposed && " · uncovered"}</span>
          </div>
        ))}
        {room && room.cases.length > 0 && <div className="why-title">PROVED THEFTS IN THE EMPIRE</div>}
        {room?.cases.map((item) => <div key={item.id} className="row"><span>{item.who} <span className="muted small">· {item.category}</span></span><span className="mono">{formatNaira(item.amount_kobo)} · {item.status}</span></div>)}
      </Panel>

      <Panel title="Case workspace" aside={`${d.sector} · ${d.headquarters}`}>
        <CompanyPicker value={d.ticker} companies={d.companies} onChange={setTicker} />
        <div className="why-title">PARTIES: WHO CONTROLS IT</div>
        <p className="small">{d.control}</p>
        {d.holders.map((holder) => (
          <div key={holder.holder} className="bar-row">
            <div className="row"><span>{holder.holder}</span><span className="mono">{formatPercent(holder.share_bps)}</span></div>
            <div className="meter"><div className="meter-fill" style={{ width: `${holder.share_bps / 100}%` }} /></div>
          </div>
        ))}
        {d.bid && <p className="small"><span className="card-tag">TAKEOVER</span> An offer of {formatNaira(d.bid.price_kobo)} a share is open{d.bid.hostile ? ", against the board's advice" : ""}. It closes with {d.bid.closes_label}. A buyer needs more than half the shares to take control.</p>}
        <div className="why-title">RISKS: WHO IS PAID FIRST IF IT FAILS ({d.period_label.toUpperCase()}, AS FILED)</div>
        <div className="scroll">
          <table>
            <thead><tr><th scope="col" className="num">Rank</th><th scope="col">Who</th><th scope="col" className="num">Owed</th><th scope="col">Why there</th></tr></thead>
            <tbody>
              {d.ranking.map((row) => (
                <tr key={row.rank}>
                  <td className="num mono">{row.rank}</td><th scope="row">{row.who}</th>
                  <td className="num mono">{formatCompact(row.amount_kobo)}</td><td className="muted small">{row.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small">Rated <Rating value={d.rating} />. {d.overdue ? <span className="change-down">▼ It has debt it has not repaid on time: its lenders may act.</span> : "Nothing it owes is past its date."} <a href={`#/companies/${d.ticker}`}>Documents: its filed accounts and notices</a>.</p>
      </Panel>

      <Panel title="Regulatory watchlist" aside="Companies the rules are closing in on">
        {d.watch.length === 0 && <p className="small">✓ No company is in default, behind on its debts, or under offer.</p>}
        {d.watch.map((row) => (
          <div key={row.ticker} className="row">
            <span><button className="link-button" onClick={() => setTicker(row.ticker)}>{row.name}</button> <Rating value={row.rating} /></span>
            <span className="small change-down">{row.reasons.join(" · ")}</span>
          </div>
        ))}
        {d.exposed_pacts.length > 0 && <div className="why-title">PACTS THAT HAVE COME TO LIGHT</div>}
        {d.exposed_pacts.map((pact, index) => <div key={index} className="row"><span>{pact.one} and {pact.other}</span><span className={pact.legal ? "muted small" : "small change-down"}>{pact.kind}{pact.legal ? "" : " · unlawful"}</span></div>)}
      </Panel>

      <Panel title="Property, litigation and evidence">
        <p className="muted small">
          The property checklist (title, environment, zoning, consent, contract) arrives with the property stage. Litigation
          before a court, and evidence folders, arrive with the law stage: until then a proved theft is decided by the head of
          the empire, and goes on the thief's legal record.
        </p>
        {d.your_record.map((line, index) => <div key={index} className="row"><span className="small">{line.words}</span></div>)}
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------------------
// Financial Journalist
// ---------------------------------------------------------------------------

export function JournalistWork({ player, onLoggedOut, onChanged }: Props) {
  const news = useLoad(() => api.news({ limit: 40 }), "journalist-news", onLoggedOut);
  const economy = useLoad(api.economy, "journalist-economy", onLoggedOut);
  const market = useLoad(api.market, "journalist-market", onLoggedOut);
  const board = useLoad(api.objectives, "journalist-objectives", onLoggedOut);
  const career = useLoad(api.career, "journalist-career", onLoggedOut);
  const empires = useLoad(api.empires, "journalist-empires", onLoggedOut);
  const [target, setTarget] = useState("");
  const [finding, setFinding] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (news.loading && !news.data) return <Loading what="the newsroom" />;
  if (news.error || !news.data) return <Failed message={news.error ?? "Could not load the newsroom."} onRetry={news.reload} />;
  const items = news.data.items;
  const seen = new Set<string>();
  const stories = items.filter((item) => { const key = `${item.story}|${item.kind}|${item.period}`; if (seen.has(key)) return false; seen.add(key); return true; })
    .sort((a, b) => b.period - a.period || b.day - a.day || b.importance - a.importance);
  const prices = economy.data?.prices ?? null;
  const history = economy.data?.history ?? [];
  const last = history[history.length - 1], before = history[history.length - 2];
  const growth = last && before && BigInt(before.company_sales_kobo) > 0n
    ? Number(((BigInt(last.company_sales_kobo) - BigInt(before.company_sales_kobo)) * 10000n) / BigInt(before.company_sales_kobo)) : null;
  const jobs = last && before && before.jobs > 0 ? Math.round(((last.jobs - before.jobs) / before.jobs) * 10000) : null;
  const movers = [...(market.data?.shares ?? [])].sort((a, b) => Math.abs(b.change_bps) - Math.abs(a.change_bps)).slice(0, 6);
  const mine = [...(board.data?.active ?? []), ...(board.data?.finished ?? [])];
  const passed = (board.data?.skills ?? []).reduce((sum, skill) => sum + skill.passes, 0);
  const league = empires.data?.directory.league ?? [];
  async function investigate() {
    setBusy(true); setFinding(null);
    try {
      const answer = await api.empire("POST", "/empire/investigations", { empire_id: Number(target) });
      setFinding(answer.notice ?? "Done."); empires.reload(); onChanged();
    } catch (problem) { setFinding(problem instanceof ApiError ? problem.message : "Could not reach the server."); }
    finally { setBusy(false); }
  }
  return (
    <>
      <NeedsYouNow cards={urgent(board.data, career.data, player)} />
      <Panel title="Newsroom: top stories" aside={<a href="#/news">The whole wire</a>}>
        {stories.length === 0 && <p className="muted small">The wire is quiet.</p>}
        {stories.slice(0, 4).map((item, index) => <Story key={`${item.story}${item.outlet}${index}`} item={item} lead={index === 0} />)}
      </Panel>

      <Panel title="Draft and publish pipeline" aside={<a href="#/work">All your work</a>}>
        <Matters objectives={mine} empty="Nothing drafted yet." />
        <p className="muted small">A story is filed as a piece of work: the server checks every fact in it against the record before it counts as published. A Financial Journalist cannot declare anybody guilty, or change market data.</p>
      </Panel>

      <Panel title="Investigations" aside="One a quarter">
        <p className="small">
          Empires make secret pacts with each other. Look into one empire each quarter: the higher your level, the better
          your chance of uncovering a pact it is party to. An uncovered pact becomes public, and an unlawful one costs both
          empires trust.
        </p>
        <div className="inline-form">
          <label className="answer"><span className="field-label">Empire to look into</span>
            <select value={target} onChange={(event) => setTarget(event.target.value)}><option value="">Choose…</option>{league.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
          <button className="button-outline" disabled={busy || !target} onClick={investigate}>Investigate</button>
        </div>
        {finding && <p className="small" role="status">{finding}</p>}
        {(empires.data?.directory.exposed_pacts ?? []).map((pact, index) => (
          <div key={index} className="row"><span>{pact.one} and {pact.other}</span><span className={pact.legal ? "muted small" : "small change-down"}>{pact.kind}{pact.legal ? "" : " · unlawful"}</span></div>
        ))}
        <p className="muted small">Sources with a status of their own arrive with the stage that brings election and court reporting.</p>
      </Panel>

      <Panel title="Economic indicators" aside={economy.data?.period_label ?? undefined}>
        <div className="tiles">
          <NumberTile label="Growth: companies' sales, on the quarter" value={growth === null ? "n/a" : <Change bps={growth} />} />
          <NumberTile label="Inflation, over the year" value={prices ? formatPercent(prices.inflation_bps) : "n/a"} note={prices ? `target ${formatPercent(prices.inflation_target_bps)}` : undefined} />
          <NumberTile label="Jobs, on the quarter" value={jobs === null ? "n/a" : <Change bps={jobs} />} note={last ? `${last.jobs.toLocaleString("en-NG")} in work` : undefined} />
          <NumberTile label="The Central Bank's rate" value={prices ? formatPercent(prices.policy_rate_bps, 2) : "n/a"} note={prices ? <Change bps={prices.policy_rate_bps - prices.previous_rate_bps} /> : undefined} />
          <NumberTile label="Confidence" value={prices ? (prices.confidence_bps / 100).toFixed(0) : "n/a"} note="100 is normal" />
          <NumberTile label="Housing index" value="n/a" note="arrives with property" />
        </div>
        <p className="small"><a href="#/economy">Macro research: the economy and the Central Bank's rule</a></p>
      </Panel>

      <Panel title="Market intelligence" aside="Today's largest moves">
        {movers.map((share) => (
          <div key={share.ticker} className="row">
            <span><a href={`#/companies/${share.ticker}`}>{share.name}</a> <span className="ticker">{share.ticker}</span> <span className="muted small">{share.sector}</span></span>
            <span><span className="mono">{formatNaira(share.price_kobo)}</span> <Change bps={share.change_bps} /></span>
          </div>
        ))}
      </Panel>

      <Panel title="Company news flow">
        {items.filter((item) => item.tickers.length > 0 && item.tickers.length <= 3).slice(0, 8).map((item, index) => (
          <div key={index} className="news-line">
            <div className="small muted">{item.outlet} · {item.period_label}, day {item.day} · {item.tickers.join(", ")}</div>
            <div className="small">{item.headline}</div>
          </div>
        ))}
      </Panel>

      <Panel title="Audience and credibility">
        <div className="row"><span>Your reputation</span><span className="mono">{career.data?.reputation ?? player.reputation} of 100</span></div>
        <div className="row"><span>Stories that stood up to checking</span><span className="mono">{passed}</span></div>
        <p className="muted small">Every story that passes its checks adds to your reputation; a pact you uncover adds more. Readers and audience figures arrive when players can publish under their own name.</p>
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------------------
// The head of an empire (the CEO's screen, used by an Acting Head with capped powers)
// ---------------------------------------------------------------------------

// Nigeria, sketched: enough to show where the empire's holdings have their head offices.
const OUTLINE: [number, number][] = [[2.7, 6.4], [2.8, 9.1], [3.8, 10.4], [3.6, 11.7], [4.4, 13.5], [6.9, 13.3], [8.0, 13.3], [9.6, 12.8], [12.3, 13.1],
  [13.6, 13.7], [14.6, 12.2], [14.2, 11.2], [13.3, 9.6], [12.8, 8.5], [11.8, 7.0], [11.2, 6.5], [10.2, 6.9], [9.2, 6.4], [8.5, 4.8], [7.5, 4.4],
  [6.1, 4.3], [5.4, 5.4], [4.4, 6.3]];
const CITIES: Record<string, { at: [number, number]; label: [number, number] }> = {
  "Lagos": { at: [3.38, 6.52], label: [0, -14] }, "Abuja": { at: [7.49, 9.06], label: [0, -14] }, "Kano": { at: [8.52, 12.0], label: [0, -14] },
  "Port Harcourt": { at: [7.01, 4.82], label: [-52, 16] }, "Aba": { at: [7.37, 5.11], label: [26, -6] },
};
const place = ([lon, lat]: [number, number]): [number, number] => [(lon - 2.2) * 24, (14.2 - lat) * 24];

function MapOfOperations({ cities }: { cities: { city: string; value_kobo: string }[] }) {
  const most = cities.reduce((top, c) => Math.max(top, Number(BigInt(c.value_kobo))), 0);
  const value = (name: string) => cities.find((c) => c.city.toLowerCase() === name.toLowerCase())?.value_kobo ?? "0";
  return (
    <div className="two-columns">
      <svg viewBox="0 0 312 250" role="img" aria-label="Nigeria, with the cities where the empire's holdings have their head offices" className="map">
        <polygon points={OUTLINE.map((p) => place(p).join(",")).join(" ")} className="map-land" />
        {Object.entries(CITIES).map(([name, spot]) => {
          const [x, y] = place(spot.at);
          const held = Number(BigInt(value(name)));
          const r = held > 0 && most > 0 ? 5 + 13 * Math.sqrt(held / most) : 4;
          return (
            <g key={name}>
              <circle cx={x} cy={y} r={r} className={held > 0 ? "map-dot" : "map-dot empty"}><title>{`${name}: ${formatNaira(value(name))}`}</title></circle>
              <text x={x + spot.label[0]} y={y + spot.label[1] - (held > 0 ? r - 6 : 0)} textAnchor="middle" className="map-label">{name}</text>
            </g>
          );
        })}
      </svg>
      <div>
        {Object.keys(CITIES).map((name) => (
          <div key={name} className="row"><span>{name}</span><span className="mono">{BigInt(value(name)) > 0n ? formatCompact(value(name)) : "—"}</span></div>
        ))}
        <p className="muted small">The size of each dot is the value of the shares the empire holds in companies with their head office there.</p>
      </div>
    </div>
  );
}

function decisions(room: EmpireRoom) {
  const out: string[] = [];
  for (const step of room.task?.steps ?? []) if (step.yours_to_approve) out.push(`Approve the investment in ${room.task?.company}.`);
  for (const item of room.cases.filter((c) => c.status === "open")) out.push(`Decide what follows ${item.who}'s proved theft of ${formatNaira(item.amount_kobo)}.`);
  for (const asked of room.applications) out.push(`${asked.display_name} asks for a seat as ${asked.build.replace("_", " ")}.`);
  for (const pact of room.pacts) {
    if (pact.ours && pact.status === "drafted") out.push(`Sign the draft pact with ${pact.with}.`);
    if (!pact.ours && pact.status === "proposed") out.push(`${pact.with} proposes a pact: sign or refuse.`);
  }
  return out;
}

export function HeadWork({ player, onLoggedOut }: Props) {
  const desk = useLoad(api.headDesk, `head:${player.empire?.name ?? ""}`, onLoggedOut);
  const empire = useLoad(api.empires, `head-empire:${player.empire?.waiting ?? 0}`, onLoggedOut);
  if (desk.loading && !desk.data) return <Loading what="the empire" />;
  if (desk.error || !desk.data || !empire.data?.room) return <Failed message={desk.error ?? "You hold no seat in an empire."} onRetry={desk.reload} />;
  const d = desk.data;
  const room = empire.data.room;
  const waiting = decisions(room);
  return (
    <>
      <div className="work-head">
        <h1>{room.name}</h1>
        <span className="muted small">{room.is_head ? "Acting Head: the powers of a CEO, capped until the rank is earned" : "The head's view, open to every member"}</span>
      </div>
      <section aria-label="Needs you now">
        {waiting.length === 0 ? <p className="muted">No decision is waiting for the head.</p> : (
          <div className="queue">
            {waiting.slice(0, 3).map((words, index) => (
              <article key={words} className={index === 0 ? "card card-first" : "card"}>
                <div className="card-top"><span className="card-tag">AWAITING APPROVAL</span></div>
                <h3>{words}</h3>
                <a className={index === 0 ? "button-primary" : "button-outline"} href="#/empire">Open the War Room</a>
              </article>
            ))}
          </div>
        )}
      </section>

      <Panel title="The empire" aside={room.place ? `Place ${room.place} of ${room.empires}` : undefined}>
        <div className="tiles">
          <NumberTile label="Net worth" value={formatCompact(d.worth_kobo)} note={`trust ${room.trust} of 100`} />
          <NumberTile label="Liquid assets" value={formatCompact(d.liquid_kobo)} note="cash, and what the Government owes it" />
          <NumberTile label="Companies held" value={d.companies} note="shares in each" />
          <NumberTile label="People" value={d.players + d.staff} note={`${d.players} players · ${d.staff} staff`} />
        </div>
        {d.history.length >= 2
          ? <SingleLine name="Net worth" data={d.history.map((h) => ({ label: h.label, value: Number(BigInt(h.worth_kobo) / 100n) }))} format={(v) => formatCompact(String(Math.round(v) * 100))} />
          : <p className="muted small">The empire's worth is written down as each quarter closes. The line appears after two.</p>}
      </Panel>

      <Panel title="Portfolio and assets by type">
        <div className="two-columns">
          <div><Wheel slices={d.assets} total={d.worth_kobo} /></div>
          <div>
            <div className="why-title">KEY HOLDINGS</div>
            {d.holdings.length === 0 && <p className="muted small">The empire holds no shares yet. An investment task ends with a purchase.</p>}
            {d.holdings.map((h) => (
              <div key={h.ticker} className="row"><span><a href={`#/companies/${h.ticker}`}>{h.name}</a> <span className="muted small">{h.sector} · {h.city}</span></span><span className="mono">{formatCompact(h.value_kobo)} <span className="muted">· {formatPercent(h.share_bps)}</span></span></div>
            ))}
          </div>
        </div>
        <p className="muted small">Subsidiaries (companies the empire controls) and property arrive with the stages that let players found companies and own property. A head cannot yet approve a takeover.</p>
      </Panel>

      <Panel title="Strategic objective" aside={room.task ? `${room.task.company} · up to ${formatCompact(room.task.amount_kobo)}` : "No task in hand"}>
        {room.task
          ? <ProgressTracker steps={room.task.steps.map((s) => ({ label: `${s.build_name}`, done: s.status === "done", note: s.status === "done" ? (s.done_by ?? "the staff") : s.taken_by ?? s.what.split(":")[0] }))} />
          : <p className="muted small">Start an investment task in the <a href="#/empire">War Room</a>: every build has a step in it.</p>}
      </Panel>

      <Panel title="Where the empire operates" aside="A map of Nigeria">
        <MapOfOperations cities={d.cities} />
      </Panel>

      <Panel title="Government exposure">
        <div className="row"><span>Lent to the Federal Government (bonds and bills)</span><span className="mono">{formatCompact(d.government_kobo)} <span className="muted">· {formatPercent(d.government_bps)} of the empire</span></span></div>
        <p className="muted small">Contracts with the Government, and what a change of policy would do to the empire, arrive with the politics stage.</p>
      </Panel>

      <Panel title="Staff activity" aside={`${d.players} players · ${d.staff} staff`}>
        {room.seats.filter((seat) => seat.held || seat.staffed).map((seat) => {
          const step = room.task?.steps.find((s) => s.build === seat.build && s.status !== "waiting");
          return (
            <div key={`${seat.build}${seat.slot}`} className="row">
              <span>{seat.name} <span className="muted small">· {seat.build_name}{seat.level ? `, Level ${seat.level}` : ""}</span></span>
              <span className="small">{step ? (step.status === "done" ? "✓ step done" : step.taken_by === seat.name ? "● working on the step" : "the step is waiting") : "no step in hand"}</span>
            </div>
          );
        })}
      </Panel>
    </>
  );
}

export function HeadRail({ player, onLoggedOut, onChanged }: Props) {
  const empire = useLoad(api.empires, `head-rail:${player.empire?.waiting ?? 0}`, onLoggedOut);
  const [busy, setBusy] = useState(false);
  const room = empire.data?.room;
  if (!room) return null;
  const act = {
    busy, error: null, notice: null,
    run: async (method: "POST" | "PUT" | "DELETE", path: string, body?: unknown) => {
      setBusy(true);
      try { await api.empire(method, path, body); empire.reload(); onChanged(); return true; } catch { return false; } finally { setBusy(false); }
    },
  };
  return (
    <>
      <Panel title="Live events" aside="The decision log">
        {room.events.slice(0, 10).map((event, index) => (
          <div key={index} className="news-line">
            <div className="small muted">{new Date(event.at).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>
            <div className="small">{event.words}</div>
          </div>
        ))}
      </Panel>
      <Chat room={room} act={act} />
    </>
  );
}
