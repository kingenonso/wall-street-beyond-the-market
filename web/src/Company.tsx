import { useState } from "react";
import { api, type Company, type FiledReport, type Kobo } from "./api";
import { AreaChart } from "./Charts";
import { changeBps, formatCompact, formatLagosDate, formatMillions, formatNaira, formatPercent, periodLabel } from "./format";
import { shortDate } from "./Market";
import { Term } from "./Term";
import { useLoad } from "./hooks";
import { FactsPanel, ResultsReportPanel } from "./Facts";
import { InvestorPanel } from "./Investor";
import { TradePanel } from "./Trade";
import { newsDate } from "./News";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";
import { TrendChart } from "./TrendChart";

type Line = {
  key: string;
  label: string;
  hint?: string;         // the plain-language meaning of an accounting term
  total?: boolean;       // drawn in bold with a rule above
  cost?: boolean;        // shown in brackets, the way accounts show money going out
  optional?: boolean;    // left out when it is zero in every quarter
  heading?: string;      // a sub-heading above this line
};

export const STATEMENTS: Record<string, { title: string; section: "income_statement" | "cash_flow" | "balance_sheet"; lines: Line[] }> = {
  income: {
    title: "Income statement",
    section: "income_statement",
    lines: [
      { key: "revenue", label: "Sales", hint: "what customers paid" },
      { key: "interest_income", label: "Interest earned", hint: "on money it has lent", optional: true },
      { key: "cost_of_sales", label: "Cost of sales", hint: "supplies bought and pay for those who make what it sells", cost: true },
      { key: "operating_expenses", label: "Running costs", hint: "wages and pension contributions", cost: true },
      { key: "ebitda", label: "EBITDA", hint: "profit before interest paid, tax and wear on assets", total: true },
      { key: "depreciation", label: "Depreciation", hint: "wear on buildings and machines", cost: true },
      { key: "operating_profit", label: "Operating profit", total: true },
      { key: "interest_expense", label: "Interest paid", hint: "on its borrowings", cost: true },
      { key: "profit_before_tax", label: "Profit before tax", total: true },
      { key: "tax", label: "Tax", cost: true },
      { key: "net_profit", label: "Net profit", hint: "what is left for the owners", total: true },
    ],
  },
  cash: {
    title: "Cash flow",
    section: "cash_flow",
    lines: [
      { key: "cash_opening", label: "Cash at the start" },
      { key: "cash_from_operations", label: "From operations", hint: "trading, interest and tax" },
      { key: "cash_from_investing", label: "From investing", hint: "upkeep spending and loans repaid to it" },
      { key: "cash_from_financing", label: "From financing", hint: "debt repaid and dividends" },
      { key: "cash_closing", label: "Cash at the end", total: true },
      { key: "capital_spending", label: "Upkeep of buildings and machines", heading: "Of which", cost: true },
      { key: "debt_repaid", label: "Debt repaid", cost: true },
      { key: "dividends_paid", label: "Dividends paid to owners", cost: true },
    ],
  },
  balance: {
    title: "Balance sheet",
    section: "balance_sheet",
    lines: [
      { key: "cash", label: "Cash", heading: "What it owns" },
      { key: "customer_loans", label: "Loans to the public", optional: true },
      { key: "loans_to_companies", label: "Loans to companies", optional: true },
      { key: "fixed_assets", label: "Buildings and machines" },
      { key: "investments", label: "Shares in other companies", optional: true },
      { key: "total_assets", label: "Total assets", total: true },
      { key: "borrowings", label: "Borrowings", hint: "loans and bonds", heading: "What it owes" },
      { key: "payables", label: "Unpaid bills", optional: true },
      { key: "customer_funds", label: "Customers' money it holds", optional: true },
      { key: "total_liabilities", label: "Total liabilities", total: true },
      { key: "share_capital", label: "Share capital", hint: "what owners paid in", heading: "Owners' funds" },
      { key: "retained_earnings", label: "Retained earnings", hint: "past profits kept in the business" },
      { key: "total_equity", label: "Total owners' funds", total: true },
    ],
  },
};

