import { api, type AbroadSummary, type ConsumersSummary, type Economy, type MoneyWatch, type PropertySummary } from "./api";
import { WatchPanel } from "./Crisis";
import { changeBps, formatCompact, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel } from "./Shell";
import { LineChart, SingleLine, naira } from "./TrendChart";
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

const MINDSET_WORDS: Record<string, string> = {
  optimistic: "Optimistic", pessimistic: "Pessimistic", risk_averse: "Careful", risk_seeking: "Risk-takers", herding: "Follow the crowd",
  contrarian: "Go against the crowd", loyal: "Loyal", fearful: "Fearful", sceptical: "Sceptical", opportunistic: "Bargain hunters",
};

const dollars = (cents: number) => `$${(cents / 100).toFixed(2)}`;
const rate = (fx: number) => `₦${Math.round(fx / 100).toLocaleString("en-NG")}`;
const moveBps = (now: number, before: number | null) => (before ? Math.round(((now - before) / before) * 10000) : null);

/** The rest of the world: oil, the naira, trade and foreign investors (the economy upgrade). */
function AbroadPanel({ abroad }: { abroad: AbroadSummary }) {
  const latest = abroad.trade[abroad.trade.length - 1];
  const fxMove = moveBps(abroad.fx, abroad.previous_fx);
  return (
    <Panel title="The rest of the world" aside="set at each quarter's close">
      <div className="tiles">
        <div className="tile">
          <div className="muted small">Oil, this quarter</div>
          <div className="mono figure-small">{dollars(abroad.oil_cents)}</div>
          <div className="small muted">a barrel{abroad.previous_oil_cents ? <> · <Change bps={moveBps(abroad.oil_cents, abroad.previous_oil_cents)} /> on last quarter</> : null}</div>
        </div>
        <div className="tile">
          <div className="muted small"><Term word="Exchange rate">One US dollar costs</Term></div>
          <div className="mono figure-small">{rate(abroad.fx)}</div>
          <div className="small muted">
            {fxMove === null || fxMove === 0 ? "– unchanged" : fxMove > 0 ? `▼ naira ${(fxMove / 100).toFixed(1)}% weaker` : `▲ naira ${(-fxMove / 100).toFixed(1)}% stronger`}
          </div>
        </div>
        {latest && (
          <div className="tile">
            <div className="muted small">Sold abroad last quarter</div>
            <div className="mono figure-small">{formatCompact(latest.exports)}</div>
            <div className="small muted">of which oil and gas {formatCompact(latest.oil_exports)}</div>
          </div>
        )}
        {latest && (
          <div className="tile">
            <div className="muted small">Bought abroad last quarter</div>
            <div className="mono figure-small">{formatCompact(latest.imports)}</div>
            <div className="small muted">by companies, for their supplies</div>
          </div>
        )}
      </div>
      <p className="small">{abroad.reason}</p>
      <div className="two-charts">
        <SingleLine name="Oil, US dollars a barrel" format={(v) => `$${v.toFixed(0)}`}
                    data={abroad.history.map((h) => ({ label: h.period_label, value: h.oil_cents / 100 }))} />
        <SingleLine name="Naira to one US dollar" format={(v) => `₦${Math.round(v).toLocaleString("en-NG")}`}
                    data={abroad.history.map((h) => ({ label: h.period_label, value: h.fx / 100 }))} />
      </div>
      {abroad.trade.length > 0 && (
        <div className="scroll" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">Quarter</th>
                <th scope="col" className="num">Sold abroad</th>
                <th scope="col" className="num">Bought abroad</th>
                <th scope="col" className="num">Government's oil share</th>
                <th scope="col" className="num">Foreign money in (out)</th>
                <th scope="col" className="num">Foreign investors' shares</th>
              </tr>
            </thead>
            <tbody>
              {abroad.trade.slice(-6).reverse().map((q) => (
                <tr key={q.period}>
                  <th scope="row">{q.period_label}</th>
                  <td className="num mono">{formatCompact(q.exports)}</td>
                  <td className="num mono">{formatCompact(q.imports)}</td>
                  <td className="num mono">{formatCompact(q.oil_royalty)}</td>
                  <td className="num mono">{BigInt(q.foreign_inflow) >= 0n ? `▲ ${formatCompact(q.foreign_inflow)}` : `▼ (${formatCompact((-BigInt(q.foreign_inflow)).toString())})`}</td>
                  <td className="num mono">{formatCompact(q.foreign_holdings)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        The oil price and the exchange rate for each quarter are set when the quarter before closes, and nobody can know
        them earlier. Dearer oil earns the oil companies and the Government more and makes energy dearer at home. A weaker
        naira makes everything bought abroad dearer. Foreign investors bring money in when interest rates here pay well
        over lending abroad, and buy and sell shares on the exchange like everybody else.
      </p>
    </Panel>
  );
}

/** The 1,000 consumer groups, added up: by income level, by mindset, and who moved. */
function ConsumersPanel({ consumers }: { consumers: ConsumersSummary }) {
  const spent = consumers.bands.reduce((sum, b) => sum + Number(BigInt(b.spending) / 100n), 0) || 1;
  const byMind = [...consumers.mindsets].sort((a, b) => Number(BigInt(b.spending) - BigInt(a.spending)));
  const largestMind = Math.max(1, ...byMind.map((m) => Number(BigInt(m.spending) / 100n)));
  return (
    <Panel title="Households, by income and by mindset" aside={`${consumers.bands.reduce((n, b) => n + b.groups, 0).toLocaleString("en-NG")} groups`}>
      <div className="scroll" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Income level</th>
              <th scope="col" className="num">Groups</th>
              <th scope="col" className="num">Income</th>
              <th scope="col" className="num">Spending</th>
              <th scope="col" className="num">Share of all spending</th>
              <th scope="col" className="num">Savings</th>
              <th scope="col" className="num">Owed to banks</th>
            </tr>
          </thead>
          <tbody>
            {consumers.bands.map((b) => (
              <tr key={b.band}>
                <th scope="row">{b.name}</th>
                <td className="num mono">{b.groups}</td>
                <td className="num mono">{formatCompact(b.income)}</td>
                <td className="num mono">{formatCompact(b.spending)}</td>
                <td className="num mono">{formatPercent(Math.round((Number(BigInt(b.spending) / 100n) / spent) * 10000))}</td>
                <td className="num mono">{formatCompact(b.cash)}</td>
                <td className="num mono">{formatCompact(b.debt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="why-title">SPENDING BY MINDSET</div>
      {byMind.map((m) => {
        const value = Number(BigInt(m.spending) / 100n);
        return (
          <div key={m.mindset} className="bar-row">
            <div className="row">
              <span>{MINDSET_WORDS[m.mindset] ?? m.mindset} <span className="muted small">· {m.groups} groups</span></span>
              <span className="mono">{formatCompact(m.spending)}</span>
            </div>
            <div className="meter" aria-hidden="true"><div className="meter-fill" style={{ width: `${(value / largestMind) * 100}%` }} /></div>
          </div>
        );
      })}
      <div className="why-title">PEOPLE MOVING</div>
      {consumers.moved === 0 ? (
        <p className="small muted">No groups moved last quarter. {consumers.moved_total} have moved since the world began.</p>
      ) : (
        <ul className="reasons">
          {consumers.moves.map((m) => (
            <li key={`${m.from_location}-${m.to_location}`}>{m.from_location} → {m.to_location}: {m.groups} {m.groups === 1 ? "group" : "groups"}</li>
          ))}
          <li className="muted">{consumers.moved_total} groups have moved since the world began.</li>
        </ul>
      )}
      <p className="muted small">
        The households are 1,000 groups. Each lives in one place, earns at one of five income levels, reacts to the news in
        one of ten ways, and has its own savings, debts and tastes. Poorer groups spend nearly all they earn, mostly on food
        and other necessities; richer ones save more and spend more on travel, hotels and property. Groups move now and then,
        more often towards places where jobs are growing. Only totals are ever shown.
      </p>
    </Panel>
  );
}

/** Property prices and rents by city (Stage 8): the average of each city's districts, 100 at the start. */
function PropertyPanel({ summary }: { summary: PropertySummary }) {
  const lagos = summary.cities.find((c) => c.city === "Lagos") ?? summary.cities[0];
  return (
    <Panel title="Property" aside="price index, start of the world = 100">
      <div className="scroll" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th scope="col">City</th>
              <th scope="col" className="num">Prices</th>
              <th scope="col" className="num">Against last quarter</th>
              <th scope="col" className="num">Rents</th>
              <th scope="col" className="num">Space let</th>
              <th scope="col" className="num">Sold at auction</th>
            </tr>
          </thead>
          <tbody>
            {summary.cities.map((c) => {
              const last = c.history[c.history.length - 1];
              const before = c.history.length > 1 ? c.history[c.history.length - 2] : null;
              if (!last) return null;
              return (
                <tr key={c.city}>
                  <th scope="row">{c.city}</th>
                  <td className="num mono">{(last.price_bps / 100).toFixed(1)}</td>
                  <td className="num"><Change bps={before ? moveBps(last.price_bps, before.price_bps) : null} /></td>
                  <td className="num mono">{(last.rent_bps / 100).toFixed(1)}</td>
                  <td className="num mono">{percentOf(last.occupancy_bps)}</td>
                  <td className="num mono">{last.sold ? `${last.sold} · ${formatCompact(last.sold_value)}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {lagos && lagos.history.length > 1 && (
        <LineChart
          names={["Lagos prices", "Lagos rents"]}
          format={(value) => value.toFixed(1)}
          data={lagos.history.map((q) => ({ label: q.label, first: q.price_bps / 100, second: q.rent_bps / 100 }))}
        />
      )}
      <p className="muted small">
        Rents follow what the city's households spend and how many people work there. Prices follow rents and interest
        rates, and rise further when buyers at the Auction House pay more than buildings are worth: that extra fades a fifth
        each quarter unless buyers keep overpaying. See every district on the <a href="#/property/map">Property</a> page.
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

      {economy.abroad && <AbroadPanel abroad={economy.abroad} />}
      {economy.property && <PropertyPanel summary={economy.property} />}

      {economy.consumers && <ConsumersPanel consumers={economy.consumers} />}

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
      <WatchPanel onLoggedOut={onLoggedOut} />
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
