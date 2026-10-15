# Stage 9: risk, borrowing, short selling, options and futures

The owner approved this stage with "build" on 15 October 2026, without answering the four questions on the
checklist in `notes/stage-9-plan.md`. So the suggested defaults were taken, and said so at the start:

- the stage was built in two parts, 9A and then 9B;
- every suggested number was used (below);
- options are offered only on the 50 biggest shares (the BSX 50's members) and on the index itself;
- "alternative investments" means the crash fund and commodity futures (oil, the naira, farm produce, metals
  and building materials).

Nothing on the checklist was dropped or put off.

Tests at the end of the stage: **1,123 on the server**, 13 on the order-matching engine and 23 on the
website. All of them pass.

## Two things built differently from the checklist, said plainly

1. **Options and futures are dealt with a market makers' desk, not on the order-matching engine.** The
   checklist put them on the Rust engine. They are dealt instead like bonds: the pension funds' desk always
   quotes two prices, one to buy at and one to sell at. Players therefore never wait for someone on the other
   side. The desk's prices come from the standard models (Black-Scholes for options, the cost of carry for
   futures). The engine still matches every share order as before.
2. **The two-times-your-worth cap covers borrowing to invest only.** The cap applies to loans against shares
   and bonds, and to short sales. A personal loan is limited by salary instead, as a mortgage is. If the cap
   covered personal loans too, a new player with a salary but nothing saved could not borrow at all.

## The numbers used (the suggested defaults)

| What | Number |
| --- | --- |
| Loan against shares and bonds | up to 50% of their value; a margin call at 70%; a forced sale at 80% (or a call not met by the next Closing Bell); the Central Bank's rate + 2% |
| Personal loan | up to a year's salary (four years' with any mortgage); the Central Bank's rate + 8%; repaid evenly over two years |
| Short selling | 150% of the shares' value held as cash; a call below 125%; a forced buy-in below 110%; a fee of 2% a year to the lender; the pension funds lend at most 30% of what they hold |
| Leverage | borrowing to invest at most 2 × what the player is worth after all debts |
| Futures margin | 15% held; a call below 10% |
| Writing an option | 20% of what it is on, plus the option's own value |
| "What could happen?" | 1,000 possible futures; one free run a day, then ₦5,000 a run |
| Crash fund | 3% of the cover a quarter; pays when the BSX 50 falls 15% or more in a quarter; cover at most half of what the empire is worth |
| Late payment | interest not paid is owed next time, 5% more |

