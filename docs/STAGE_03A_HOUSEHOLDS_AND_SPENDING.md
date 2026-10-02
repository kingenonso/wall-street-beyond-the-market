# Stage 3, Part A: households, wages and money that circulates

**Status: built and tested.** 319 automated server tests and 12 website tests pass.
An 80-quarter run (20 game years) kept turning over with no money created or lost.
Part B (banks' lending, the Central Bank, inflation, commodity prices, the Money
Watch and the news wire) is not started.

Words used below:

- **Household group**: all the households of one location, treated as one earner and spender.
- **Pull**: how strongly a company attracts customers compared with its rivals.
- **Supplier**: a company another company buys from.

## The checklist, item by item

| # | Promised | Done | Proved by (`tests/test_economy.py` unless named) |
| --- | --- | --- | --- |
| 1 | Households exist in each of the five locations, with their own income and savings | Yes | `test_each_of_the_five_locations_has_its_households_with_their_own_savings` |
| 2 | Wages: companies employ people and pay them each quarter; a company in trouble cuts jobs, a growing one hires | Yes | `test_every_company_pays_wages_every_quarter_to_households`, `test_a_company_in_trouble_cuts_jobs_and_a_growing_one_hires` |
| 3 | Households spend their wages at companies; when jobs are lost, spending falls | Yes | `test_households_spend_from_what_they_earned_last_quarter...`, `test_when_jobs_are_lost_in_a_location_its_households_spend_less_the_next_quarter` |
| 4 | Companies buy from each other | Yes | `test_companies_buy_from_other_companies`, `test_builders_buy_cement_and_power_companies_buy_gas` |
| 5 | Rivals compete: one gains what another loses | Yes | `test_what_one_company_gains_its_rivals_lose`, `test_companies_in_one_sector_take_different_shares_that_shift_over_time` |
| 6 | Head offices matter: costs differ by location | Yes, in part: see the note below | `test_the_same_company_costs_less_to_run_in_kano_than_in_lagos`, `test_buyers_favour_companies_based_in_their_own_location` |
| 7 | Pension saving from every wage, with the employer adding to it | Yes | `test_part_of_every_wage_goes_into_the_pension_funds_with_the_employer_adding_more` |
| 8 | Money keeps circulating; the Stage 2 pooling is fixed | Yes | `test_money_does_not_pile_up_in_one_place_over_twenty_quarters`, and the 80-quarter run below |

**Item 6, the part not yet done:** the checklist also said "a local event hits the
companies based there first". Local events (floods, power failures, strikes) arrive
in Part B with the other real causes, so that half of item 6 is still to come.

On screen: a new **Economy** page, and each company page now shows staff, wages,
who it sells to, what it buys and what its location does to its costs.
Screenshots are in `docs/screenshots/stage-03a/`.

## How it works, in plain words

Each game quarter now runs in this order:

1. **Households spend.** Each location's households spend most of what they earned
   last quarter, plus a little of their savings. Their mood varies a little from
   quarter to quarter. The money goes to the companies, shared between sectors,
   then between rivals by their pull. Buyers favour companies based near them.
2. **Companies buy from each other.** Each company orders supplies in step with what
   it sold last quarter: builders buy cement and steel, power companies buy gas,
   everyone buys power, transport, banking and insurance.
3. **Each company closes its quarter.** Its sales are whatever customers actually paid
   it. It pays its people, its interest, its tax and its owners. If it has spare cash
   and is profitable it expands, which is paid to the companies that build and supply.
4. **The Government spends** the tax it collected: part on purchases from companies,
   the rest on public-sector pay.
5. **Pension funds pay pensions** to households.
6. **Everything is written up.** What households earn this quarter, they spend next quarter.

A company's sales are no longer set by a trend line. They are the result of what
households, other companies and the Government chose to spend with it.

**Wages and jobs.** Staff costs move a quarter of the way, each quarter, towards what
sales justify. A company in trouble cuts a further 3%. Half of a company's staff are
taken to work where its head office is; the rest are spread by population.

**Pensions.** 8% is taken from each wage and the employer adds 10% on top. Both go to
the pension funds, which pay pensions to households.

**Head offices.** Running costs against the national average: Lagos +10%, Abuja +5%,
Port Harcourt average, Aba -12%, Kano -15%. A business that suits its location pays
less still (oil and gas in Port Harcourt, farming in Kano, manufacturing in Aba,
banking in Lagos); one that does not pays more.

## The 80-quarter run

| Quarter | Sales of all companies | Household income | Household spending | Household savings | Jobs | In default |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ₦2.33tn | ₦1.41tn | ₦1.71tn | ₦11.7tn | 537,000 | 2 |
| 8 | ₦2.17tn | ₦1.30tn | ₦1.34tn | ₦11.2tn | 491,000 | 2 |
| 20 | ₦2.30tn | ₦1.37tn | ₦1.39tn | ₦10.8tn | 501,000 | 3 |
| 40 | ₦2.42tn | ₦1.45tn | ₦1.46tn | ₦10.5tn | 531,000 | 5 |
| 80 (before the review fixes) | ₦2.40tn | ₦1.43tn | ₦1.44tn | ₦10.3tn | 530,000 | 5 |

In Stage 2 customers ran short of money at about quarter 29 and the economy seized
up. Here it is still turning over at quarter 80, the whole ledger re-adds to zero,
and the money in existence has not changed by one kobo.

