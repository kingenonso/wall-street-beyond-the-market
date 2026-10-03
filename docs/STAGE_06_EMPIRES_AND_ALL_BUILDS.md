# Stage 6: all builds and empires

The stage test, from the design: **"An empire of three humans plus NPC staff completes a task
that needs five builds."** It passes:
`tests/test_empires.py::test_an_empire_of_three_humans_plus_staff_completes_a_task_that_needs_five_builds`.
(The task in fact needs all six builds and the head's approval. Three players do three of the
steps and the head's approval; computer-run staff do the other three.)

Tests at the end of the stage: **721 on the server**, 13 on the order-matching engine,
12 on the website. All pass.

## Checklist

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| 1 | The other four starting builds (Investment Banker, Risk Manager, Lawyer, Journalist): employers, salary, levels, six pieces of work each | Yes | `tests/test_builds.py` (every piece of work is taken, done right, and paid by its named payer) |
| 2 | Their four screens and the CEO screen, each in its own colour (purple, orange, red, blue; CEO gold) | Yes | `test_the_new_build_screens_have_their_figures_and_show_nothing_hidden`; screenshots 04, 06, 07, 08, 15 |
| 3 | Founding an empire: Level 20, ₦25 million fee, partners pool; founder is Acting Head with capped powers | Yes | `test_founding_needs_level_twenty_three_players_and_the_fee...`, `test_an_empire_with_fewer_than_three_players_cannot_open...`, `test_the_founder_is_acting_head_with_capped_powers` |
| 4 | 13 seats (a head, and two for each of six builds); empty seats filled by computer-run staff at Level 40, paid by the empire | Yes | `test_five_empires_exist_from_the_first_day...`, `test_staff_are_paid_by_the_empire_each_quarter...` |
| 5 | Five computer-run empires created with the world | Yes | the same two tests |
| 6 | Chain of command and structured handoffs | Yes | the stage test; `test_in_a_players_empire_the_head_decides_what_follows` |
| 7 | Empire tasks that need several builds | Yes | the stage test; `test_a_step_can_be_tried_once...` |
| 8 | Secret pacts: a Lawyer drafts, hidden, breakable | Yes | `test_a_lawyer_drafts_a_pact_the_heads_sign_it_and_it_stays_hidden`, `test_a_journalist_can_uncover_a_pact...` |
| 9 | War Room: shared tracker, text chat. Voice: a marked placeholder | Yes (voice is a placeholder, as agreed) | `test_the_war_room_is_for_members_only`; screenshots 03, 12 |
| 10 | Asset Managers trade the empire's money | Yes | `test_asset_managers_trade_the_empires_money_within_the_limit_the_head_set` |
| 11 | Every retirement fund has a bad side; best quarter, worst quarter and growth after rising prices are shown | Yes | `test_every_fund_has_a_stated_weakness_and_can_have_a_bad_quarter`, `test_the_career_page_shows_each_funds_best_and_worst_quarter...` |
| 12 | Rewards for saving extra: less tax, employer match, the "sound finances" mark, one early withdrawal for founding an empire | Yes | `test_extra_saving_lowers_the_tax...`, `test_extra_saving_is_paid_on_pay_day...`, `test_the_sound_finances_mark...`, `test_the_one_early_withdrawal...` |
| 13 | Retirement at Level 50 or after 10 game years; then a pension every quarter | Yes | `test_retirement_opens_after_ten_game_years_of_work_and_a_pension_is_then_paid_every_quarter` |
| 14 | The shadow feature: taking from your own empire, each build in its own way, within the signing limit | Yes | `test_a_member_can_take_the_empires_money_disguised_in_its_books_within_their_signing_limit` |
| 15 | Audits: an Accountant's audit; the paid AI audit (95% accurate, only in audit seasons, looks back four quarters, large fee) | Yes | `test_an_accountants_audit_finds_it...`, `test_an_auditor_can_look_away...`, `test_the_ai_audit_can_be_hired_only_in_an_audit_season...`, `test_the_ai_audit_is_right_about_ninety_five_times_in_a_hundred` |
| 16 | Consequences decided by the head: repay with a fine, sacked, reputation down, debt taken from salary; a reward for reporting a theft that is proved | Yes | `test_in_a_players_empire_the_head_decides_what_follows`, `test_the_head_may_forgive...`, `test_reporting_a_theft_that_is_proved_is_rewarded...` |
| 17 | Pension funds run by players, under the same theft and audit rules, from Level 20 | Yes | the last five tests of `tests/test_savings.py` |
| | Accepted suggestions: players can join the computer-run empires from the first day; text chat now, voice later; pension managers at Level 20 | Yes | `test_a_new_player_joins_an_empire_from_the_first_day_and_uses_the_war_room` |

## What each part does, in plain words

**The six builds.** A new player may now choose any of six professions. Investment Bankers
and Risk Managers are hired by banks and insurers, Lawyers by every company, Journalists by
the three media houses. Each has six pieces of practical work, judged by the server against
the game's own records and paid for by a named payer, exactly as in Stage 5.

**An empire** is a team with thirteen places: a head, and two seats for each build. It has
its own account in the ledger (the game's record of every naira). A seat is *in addition to*
a job: the employer still pays the salary; the empire pays for work done for it.

**Five empires run by the computer** exist from the first day: Savannah Crown Holdings, Delta
Meridian Group, Niger Bend Partners, Atlantic Gate Holdings and Kola Ridge Group. Each has
its home in one of the five cities, and its ₦5 billion of founding capital was put up by the
households of that city out of their savings: the money was moved, not made. Any player with
a build can take a seat in one at once.

**Computer-run staff** fill seats no player holds. They work at a fixed Level 40, do one step
of a task each working day, and are paid by the empire each quarter. Staff who are let go are
paid for the quarter. An empire that cannot pay its staff loses them.

**Founding.** A Level 20 player begins a founding, names the empire and puts money in.
Partners apply, the founder accepts them, and everybody may add to the pool. When there are
three players and ₦25 million in the pool, the founder opens it: the fee goes to the prize
pool. If the founding is cancelled, every naira goes back to whoever put it in.

**Acting Head, with capped powers.** CEO is a rank that must be earned, so the founder leads
as Acting Head. They recruit, set limits, start tasks, approve, pay bonuses and sign pacts.
The caps: they may sign for costs of at most 2% of the empire's cash in a quarter; bonuses
may not pass a tenth of the empire's worth in a quarter; they cannot pay themselves a bonus;
they cannot decide their own case; they cannot approve a takeover (that comes later).

**A task and its handoffs.** The head starts an investment task. The server chooses a company.
Seven steps follow, each handed to the next: the Journalist researches it, the Accountant
reviews its accounts, the Investment Banker values it, the Risk Manager stress-tests it, the
Lawyer checks who controls it, the head approves, and the Asset Manager buys the shares with
the empire's money. A step a player takes is a real piece of work, judged like any other and
paid for by the empire. One task a quarter.

**Trading the empire's money.** Asset Managers (and the head) place the empire's orders. What
they buy belongs to the empire. The head sets how much of the empire each may trade in a
quarter.

**The shadow feature.** Any member may "sign for a cost" that is not real: the money moves
from the empire to them, and is written in the empire's books under their build's ordinary
heading (a Lawyer's reads "Legal fees and filings"). Genuine costs use the same headings, so
the books do not give a thief away. Each member has a signing limit for the quarter, set by
the head.

**Audits.**
- *An Accountant's audit* (once a quarter, last two quarters). How much it finds depends on
  the Accountant's level against the thief's. The Accountant sees what was found and decides
  what goes in the report: an auditor can look away.
- *The staff Accountant* audits each quarter as it closes, and reports everything it finds.
- *The AI audit*: an outside firm, right 95 times in 100, that checks the last four quarters.
  It can be hired only in an **audit season** (the last quarter of each game year: one real
  week in four), once, for 2% of the empire's worth and never less than ₦5 million. Thefts
  older than four quarters get away.
- *Reporting.* Any member may report an entry. If it is proved, they get a tenth of what is
  recovered. A groundless report costs a little reputation. Three a quarter.

**Consequences.** A proved theft opens a case. The head decides: punish or forgive. Punished
means repay the amount with a fine of the same again, lose the seat, lose 10 reputation, a
line on the legal record, and a year's ban from that empire. What cannot be repaid becomes a
debt: a quarter of every take-home pay goes to the empire until it is cleared. In an empire
the computer runs, and whenever the thief is the head, this happens without anybody deciding.

**Secret pacts.** A Lawyer drafts an agreement with another empire; both heads sign. Nobody
outside the two empires can see it. Either side can break it and loses trust. Four kinds are
lawful; four (fixing prices, rigging bids, dividing a market, staying out of each other's
deals) are offences. A Journalist may investigate one empire a quarter and may uncover a pact.

**Retirement savings.**
- Every fund now has a weakness, written beside it. Bonds lose value when the Central Bank
  raises its rate, and lose when a company defaults; shares fall with the market; the Income
  fund can buy less after a year of rising prices.
- Saving extra (up to 20% of salary) is taken before tax, the employer matches it up to 3%,
  and savings worth two quarters of salary earn the "sound finances" mark.
- One early withdrawal, of up to half, may be used to found an empire. It is paid straight
  into the empire.
- Retirement opens at Level 50 or after forty quarters of paid work. A pension of 2.5% of the
  savings is then paid every quarter, by the pension funds, and the player may keep working.

**Pension funds run by players.** A Level 20 Asset Manager may open one for ₦5 million. Savers
move their retirement savings in and own *units*: a unit is worth the fund's whole value
divided by the units in issue, so everybody gains and loses in the same proportion. The
manager invests the money and takes a fee of up to 0.5% a quarter. The manager can also take
from it (up to 1% of the fund a quarter), and is audited by the regulator every quarter; any
saver can hire the AI audit in an audit season. A manager proved to have taken savers' money
repays it with a fine and is struck off for good.

## Decisions I made that you did not specify

- A task needs **all six builds**, not five: it seemed wrong for one build to have no part.
- The computer-run empires' ₦5 billion each comes from the **households of the five cities**
  (the founders of the companies hold shares, not cash, at the start of the world).
- **Staff do one step a working day** when an empire has players in it, and wait two days for
  a player who holds the seat before doing the step themselves.
- Signing limits: in a computer-run empire, ₦100,000 a quarter for each level the player
  holds; in a player's empire, whatever the head sets.
- A **pension fund must deal within 2% of the market price**, cannot deal with its own
  manager, and may trade its own worth once a quarter. The same 2% rule applies when a player
  trades for a computer-run empire. Without these, a manager could hand savers' money to a
  friend through one bad trade and no audit would see it.
- Moves into and out of a player's fund are **carried out as the quarter closes**, like any
  change of fund, so nobody can choose after seeing how the quarter went.

## Needs your decision

1. **Three things an earlier note of mine mentioned for Stage 6 are not built**, because they
   were not in the checklist you approved: players making takeover bids; a player running a
   company (its dividend, growth and research dials); and players founding companies and
   selling shares to the public for the first time. The CEO screen says so where those panels
   would be. Tell me which stage you want them in.
2. **Voice chat** needs an outside voice service (a monthly cost). Text chat works now.
3. The blueprint caps levels at 20 until "rank cases" exist, so **Level 50 cannot be reached
   yet**: for now retirement opens only by the forty-quarter route.
4. Carried forward from earlier stages: the phone check for multiple accounts (a paid
   service); uploaded profile pictures; cheaper loans against savings (Stage 9); courts and
   juries (Stage 11).

## The loophole check

| # | Question | Answer for Stage 6 | Tests |
| --- | --- | --- | --- |
| 1 | Can money be made from nothing? | No. Every naira an empire or fund has was moved to it through the ledger; ten quarters of empires re-add exactly | `sound(db)` in every money test; `test_ten_quarters_of_empires_never_make_or_lose_a_kobo` |
| 2 | Can a payment be collected twice? | No. One case per entry, one fee per audit season, one refund per founding; the reviewer tried each of these several times at the same moment | `test_an_accountants_audit_finds_it...`; reviewer's attacks B1 to B5 |
| 3 | Can somebody be paid without a payer who has the cash? | No. Bonuses, step pay, staff pay, rewards and pensions are capped at what the payer holds; an unpaid fine becomes a debt | `test_in_a_players_empire_the_head_decides_what_follows` |
| 4 | Can the reward be had without the work? | Closed: one task a quarter, one step of each kind a quarter, a failed step goes to the staff, no reward for "uncovering" your own or a lawful pact | `test_one_step_of_each_kind_a_quarter...`, `test_one_pact_of_a_kind...`, `test_smaller_things_the_reviewer_found` |
| 5 | Can a player see what they should not? | No. The books never show who entered an entry or whether it is genuine; genuine and false entries share headings; another empire's room, chat and pacts are closed; one empire's holdings are never shown on their own line | `test_genuine_costs_and_false_ones_share_their_headings`, `test_one_players_requests_never_reach_another_empires_room`, `test_what_one_fund_or_empire_holds...` |
| 6 | Can a player act on an empire or fund that is not theirs, or pass their limits? | No. The server works out the empire from its own records. Limits hold across empires and against what a trade really costs | `test_a_signing_limit_is_the_players_for_the_quarter_wherever_they_sit`, `test_the_trading_limit_is_checked_against_what_a_bond_trade_really_comes_to` |
| 7 | Can bad input break anything? | No. The reviewer sent negatives, fractions, text, huge numbers and other empires' identifiers to all 65 requests: no fault | `test_text_that_cannot_be_kept_is_refused_not_a_fault`, `test_an_empires_name_is_plain_letters...` |
| 8 | Can one player stop the quarter or the bell for everybody? | No. The close survived a cashless empire, a step-taker who left, a cancelled founding, an empty fund and a struck-off fund | reviewer's attacks C5 and C6 |
| 9 | Can a thief escape what the rules promise? | Closed: leaving before the audit, becoming head to forgive yourself, letting the staff Accountant go before the close | `test_a_thief_who_left_before_the_audit_is_still_kept_out`, `test_nobody_decides_their_own_case...`, `test_staff_who_are_let_go_are_paid_for_the_quarter_and_the_audit_still_happens` |
| 10 | Are records permanent? | The decision log, legal records, capital put in, ended memberships, book entries, decided cases, audits, fund prices and empire worth cannot be changed or deleted, even in the database | `test_memberships_books_and_cases_are_guarded_in_the_database` |

### The independent review

A second reviewer, who did not write the code, attacked Stage 6 with 39 tests of its own. It
found **21 holes and six smaller things; none made or destroyed money.** All are closed, each
kept as a test in `tests/test_review6.py`.

| Found | Fixed |
| --- | --- |
| An Asset Manager could sell their own shares to a computer-run empire at the top of the day's price range | An empire or fund cannot deal with its own people; a computer-run empire deals within 2% of the market; a player's trading limit there is small |
| A locked pension could be turned into cash by trading between a fund and its manager | The same bar; a fund deals within 2% of the market and trades its own worth once a quarter |
| One kobo taken made a computer-run empire pay ₦88 million for an AI audit | The computer hires it only when more is at stake than its fee |
| The signing limit was multiplied by moving from empire to empire | The limit is the player's for the quarter, wherever they sit |
| Joining or leaving a player's fund on the last day picked the quarter's return after seeing it | Moves are carried out as the quarter closes |
| The early withdrawal could be cashed by founding and cancelling | It goes straight into the empire, and back to the savings on cancelling |
| A thief who left before the audit was never banned | The ban follows the proved case, not the way they left |
| A thief who became head forgave their own case | Nobody decides their own case; an accused member does not become head |
| A bonus could be paid out of an empire still being founded, after which it could not be cancelled | Pooled money cannot be spent until the empire opens |
| A head could empty the empire with one bonus | Bonuses are capped at a tenth of the empire's worth in a quarter |
| The heading alone said which entries were false, and whose | Genuine costs (staff pay, pay for steps) use the same headings |
| Staff could work all quarter and be let go before pay day; this also switched off the staff audit | Staff let go are paid for the quarter; the audit still happens |
| Pacts without limit, and a colleague "uncovering" one for experience | One pact of a kind between two empires; no reward for your own empire's or a lawful pact |
| An Asset Manager was paid for the same step in several empires, for shares the staff had already ordered | One step of each kind a quarter; the count starts when the player takes the step |
| A bond priced above its face value passed the trading limit | The limit is checked against what the trade really came to |
| A fine recovered for a fund nobody was left in was stranded | It goes to the ordinary pension funds |
| An unprintable character in chat was a server fault | Refused with an ordinary message |
| Several actions worked between a quarter's end and its close | Refused, like everything else |
| A look-alike of an empire's name (a foreign letter) was accepted | Names are plain letters and numbers |
| One fund's whole holding showed on the Lawyer's screen | Counted with the small investors |
| Ended memberships, book entries and decided cases could be rewritten in the database | Guarded |

The smaller things: a Lawyer in a computer-run empire can now have a lawful pact signed; an
Accountant who has left cannot file their audit; a manager is struck off once, not twice;
colleagues' identifiers go to the head alone; a saver needs ₦1,000 to move; somebody with too
low a reputation to join cannot found; a seat is given up before changing build; a failed
step cannot be retaken by a colleague who has seen the answers.

## The economy still holds

Ten game years on fast-forward, one quarter at a time, with the five computer-run empires in
the world: inflation between 3.3% and 9.2% (Stage 5: 3.8% to 8.7%), the Central Bank's rate
between 11.5% and 14%, the Money Watch green throughout, no company's books out, and the
ledger re-adding exactly at every close. The small difference from Stage 5 is the ₦25 billion
the households put into the five empires, most of which the empires lend to the Government.

The computer-run empires pay their own way: each began with ₦5.0 billion, pays about ₦75
million to ₦130 million a quarter to its staff, earns interest on what it lends to the
Government, and is worth ₦6.1 billion after ten game years.

## Honest limits

- **Accounts working together.** A thief with a second account in the same empire can report
  their own theft through it and get a tenth back. They still lose the amount, the fine, the
  seat and reputation, so it never pays; but it softens the blow. The multi-account check
  (carried forward) is the real answer.
- **A head and an accomplice.** A head may still pay an accomplice bonuses of up to a tenth of
  the empire a quarter. That is a crime against their own partners, which the rules allow;
  the partners can see every bonus in the books and can leave.
- **A manager and a friend.** Within the 2% rule, a fund manager can still lose a little of
  the savers' money to a friend on each trade: at most about 2% of the fund a quarter.
  Savers see the price of a unit fall, and can leave.
- **The computer-run empires rarely finish a purchase on fast-forward**, because nobody sells
  to them when no trading day runs. In the live game the investors' orders meet theirs.
- **Catching up after the server has been off.** When several quarters are closed in one go, the
  computer-run empires lend their idle cash only at the last of them, so they earn a little less.
- **The CEO rank cannot be earned yet**, so every player-founded empire is led by an Acting
  Head. The "CEO screen" is shown as "Head of empire" (to members who are not the head, as
  "Empire overview").
- **Value-at-risk needs ten Closing Bells of history** and is worked out from how the BSX 50
  index has moved, not share by share.
- **Panels that wait for later stages** say so on the screen: subsidiaries and property (CEO);
  derivatives and hedges (Risk Manager); property checklist, litigation and evidence
  (Lawyer); sources and audience (Journalist); deals a player arranges for a fee (Investment
  Banker).
- The map of Nigeria on the head's screen is a sketch, not a survey.

## Screenshots

In `docs/screenshots/stage-06/`: 01 the six builds; 02 the league of empires; 03 the War Room
as a member; 04 the Lawyer's screen; 05 the books and the shadow side; 06 the Journalist's
screen; 07 the Risk Manager's screen; 08 the Investment Banker's screen; 09 a banker's work;
10 and 11 founding an empire; 12 the War Room as head; 13 a step waiting; 14 the step as a
piece of work; 15 the head's screen; 16 retirement savings and pension funds; 17 the War Room
on a phone.

## Run it

Your world is kept. The new tables are added when the server starts.

```powershell
cd $HOME\wall-street-beyond-the-market
git pull
docker compose up --build
```

Then open http://localhost:5173. Choose a build on the Career page, then open **Empires** in
the menu on the left and take a seat.
