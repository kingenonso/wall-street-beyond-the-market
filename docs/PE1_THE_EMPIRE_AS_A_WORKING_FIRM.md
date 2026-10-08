# Private equity stage, part 1: the empire becomes a working firm

The owner's checklist of 4 October 2026 (63 items) was approved with "build". Part 2 (deals and
private companies) follows, with its own checklist.

The stage test: **every build has a desk in the empire with work that comes round every quarter,
marked from the empire's own figures, and the desks depend on one another.** It passes:
`tests/test_firm.py::test_the_stage_test_every_desk_has_standing_work_that_is_marked_and_the_desks_depend_on_one_another`.
In it the Accountant closes the books; money is raised by the banker, checked by the Accountant,
approved by the Risk Manager, read by the Lawyer and signed by the head; the quarter closes and
every desk is scored, interest is paid and the empire's accounts are kept.

Tests at the end of the stage: **806 on the server** (of which 57 are new for this part:
31 in `tests/test_firm.py`, 2 in `tests/test_firm_api.py`, 24 in `tests/test_firm_review.py`, and
older tests brought up to date), 13 on the order-matching engine, 12 on the website. All pass.
(The full run also found three exchange tests that had begun to fail only because the real date had
passed the test world's first trading day; the test world's first trading day is now fixed.)