export function StatementTable({ name, reports }: { name: keyof typeof STATEMENTS; reports: FiledReport[] }) {
  const statement = STATEMENTS[name];
  const value = (report: FiledReport, key: string): Kobo => report.figures[statement.section][key] ?? "0";
  const lines = statement.lines.filter((line) => !line.optional || reports.some((r) => value(r, line.key) !== "0"));
  return (
    <div className="scroll">
      <table className="statement">
        <caption className="muted small">₦ millions. Figures in brackets are money going out.</caption>
        <thead>
          <tr>
            <th scope="col">{statement.title}</th>
            {reports.map((r) => <th key={r.period} scope="col" className="num">{r.period_label}</th>)}
          </tr>
        </thead>
        <tbody>
          {lines.flatMap((line) => {
            const rows = [];
            if (line.heading) {
              rows.push(
                <tr key={`${line.key}-heading`} className="sub-heading">
                  <th scope="colgroup" colSpan={reports.length + 1}>{line.heading}</th>
                </tr>,
              );
            }
            rows.push(
              <tr key={line.key} className={line.total ? "total" : undefined}>
                <th scope="row">
                  {line.label}
                  {line.hint && <span className="muted small hint-inline"> {line.hint}</span>}
                </th>
                {reports.map((r) => {
                  const raw = value(r, line.key);
                  const shown = line.cost && raw !== "0" ? (BigInt(raw) * -1n).toString() : raw;
                  return <td key={r.period} className="num mono">{formatMillions(shown)}</td>;
                })}
              </tr>,
            );
            return rows;
          })}
        </tbody>
      </table>
    </div>
  );
}

function Tile({ label, now, before, against = "on last quarter" }: { label: string; now: Kobo; before?: Kobo; against?: string }) {
  return (
    <div className="tile">
      <div className="muted small">{label}</div>
      <div className="mono figure-small">{formatCompact(now)}</div>
      <div className="small"><Change bps={changeBps(now, before)} /> <span className="muted">{against}</span></div>
    </div>
  );
}

