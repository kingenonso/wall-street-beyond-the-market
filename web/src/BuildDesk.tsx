// The build screens (design document, section 18). Every build's screen has the same four
// zones; this file holds the work area and the context rail for the two builds open so far.
//   Asset Manager   what you own and how it is divided, the trading console, research
//   Accountant      a company's filed statements, ratios, tax, and the audit list

import { useState } from "react";
import {
  api, type AccountantDesk, type FiledReport, type Objective, type ObjectiveBoard, type Player, type Career,
} from "./api";
import { StatementTable } from "./Company";
import { formatCompact, formatMillions, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { WatchlistPanel } from "./Market";
import { LevelPanel, ObjectivesPanel, PayPanel, SkillTree, StateTag, Wheel, progressWords } from "./Parts";
import { Band, BandCell, Change, Failed, Loading, PageHead, Panel, Rating } from "./Shell";
import { TradePanel } from "./Trade";
import { LineChart, naira } from "./TrendChart";

type Props = { player: Player; onLoggedOut: () => void; onChanged: () => void };
type Card = { tag: string; when: string; title: string; text: string; action: string; href: string };

/** "Needs you now" for a professional: only things that are true for this player at this moment. */
export function urgent(board: ObjectiveBoard | null, career: Career | null, player?: Player): Card[] {
  const cards: Card[] = [];
  if (!career || !board) return cards;
  if (player?.empire && player.empire.waiting > 0) {
    cards.push({ tag: "War Room", when: player.empire.name, title: `${player.empire.waiting} waiting for you in the War Room`,
                 text: "A step in the empire's task, an approval, or a report to file. Your colleagues cannot go on until it is done.",
                 action: "Open the War Room", href: "#/empire" });
  }
  if (career.career?.review) {
    cards.push({ tag: "Performance review", when: `${career.career.review.passes} passed of ${career.career.review.finished}`,
                 title: "Your work is under review", text: `${career.career.review.why} ${career.career.review.how_to_recover}`,
                 action: "See the work on offer", href: "#/work" });
  }
  if (career.career && career.career.at_cap && career.career.level < career.career.top_level) {
    cards.push({ tag: "Rank", when: `Level ${career.career.gate}`, title: `You are at the Level ${career.career.gate} gate`,
                 text: "Work alone goes no further. Mastery across your modules and a rank case open the levels above. Experience you earn meanwhile is kept.",
                 action: "See what the rank case needs", href: "#/rank" });
  }
  if (board.weekend.open && board.offers.some((offer) => offer.setting === "live" && offer.available)) {
    cards.push({ tag: "Weekend challenge", when: "Open now", title: "The weekend challenge is open",
                 text: "Work passed in it makes a module proven, and pays and teaches one and a half times as much. It closes on Sunday at 22:00, Lagos time.",
                 action: "See the challenge", href: "#/work" });
  }
  for (const objective of board.active) {
    const waiting = objective.can_hand_in && objective.terms.fields.length > 0;
    cards.push({
      tag: waiting ? "Hand in" : "In hand", when: formatNaira(objective.reward_kobo),
      title: objective.title,
      text: `${progressWords(objective) ?? ""} Deadline: ${objective.terms.deadline} ${objective.payer} is waiting for it.`,
      action: waiting ? "Do the work" : "Open it", href: "#/work",
    });
  }
  if (career.job && career.pay && !career.pay.worked_this_quarter) {
    cards.push({ tag: "Pay day", when: "This quarter", title: "No work finished yet this quarter",
                 text: `${career.job.name} pays a quarter's salary only to staff who finished at least one piece of work in it.`,
                 action: board.active.length ? "Open your work" : "Take work on", href: "#/work" });
  }
  const free = board.offers.filter((offer) => offer.available);
  if (board.ready && board.active.length < board.limit && free.length > 0) {
    const again = free.find((offer) => offer.practise_again);
    const offer = again ?? free[0];
    cards.push({ tag: again ? "Practise again" : "Work on offer", when: formatNaira(offer.reward_kobo), title: offer.title,
                 text: `${offer.idea} ${free.length} piece${free.length === 1 ? "" : "s"} of work on offer.`,
                 action: "See the work on offer", href: "#/work" });
  }
  if (!career.job) {
    cards.unshift({ tag: "Career", when: "Three steps", title: career.bank ? "Find an employer" : "Choose your bank and find an employer",
                    text: "Work and salary come through an employer.", action: "Go to your career", href: "#/career" });
  }
  return cards.slice(0, 3);
}

export function NeedsYouNow({ cards }: { cards: Card[] }) {
  return (
    <section aria-labelledby="needs-heading">
      <div className="work-head">
        <h1 id="needs-heading">Needs you now</h1>
        <span className="muted small">{cards.length === 0 ? "Nothing waiting" : cards.length === 1 ? "1 item" : `${cards.length} items`}</span>
      </div>
      {cards.length === 0 && <p className="muted">Nothing is waiting on you. The workspace below is yours.</p>}
      <div className="queue">
        {cards.map((card, index) => (
          <article key={card.title + card.tag} className={index === 0 ? "card card-first" : "card"}>
            <div className="card-top"><span className="card-tag">{card.tag}</span><span className="mono muted">{card.when}</span></div>
            <h3>{card.title}</h3>
            <p className="muted">{card.text}</p>
            <a className={index === 0 ? "button-primary" : "button-outline"} href={card.href}>{card.action}</a>
          </article>
        ))}
      </div>
    </section>
  );
}

/** Zone 4, the same for every build: objectives, level, pay and the skill tree. */
export function BuildRail({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const board = useLoad(api.objectives, `rail-objectives:${player.cash.amount_kobo}`, onLoggedOut);
  const career = useLoad(api.career, `rail-career:${player.level}:${player.employer}`, onLoggedOut);
  return (
    <>
      {board.data && <ObjectivesPanel board={board.data} />}
      {career.data?.career && <LevelPanel career={career.data.career} />}
      {career.data && <PayPanel career={career.data} />}
      {board.data && career.data?.career && <SkillTree skills={board.data.skills} tracks={board.data.tracks} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Asset Manager
// ---------------------------------------------------------------------------

export function AssetManagerWork({ player, onLoggedOut, onChanged }: Props) {
  const desk = useLoad(api.assetDesk, `asset-desk:${player.cash.amount_kobo}`, onLoggedOut);
  const portfolio = useLoad(api.portfolio, `asset-portfolio:${player.cash.amount_kobo}`, onLoggedOut);
  const bonds = useLoad(api.bonds, `asset-bonds:${player.cash.amount_kobo}`, onLoggedOut);
  const board = useLoad(api.objectives, "asset-objectives", onLoggedOut);
  const career = useLoad(api.career, "asset-career", onLoggedOut);
  const ticker = useLoad(api.ticker, "asset-ticker", onLoggedOut);
  const [trading, setTrading] = useState<string>("");
  if (desk.loading && !desk.data) return <Loading what="your desk" />;
  if (desk.error || !desk.data) return <Failed message={desk.error ?? "Could not load your desk."} onRetry={desk.reload} />;
  const d = desk.data;
  const holdings = portfolio.data?.holdings ?? [];
  const held = bonds.data?.holdings ?? [];
  const chosen = trading || holdings[0]?.ticker || ticker.data?.shares[0]?.ticker || "";
  const ahead = d.change_year_bps !== null && d.index_change_year_bps !== null ? d.change_year_bps - d.index_change_year_bps : null;

  return (
    <>
      <PageHead title="Asset manager"
                sub="What you are looking after, how it is divided, and the console to trade it"
                aside={`${d.companies_held} companies · ${d.industries_held} industries`} />

      <Band label="What you are looking after">
        <BandCell label="Total value" value={formatCompact(d.total_kobo)} note={<><Change bps={d.change_today_bps} /> against yesterday's close</>} />
        <BandCell label="Over the last game year" value={d.change_year_bps === null ? "n/a" : formatPercent(d.change_year_bps)}
                  note={d.index_change_year_bps === null ? "needs a few Closing Bells" : `BSX 50: ${formatPercent(d.index_change_year_bps)}`} />
        <BandCell label="Against the BSX 50" value={ahead === null ? "n/a" : <Change bps={ahead} />} note="includes money paid in" />
        <BandCell label="Largest single share" value={formatPercent(d.largest_bps)} note="of everything you own" />
      </Band>

      <NeedsYouNow cards={urgent(board.data, career.data, player)} />

      <Panel title="How your money is divided">
        <div className="two-columns">
          <div>
            <div className="why-title">Allocation</div>
            <Wheel slices={d.allocation} total={d.total_kobo} />
          </div>
          <div>
            <div className="why-title">Top industries in your shares</div>
            {d.sectors.length === 0 && <p className="muted small">You hold no shares yet.</p>}
            {d.sectors.slice(0, 6).map((sector) => (
              <div key={sector.label} className="bar-row">
                <div className="row"><span>{sector.label}</span><span className="mono">{formatPercent(sector.share_bps)} <span className="muted">· {formatCompact(sector.value_kobo)}</span></span></div>
                <div className="meter"><div className="meter-fill" style={{ width: `${sector.share_bps / 100}%` }} /></div>
              </div>
            ))}
          </div>
        </div>
      </Panel>

      <Panel title="Holdings" aside={<a href="#/portfolio">Full portfolio</a>}>
        {holdings.length === 0 && held.length === 0 && <p className="muted small">Nothing held yet. Use the trading console below, or the <a href="#/market/bonds">Bonds and bills</a> page.</p>}
        {holdings.length > 0 && (
          <div className="scroll" tabIndex={0}>
            <table>
              <thead><tr><th scope="col">Share</th><th scope="col" className="num">Held</th><th scope="col" className="num">Price</th><th scope="col" className="num">Today</th><th scope="col" className="num">Value</th><th scope="col" className="num">Gain since bought</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
              <tbody>
                {holdings.map((h) => (
                  <tr key={h.ticker}>
                    <th scope="row"><a href={`#/companies/${h.ticker}`}>{h.name}</a> <span className="ticker">{h.ticker}</span></th>
                    <td className="num mono">{h.shares.toLocaleString("en-NG")}</td>
                    <td className="num mono">{formatNaira(h.price_kobo)}</td>
                    <td className="num"><Change bps={h.change_bps} /></td>
                    <td className="num mono">{formatCompact(h.value_kobo)}</td>
                    <td className={h.gain_kobo.startsWith("-") ? "num mono change-down" : "num mono change-up"}>{h.gain_kobo.startsWith("-") ? "▼" : "▲"} {formatNaira(h.gain_kobo.replace("-", ""))}</td>
                    <td className="num"><button className="button-quiet" onClick={() => setTrading(h.ticker)}>Trade</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {held.length > 0 && (
          <div className="scroll" tabIndex={0}>
            <table>
              <thead><tr><th scope="col">Bond or bill</th><th scope="col">Kind</th><th scope="col" className="num">Held</th><th scope="col" className="num">Return a year</th><th scope="col" className="num">Value</th></tr></thead>
              <tbody>
                {held.map((b) => (
                  <tr key={b.code}>
                    <th scope="row"><a href="#/market/bonds">{b.name}</a></th>
                    <td>{b.kind_label}</td>
                    <td className="num mono">{b.units.toLocaleString("en-NG")}</td>
                    <td className="num mono">{formatPercent(b.yield_bps, 2)}</td>
                    <td className="num mono">{formatCompact(b.value_kobo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Trading console" aside={<a href="#/market">The whole market</a>}>
        <label className="answer">
          <span className="field-label">Share</span>
          <select value={chosen} onChange={(event) => setTrading(event.target.value)}>
            {(ticker.data?.shares ?? []).map((s) => <option key={s.ticker} value={s.ticker}>{s.ticker} · {formatNaira(s.price_kobo)}</option>)}
          </select>
        </label>
        {chosen && <TradePanel key={chosen} ticker={chosen} onLoggedOut={onLoggedOut} onTraded={() => { onChanged(); desk.reload(); portfolio.reload(); }} />}
        <p className="muted small">Bonds and bills are bought and sold on the <a href="#/market/bonds">Bonds and bills</a> page. Derivatives and alternative investments arrive in a later stage.</p>
      </Panel>

      <Panel title="Research" aside="From the game's own records">
        {(portfolio.data?.advice ?? []).length === 0 && <p className="muted small">Nothing to flag on what you hold.</p>}
        <ul className="reasons">{(portfolio.data?.advice ?? []).map((line) => <li key={line}>{line}</li>)}</ul>
        <p className="small"><a href="#/market/industries">Industries: heat map, growth and rankings</a> · <a href="#/economy">The economy and the Central Bank's rule</a> · <a href="#/news">News</a></p>
      </Panel>
    </>
  );
}

export function AssetManagerRail({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  return (
    <>
      <BuildRail player={player} onLoggedOut={onLoggedOut} />
      <WatchlistPanel onLoggedOut={onLoggedOut} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Accountant
// ---------------------------------------------------------------------------

const asReports = (desk: AccountantDesk): FiledReport[] =>
  [...desk.quarters].reverse().map((q) => ({
    period: q.period, period_label: q.period_label,
    figures: { income_statement: q.income_statement, cash_flow: q.cash_flow, balance_sheet: q.balance_sheet },
  }) as unknown as FiledReport);

function AuditList({ objectives }: { objectives: Objective[] }) {
  if (objectives.length === 0) return <p className="muted small">No work for clients yet. <a href="#/work">See the work on offer</a>.</p>;
  return (
    <>
      {objectives.map((o) => (
        <div key={o.id} className="row">
          <span><StateTag state={o.state} /> <a href="#/work">{o.title}</a>{o.terms.client && <span className="muted small"> · {o.terms.client.name}</span>}</span>
          <span className="mono">{o.state === "passed" ? `+ ${formatNaira(o.paid_kobo)}` : o.state === "active" ? formatNaira(o.reward_kobo) : "—"}</span>
        </div>
      ))}
    </>
  );
}

export function AccountantWork({ player, onLoggedOut }: Props) {
  const [ticker, setTicker] = useState<string | undefined>(undefined);
  const [statement, setStatement] = useState<"income" | "balance" | "cash">("income");
  const desk = useLoad(() => api.accountantDesk(ticker), `accountant:${ticker ?? ""}:${player.employer}`, onLoggedOut);
  const board = useLoad(api.objectives, "accountant-objectives", onLoggedOut);
  const career = useLoad(api.career, "accountant-career", onLoggedOut);
  if (desk.loading && !desk.data) return <Loading what="the books" />;
  if (desk.error || !desk.data) return <Failed message={desk.error ?? "Could not load the books."} onRetry={desk.reload} />;
  const d = desk.data;
  const latest = d.quarters[0];
  const before = d.quarters[1];
  const reports = asReports(d);
  const mine = [...(board.data?.active ?? []), ...(board.data?.finished ?? [])];
  const forecasts = (board.data?.finished ?? []).filter((o) => o.template === "ac_forecast" && o.submission && o.result?.answers);
  const change = (key: string) => {
    if (!before) return null;
    const was = Number(BigInt(before.income_statement[key]));
    return was > 0 ? Math.round(((Number(BigInt(latest.income_statement[key])) - was) / was) * 10000) : null;
  };

  return (
    <>
      <PageHead title="Accountant"
                sub="The statements a company files, what they say quarter by quarter, and what waits on an audit"
                aside={d.is_employer ? "Your employer" : d.sector} />

      {latest && (
        <Band label={`${d.name}, as it filed`}>
          <BandCell label={`Sales, ${latest.period_label}`} value={formatCompact(latest.income_statement.revenue)}
                    note={<><Change bps={change("revenue")} /> on the quarter before</>} />
          <BandCell label="Profit after tax" value={formatCompact(latest.income_statement.net_profit)}
                    note={<><Change bps={change("net_profit")} /> on the quarter before</>} />
          <BandCell label="Cash" value={formatCompact(latest.balance_sheet.cash)} note={`${latest.staff?.toLocaleString("en-NG") ?? "?"} staff`} />
          <BandCell label="Credit rating" value={<Rating value={latest.credit_rating} />} note={<a href={`#/companies/${d.ticker}`}>Company page</a>} />
        </Band>
      )}

      <NeedsYouNow cards={urgent(board.data, career.data, player)} />

      <Panel title="The books">
        <label className="answer">
          <span className="field-label">Company</span>
          <select value={d.ticker} onChange={(event) => setTicker(event.target.value)}>
            {d.companies.map((c) => <option key={c.ticker} value={c.ticker}>{c.name} ({c.ticker}) · {c.sector}</option>)}
          </select>
        </label>
        <div className="tabs tabs-inline" role="tablist">
          {([["income", "Income statement"], ["balance", "Balance sheet"], ["cash", "Cash flow"]] as const).map(([key, label]) => (
            <button key={key} role="tab" aria-selected={statement === key} className={statement === key ? "tab active" : "tab"} onClick={() => setStatement(key)}>{label}</button>
          ))}
        </div>
        <StatementTable name={statement} reports={reports} />
        {latest && latest.notes.length > 0 && (
          <>
            <div className="why-title">Notes to the accounts, {latest.period_label}</div>
            <ul className="reasons">{latest.notes.map((note) => <li key={note}>{note}</li>)}</ul>
          </>
        )}
      </Panel>

      {reports.length > 1 && (
        <Panel title="Sales and profit history" aside="As filed, by quarter">
          <LineChart names={["Sales", "Net profit"]}
                     data={reports.map((r) => ({ label: r.period_label, first: naira(r.figures.income_statement.revenue), second: naira(r.figures.income_statement.net_profit) }))} />
        </Panel>
      )}

      {latest && (
        <Panel title="Key ratios" aside="Worked out from the filed figures">
          <div className="scroll" tabIndex={0}>
            <table className="statement">
              <thead><tr><th scope="col">Ratio</th>{reports.map((r) => <th key={r.period} scope="col" className="num">{r.period_label}</th>)}</tr></thead>
              <tbody>
                {Object.keys(latest.ratios).map((name) => (
                  <tr key={name}>
                    <th scope="row">{name}</th>
                    {[...d.quarters].reverse().map((q) => <td key={q.period} className="num mono">{q.ratios[name] === null ? "n/a" : q.ratios[name]?.toLocaleString("en-NG", { maximumFractionDigits: 2 })}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">Lenders grow wary when debt passes about four times a year's EBITDA, or when profit covers interest less than twice.</p>
        </Panel>
      )}

      {latest && (
        <Panel title="Tax position" aside={`Company tax is ${d.tax_rate_bps / 100}% of profit before tax`}>
          <div className="scroll" tabIndex={0}>
            <table className="statement">
              <thead><tr><th scope="col">₦ millions</th>{reports.map((r) => <th key={r.period} scope="col" className="num">{r.period_label}</th>)}</tr></thead>
              <tbody>
                <tr><th scope="row">Profit before tax</th>{reports.map((r) => <td key={r.period} className="num mono">{formatMillions(r.figures.income_statement.profit_before_tax)}</td>)}</tr>
                <tr><th scope="row">Tax charged</th>{reports.map((r) => <td key={r.period} className="num mono">{formatMillions(r.figures.income_statement.tax)}</td>)}</tr>
              </tbody>
            </table>
          </div>
          <p className="small">
            {BigInt(latest.tax_owed_kobo) > 0n
              ? <span className="change-down">▼ {d.name} owes the tax office {formatNaira(latest.tax_owed_kobo)} it has not been able to pay.</span>
              : <span>✓ {d.name} owes the tax office nothing. A company that makes a loss pays no tax for the quarter.</span>}
          </p>
        </Panel>
      )}

      <Panel title="Audit and client work" aside={<a href="#/work">All your work</a>}>
        <AuditList objectives={mine.filter((o) => o.terms.client)} />
      </Panel>

      {forecasts.length > 0 && (
        <Panel title="Budgets: your forecasts against what was filed">
          {forecasts.map((o) => (
            <div key={o.id} className="row">
              <span>{o.terms.client?.name} <StateTag state={o.state} /></span>
              <span className="mono small">you said {Number(o.submission?.revenue).toLocaleString("en-NG")} m · filed {Number(o.result?.answers?.revenue).toLocaleString("en-NG")} m</span>
            </div>
          ))}
        </Panel>
      )}

      <Panel title="Compliance watch" aside="Companies behind on what they owe, from their latest filings">
        {d.watch.length === 0 && <p className="muted small">✓ Every company is up to date with its bills and its lenders.</p>}
        {d.watch.length > 0 && (
          <div className="scroll" tabIndex={0}>
            <table>
              <thead><tr><th scope="col">Company</th><th scope="col">Rating</th><th scope="col" className="num">Bills unpaid</th><th scope="col" className="num">Debt past its date</th><th scope="col" className="num">Cash</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
              <tbody>
                {d.watch.map((w) => (
                  <tr key={w.ticker}>
                    <th scope="row">{w.name}</th>
                    <td><Rating value={w.credit_rating} /></td>
                    <td className="num mono">{formatCompact(w.unpaid_bills_kobo)}</td>
                    <td className="num mono">{formatCompact(w.overdue_debt_kobo)}</td>
                    <td className="num mono">{formatCompact(w.cash_kobo)}</td>
                    <td className="num"><button className="button-quiet" onClick={() => setTicker(w.ticker)}>Open its books</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">Forensic cases, and evidence that can be taken to court, arrive with the law stage.</p>
      </Panel>
    </>
  );
}

export function AccountantRail({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  return <BuildRail player={player} onLoggedOut={onLoggedOut} />;
}
