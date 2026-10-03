# Stage 5: players and first screens

The stage test, from the design: **"A new player is hired, completes an objective and is
paid by a named payer."** It passes, through the website's own doors:
`tests/test_objectives.py::test_a_new_player_is_hired_completes_an_objective_and_is_paid_by_a_named_payer`.

Tests at the end of the stage: **646 on the server**, 13 on the order-matching engine,
12 on the website. All pass.

Before the stage began, one fix asked for by the owner: on the price ticker, a share nobody
has bought or sold today now says **"no trades yet"** instead of "– 0.0%"
(`test_the_ticker_says_which_shares_have_not_traded_today`).

## Checklist

| Agreed | Done | Proved by |
| --- | --- | --- |
| Player identity: choose a build. Asset Manager and Accountant open now; the rest in Stage 6; CEO is earned | Yes | `test_only_the_two_builds_of_this_stage_can_be_chosen`, `test_a_build_can_be_changed_once_in_a_real_month_and_each_keeps_its_own_level`, screenshot 02 |
| Getting hired by an employer | Yes | `test_an_employer_needs_to_know_where_to_pay_and_must_hire_that_build`, `test_a_company_has_only_so_many_places`, `test_two_people_cannot_take_the_last_place_at_the_same_moment`, `test_nobody_can_hop_between_employers_within_a_quarter`, screenshot 03 |
| Salary each quarter, paid by a named payer from its own cash | Yes | `test_pay_day_the_employer_pays_and_forty_percent_is_taken`, `test_a_players_salary_comes_out_of_the_wage_bill_the_company_already_pays`, `test_an_employer_with_no_cash_owes_the_salary_and_pays_it_when_it_can`, screenshot 12 |
| About 40% taken automatically for tax and living costs | Yes | `test_about_forty_percent_is_taken_and_every_kobo_is_accounted_for`, `test_the_salary_scale_matches_the_design_document` |
| Levels and experience from real work | Yes | `test_levels_come_from_experience_and_stop_at_twenty_until_rank_cases_exist`, `test_harder_work_opens_with_level`, the stage test |
| Choosing your bank: one of six, can move later | Yes | `test_only_the_six_banks_can_be_chosen_and_a_player_moves_at_most_once_a_quarter`, `test_the_bank_pays_interest_on_the_least_cash_kept_through_a_whole_quarter`, `test_a_weaker_bank_pays_more_on_savings` |
| Professional objectives from learning modules, checked by the server against real records, paid by a named payer. No question papers, no exam bodies' names | Yes | all of `tests/test_objectives.py`; `test_the_library_has_six_pieces_of_work_for_each_build_and_every_module_has_one` |
| A small set of objectives done well: six for each build | Yes | the twelve are listed below, each with its own test |
| The Asset Manager screen | Yes | `test_the_build_screens_have_their_figures`, screenshot 11 |
| The Accountant screen | Yes | the same test, screenshot 09 |
| The shared screen parts: objectives panel, progress tracker, number tile, pay, level, skill tree | Yes | `web/src/Parts.tsx`; screenshots 05 to 12 |
| Not done, as the owner decided: no change to the starting grant's steps, and no stop between two parts | Kept to | |

## What each part does, in plain words

**Build.** A build is the player's profession. A new player chooses Asset Manager or
Accountant on the Career page. A build can be changed once in a real month; each build
keeps its own level; a player may hold up to three. Changing build means leaving the job.

