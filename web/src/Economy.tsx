import { api, type Economy } from "./api";
import { changeBps, formatCompact, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel } from "./Shell";
import { LineChart, naira } from "./TrendChart";

const people = (count: number) => count.toLocaleString("en-NG");

function Tile({ label, value, change }: { label: string; value: string; change: number | null }) {
  return (
    <div className="tile">
      <div className="muted small">{label}</div>
      <div className="mono figure-small">{value}</div>
      <div className="small"><Change bps={change} /> <span className="muted">on last quarter</span></div>
    </div>
  );
}

function Body({ economy }: { economy: Economy }) {
  const latest = economy.history[economy.history.length - 1];
  const before = economy.history[economy.history.length - 2];
  if (!latest) {
    return (
      <Panel>
        <p className="muted">
          The first quarter has not ended yet. Households, wages and spending are reported here when it does, one real week
          after the world opens.
        </p>
      </Panel>
    );
  }
  const jobsChange = before && before.jobs > 0 ? Math.round(((latest.jobs - before.jobs) / before.jobs) * 10000) : null;

  return (
    <>
      <Panel title="The whole economy" aside={latest.period_label}>
        <div className="tiles">
          <Tile label="Sales of all companies" value={formatCompact(latest.company_sales_kobo)}
                change={changeBps(latest.company_sales_kobo, before?.company_sales_kobo)} />
          <Tile label="Household income" value={formatCompact(latest.household_income_kobo)}
                change={changeBps(latest.household_income_kobo, before?.household_income_kobo)} />
          <Tile label="Household spending" value={formatCompact(latest.household_spending_kobo)}
                change={changeBps(latest.household_spending_kobo, before?.household_spending_kobo)} />
          <Tile label="Jobs at the companies" value={people(latest.jobs)} change={jobsChange} />
        </div>
        <LineChart
          names={["Sales", "Spending"]}
          data={economy.history.map((q) => ({
            label: q.period_label,
            first: naira(q.company_sales_kobo),
            second: naira(q.household_spending_kobo),
          }))}
        />
        <p className="muted small">
          Sales are everything the companies sold: to households, to each other and to the Government. Spending is what
          households alone spent. What households earn in one quarter, they spend in the next.
        </p>
      </Panel>

      <Panel title="Households, by location" aside={`${latest.period_label}, per quarter`}>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Location</th>
                <th scope="col" className="num">Share of people</th>
                <th scope="col" className="num">Jobs</th>
                <th scope="col" className="num">Against last quarter</th>
                <th scope="col" className="num">Income</th>
                <th scope="col" className="num">Against last quarter</th>
                <th scope="col" className="num">Spending</th>
                <th scope="col" className="num">Savings</th>
              </tr>
            </thead>
            <tbody>
              {economy.households.map((h) => (
                <tr key={h.location}>
                  <th scope="row">{h.location}</th>
                  <td className="num mono">{formatPercent(h.population_bps, 0)}</td>
                  <td className="num mono">{people(h.jobs)}</td>
                  <td className="num"><Change bps={h.jobs_change_bps} /></td>
                  <td className="num mono">{formatCompact(h.income_kobo)}</td>
                  <td className="num"><Change bps={h.income_change_bps} /></td>
                  <td className="num mono">{formatCompact(h.spending_kobo)}</td>
                  <td className="num mono">{formatCompact(h.savings_kobo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">Jobs are the people employed by the 50 companies. Half of a company's staff work where its head office is.</p>
      </Panel>

      <Panel title="Where household income came from" aside={latest.period_label}>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Location</th>
                <th scope="col" className="num">Pay from companies</th>
                <th scope="col" className="num">Public-sector pay</th>
                <th scope="col" className="num">Pensions</th>
                <th scope="col" className="num">Total income</th>
              </tr>
            </thead>
            <tbody>
              {economy.households.map((h) => (
                <tr key={h.location}>
                  <th scope="row">{h.location}</th>
                  <td className="num mono">{formatCompact(h.wages_kobo)}</td>
                  <td className="num mono">{formatCompact(h.government_kobo)}</td>
                  <td className="num mono">{formatCompact(h.pensions_kobo)}</td>
                  <td className="num mono">{formatCompact(h.income_kobo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

export function EconomyWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.economy, "economy", onLoggedOut);
  return (
    <>
      <div className="work-head">
        <h1>The economy</h1>
        <span className="muted small">Who earns, who spends and where the money sits</span>
      </div>
      {loading && !data && <Loading what="the economy" />}
      {error && <Failed message={error} onRetry={reload} />}
      {data && <Body economy={data} />}
    </>
  );
}

export function EconomyRail({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data } = useLoad(api.economy, "economy", onLoggedOut);
  if (!data) return null;
  const largest = Math.max(1, ...data.household_spending.map((s) => s.share_bps));
  return (
    <>
      <Panel title="Where the money sits" aside={formatCompact(data.money_in_existence_kobo)}>
        {data.money.map((holder) => (
          <div key={holder.holder} className="bar-row">
            <div className="row">
              <span>{holder.holder}</span>
              <span className="mono">{formatCompact(holder.amount_kobo)} <span className="muted">{formatPercent(holder.share_bps)}</span></span>
            </div>
            <div className="meter" aria-hidden="true"><div className="meter-fill" style={{ width: `${holder.share_bps / 100}%` }} /></div>
          </div>
        ))}
        <p className="muted small">
          All the naira in existence. None is created or destroyed: it only moves from one holder to another.
        </p>
      </Panel>

      {data.household_spending.length > 0 && (
        <Panel title="What households spent on" aside={data.period_label ?? undefined}>
          {data.household_spending.map((share) => (
            <div key={share.sector} className="bar-row">
              <div className="row">
                <span>{share.sector}</span>
                <span className="mono">{formatPercent(share.share_bps)}</span>
              </div>
              <div className="meter" aria-hidden="true"><div className="meter-fill" style={{ width: `${(share.share_bps / largest) * 100}%` }} /></div>
            </div>
          ))}
        </Panel>
      )}

      <Panel title="Still to come">
        <p className="muted small">
          Bank lending, the Central Bank's interest rate, prices and inflation, commodity prices and the Money Watch arrive
          in the next part of this stage.
        </p>
      </Panel>
    </>
  );
}