function WhySales({ latest, previous }: { latest: FiledReport; previous?: FiledReport }) {
  const causes = latest.figures.notes.why_revenue;
  if (causes.length === 0) return null;
  const change = changeBps(latest.figures.income_statement.revenue, previous?.figures.income_statement.revenue);
  const outcome =
    change === null ? null : change >= 0
      ? `Sales rose ${formatPercent(change)} from last quarter`
      : `Sales fell ${formatPercent(-change)} from last quarter`;
  const steps = outcome ? [...causes, outcome] : causes;
  return (
    <div className="why">
      <div className="why-title">WHY DID SALES MOVE IN {latest.period_label.toUpperCase()}?</div>
      <ol className="chain">
        {steps.map((step, index) => (
          <li key={step} className="chain-step">
            {index > 0 && <span className="chain-arrow" aria-hidden="true">→</span>}
            <span className="chain-box">{step}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

type CompanyTab = "overview" | "accounts" | "investors" | "about";
const COMPANY_TABS: [CompanyTab, string][] = [["overview", "Overview"], ["accounts", "Accounts"], ["investors", "For investors"], ["about", "About it"]];
const CHART_RANGES: [string, number][] = [["A week (one quarter)", 7], ["Four weeks (one year)", 28], ["Everything", 9999]];

/** The company's name, price and today's move, with its rating and a watch button. */
function CompanyHeader({ company, onLoggedOut }: { company: Company; onLoggedOut: () => void }) {
  const quote = useLoad(() => api.quote(company.ticker), `quote:${company.ticker}`, onLoggedOut);
  const watched = useLoad(api.watchlist, "watchlist", onLoggedOut);
  const [busy, setBusy] = useState(false);
  const latest = company.reports[company.reports.length - 1];
  const watching = (watched.data ?? []).some((w) => w.ticker === company.ticker);
  const q = quote.data;
  const price = q ? q.last_price_kobo ?? q.reference_price_kobo : null;
  const move = q && q.last_price_kobo ? changeBps(q.last_price_kobo, q.reference_price_kobo) : null;
  async function toggle() {
    setBusy(true);
    try { await (watching ? api.unwatch(company.ticker) : api.watch(company.ticker)); } catch { /* the star simply stays as it was */ }
    watched.reload();
    setBusy(false);
  }
  return (
    <div className="company-head">
      <nav aria-label="Breadcrumb" className="small muted"><a href="#/companies">Companies</a> › {company.sector} › {company.name}</nav>
      <div className="company-title">
        <h1>{company.name}</h1>
        <span className="ticker mono">{company.ticker}</span>
        <Rating value={latest.credit_rating} />
        <span className="muted small">{company.sector} · head office in {company.headquarters}</span>
      </div>
      <div className="company-price">
        {price && <span className="mono figure">{formatNaira(price)}</span>}
        {q && (q.last_price_kobo ? <Change bps={move} /> : <span className="muted small">not yet traded</span>)}
        {q && <span className="muted small">Can trade between {formatNaira(q.lowest_today_kobo)} and {formatNaira(q.highest_today_kobo)} today</span>}
        <span className="company-actions">
          <button className="button-quiet" disabled={busy} aria-pressed={watching} onClick={toggle}>{watching ? "★ Watching" : "☆ Watch"}</button>
          <a className="button-quiet" href="#trade-panel">Trade ↓</a>
        </span>
      </div>
      <span className="muted small">
        {latest.period === 0 ? "Opening balance sheet" : `Latest filing: ${latest.period_label}`}
        {latest.amended && <span className="amended"> · Amended filing, version {latest.version}</span>}
      </span>
    </div>
  );
}

/** The share price day by day, with how many shares traded, over a chosen stretch. */
function PriceChartPanel({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const days = useLoad(() => api.priceHistory(ticker), `history:${ticker}`, onLoggedOut);
  const [range, setRange] = useState(28);
  const shown = (days.data ?? []).slice(-range);
  const naira = (v: number) => `₦${v.toFixed(2)}`;
  return (
    <Panel>
      <div className="panel-head">
        <h2>Price, day by day</h2>
        <div className="range-buttons" role="group" aria-label="How far back">
          {CHART_RANGES.map(([label, n]) => <button key={n} aria-pressed={range === n} onClick={() => setRange(n)}>{label}</button>)}
        </div>
      </div>
      {shown.length >= 2 ? (
        <AreaChart
          points={shown.map((d) => ({ label: shortDate(d.session_date), value: Number(d.close_kobo) / 100, volume: d.volume }))}
          format={naira} baseline={Number(shown[0].close_kobo) / 100} baselineLabel={`its close on ${shortDate(shown[0].session_date)}`}
          label={`Closing price from ${naira(Number(shown[0].close_kobo) / 100)} on ${shortDate(shown[0].session_date)} to ${naira(Number(shown[shown.length - 1].close_kobo) / 100)}. Bars below: shares traded each day.`} />
      ) : <p className="muted small">The chart appears after two days of trading.</p>}
      {shown.length >= 2 && <p className="muted small" style={{ marginTop: 6 }}>Bars at the bottom: how many shares changed hands each day.</p>}
    </Panel>
  );
}

/** The key figures an investor looks at, each with its meaning in plain words. */
function PlainFacts({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const { data: a } = useLoad(() => api.analysis(ticker), `analysis:${ticker}`, onLoggedOut);
  if (!a) return null;
  const times = (v: number | null) => (v === null ? "n/a" : `${v.toFixed(1)}`);
  return (
    <div className="fact-grid">
      <div className="fact"><span className="lbl"><Term word="Market value" /></span><span className="fact-value">{formatCompact(a.market_value_kobo)}</span><span className="muted small">What the whole company is worth on the exchange.</span></div>
      <div className="fact"><span className="lbl"><Term word="P/E" /></span><span className="fact-value">{times(a.price_to_profit)}</span><span className="muted small">{a.price_to_profit === null ? "It made no profit over the past year." : `The price is ${a.price_to_profit.toFixed(1)} years of today’s profit.`}</span></div>
      <div className="fact"><span className="lbl"><Term word="Dividend" /></span><span className="fact-value">{formatPercent(a.dividend_yield_bps)} a year</span><span className="muted small">Cash paid to owners, per ₦100 of shares.</span></div>
      <div className="fact"><span className="lbl">Profit, past year</span><span className="fact-value">{formatCompact(a.yearly_profit_kobo)}</span><span className="muted small">After tax, over the last four quarters.</span></div>
      <div className="fact"><span className="lbl">Sales, past year</span><span className="fact-value">{formatCompact(a.yearly_sales_kobo)}</span><span className="muted small">What customers paid it over four quarters.</span></div>
      <div className="fact"><span className="lbl">Owners’ funds a share</span><span className="fact-value">{formatNaira(a.book_per_share_kobo)}</span><span className="muted small">What owners would have if it sold everything and paid every debt.</span></div>
    </div>
  );
}

/** Why the price is where it is, in plain reasons. */
function WhyPricePanel({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const { data: w } = useLoad(() => api.why(ticker), `why:${ticker}`, onLoggedOut);
  if (!w) return null;
  return (
    <Panel title="Why the price is where it is">
      <p className="small">{w.move_bps !== 0 && <><Change bps={w.move_bps} />{" "}</>}{w.summary}</p>
      {w.reasons.length > 0 && <ul className="reasons">{w.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
      {w.valuation_reasons.length > 0 && (
        <>
          <p className="small muted">What changed investors’ view of its worth at its {w.valuation_label} results:</p>
          <ul className="reasons">{w.valuation_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </>
      )}
    </Panel>
  );
}

function CompanyBody({ company, onLoggedOut }: { company: Company; onLoggedOut: () => void }) {
  const [view, setView] = useState<CompanyTab>("overview");
  const [tab, setTab] = useState<keyof typeof STATEMENTS>("income");
  const trading = company.reports.filter((r) => r.period >= 1);
  const latest = company.reports[company.reports.length - 1];
  const previous = company.reports[company.reports.length - 2];
  const shown = tab === "balance" ? company.reports : trading;
  // Results are set against the same quarter a year ago once there is one: many businesses swing with the seasons.
  const yearAgo = trading.find((r) => r.period === latest.period - 4);
  const compare = yearAgo ?? previous;
  const against = yearAgo ? "on a year ago" : "on last quarter";

  return (
    <>
      <CompanyHeader company={company} onLoggedOut={onLoggedOut} />

      <div className="underline-tabs" role="tablist" aria-label="About this company">
        {COMPANY_TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={view === key} className={view === key ? "active" : undefined} onClick={() => setView(key)}>{label}</button>
        ))}
      </div>

      {view === "overview" && (
        <>
          <PriceChartPanel ticker={company.ticker} onLoggedOut={onLoggedOut} />
          <PlainFacts ticker={company.ticker} onLoggedOut={onLoggedOut} />
          <WhyPricePanel ticker={company.ticker} onLoggedOut={onLoggedOut} />
          {trading.length === 0 ? (
            <Panel>
              <p className="muted">
                This company has not traded yet. Its first quarterly results are filed when {periodLabel(1)} ends, one real week
                after the world opens. Its opening balance sheet is under Accounts.
              </p>
            </Panel>
          ) : (
            <Panel title="Sales and profit" aside="As filed, by quarter">
              <div className="tiles">
                <Tile label="Sales" now={latest.figures.income_statement.revenue} before={compare?.figures.income_statement.revenue} against={against} />
                <Tile label="EBITDA" now={latest.figures.income_statement.ebitda} before={compare?.figures.income_statement.ebitda} against={against} />
                <Tile label="Net profit" now={latest.figures.income_statement.net_profit} before={compare?.figures.income_statement.net_profit} against={against} />
                <Tile label="Cash" now={latest.figures.balance_sheet.cash} before={compare?.figures.balance_sheet.cash} against={against} />
              </div>
              <TrendChart reports={trading} />
              <WhySales latest={latest} previous={previous?.period >= 1 ? previous : undefined} />
            </Panel>
          )}
          <ResultsReportPanel ticker={company.ticker} onLoggedOut={onLoggedOut} />
        </>
      )}

      {view === "accounts" && (
        <Panel>
          <div className="tabs tabs-inline" role="tablist" aria-label="Statements">
            {(Object.keys(STATEMENTS) as (keyof typeof STATEMENTS)[]).map((name) => (
              <button key={name} role="tab" aria-selected={tab === name} className={tab === name ? "tab active" : "tab"} onClick={() => setTab(name)}>
                {STATEMENTS[name].title}
              </button>
            ))}
          </div>
          {shown.length === 0 ? <p className="muted">Nothing to show until the first quarter ends.</p> : <StatementTable name={tab} reports={shown} />}
        </Panel>
      )}

      {view === "investors" && (
        <>
          <FactsPanel ticker={company.ticker} onLoggedOut={onLoggedOut} />
          <InvestorPanel ticker={company.ticker} onLoggedOut={onLoggedOut} />
        </>
      )}

      {view === "about" && <CompanyAbout company={company} />}
    </>
  );
}

export function CompanyWork({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void; onTraded?: () => void }) {
  const { data, error, loading, reload } = useLoad(() => api.company(ticker), `company:${ticker}`, onLoggedOut);
  if (loading && !data) return <Loading what="the company" />;
  if (error) return <Failed message={error} onRetry={reload} />;
  return data ? <CompanyBody company={data} onLoggedOut={onLoggedOut} /> : null;
}

function CompanyNews({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const { data } = useLoad(() => api.news({ ticker, limit: 12 }), `news:${ticker}`, onLoggedOut);
  // One telling of each story is enough here.
  const seen = new Set<string>();
  const items = (data?.items ?? []).filter((item) => {
    const key = `${item.story}|${item.kind}|${item.period}`;
    return seen.has(key) ? false : (seen.add(key), true);
  }).slice(0, 5);
  if (items.length === 0) return null;
  return (
    <Panel title="In the news" aside={<a href="#/news">All news</a>}>
      {items.map((item, index) => (
        <div key={index} className="news-line">
          <div className="small muted"><span className="mono">{newsDate(item)}</span> · {item.outlet}</div>
          <div className="strong">{item.headline}</div>
          <div className="small muted">{item.body}</div>
        </div>
      ))}
    </Panel>
  );
}

/** Beside a company's page: trading it, and the latest news about it. */
export function CompanyRail({ ticker, onLoggedOut, onTraded }: { ticker: string; onLoggedOut: () => void; onTraded?: () => void }) {
  return (
    <>
      <div id="trade-panel"><TradePanel ticker={ticker} onLoggedOut={onLoggedOut} onTraded={onTraded ?? (() => undefined)} layout="rail" /></div>
      <CompanyNews ticker={ticker} onLoggedOut={onLoggedOut} />
    </>
  );
}

/** Everything else about the company: its rating, its people and places, who it sells to and buys from, its debts. */
function CompanyAbout({ company: data }: { company: Company }) {
  const latest = data.reports[data.reports.length - 1];
  const notes = latest.figures.notes;
  return (
    <>


      <Panel title="Credit rating">
        <div className="headline"><Rating value={latest.credit_rating} /></div>
        <div className="why-title">WHY THIS RATING?</div>
        <ul className="reasons">
          {latest.rating_reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      </Panel>

      {(notes.staff !== undefined || data.location) && (
        <Panel title="People and place">
          {notes.staff !== undefined && (
            <div className="row"><span>Staff</span><span className="mono">{notes.staff.toLocaleString("en-NG")}</span></div>
          )}
          {notes.wages !== undefined && (
            <div className="row"><span>Wages paid this quarter</span><span className="mono">{formatCompact(notes.wages)}</span></div>
          )}
          {data.location && (
            <>
              <div className="row">
                <span>Running costs in {data.headquarters}</span>
                <span className="mono">
                  {data.location.running_cost_bps === 10000
                    ? "average"
                    : `${formatPercent(Math.abs(data.location.running_cost_bps - 10000), 0)} ${data.location.running_cost_bps < 10000 ? "below" : "above"} average`}
                </span>
              </div>
              <ul className="reasons">{data.location.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
            </>
          )}
        </Panel>
      )}

      {notes.sales_to && latest.period >= 1 && (
        <Panel title="Who it sells to" aside={latest.period_label}>
          {([["Households", notes.sales_to.households], ["Other companies", notes.sales_to.other_companies], ["The Government", notes.sales_to.government]] as const).map(([who, amount]) => (
            <div key={who} className="row">
              <span>{who}</span>
              <span className="mono">{formatCompact(amount)}</span>
            </div>
          ))}
        </Panel>
      )}

      {data.buys_from.length > 0 && (
        <Panel title="What it buys" aside="share of its sales">
          {data.buys_from.slice(0, 6).map((supplier) => (
            <div key={supplier.sector} className="row">
              <span>{supplier.sector}</span>
              <span className="mono">{formatPercent(supplier.share_bps)}</span>
            </div>
          ))}
          <p className="muted small">It buys from the companies in these sectors, so its good and bad quarters reach them too.</p>
        </Panel>
      )}

      <Panel title="What it owes">
        {notes.borrowings.length === 0 && <p className="muted">It has no borrowings.</p>}
        {notes.borrowings.map((debt) => (
          <div key={debt.name} className="definition">
            <div className="row">
              <span className="strong">{debt.kind === "bond" ? "Bond" : "Bank loan"}</span>
              <span className="mono">{formatCompact(debt.principal_outstanding)}</span>
            </div>
            <div className="muted small">
              Owed to {debt.lender}. Interest {formatPercent(debt.annual_rate_bps)} a year.{" "}
              {debt.maturity_period <= latest.period
                ? debt.maturity_period <= 0
                  ? "It should have been repaid before the game began, and has not been."
                  : `It should have been repaid by ${periodLabel(debt.maturity_period)}, and has not been.`
                : `${debt.repayment === "bullet" ? "Repaid in one go in" : "Repaid a little each quarter until"} ${periodLabel(debt.maturity_period)}.`}
            </div>
          </div>
        ))}
        {notes.principal_overdue !== "0" && (
          <p className="warning">{formatCompact(notes.principal_overdue)} is past its repayment date and unpaid.</p>
        )}
      </Panel>

      {notes.management_notes.length > 0 && (
        <Panel title="Notes from management">
          <ul className="reasons">
            {notes.management_notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </Panel>
      )}

      <Panel title="About this filing">
        <p className="muted small">
          Filed by {latest.filed_by.toLowerCase()} on {formatLagosDate(new Date(latest.filed_at))}.
          These are the company's own figures, as filed for the public.
        </p>
      </Panel>
    </>
  );
}
