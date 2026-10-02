import { useState } from "react";
import { api, type Company, type FiledReport, type Kobo } from "./api";
import { changeBps, formatCompact, formatCount, formatLagosDate, formatMillions, formatPercent, periodLabel } from "./format";
import { useLoad } from "./hooks";
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

const STATEMENTS: Record<string, { title: string; section: "income_statement" | "cash_flow" | "balance_sheet"; lines: Line[] }> = {
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

function StatementTable({ name, reports }: { name: keyof typeof STATEMENTS; reports: FiledReport[] }) {
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

function Tile({ label, now, before }: { label: string; now: Kobo; before?: Kobo }) {
  return (
    <div className="tile">
      <div className="muted small">{label}</div>
      <div className="mono figure-small">{formatCompact(now)}</div>
      <div className="small"><Change bps={changeBps(now, before)} /> <span className="muted">on last quarter</span></div>
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

function CompanyBody({ company }: { company: Company }) {
  const [tab, setTab] = useState<keyof typeof STATEMENTS>("income");
  const trading = company.reports.filter((r) => r.period >= 1);
  const latest = company.reports[company.reports.length - 1];
  const previous = company.reports[company.reports.length - 2];
  const shown = tab === "balance" ? company.reports : trading;

  return (
    <>
      <div className="work-head">
        <div>
          <a href="#/companies" className="small">← All companies</a>
          <h1>{company.name} <span className="ticker mono">{company.ticker}</span></h1>
          <span className="muted small">{company.sector} · Head office in {company.headquarters}</span>
        </div>
        <span className="muted small">
          {latest.period === 0 ? "Opening balance sheet" : `Latest filing: ${latest.period_label}`}
          {latest.amended && <span className="amended"> · Amended filing, version {latest.version}</span>}
        </span>
      </div>

      {trading.length === 0 ? (
        <Panel>
          <p className="muted">
            This company has not traded yet. Its first quarterly results are filed when {periodLabel(1)} ends, one real week
            after the world opens. Its opening balance sheet is below.
          </p>
        </Panel>
      ) : (
        <Panel title="Sales and profit" aside="As filed, by quarter">
          <div className="tiles">
            <Tile label="Sales" now={latest.figures.income_statement.revenue} before={previous?.figures.income_statement.revenue} />
            <Tile label="EBITDA" now={latest.figures.income_statement.ebitda} before={previous?.figures.income_statement.ebitda} />
            <Tile label="Net profit" now={latest.figures.income_statement.net_profit} before={previous?.figures.income_statement.net_profit} />
            <Tile label="Cash" now={latest.figures.balance_sheet.cash} before={previous?.figures.balance_sheet.cash} />
          </div>
          <TrendChart reports={trading} />
          <WhySales latest={latest} previous={previous?.period >= 1 ? previous : undefined} />
        </Panel>
      )}

      <Panel>
        <div className="tabs tabs-inline" role="tablist" aria-label="Statements">
          {(Object.keys(STATEMENTS) as (keyof typeof STATEMENTS)[]).map((name) => (
            <button key={name} role="tab" aria-selected={tab === name} className={tab === name ? "tab active" : "tab"} onClick={() => setTab(name)}>
              {STATEMENTS[name].title}
            </button>
          ))}
        </div>
        {shown.length === 0 ? (
          <p className="muted">Nothing to show until the first quarter ends.</p>
        ) : (
          <StatementTable name={tab} reports={shown} />
        )}
      </Panel>
    </>
  );
}

export function CompanyWork({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(() => api.company(ticker), `company:${ticker}`, onLoggedOut);
  if (loading && !data) return <Loading what="the company" />;
  if (error) return <Failed message={error} onRetry={reload} />;
  return data ? <CompanyBody company={data} /> : null;
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

export function CompanyRail({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const { data } = useLoad(() => api.company(ticker), `company:${ticker}`, onLoggedOut);
  if (!data) return null;
  const latest = data.reports[data.reports.length - 1];
  const notes = latest.figures.notes;
  return (
    <>
      <CompanyNews ticker={ticker} onLoggedOut={onLoggedOut} />

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

      <Panel title="Who owns it" aside={`${formatCount(data.shares_in_issue)} shares`}>
        <div className="stack" role="img" aria-label={data.owners.map((o) => `${o.name} ${formatPercent(o.share_bps, 0)}`).join(", ")}>
          {data.owners.map((owner, index) => (
            <span key={owner.name} className={`stack-part stack-${index}`} style={{ width: `${owner.share_bps / 100}%` }} />
          ))}
        </div>
        {data.owners.map((owner, index) => (
          <div key={owner.name} className="row">
            <span><span className={`swatch stack-${index}`} />{owner.name}</span>
            <span className="mono">{formatPercent(owner.share_bps, 0)}</span>
          </div>
        ))}
      </Panel>

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