Credit ratings after eight quarters: AAA 4, AA 3, A 5, BBB 11, BB 16, B 4, CCC 5, D 2.
The blueprint's target was AAA 3, AA 5, A 8, BBB 10, BB 9, B 7, CCC 5, D 3.

## Decisions I made that you did not specify

| Decision | Why |
| --- | --- |
| Households spend 85% of last quarter's income plus about 2% of savings, give or take up to 3% for mood | A simple habit that keeps spending in step with earnings, without being exactly predictable |
| Population shares: Lagos 35%, Kano 20%, Abuja 15%, Port Harcourt 15%, Aba 15% | Needed to share out savings, public pay and pensions |
| Monthly wage per worker: Lagos ₦300,000, Abuja ₦280,000, Port Harcourt ₦260,000, Aba ₦200,000, Kano ₦185,000 | Sets staff numbers from the wage bill |
| What households spend on is worked out, not typed in | Each sector's household sales are what is left of its opening sales after other companies, the Government and investment have bought from it |
| A company's pull drifts 5% of the way back, each quarter, towards where it began | Without it one company eventually takes its whole market |
| Money that reaches or leaves a company outside its normal business is shown in its accounts as other sales or a cost | The alternative was that one stray payment stopped the calendar for ever |

## Stand-ins still in place

Flagged in the code as temporary, with the stage that replaces each.

| Stand-in | Replaced in | Honest note |
| --- | --- | --- |
| A sound borrower's loan or bond is renewed automatically instead of being repaid | Part B (loans), Stage 4 (bonds) | Banks do not yet choose whom to lend to |
| Pension funds hold what they own and pay out about what comes in | Stage 4 and the Asset Manager build | They have no market to invest in yet |
| The Government spends exactly the tax it collects, 40% on purchases and 60% on pay | Stage 12 | No budget, no borrowing |
| Founders and small investors spend most of their dividends | Stages 4 and 5 | |
| Banks' loans to the public and customers' deposits do not move | Part B | |
| There are no exports | With the other regions | So households appear to buy all the oil and gas. Their spending shows 26% on oil and gas, which is unrealistic |
| No prices: everything is in naira amounts | Part B | So there is no inflation figure yet |
| A company that has failed keeps trading | Law and restructuring stages | Five companies are in default by quarter 40 with no way out yet |

## The loophole check

The ten questions of section 19, applied to Part A.

| # | Question | Answer |
| --- | --- | --- |
| 1 | Forgery | Part A adds one request, which only reads. No request moves money. |
| 2 | Money from nothing | No. Every new flow goes through the ledger. Checked every quarter for 45 quarters by the reviewer, and on a second run of 148 quarters. |
| 3 | Farming | Nothing new can be collected by a player. |
| 4 | Timing | Four servers closing at once, with sign-ups and payments landing during the close: each quarter closed once, 29 starting grants each paid once. |
| 5 | Permissions | No new flow touches a player's account. |
| 6 | Hidden information | The households' spending habit, each company's pull and the world's secret are never sent. See "predictability" below. |
| 7 | Bad numbers | Households, pension funds and Treasury at zero, a sector with no demand, 100% tax, a one-company sector: all closed cleanly. |
| 8 | Collusion | Not applicable until players can pay each other (Stage 4). |
| 9 | Many accounts | Unchanged from Stage 2. |
| 10 | The clock | Unchanged. A world created before households existed is refused cleanly and nothing is written. |

### What the independent reviewer found

It could not create or destroy money, and could not make the books fail to balance.
It found ten weaknesses.

| Finding | Severity | Done |
| --- | --- | --- |
| One stray payment touching a company stopped every future quarter, for ever | Medium now, high once players deal with companies | **Fixed.** It is shown in the company's accounts and the calendar carries on. |
| A company with a steady trend swallowed up to 98% of its market after 130 quarters, and the trend was published | Medium | **Fixed.** Pull drifts back towards where it began. |
| All nine bonds fell due in the same quarter, and a single bad quarter decided who defaulted | Medium | **Fixed.** Dates are staggered and renewal looks at the last four quarters. |
| Next quarter's household spending could be worked out to the kobo from published figures | Medium for Stage 4 | **Mostly fixed.** Mood now varies and companies' orders vary. See below. |
| Unpaid wages and pension contributions were all re-addressed to the head-office households | Low to medium | **Fixed.** Each stays owed to whoever was due it. |
| Failed companies trade for ever | Low to medium | **Open.** Needs the law and restructuring stages. |
| Closing a quarter gets slower as history grows | Low | **Partly fixed** (two re-counts per company instead of four). To be measured again at Stage 16. |
| A world made before this change kept taking sign-ups while frozen | Low | **Partly fixed.** The money table now always adds up. Such a world must be replaced. |
| With one player, the "Players" total was that player's balance | Low | **Fixed.** Shown only once there are 20 players. |
| Smaller items | Low | Fixed where cheap; the rest noted in the code. |

**Predictability, stated plainly.** Some of next quarter is still knowable in advance,
and I think that is right: it is what analysts do. A careful player can estimate
household spending to within about 3%, each sector's supply orders to within a few
percent, and the Government's purchases exactly (it spends what it collected). What
they cannot know is how spending splits between sectors and rivals that quarter. This
matters from Stage 4, when there are share prices to bet on. If you want less to be
knowable, the mood and order swings can be widened.

## Run it

```
git pull
docker compose down -v
docker compose up --build
```

A new world is needed, because a world is only created once. Then open
http://localhost:5173, create an account and look at **Economy**, and at any company
for its staff, customers and suppliers.