## Checklist

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| A1 | A stochastic engine: fat tails, common forces, investor tempers, squeezes | Yes. Every random draw (company sales, sector demand, household mood, costs, commodities, oil, the naira) now has fat tails (Student's t) and shares five common forces: the economy, energy, building, farming and money. Computer investors have tempers that follow recent moves. A heavily shorted share that rises is bid up further. | `test_draws_have_the_old_typical_spread_fat_tails_and_shared_forces`, `test_the_computer_investors_have_tempers_and_bid_up_a_rising_heavily_shorted_share` |
| A2 | The forces are never sent to players | Yes. They are kept for checking only. | `test_the_quarters_forces_are_recorded_and_never_sent` |
| A3 | Risk figures: volatility (swing) and beta | Yes, for every share, from its last 60 trading days. A share with too short a record gets the usual figures, marked "usual". | `test_every_traded_share_has_a_volatility_and_a_beta` |
| A4 | Monte Carlo, "What could happen?": public assumptions only | Yes. It works from public prices and risk figures, never the secret seed. One free run a day, then a fee. It is offered for what you hold, an empire, a share and a property. | `test_what_could_happen_uses_public_figures_and_charges_after_the_free_run`, loophole 5 |
| A5 | Personal loans | Yes | `test_a_personal_loan_is_limited_by_salary_and_repaid_over_two_years`, `test_two_missed_payments_put_a_loan_in_default_and_stop_more_borrowing` |
| A6 | Loans against shares (margin), margin calls, forced sales | Yes | `test_a_margin_loan_is_half_the_shares_and_a_fall_brings_a_call_then_a_forced_sale`, review 7 |
| A7 | Short selling from the pension funds' pool, with recall, the fee and dividends to the lender | Yes | the four short-selling tests in `test_lending.py`, loophole 2 |
| A8 | Leverage limit | Yes | `test_all_borrowing_together_is_at_most_twice_what_a_player_is_worth`, loophole 1 |
| A9 | Empires borrow and sell short inside the Risk Manager's limits; above them the head decides | Yes | `test_an_empire_borrows_and_shorts_inside_the_risk_managers_limits_and_above_them_the_head_decides`, loopholes 7 and 9, review 8 |
| B1 | Options on the BSX 50's members and the index; futures on the BSX 50, oil, the naira, farm produce, metals and materials | Yes. Each is listed to the end of this quarter and the next: three strikes a share and five on the index. | `test_options_and_futures_are_listed_for_this_quarter_and_the_next`, `test_prices_follow_the_model_...` |
| B2 | Margin, nightly settlement, forced closes | Yes | `test_writing_an_option_needs_margin_...`, `test_a_future_is_settled_every_night_...`, loophole 4 |
| B3 | Settled in cash at the quarter's close | Yes | `test_a_bought_call_pays_out_at_the_close_...`, `test_every_future_settles_at_the_quarters_close_...`, review 2 |
| B4 | The hedging desk | Yes. The Risk Manager buys protection for the empire, and each hedge is scored in the empire's record when it ends. | `test_the_risk_manager_buys_protection_inside_the_limit_and_the_hedge_is_scored` |
| B5 | The crash fund | Yes | `test_the_crash_fund_pays_cover_when_the_market_falls_fifteen_percent_in_a_quarter`, loophole 8, review 10 |
| C1 | Work for each of the six builds, with "How to do this" | Yes. Asset Manager: leverage and margin. Accountant: futures and the cost of carry. Investment Banker: option pricing. Risk Manager: value at risk. Legal Counsel: securities lending. Journalist: market positioning. That makes eight modules for each build. | `test_objectives.py`, `test_mastery.py`, `test_rank_api.py` |
| C2 | Screens: the Derivatives tab in Market, the Borrow page, the Sell short link, the What-could-happen panels, margin warnings in Needs you now | Yes. The Market section also gained a Risk tab. | screenshots below |

## What it does, in plain words

**Borrowing.** A player with a job can borrow against their salary. Anyone can borrow up to half the value of
their shares and bonds. Interest builds up day by day for as long as the money is held. It is paid when the loan
is repaid, and at each quarter's close. Interest that cannot be paid is owed next time, 5% more. Two missed
payments put the loan in default: no new borrowing at all, and each quarter the bank takes the borrower's cash,
then shares and bonds sold at 5% below the price.

At every Closing Bell a loan against shares is measured against the shares, bonds and cash held:

- at 70%, a margin call;
- at 80%, or a call not met by the next bell, shares and bonds are sold until the loan is back to half.

Shares borrowed to sell short do not count as security.

**Short selling.** A player borrows shares from the pension funds and sells them. They hope to buy them back
cheaper later. They must put up 150% of the shares' value in cash, which the exchange holds. They pay the
lender 2% a year, and any dividend the lender misses. If the price climbs, a margin call comes first, then a
forced buy-in. The pension funds can recall shares when they have lent too many. Short interest (how much of a
share is lent out) is published as a total only, never with names.

**Options and futures.** A call pays what the price ends above its strike, and a put pays what it ends below.
Buying one costs only its price. Writing (selling) one brings in its price but needs margin. A future gains or
loses with the price, one for one. It is settled every night at the Closing Bell, and a call not met by the
next bell closes it. Everything is settled in cash at the quarter's close.

A share's options use that session's volume-weighted price. One small trade near the bell therefore cannot move
them. When a company splits its shares, lent shares and options on it are adjusted by the same ratio.

**The crash fund.** An empire pays 3% of its cover each quarter. If the BSX 50 falls 15% or more in a quarter,
the fund pays the cover of every empire that paid for that quarter before it began. Joining once a fall is
under way buys nothing for that fall. If the fund cannot pay everybody in full, it shares out what it has.

**A loss beyond the cash held for it** can happen in two ways: a buy-in dearer than the collateral, or a future's
loss beyond its margin. It does not vanish. It becomes a debt to whoever bore it, in default from the start. The
player's cash, then their shares and bonds, go to it each quarter until it is paid.

## Money: the ledger

Every naira moves through the double-entry ledger, which is re-added at every quarter's close. Three new
accounts hold cash for others. Each is checked at every close against what its records say, and the quarter
does not close if one is out by a single kobo:

| Account | Holds | Must equal |
| --- | --- | --- |
| `short:collateral` | short sellers' cash | the collateral on open shorts |
| `derivatives:margin` | margin for options and futures | the margin on open positions |
| `crash:fund` | the crash fund | premiums paid in, less payouts |

Bank interest on players' loans is booked under its own kind (`player_loan_interest`), so it is counted once in
each bank's accounts. An early version reused the households' kind and counted it twice. The long economy run
caught this, and it was fixed.

## The ten-question loophole check (`tests/test_stage9_loopholes.py`)

| # | Question | Answer |
| --- | --- | --- |
| 1 | Can borrowing against shares be looped (borrow, buy more, borrow again) without end? | No. It converges at about the first holding's worth, and never above twice the borrower's worth. |
| 2 | Can a short seller escape the fee or the dividend by holding no cash? | No. They come out of the collateral, and what is still missing is owed. |
| 3 | Can opening and closing at once make money? | No. A short gives back nothing. An option or future loses the desk's spread. |
| 4 | Can a player write options or take futures without the cash for the margin? | No |
| 5 | Can "What could happen?" be run free again and again? | No. One free run a day. |
| 6 | Can anyone see who is short, or anybody else's loans, shorts or contracts? | No. Only totals, never names. |
| 7 | Can an Asset Manager slip past the limit by splitting a trade? | No. What is already committed counts, under the empire's lock. |
| 8 | Can an empire join the crash fund once a fall is under way and be paid? | No |
| 9 | Can a seat other than the Asset Manager, Risk Manager or head act for the empire? | No |
| 10 | Can money be made or lost by the books? | No. Every escrow ends at what its records say. |

Writing these tests found one real fault. The Risk tab's address (`/api/market/risk`) was swallowed by the share
page's address (`/api/market/{ticker}`), so the tab would have failed to load. It now has its own address.

## The independent review: eleven findings, all fixed and tested (`tests/test_stage9_review.py`)

A separate reviewer, who had not seen the work being written, read the whole stage looking for faults.

| # | Found | Fixed |
| --- | --- | --- |
| 1 | A share split did not touch lent shares or options. A short seller could keep half the shares, and an option holder was paid on the old strike. | Shorts, option contracts and strikes are adjusted by the split's ratio. |
| 2 | Oil and naira futures settled at a level known all quarter: a riskless trade. | They settle after the quarter's new oil price and exchange rate are set. |
| 3 | Interest and the lending fee were charged only on what was owed at the close. Borrowing after one close and repaying before the next cost nothing. | Both build up by the time held, and are charged on repaying, on closing a short, and at the close. |
| 4 | Losses beyond the margin or collateral vanished. Missed interest was forgiven. A default took only cash. | A shortfall is owed, in default. Missed interest is owed with the 5% late charge (which now does what it says). A default sells shares and bonds. |
| 5 | Options were priced and settled on the single last trade. | They use the session's volume-weighted price. |
| 6 | The quarter close worked from copies of rows a player could change at the same moment. | The close locks the rows it changes. |
| 7 | A loan backed by bonds could never be brought down, and a forced sale cleared a default. | Bonds are sold too, and a default stays a default until it is repaid. |
| 8 | The Risk Manager could sign itself any limit and speculate under it. Two requests at once could both slip under a limit. | Raising a limit needs the head's approval; lowering one is immediate. The Risk Manager only buys options. Each check is made under the empire's lock. |
| 9 | Borrowed shares counted as security for a loan. | They are taken off. |
| 10 | The crash fund's cash was never checked. | It is checked at every close. |
| 11 | Four smaller faults. The derivatives board worked out every share's risk hundreds of times per view. A future could be listed twice. Net worth used the computer's clock. A pension fund's seat could test the fund. | All four fixed. |

## The ten-year run (40 quarters)

The run uses a fresh world and eight players. Every trading day each player might take a personal loan, borrow
against shares, repay, sell short, close a short, or open or close options and futures. Three empires held cover
in the crash fund, and the Closing Bell rang every night.

| | Result |
| --- | --- |
| Done by the players | 236 personal loans, 312 loans against shares, 220 repayments, 293 shorts opened and 199 closed, 451 options and futures opened and 195 closed early (249 ran to their close) |
| Refused, correctly | options worth nothing to the desk (64), shorts without the cash for the collateral, and amounts of nought |
| Forced by the rules | 4 short positions bought in after margin calls |
| The ledger | re-added at all 40 closes: nothing out |
| The three cash-holding accounts | each equal to its records at every check (the last one: short sellers ₦595.1M, margin ₦18,115, crash fund ₦1.73B) |
| Losses beyond the cash held, defaults | none arose in this run (the forced buy-ins all stayed within their collateral); the review tests cover them |
| Banks' accounts | no income booked outside its normal business (0, as on main) |
| Inflation | between 3.6% and 8.1% a year throughout; the Central Bank's rate ended at 13% |
| The crash fund | the BSX 50 never fell 15% in a quarter, so it paid nothing and kept its premiums for the next crash |

The same run before the review's fixes also gave clean books. The fixes moved the economy's figures only in the
last decimal place (inflation never by more than 0.01 of a point).

## Screenshots (`docs/screenshots/stage-09/`)

| File | Shows |
| --- | --- |
| `s9-01-needs-you-now-margin-call.png` | The desk: a margin call at the top of Needs you now |
| `s9-02-borrow-loans.png` | Borrow: the meter, a personal loan, a loan against shares |
| `s9-03-borrow-short-selling.png` | Borrow: short selling, with short interest by total only |
| `s9-04-borrow-for-the-empire.png` | Borrow: the empire's limits |
| `s9-05-options-and-futures.png` | Market → Options and futures: the desk's two prices, the player's positions, the crash fund |
| `s9-06-hedging-desk-and-crash-fund.png` | The Risk Manager's view: a hedge with its purpose, and asking for cover |
| `s9-07-risk-figures.png` | Market → Risk: swing, beta and short interest for every share |
| `s9-08-share-what-could-happen.png` | A company's page: "What could happen?" and the other ways to take a view |
| `s9-09-portfolio-what-could-happen.png` | Portfolio: the fan of possible futures |
| `s9-10-phone-borrow.png`, `s9-11-phone-derivatives.png` | On a phone |
| `s9-12-light-borrow.png` | Light mode |

An automated accessibility check (axe) ran on every screen. It found nothing on the final screens. It had found
an empty column heading and low-contrast links in the risk table; both were fixed.

## Things to know

- **Three older tests needed changes, not the game.**
  - Two private-equity tests (`test_q6` in `test_deals_loopholes.py`, `test_f03` in `test_deals_review.py`):
    the new random draws picked a different company. Its price sat just under the level where a deal needs the
    Banker's fairness opinion, and the tests' bids went over it. The game asked for the opinion, as it should.
    The tests now give it whenever their bid needs one.
  - One Stage 8 test counted exactly three things added to net worth. Stage 9 adds two more (loans and shorts;
    options and futures), so it now counts five, by name.

- **"What could happen?" tests a loan inside what you hold.** The plan listed a loan as something to test. A
  loan is tested as part of everything the player holds: the debt is taken off, and the result shows the chance
  of a margin call. There is no separate "test this loan" choice.
- **"Loans against savings" means loans against shares and bonds.** Retirement savings stay locked until
  retirement, as before, and cannot be borrowed against.
- **"Sell short" is a link, not a choice in the trade form.** A company's page has "Other ways to take a view",
  which opens the short-selling form with that share filled in. Short selling needs the collateral and borrowing
  checks that the ordinary trade form does not have.

- **An existing world needs no reset.** The two new database changes apply by themselves on start-up, and
  options and futures are listed the first time anyone opens the page. This was checked on a copy of the
  development world.
- **Risk figures need a trading record.** A share with fewer than 8 days of trades shows the usual
  figures, marked "usual", until it has more.
- **Settlement is on the session's volume-weighted price.** A player who trades heavily in a share all session
  can still move it, at the cost of the fees and in plain view: every trade is on the record, and trades with
  oneself are flagged.
