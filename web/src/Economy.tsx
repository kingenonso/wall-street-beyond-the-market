import { api, type Economy, type MoneyWatch } from "./api";
import { changeBps, formatCompact, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel } from "./Shell";
import { LineChart, naira } from "./TrendChart";
import { Term } from "./Term";

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

const percentOf = (bps: number) => `${(bps / 100).toFixed(1).replace(/\.0$/, "")}%`;

const WATCH = {
  green: { mark: "●", word: "Green", meaning: "Money is growing in step with the economy." },
  amber: { mark: "▲", word: "Amber", meaning: "Money is growing faster than the economy, or gathering in one place." },
  red: { mark: "■", word: "Red", meaning: "Money is growing far too fast." },
} as const;

/** The Money Watch: a shape and a word as well as a colour, so it reads without colour. */
function MoneyWatchPanel({ watch, quarter }: { watch: MoneyWatch; quarter: string | null }) {
  const reading = WATCH[watch.reading];
  return (
    <Panel title="The Money Watch" aside={quarter ?? undefined}>
      <div className={`watch watch-${watch.reading}`}>
        <span className="watch-mark" aria-hidden="true">{reading.mark}</span>
        <span className="watch-word">{reading.word}</span>
      </div>
      <p className="small">{reading.meaning}</p>
      <div className="row"><span>Money, over the past year</span><Change bps={watch.money_growth_bps} /></div>
      <div className="row"><span>The economy's sales, over the past year</span><Change bps={watch.output_growth_bps} /></div>
      <div className="why-title">WHY THIS READING?</div>
      <ul className="reasons">{watch.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      <p className="muted small">{watch.action}</p>
      <p className="muted small">
        The Money Watch checks every quarter that there is not too much money for the goods on sale. It never takes money
        from anybody.
      </p>
    </Panel>
  );
}

function PricesPanel({ economy }: { economy: Economy }) {
  const prices = economy.prices;
  if (!prices) return null;
  const inBand = prices.inflation_bps >= prices.inflation_low_bps && prices.inflation_bps <= prices.inflation_high_bps;
  const rateMove = prices.policy_rate_bps - prices.previous_rate_bps;
  const mood = prices.confidence_bps - 10000;
  return (
    <Panel title="Prices and the Central Bank" aside={economy.period_label ?? undefined}>
      <div className="tiles">
        <div className="tile">
          <div className="muted small"><Term word="Inflation">Prices, over the past year</Term></div>
          <div className="mono figure-small">{percentOf(prices.inflation_bps)}</div>
          <div className="small muted">
            {inBand ? "Inside" : prices.inflation_bps > prices.inflation_high_bps ? "▲ Above" : "▼ Below"} the Central Bank's
            band of {percentOf(prices.inflation_low_bps)} to {percentOf(prices.inflation_high_bps)}
          </div>
        </div>
        <div className="tile">
          <div className="muted small"><Term word="Policy rate">Central Bank interest rate</Term></div>
          <div className="mono figure-small">{percentOf(prices.policy_rate_bps)}</div>
          <div className="small muted">
            {rateMove === 0 ? "– Unchanged" : `${rateMove > 0 ? "▲ Up" : "▼ Down"} from ${percentOf(prices.previous_rate_bps)}`}
          </div>
        </div>
        <div className="tile">
          <div className="muted small">Households pay on a bank loan</div>
          <div className="mono figure-small">{percentOf(prices.household_loan_rate_bps)}</div>
          <div className="small muted">a year. They owe {formatCompact(prices.household_debt_kobo)}</div>
        </div>
        <div className="tile">
          <div className="muted small">Households' readiness to spend</div>
          <div className="mono figure-small">
            {Math.abs(mood) < 50 ? "As usual" : `${mood > 0 ? "▲" : "▼"} ${percentOf(Math.abs(mood))}`}
          </div>
          <div className="small muted">{Math.abs(mood) < 50 ? "neither keen nor cautious" : mood > 0 ? "keener than usual" : "more cautious than usual"}</div>
        </div>
      </div>
      <p className="small">{prices.rate_reason}</p>
      <LineChart
        names={["Price rises", "Interest rate"]}
        format={(value) => `${value.toFixed(1)}%`}
        data={economy.macro_history.map((q) => ({ label: q.period_label, first: q.inflation_bps / 100, second: q.policy_rate_bps / 100 }))}
      />
      <p className="muted small">
        The Central Bank aims for prices to rise {percentOf(prices.inflation_target_bps)} a year. When they rise faster it
        raises its interest rate, which makes every loan dearer and slows borrowing and spending. When they rise slower, it
        cuts. Prices today are {percentOf(prices.price_index_bps - 10000)} above where they stood when the world began.
      </p>
      <div className="scroll" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Commodity</th>
              <th scope="col" className="num">Price (start of the world = 100)</th>
              <th scope="col" className="num">Against last quarter</th>
            </tr>
          </thead>
          <tbody>
            {prices.commodities.map((commodity) => (
              <tr key={commodity.name}>
                <th scope="row">{commodity.name}</th>
                <td className="num mono">{(commodity.index_bps / 100).toFixed(1)}</td>
                <td className="num"><Change bps={commodity.change_bps} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        A commodity's price is a cost for the companies that use it and extra sales for those that sell it. Energy is sold
        by oil and gas companies, farm produce by farms, metals by manufacturers, building materials by cement makers.
      </p>
    </Panel>
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

      <PricesPanel economy={economy} />

      <Panel title="Households, by location" aside={`${latest.period_label}, per quarter`}>
        <div className="scroll" tabIndex={0}>
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
        <div className="scroll" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">Location</th>
                <th scope="col" className="num">Pay from companies</th>
                <th scope="col" className="num">Public-sector pay</th>
                <th scope="col" className="num">Pensions</th>
                <th scope="col" className="num">Insurance claims</th>
                <th scope="col" className="num">Total income</th>
                <th scope="col" className="num">Owed to banks</th>
              </tr>
            </thead>
            <tbody>
              {economy.households.map((h) => (
                <tr key={h.location}>
                  <th scope="row">{h.location}</th>
                  <td className="num mono">{formatCompact(h.wages_kobo)}</td>
                  <td className="num mono">{formatCompact(h.government_kobo)}</td>
                  <td className="num mono">{formatCompact(h.pensions_kobo)}</td>
                  <td className="num mono">{formatCompact(h.claims_kobo)}</td>
                  <td className="num mono">{formatCompact(h.income_kobo)}</td>
                  <td className="num mono">{formatCompact(h.debt_kobo)}</td>
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
        <span className="muted small">Prices, interest rates, who earns, who spends and where the money sits</span>
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
      {data.money_watch && <MoneyWatchPanel watch={data.money_watch} quarter={data.period_label} />}

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
          All the naira in existence. New naira appear in one way only: when the Central Bank lends to a bank that is
          short of cash to lend. They go out of existence when the bank repays.
          {data.prices && ` Banks owe the Central Bank ${formatCompact(data.prices.central_bank_lending_kobo)}.`}
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

    </>
  );
}