## Checklist

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| 1 | Desks: duties every quarter, a budget, a scorecard; staff do a desk's basic duties when nobody holds the seat | Yes: 26 duties across the seven desks | the stage test; `test_a_duty_nobody_does_is_done_by_the_staff_or_missed_and_a_missed_one_costs_a_league_point` |
| 2 | Approvals never stall: 24 hours, then the head, then the deputy | Yes (and a request nobody decides lapses after three days) | `test_a_request_passes_to_the_head_after_a_day_and_to_the_deputy_after_two_and_lapses_after_three` |
| 3 | More kinds of task: raise money, rescue, defend | Yes (the contested bid is Part 2) | `test_up_to_three_tasks_of_different_kinds_and_the_head_gives_each_step_to_a_member` |
| 4 | Up to three tasks at once, the head assigning people | Yes | the same test |
| 5 | Rival empires with a head-to-head score | Yes | `test_every_empire_has_a_rival_and_a_head_to_head_score` |
| 6 | Empire events: a loan called in, a holding collapses, an inspection, an offer with a deadline | Yes: all four | `test_an_inspection_is_answered_by_three_desks_and_a_failed_one_is_fined_unless_insured` |
| 7 | Borrowing from banks or by bonds, with promises; debt at most half of worth | Yes | `test_an_empire_may_not_owe_more_than_half_of_what_it_owns`, `test_a_broken_promise_lets_the_lender_call_the_debt_and_an_unpaid_debt_is_a_default` |
| 8 | Quarterly accounts published to members | Yes | the stage test |
| 9 | Quarterly board meeting with votes on big items | Yes: the head's duty "chair the board meeting" sets the plan; big items go to the vote | Board tab; `test_members_vote_the_treasury_policy_and_the_head_breaks_a_tie` |
| 10 | Dividends to partners, up to half the quarter's profit | Yes | `test_a_dividend_is_paid_to_the_partners_by_their_units_and_never_more_than_half_the_profit` |
| 11 | Desk budgets and a bonus pool for desks under budget | Yes | `test_a_desk_under_budget_that_did_its_duties_earns_a_pool_for_its_members` |
| 12 | Apprentices | Yes | `test_a_mentor_gains_when_their_apprentice_does_good_work` |
| 13 | Promotions: desk lead, deputy head | Yes | `test_a_request_passes_...` (deputy), `name_title` |
| 14 | Poaching, 48 hours to match | Yes, with a transfer fee for a member under contract | `test_poaching_gives_the_home_empire_two_days_to_match_...` |
| 15 | Treasury policy by vote | Yes | `test_members_vote_the_treasury_policy_...` |
| 16 | Mandate and performance report against the index | Yes (duty) | `firm_duties._am_mandate` |
| 17 | Several pots | Yes: safe (cash), main (bonds), growth (shares), measured against the policy | duty "Check the three pots" |
| 18 | Voting the empire's shares | Yes: the duty casts the empire's vote | duty "Vote the empire's shares" |
| 19 | Cash management | Yes (duty) | duty "Ladder the cash" |
| 20 | Investment committee | Yes: idea, the head's approval, judged next quarter | duty "Bring an idea" |
| 21 | Pension plan for members | Yes: the members vote a fund run by one of the empire's Asset Managers; a quarterly report duty | `pension_plan` vote; duty "Report on the members' pension plan" |
| 22 | Closing the books | Yes | the stage test |
| 23 | Budget war room | Yes (duty) | duty "Run the budget war room" |
| 24 | Bonus pool proposal | Yes: the Accountant proposes, the head approves seeing who gets what | `test_f15_...` |
| 25 | Expense approval above ₦250,000 | Yes, counting what the member already signed that quarter | `test_a_cost_above_the_threshold_waits_for_the_accountant_who_sees_only_its_heading`, `test_f05_...` |
| 26 | Covenant watch | Yes (duty) and tested at every close | duty "Watch the promises" |
| 27 | Report to partners | Yes (duty) | duty "Report to the partners" |
| 28 | Bookkeeper for player clients | Yes | `test_a_bookkeeper_reports_on_a_clients_money_and_the_fee_is_shared_with_their_empire` |
| 29 | Raising money | Yes: loan, bond or stake | the stage test |
| 30 | Deal origination: the board picks from the banker's shortlist | Yes | `test_the_bankers_shortlist_decides_the_next_investment_...` |
| 31 | Report on how much to borrow | Yes (duty) | duty "Advise on how much to borrow" |
| 32 | Limits with teeth | Yes: limit for one trade, and the freeze | `test_a_trade_above_the_risk_managers_limit_waits_...` |
| 33 | Risk report at every Closing Bell | Yes, kept for good | the stage test |
| 34 | Approving large deals; the head's overrule on the record | Yes | `test_the_head_overrules_the_risk_managers_refusal_on_the_record` |
| 35 | Counterparty watch | Yes (duty) | duty "Watch the banks" |
| 36 | Insurance programme | Yes: two kinds of cover, from the insurance companies | the inspection test |
| 37 | Liquidity plan | Yes (duty) | duty "Test the liquidity plan" |
| 38 | New-venture reviews | Yes: a first purchase in a new industry waits for the Risk Manager | `firm_risk.gate_trade` |
| 39 | Risk appetite by vote | Yes | `risk_appetite` vote; duty "Measure against the risk appetite" |
| 40 | Post-mortems, permanent | Yes (duty after a loss; shown on the Board tab) | duty "Write the post-mortem" |
| 41 | Risk report to the board, checked next quarter | Yes | duty "Name the three biggest dangers" |
| 42 | Public track record of signed opinions | Yes | `track_record`; `/api/people/{id}/record` |
| 43 | Lawyer's sign-off on every pact, loan and deal | Yes for loans, bonds and stakes (papers with traps); deals come in Part 2 | `test_a_paper_hides_which_clauses_are_traps_...` |
| 44 | Required filings, a fine for a missed one | Yes | `test_a_missed_filing_is_a_fine_and_the_staff_file_correctly` |
| 45 | The empire's constitution, voted and enforced | Yes | `constitution` vote; `test_f03_...` (buy-back) |
| 46 | Employment contracts with a non-compete | Yes | `test_a_contract_drafted_by_the_lawyer_sets_the_notice_and_its_non_compete_bars_the_rival` |
| 47 | Legal risk register | Yes (duty) | duty "Keep the legal risk register" |
| 48 | Intelligence briefings on rivals | Yes (duty) | duty "Brief the head on the rival" |
| 49 | Letter to partners | Yes (duty), published on the Board tab | duty "Write the letter to the partners" |
| 50 | Talent scouting | Yes (duty) | duty "Scout for talent" |
| 51 | The year's strategy with targets | Yes | `test_the_strategy_is_set_once_a_year_and_judged_against_its_own_targets` |
| 52 | Chairing the board, deciding vote | Yes | board duty; the tie rule in the vote count |
| 53 | Staffing desks and setting targets | Yes: titles, giving duties and steps to members | `test_up_to_three_tasks_...` |
| 54 | Sharing out the money | Yes: budgets, the treasury policy, the tasks' sizes | Money tab |
| 55 | Pay and bonus policy | Yes: the bonus pool, desk pools, contracts' promised share | `test_a_desk_under_budget_...` |
| 56 | Final signature and the recorded overrule | Yes | the overrule test |
| 57 | Crisis command | Yes: the head answers for the head's desk in each event, and it goes on the record | the inspection test |
| 58 | Dealing with other heads | Partly: pacts (already built), poaching and matching, choosing the rival. Truces, syndicates and joint bids come with Part 2 | |
| 59 | Yearly vote of confidence, public scorecard | Yes | `test_the_head_loses_the_yearly_vote_of_confidence_and_the_deputy_leads`, `test_a_head_keeps_the_members_confidence_on_a_tie_...` |
| 60 | Succession through a deputy | Yes | the confidence test |
| 61 | Code of conduct | Yes: how theft is handled, and a fine for a missed duty | `conduct` vote |
| 62 | Public face and a personal record that follows the CEO | Yes: the year's letter, the head's record across empires | `ceo_record` |
| 63 | Outside-client fees split 60% empire, 40% player | Yes | the bookkeeper test |

