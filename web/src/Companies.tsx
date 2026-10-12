import { api } from "./api";
import { formatCompact } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";

export function CompaniesWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.companies, "companies", onLoggedOut);
  const all = data?.sectors.flatMap((s) => s.companies) ?? [];
  const period = all[0]?.period_label;
  const opening = all[0]?.period === 0;

  return (
    <>
      <div className="work-head">
        <h1>Companies</h1>
        {period && (
          <span className="muted small">
            {all.length} companies · {opening ? "opening balance sheets" : `figures from the ${period} filings`}
          </span>
        )}
      </div>
      {loading && <Loading what="the companies" />}
      {error && <Failed message={error} onRetry={reload} />}
      {data?.sectors.map((sector) => (
        <Panel key={sector.code} title={sector.name} aside={`${sector.companies.length} companies`}>
          <div className="scroll" tabIndex={0}>
            <table className="companies">
              <thead>
                <tr>
                  <th scope="col">Company</th>
                  <th scope="col">Head office</th>
                  <th scope="col" className="num">{opening ? "Total assets" : "Sales this quarter"}</th>
                  {!opening && <th scope="col" className="num">Against last quarter</th>}
                  {!opening && <th scope="col" className="num" title="Profit before interest, tax and wear on buildings and machines">EBITDA</th>}
                  {!opening && <th scope="col" className="num">Net profit</th>}
                  <th scope="col">Rating</th>
                </tr>
              </thead>
              <tbody>
                {sector.companies.map((c) => (
                  <tr key={c.ticker}>
                    <th scope="row">
                      <a href={`#/companies/${c.ticker}`}>{c.name}</a> <span className="ticker mono">{c.ticker}</span>
                    </th>
                    <td className="muted">{c.headquarters}</td>
                    <td className="num mono">{formatCompact(opening ? c.total_assets_kobo : c.revenue_kobo)}</td>
                    {!opening && <td className="num"><Change bps={c.revenue_change_bps} /></td>}
                    {!opening && <td className="num mono">{formatCompact(c.ebitda_kobo)}</td>}
                    {!opening && <td className={c.net_profit_kobo.startsWith("-") ? "num mono change-down" : "num mono"}>{formatCompact(c.net_profit_kobo)}</td>}
                    <td><Rating value={c.credit_rating} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ))}
    </>
  );
}

const SCALE = [
  ["AAA, AA, A", "Strong. Very likely to repay what it owes."],
  ["BBB, BB", "Middling. Sound today, with less room for bad news."],
  ["B, CCC", "Weak. Short of cash or behind on its bills."],
  ["D", "In default. A debt has passed its date unpaid."],
];

export function CompaniesRail() {
  return (
    <>
      <Panel title="Reading the ratings">
        {SCALE.map(([grades, meaning]) => (
          <div key={grades} className="definition">
            <div className="mono strong">{grades}</div>
            <div className="muted small">{meaning}</div>
          </div>
        ))}
        <p className="muted small">A weaker rating means a company pays more interest to borrow.</p>
      </Panel>
      <Panel title="What is EBITDA?">
        <p className="muted small">
          Profit before interest, tax, and the wear on buildings and machines. It shows how much cash the business itself
          produces, before the cost of its debts. Lenders compare it with what a company has borrowed.
        </p>
      </Panel>
      <Panel title="Where these figures come from">
        <p className="muted small">
          Everything here is what each company filed for the public. Open a company to see its accounts quarter by quarter,
          who owns it and what it owes.
        </p>
      </Panel>
    </>
  );
}