**Bank.** The player chooses one of the six banks before an employer can hire them ("the
employer needs to know where to pay you"). The bank pays interest each quarter, out of the
bank's own cash, on the *least* cash the player kept with it through the whole quarter. A
weaker bank (lower credit rating) pays more. A player can move once a quarter.

**Employer.** Banks and insurers hire Asset Managers; every company hires Accountants. A
company has one place for a player for every 500 people it employs. A computer-run employer
takes anybody of the right build while it has a place. A player can move once a quarter.

**Salary.** The design's scale: ₦300,000 a game month at Level 1, ₦750,000 at Level 20, and so
on up; three game months make a quarter; pay keeps pace with wages in the economy. On pay
day (when the quarter closes) the employer pays, in one recorded payment: take-home pay to
the player (60%), income tax to the Government (12%), living costs to the households of the
city the player works in (20%), and the player's own retirement saving (8%) to the pension
funds. That is the design's "about 40% taken automatically". The employer adds 10% more to
the retirement savings.

*The salary is not a new cost.* It is carved out of the wage bill the company already pays:
the player takes the place of one computer-run member of staff. The test closes the same
quarter twice, with and without a player on the staff, and the employer's costs, profit and
cash are the same to within ten kobo.

*No work, no pay.* An employer pays a quarter's salary only to staff who finished at least
one real piece of work in it: work passed, or work honestly attempted (not passed, but with
at least one milestone earned). A blank sheet, work given up and work never done earn nothing.
Somebody who starts part-way through a quarter is paid for the days worked.

*If the employer has no cash,* it pays what it can and owes the rest, which is paid when it
has the cash. The list of employers warns which companies are behind on their bills.

**Retirement savings.** Part of every salary is saved for the player and the employer adds
more. The money itself goes to the pension funds with every other worker's; the player holds
a locked claim on it. They choose one of the design's four fund kinds (Growth, Balanced,
Cautious, Income); the savings grow each quarter by what that mix earned (shares: the BSX 50;
bonds: the Government's five-year rate; cash: its three-month rate), less a small fee. A fund
can be changed once in a game year, from the next quarter.

**Levels.** Experience comes only from work passed. Level *n* needs 30 × *n* × (*n* − 1)
experience: 60 for Level 2, 11,400 for Level 20. Level 20 is the cap until rank cases exist
(Stage 7). Harder work opens at Levels 2, 3 and 4. Reputation starts at 50 and each piece of
work passed adds one. Level, reputation and wealth are kept apart.

**Failure.** A piece of work not passed costs its reward and nothing else. Five not passed
in any ten opens a performance review; the player is told why and how to recover. Three
passes in the next five close it. Otherwise the player steps down one level, and loses
nothing else.

**Professional objectives.** Each is practical work from one learning module, in five steps:
the idea, a situation in the live world, a decision, what came of it, and why. The server
fixes the terms when the work is taken on, chooses the client (so nobody can pick an easy
one), judges the result from the game's own records, and has the named payer pay out of its
own cash. Afterwards the player is shown why, in plain words first, then the professional
method, then the arithmetic. At most three pieces in hand; each piece once a quarter.

### The twelve objectives

**Accountant** (the client company pays the fee)

| Opens at | Module | The work | Judged by |
| --- | --- | --- | --- |
| Level 1 | Reading financial statements | The lender's one-page view: EBITDA, profit margin, debt against EBITDA, interest cover, from the client's filed accounts | Worked out again by the server from the filing. Three of four right passes |
| Level 1 | The cash flow statement | Sort the client's real cash movements for the quarter into day-to-day business, investing, and owners and lenders; give the totals and the closing cash | The filed cash flow statement |
| Level 2 | Company tax | Finish the income statement and work out the tax | The filed income statement. The tax must be right |
| Level 2 | Budgeting and forecasting | Forecast the client's sales for the quarter now running | What the company files when the quarter ends. Within 3% passes |
| Level 3 | Audit: can it keep going? | Decide whether a strained company will pay everything that falls due this quarter | What its accounts show at the quarter end |
| Level 4 | Credit analysis | Call the client's credit rating at its next filing | The rating it is given |

**Asset Manager** (the employer pays, as performance pay; the work is done with the player's own money)

| Opens at | Module | The work | Judged by |
| --- | --- | --- | --- |
| Level 1 | Portfolio construction | Spread the risk: ₦100,000 of shares in five companies from three industries, none above 30% | What is actually held at two Closing Bells running |
| Level 1 | Money markets | Put idle cash to work in Government bills | Held at two Closing Bells and repaid at the quarter end |
| Level 2 | Interest rates and bond prices | Call the Central Bank's decision and position bonds for it | The decision itself, and how the bonds did against the Government's five-year bond |
| Level 2 | Asset allocation | Run a balanced mandate: shares 40 to 60%, bonds 30 to 50%, cash 5 to 20% | What is held at three Closing Bells running |
| Level 3 | Share valuation | Back your valuation: name a share and hold it through the results | The share against the BSX 50, at the first Closing Bell after the results |
| Level 4 | Measuring performance | Beat the BSX 50 over seven Closing Bells, staying 60% invested | The player's return against the index, with salary and other money paid in taken out |

**The screens.** Both build screens use the standard four zones, each in its own accent
colour (violet for the Asset Manager, green for the Accountant). "Needs you now" comes first
and is built only from things that are true: work to hand in, work in hand, a review, pay day.

- *Asset Manager:* total value and performance against the BSX 50, the allocation wheel, top
  industries, holdings, the trading console, research, the watchlist.
- *Accountant:* any company's income statement, balance sheet and cash flow by quarter, key
  ratios, sales and profit history, tax position, the audit and client work list, forecasts
  against what was filed, and a compliance watch of companies behind on what they owe.
- *Every build:* the objectives panel, level, pay, and the skill tree with its coverage
  tracker ("1 of 6 modules learned").
- New sections: **Work** (objectives) and **Career** (build, bank, employer, payslips,
  retirement savings, record).

**The Money Watch** gained its Stage 5 measure: what players were paid in each quarter, by
reason (salary, fees, interest, grant), and how many players
(`test_the_money_watch_records_what_players_were_paid_and_why`).

## Decisions I made that you did not specify

| Decision | Why |
| --- | --- |
| Salary is carved out of the employer's existing wage bill | So that players joining never changes a company's costs or creates money |
| The 40% is 12% tax, 20% living costs, 8% retirement saving | The design says "about 40% for tax and living costs"; every worker already saves 8% |
| No work, no pay | Without it, an account that never plays would collect a salary for ever |
| One place for a player per 500 staff | Keeps players' pay a tiny part of any wage bill; about 1,300 places in all |
| Deposit interest on the least cash kept through a whole quarter, at about a quarter to under a half of the Central Bank's rate | So that money parked for a day earns nothing, and bills still pay more than a bank |
| Retirement savings are a locked record, with the four fund kinds run by the computer | See "Needs your decision" below |
| Experience scale, and Level 20 cap | The design says moving past 20 needs a rank case, which is Stage 7 |
| Rewards of ₦40,000 to ₦150,000, rising with wages | Small beside a quarter's take-home pay of about ₦540,000 at Level 1 |
| The share valuation objective became "back your valuation" | In this market, prices sit almost exactly on worth, so "buy 10% below worth" would almost never be on offer |
| Nothing can be changed in the minute between a quarter's end and its close | So nobody acts knowing how the quarter ended |

## Needs your decision

The design says "player-run pension managers arrive with the Asset Manager build". I built
the player's retirement savings and the four fund kinds, run by the computer. I did **not**
let an Asset Manager player run other players' retirement money. A manager could lose or
misuse it, and the regulator, the lawsuits and the courts that the design sets against that
arrive in Stage 11. I recommend it comes in with Stage 11, or in Stage 6 limited to
high-level managers. It is your call.

Uploading your own profile picture is still not built (it needs a person to check pictures
before others see them); the male and female icons are.

## The loophole check

| # | Question | Answer for Stage 5 | Tests |
| --- | --- | --- | --- |
| 1 | Can money be made from nothing? | No. Salary, fees and interest are payments from a company's cash; the ledger is re-added and money in existence checked in the tests | `sound(db)` in the pay, interest, objective and review tests |
| 2 | Can a payment be collected twice? | No. One payslip per player per quarter, one interest payment, one result per objective, all enforced by the database; eight hand-ins at once are paid once | `test_work_is_handed_in_once_and_only_by_its_owner`; reviewer's W1 to W3, W6 |
| 3 | Can somebody be paid without a payer who has the cash? | No. A reward is capped at what the payer has; work is not offered by a payer without cash; unpaid salary is owed, not invented | `test_a_payer_without_the_cash_is_not_offering_work...`, `test_an_employer_with_no_cash_owes...` |
| 4 | Can the reward be had without the work? | Closed: blank sheets, last-day bank moves, last-day fund changes, joining after the quarter ended, borrowing shares for one bell | `tests/test_review5.py`, `test_shares_borrowed_for_the_moment_of_the_bell...`, `test_no_work_no_pay` |
| 5 | Can a player see what they should not? | No. Nothing shown before judging holds an answer; the Accountant's screen uses only filed accounts | `test_nothing_shown_before_judging_gives_the_answer_away` |
| 6 | Can a player act on another's work? | No | `test_the_website_cannot_send_extras_or_reach_another_players_work` |
| 7 | Can bad input break anything? | No. Not-a-number, infinity and oversize answers are refused | `test_answers_that_are_not_ordinary_numbers_are_refused` |
| 8 | Can one player stop the quarter or the bell for everybody? | No. A fault in judging one objective is logged and skipped; salaries can never exceed a tenth of a wage bill | reviewer's W7 and W10 |
| 9 | Can accounts working together farm it? | Partly: see the honest limits | |
| 10 | Are records permanent? | Payslips, interest, retirement entries, the career record and judged objectives cannot be changed or deleted, even in the database | `test_the_terms_and_the_result_cannot_be_changed_in_the_database`, `test_more_of_the_record_is_guarded_in_the_database` |

### The independent review

A second reviewer, who did not write the code, attacked Stage 5 with 21 tests of its own.
It found **eleven holes; none made or lost money.** All are closed, each kept as a test in
`tests/test_review5.py`.

| Found | Fixed |
| --- | --- |
| Moving bank on the last day earned a whole quarter's interest on money that arrived a minute before | Interest is only for a whole quarter with the bank, on the least cash since the last close |
| A blank hand-in counted as "work", so salary could be collected for ever without passing anything | Only work passed, or failed with a milestone earned, counts |
| A rate call taken in the seconds after a quarter ended was judged against a decision already made | Nothing can be taken on or changed between a quarter's end and its close |
| A forecast of "not a number" could never be judged | Refused when handed in |
| A retirement fund chosen in the last minute was credited with the whole quarter | A change takes effect from the next quarter |
| Not-a-number and infinity caused a server error | Refused with an ordinary message |
| A share named while the Closing Bell was ringing could be lost | The bell now reads each objective afresh, under lock |
| Moving employer in the gap lost the pay already earned | Covered by the gap rule |
| Moving employer with work in hand left the old employer paying | Work must be finished first |
| Salary paid late never reached the retirement savings | The saving is credited for the quarter it was earned in |
| Several records could be rewritten by somebody with database access | More fields and tables are guarded |

Found while walking through the screens: the same piece of work could be in hand twice, once
from each of two quarters. Closed (`test_the_same_work_cannot_be_in_hand_twice`).

## The economy still holds

Ten game years on fast-forward give exactly the figures of Stage 4 (inflation 3.8% to 8.7%,
the interest rate 12% to 14%, the ledger and every company's books clean): with no players,
Stage 5 changes nothing in the economy, and with players their pay replaces a computer-run
worker's.

## Honest limits

- **One person with several accounts** can pass one easy piece of work on each and draw a
  salary on each. No money is made (each takes a computer-run worker's wage), but it is unfair.
  The cure is checking a phone number at sign-up, which needs a paid service: your decision,
  before the trial opens.
- **Pushing a price just before a Closing Bell** could help two of the Asset Manager's
  objectives, and two accounts trading with each other at an odd price could help one. Both
  are market manipulation between players; the law stage (11) is where they are caught.
- The Asset Manager works with their **own** money. Managing an employer's or a client's
  money comes with empires (Stage 6).
- Some Asset Manager work needs Closing Bells, which ring once a real day. It cannot be
  hurried, and it does not run in a fast-forwarded test world.
- Three of the Accountant's objectives are calls with a yes-or-no or a short list of answers,
  so luck plays a part. The reward is smaller, and wrong calls count towards a review.
- Derivatives and alternative investments (Stage 9), forensic cases (Stage 11) and the
  personal tax return (Stage 12) are named on the screens as coming later.
- Twelve objectives now; the library of 350 is Stage 7.

## Screenshots

`docs/screenshots/stage-05/`: 01 a new player's desk, 02 choosing a build, 03 bank and
employer, 05 work on offer, 06 work in hand, 07 the debrief, 08 the cash flow work,
09 the Accountant screen, 10 the Asset Manager's work, 11 the Asset Manager screen,
12 a payslip and retirement savings, 14 the Work page on a phone.

## Run it

```
git pull
docker compose down
docker compose up --build
```

Your world and your player are kept: the new tables are added by themselves when the server starts.
Then open http://localhost:5173, log in (or sign up), and go to **Career**.

In a second PowerShell window, to move a test world one quarter ahead and see a pay day:

```
docker compose exec server python -m simulation.fast_forward 1
```