## What each part does, in plain words

**The firm** is a new section, "The firm", for every member of an open empire. It opens on
"Needs you now" (events to answer, requests to decide, papers to read, votes, contracts, your
desk's duties) and has seven tabs: Desks, Requests and votes, Money, People, Work and events,
Risk, Board.

**Duties.** Each desk has standing work each quarter (26 in all), set from the empire's own
figures at the moment a member opens it and marked by the server: no question papers. A duty
nobody does is done by computer-run staff where the empire has staff in that seat (scored 70),
or missed (a league point lost). A duty that does not arise that quarter (no debts to watch, say)
is not counted. Judgement duties (an idea, three dangers, a shortlist) pass when handed in and
earn the rest when the next quarter shows they were right.

**Requests.** Whatever needs a desk's yes goes to that desk. Nobody decides their own request or
one that pays them. After a day the head may decide it, after two the deputy, after three it
lapses. A refusal by the Risk Manager or the Lawyer can be overruled by the head within two
days, and it goes on the head's record for good, judged later on how it turned out.

**Votes.** In an empire run by players the members vote the dividend, the treasury policy, the
risk appetite, the constitution, the code of conduct and the members' pension plan. A vote
passes as soon as enough say yes; at the end, more yes than no carries it, and on a tie the head
decides (except the vote about the head).

**Papers.** Every loan, bond and stake comes with a paper of 6 to 8 clauses, one to three of them
traps. The Lawyer strikes out what would hurt the empire. A trap left in is in force (a rate that
jumps, a lender who can call at any time, a personal guarantee, a fee to repay early...); a fair
clause struck out costs half a point on the rate.

**Money.** Partners own the empire in units, bought at today's worth, exactly, so nobody already
in is diluted. Raising money goes banker → Accountant → Risk Manager → Lawyer → head. Interest is
paid every quarter and the promises tested; a broken promise lets the lender call the debt, and
a debt not paid is a default: the lender takes cash, then shares, and the head who signed a
personal guarantee pays a tenth. Budgets per desk; a desk under budget that did its duties well
earns a fifth of what it did not spend. Any cost above ₦250,000 (counting what the member already
signed that quarter) waits for the Accountant, who sees its heading and amount and nothing that
marks a theft from a genuine cost.

**People.** Contracts drafted by the Lawyer, offered by the head, signed by the member: notice,
a promised share of the desk's pool, a non-compete against the rival. Apprentices. Poaching with
two days to match, and a transfer fee for a member under contract. The year's strategy, judged
against its own targets; the yearly vote of confidence; the head's record across empires.

**Work and events.** Up to three tasks at once (invest, rescue, defend, raise money), one of each a
quarter, each step given to a member. The banker's shortlist decides the next investment. Every
empire has a rival and a head-to-head score. Four kinds of event land at Closing Bells and must
be answered by two or three desks within two days; insurance pays from the insurer's own cash.

**Risk.** A limit for one trade; a first step into a new industry, or a trade against the
treasury policy, waits for the Risk Manager; the freeze stops a member's share and bond trades
and anything they had waiting. A risk report is written at every Closing Bell and kept.

**Bookkeeping.** Any player may hire an Accountant for the quarter; the report is marked against
the client's own payments; the fee is split 60/40 with the Accountant's empire.

## Decisions I made that you did not specify

All are starting values and can be changed: request timings 24/48/72 hours; overrule within 48
hours; votes open 48 hours; staff duty score 70, pass mark 60, a duty teaches 50 experience times
one more than the rank; a missed duty −1 league point, a well-run quarter +3, an event answered
well +2 (badly −1); a loan at the Central Bank's rate +4 points, a bond +2.5; least loan ₦5m,
bond ₦50m, stake ₦5m; terms of 4 or 8 quarters; a stake offer open 3 days for up to a quarter of
worth; training gives a point of experience per ₦10,000, at most 500 a quarter; an apprentice's
mentor is 10 levels above, gains a fifth of what the apprentice earns, the apprentice a tenth
more on duties; insurance premiums 6% (a holding's collapse) and 3% (an inspection) a quarter, for
four quarters, cover up to a tenth of worth; a failed inspection costs half of one percent of
worth, a missed filing a tenth of one percent, filings at 5% of a company; at each Closing Bell a
one-in-four chance of an event for an empire with players in it; the staff answer an event right
seven times in ten; a bookkeeper's fee from ₦50,000 to ₦5m.

Empires run by the computer keep to published rules: they do not borrow, vote or offer contracts,
and their costs need no countersignature (as before). Their staff do every duty.

## Needs your decision

Nothing blocks Part 2. If you want any figure above changed, say which.

## The loophole check

The rule: players can commit crimes against each other's empires, but not against the game.

| # | Question | Answer | Tests |
| --- | --- | --- | --- |
| 1 | Can anyone decide or vote on their own request, or one that pays them? | No | `test_nobody_decides_their_own_request_...`, `test_f15_...`, `test_f16_...` |
| 2 | Can money be made or lost by the game, or paid twice? | No | every money test ends with the ledger check; `test_f01_...` |
| 3 | Can a limit be passed (signing, trading, debt, dividend, bonus, the threshold)? | No | `test_f04_...`, `test_f05_...`, `test_f06_...`, `test_f08_...`, `test_f13_...`, `test_an_empire_may_not_owe_more_than_half_...` |
| 4 | Can partners be diluted or enriched by units? | No | `test_f02_...`, `test_f03_...`, `test_new_capital_and_a_stake_buy_units_...` |
| 5 | Is hidden information shown early (answers, traps, event truths, player numbers, a theft's mark)? | No | `test_a_paper_hides_...`, `test_f07_...`, `test_f12_...`, `test_a_member_sees_the_firm_..._never_sees_a_colleagues_player_number_or_an_answer` |
| 6 | Can a duty be done twice, by someone else, late, or changed? | No | `test_a_duty_is_fixed_once_opened_...`, `test_f14_...` |
| 7 | Can poaching, contracts or apprenticeships be abused? | No | `test_f08_...`, `test_f17_...`, `test_f22_...`, `test_f23_...` |
| 8 | Can events or insurance pay unfairly? | No | `test_an_inspection_...`, `test_f21_...` |
| 9 | Can the freeze or the Risk Manager's limit be got round? | No | `test_a_trade_above_...`, `test_f09_...`, `test_f10_...`, `test_f11_...` |
| 10 | Can a permanent record be changed? | No | `test_f18_...`, `test_f19_...`, `test_f20_...`, `test_f24_...` |

**The independent review.** A second AI reviewer that did not write the code tried to break it
and found 24 confirmed holes. None created or destroyed money; they moved money to the wrong
place or let a limit or a hidden fact through. The worst: a debt in default stopped counting as
owed; units were priced with a rounding that diluted the founders; a leaving partner could be
paid more than their share; a poaching bonus escaped the bonus limit; the freeze did not stop a
trade already waiting; bond trades skipped the Risk Manager; a dividend voted on old figures
could be paid after a loss; a request named the banker's player number; several records could
be rewritten in the database. All 24 are closed, each with its test in
`tests/test_firm_review.py`. I also closed what it listed as suspected: a good answer to a called
loan no longer reopens a loan whose promises are broken; a buyer's offer is priced from the lower
of the market and the company's worth; an inspection's right answer depends on what the empire
holds; the stake paper's two traps now take effect; a contract's promised pool share is paid; the
head sees who gets what in a bonus pool; a tie in a vote of confidence keeps the head; a duty
opened by a member who leaves can be picked up; judgements are checked a quarter later; a
personal guarantee falls on the head who signed; and the bookkeeper (item 28) was built.

## The economy still holds

The ten-year run (40 quarters) is unchanged from Stage 7: inflation 3.25% to 9.22%, the Central
Bank's rate 11.5% to 14%, the ledger audit empty, every figure within ₦0.1 billion of Stage 7's.

## Honest limits

- Duties are marked numbers, choices and picks; written parts (a plan, a letter, a lesson) are
  kept and shown to members but not marked.
- The pots are views of the empire's cash, bonds and shares, not separate accounts.
- Item 58 is partly done: truces, syndicates and joint bids come in Part 2.
- Events need a player-run empire; computer-run empires do not get them.
- A rival is named automatically at the next Closing Bell; the head can choose another.

## Screenshots

`docs/screenshots/pe1/`: the desks (01), a duty open (02) and marked (03), the Money tab (04),
a request to decide (05), a paper to read (06) and read (07), money borrowed (08), a vote (09),
the People tab for the head (10), "Needs you now" (11), a contract to sign (12), events and
tasks (13), an event to answer (14), the Risk tab (15), the Board (16), bookkeeping (17), a phone (18).

## Run it

```powershell
cd $HOME\wall-street-beyond-the-market
git pull
docker compose up --build
```

Then open http://localhost:5173, take a seat in an empire, and choose "The firm".
