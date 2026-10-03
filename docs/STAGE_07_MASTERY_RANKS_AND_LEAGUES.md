# Stage 7: syllabus maps, mastery, rank cases and leagues

The stage test, from the design: **"Every module on every syllabus map has a solo, an empire
and a live-event objective; a player at Level 20 cannot advance until the required modules are
mastered and the rank case is passed."** It passes:
`tests/test_mastery.py::test_stage_seven_every_module_has_three_kinds_of_work_and_level_twenty_is_a_gate`.

Tests at the end of the stage: **798 on the server**, 13 on the order-matching engine,
12 on the website. All pass.

## Checklist

Part A is what the design puts in Stage 7. Part B is what the owner added after Stage 6.

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| 1 | A syllabus map (skill tree) for each of the six builds and for CEO. Exam bodies' names never shown | Yes | `test_every_module_has_work_alone_with_the_empire_and_as_a_weekend_challenge`, `test_the_names_of_exam_bodies_appear_nowhere_in_the_library` |
| 2 | Every piece of work tagged to its module | Yes | the same test (every template carries a module and a track) |
| 3 | Three mastery stages: learned (alone), practised (with the empire), proven (live event) | Yes | `test_a_module_is_learned_alone_practised_with_the_empire_and_proven_in_a_weekend_challenge` |
| 4 | The library: a first batch of about 120 templates, every module covered three ways | Yes: 127 on offer (42 alone, 43 with the empire, 42 weekend), 129 in all | the stage test; `test_every_piece_of_work_in_every_setting_can_really_be_offered` |
| 5 | One solo, one empire and one live-event piece per module; the live-event piece a timed weekend challenge until Stage 15 | Yes | `test_a_weekend_challenge_is_timed_and_a_late_paper_does_not_pass` |
| 6 | Rank cases at Levels 20, 40, 60 and 80: one large piece of work made from the live world, a fee that leaves the economy, retry after three real days | Yes | `test_a_rank_case_needs_the_level_and_the_mastery_and_its_fee_leaves_the_economy`, `test_a_failed_case_can_be_sat_again_after_three_real_days_on_a_fresh_case`, `test_every_build_has_a_rank_case_made_from_the_live_world_that_can_be_passed` (all six builds) |
| 7 | Levels above 20 open | Yes, to Level 100 | `test_a_career_stops_at_each_gate_until_its_rank_case_is_passed`, `test_passing_the_case_opens_the_levels_above_and_work_then_teaches_more` |
| 8 | The CEO rank: Level 60, the CEO rank case, reputation 75; or voted in by the empire. The Acting Head's caps lift | Yes | `test_the_ceo_rank_needs_level_sixty_the_case_and_a_reputation_of_seventy_five`, `test_a_member_who_holds_the_ceo_rank_can_be_voted_in_by_the_empire` |
| 9 | The debrief (plain words, the professional method, the arithmetic) on all new work | Yes | `test_the_new_work_is_marked_against_the_record` (seven new pieces) |
| 10 | Coverage tracker | Yes | the mastery test; `tests/test_rank_api.py` |
| 11 | Leagues: divisions, promotion and relegation as each game year ends | Yes | `tests/test_leaving.py`: the four league tests |
| 12 | Retirement at Level 50 reachable | Yes | `test_retirement_at_level_fifty_can_now_be_reached` |
| 13 | Leaving by resignation letter: head told, counter-offer, automatic exit after two real weeks | Yes | `tests/test_leaving.py`: the seven resignation tests |
| 14 | A thief can be prosecuted after leaving; the new head sees the legal record and decides | Yes | `test_a_theft_found_after_the_thief_has_left_is_still_punished_...`, `test_a_new_head_sees_the_legal_record_and_decides` |
| 15 | Signing limit: a flat ₦500,000 a quarter for everybody; the same starting figure in a player-run empire | Yes | `test_the_signing_limit_is_the_same_flat_figure_at_every_level` (Levels 1, 4, 20), `test_a_player_run_empire_starts_at_the_same_figure_...` |
| 16 | The empire's trading form: company by name, price, allowed range, buyers and sellers waiting, cost and fee calculator, a line about tax; the same for bonds and for the pension fund | Yes | screenshots 13 and 14; the website's own checks |
| 17 | "After a takeover": savings a green up arrow, extra costs a red down arrow | Yes | `web/src/Capital.tsx` |
| | Decision: model answers checked by two independent AI checks, plus players' reports | Yes | see "Two independent checks of the answers" below; `test_a_player_can_report_marking_they_believe_is_wrong_once` |
| | Decision: each track-to-level mapping checked against the current syllabuses | Yes | see "The syllabus maps against the real syllabuses" below |

## What each part does, in plain words

### The syllabus map and the three settings

Each build has six learning modules, and the leadership track (the CEO's map) has six more:
42 in all. On the Work page and on each build's own screen the map shows every module with
three small circles: learned, practised, proven. Above it the coverage tracker shows three
bars: what share of the map is learned, practised and proven.

Each module's work now comes in three settings:

1. **On your own.** As before: for a client or your employer. Passing it makes the module *learned*.
2. **With your empire.** The same skill, done for your empire and paid by the empire out of its
   own cash. It needs a seat in an open empire. Passing it makes the module *practised* and
   adds 2 points to the empire in the league.
3. **Weekend challenge.** Open from Friday 18:00 to Sunday 22:00, Lagos time, to everybody at
   once. Work you prepare must be handed in within three hours of taking it on, and the client
   and figures are not shown until you take it on. It pays and teaches one and a half times as
   much. Passing it makes the module *proven* and adds 3 points to your empire. This is the
   stand-in for live events until Stage 15.

**One setting of each module a quarter.** A module can be worked alone, or with the empire, or
in the weekend challenge in a quarter, not all three. (The independent review showed why: see
below.) So the fastest road to a fully proven map is three quarters, which is three real weeks.

### The new work

- **Lawyer: "Has the borrower broken its promises?"** (Contracts). A loan agreement with two
  promises, tested against the filed accounts. This gives the Lawyer six pieces of work alone,
  like every other build; drafting a pact stays as extra empire work for the same module.
- **The leadership track**, six pieces: return on capital; dividend policy; costs and
  break-even; capital allocation; acquisitions; people and productivity. It opens to the head
  of an open empire at once, and to anybody at Level 40. Its experience goes to the player's
  own build. Nobody starts the game on it, as the design says.
- **A portfolio review**, which exists only as a part of the Asset Manager's rank case.

### Levels, ranks and rank cases

A career now runs to Level 100, with gates at 20, 40, 60 and 80. Experience alone carries a
player to a gate and no further; experience earned while waiting at a gate is kept and counts
the moment the gate is passed. The five ranks are Associate, Professional, Senior, Principal
and Master.

To pass a gate a player needs mastery and then a rank case:

| Gate | Modules learned | Practised | Proven | Fee (at the start of the game) | Pass mark |
| --- | --- | --- | --- | --- | --- |
| Level 20 | all 6 | 3 | 1 | ₦200,000 | 80 in 100 |
| Level 40 | all 6 | all 6 | 3 | ₦500,000 | 85 |
| Level 60 | all 6 | all 6 | all 6 | ₦1,000,000 | 90 |
| Level 80 | all 6 | all 6 | all 6 | ₦2,000,000 | 95 |

A rank case is one large piece of work in three or four parts, all on one company drawn for
that player and that attempt from the world as it stands (a company already used for a case
that quarter is avoided, and banks and insurers are never used, because their accounts read
differently). Every figure in every part carries marks. The fee is paid when the case begins,
into the prize pool, and is not returned; it keeps pace with wages. There are 48 real hours to
hand it in, and never past the end of the quarter. A case that is not passed can be sat again
after three real days, on a fresh case. The marks for each figure and the professional method
are shown at once; the worked answers and the arithmetic are shown when the quarter has
closed, so that they cannot be carried into somebody else's case.

Work done after a rank case teaches more: experience from a piece of work is doubled after
the first case, trebled after the second, and so on. Without that, Level 100 would take many
years. With it, a player who works all six modules every quarter (a quarter is one real week)
reaches Level 20 in about four real months, Level 50 (retirement) in about nine months, and
Level 100 in about fifteen months. The first part of that, the road to Level 20, is the same
pace as in Stages 5 and 6.

### The CEO rank

Three things together: Level 60 in your own build, the CEO rank case (₦1,000,000, pass mark
90), and a reputation of 75. Once earned it is kept. A head who holds it leads as CEO, not
Acting Head, and the caps lift:

| | Acting Head | CEO |
| --- | --- | --- |
| May sign for, a quarter | 2% of the empire's cash | 5% |
| Bonuses, a quarter | a tenth of the empire's worth | a quarter |
| An investment task | up to ₦50 million | up to ₦200 million |

Any member who holds the CEO rank can be voted in as head by an empire founded by players:
one member, one vote, changeable; more than half of the empire's players carries it. A vote
is cast for a seat, because members are not given each other's identifiers. Somebody with a
proved theft waiting to be decided, or who has handed in a resignation letter, cannot be
voted in.

### Leagues

Empires compete in divisions of five. The five computer-run empires fill Division 1; a newly
opened empire enters the bottom division. Points through a game year:

| For | Points |
| --- | --- |
| A task finished (all six builds) | 10 |
| A piece of work passed for the empire | 2 |
| A weekend challenge passed by a member | 3 |
| An unlawful pact that comes to light | minus 5, to both sides |
| Growth in the empire's worth over the year | 1 for each 1%, up to 20 either way |

Growth leaves out money put in by members, and money taken and paid back with a fine, so it
cannot be bought. As each game year ends the top of each division goes up and the bottom goes
down, the final table is written down for good, and everybody starts the new year from
nought. Every player is also ranked within their build, by level and then experience. The
tables are public.

### Leaving an empire

Nobody leaves overnight. A member hands in a resignation letter.

- **In an empire run by players:** the head is told. The member works out a notice of 14 real
  days as a member in full: they work, they are paid, they may withdraw the letter. The head
  may make an offer to stay (a bonus of up to 5% of the empire's worth, a higher signing
  limit, or both), or let them go at once. Nothing is paid until the member accepts; if the
  empire cannot pay what it offered, the acceptance does not go through and the letter stands.
  If nothing is agreed, the member leaves at the first Closing Bell after the notice has run.
- **In an empire run by the computer:** there is nobody to make an offer, so the member leaves
  when the quarter ends.
- **In an empire still being founded:** a partner leaves at once and takes back what they put in.
- A head who resigns serves the same notice; the most experienced member then becomes Acting Head.
- A proved thief is still sacked at once, whatever letter is in.
- The letter and any offer are between the member and the head. Other members are not told
  until somebody actually leaves.

**A thief who leaves can still be prosecuted.** An audit at the old empire can prove the theft
after they have gone: they repay it with the fine, lose reputation, it goes on their legal
record, and the old empire will not have them back for a game year. They do not lose a seat
in a new empire automatically: the new head sees the legal record (on the Seats panel, and on
any application) and decides.

### The flat signing limit

Every member may sign for ₦500,000 a quarter, whatever their level (it was ₦100,000 for each
level). A player-run empire starts at the same figure until its head sets another. The limit
is still the player's for the quarter wherever they sit.

### The trading form

On the War Room and on a pension fund manager's screen, the form now asks for the company by
name from a list (with its price), then shows: the last price and today's change; the range
it may trade in today; what the empire or fund already holds; the buyers and sellers waiting;
and a sum, line by line: what the shares come to, the fees, the tax (none yet), and the total
the empire pays or receives. Where the empire or fund must deal within 2% of the market, the
form says what the highest buying price and lowest selling price are, and will not send an
order outside them. Bonds and bills have the same form, choosing by name.

One correction to what I told you when you first asked: the 0.50% is not all the exchange's
fee. It is 0.30% to the exchange and 0.20% stamp duty to the Government, and it was so since
Stage 4. The form now says so. There is still no tax on a gain from trading.

## The syllabus maps against the real syllabuses

The design gives a starting mapping (Levels 1 to 40, 41 to 70 and 71 to 100 against each
body's three stages) and asks for it to be checked against the current syllabuses. I checked
on 3 October 2026:

| Body | The design's mapping | What I found | Verdict |
| --- | --- | --- | --- |
| CFA | Level I, II, III | Still three levels. Level I in 2026 has ten topic areas | Holds |
| ACCA | Applied Knowledge, Applied Skills, Strategic Professional | Still those three, with 3, 6 and 4 papers | Holds |
| ICAN | Foundation, Skills, Professional | A revised syllabus took effect from the November 2025 diet: still 15 subjects, some renamed, with new digital and sustainability content. The article I found does not list the level names | Holds as far as I could confirm; the subject names should be re-read from ICAN's own document before the next batch of templates |
| CPA | Core topics, then specialist discipline | Since 2024: three core sections and one discipline chosen from three | Holds |
| FRM and CRM, Nigerian Bar finals | Part I and Part II; standard to contested matters | Not re-checked online this stage | Unchanged from the design |

**What the first batch covers, honestly.** All 42 modules sit in the first band (Levels 1 to
40: the foundation stage of each syllabus). Six modules a build is a first cut, not the whole
syllabus. Against CFA Level I's ten topic areas, for example, the Asset Manager's map covers
portfolio management, fixed income, equity and (through the Accountant's and Banker's work)
financial statements and corporate issuers. It does not yet cover ethics, quantitative
methods, economics as a module of its own, derivatives or alternative investments. The second
and third bands (Levels 41 to 100) have no modules of their own yet: work at those levels is
the same modules, with tighter pass marks at the gates. Growing the library toward 350 and
filling those bands is the "growing afterwards" you agreed.

## Decisions I made that you did not specify

- **One setting of each module a quarter** (after the review).
- **Experience multiplied after each rank case** (so that Level 100 can be reached in about fifteen months, not many years).
- **The numbers of the gates** (the mastery table above, fees, pass marks, 48 hours).
- **The weekend challenge's three-hour limit**, and that its client is hidden until it is taken on.
- **The leadership track opens to a head at once and to others at Level 40.**
- **The CEO's lifted caps** (5%, a quarter, ₦200 million).
- **League points**, and that Division 1 starts with the five computer-run empires.
- **A cap of eight pieces of empire-paid work a member a quarter**, so that a member cannot
  draw pay from a small empire without end.
- **A counter-offer's bonus is capped at 5% of the empire's worth**, and counts within the
  quarter's cap on bonuses.
- **Votes are for a seat**, and an election happens only in an empire founded by players.
- **Work in hand for an empire ends when the seat ends.**
- **A build cannot be changed with a rank case in hand.**

## Needs your decision

1. **Should the head approve empire-paid work?** Today a member of a player-run empire may take
   up to eight pieces of work a quarter that the empire pays for, without asking. I suggest
   leaving it: it is how members become "practised", it earns the empire league points, and
   the cap bounds it. Say if you want a switch for the head.
2. **The pace.** About four real months to Level 20, nine to Level 50 and fifteen to Level 100,
   for a player who does all their work every week. If you want it faster (or slower), it is
   two numbers: the experience a level needs, and the multiplier after each rank case. I
   suggest deciding this after the first real players have played for a few weeks.
3. **Qualified human reviewers** for the model answers, when you are ready: the reports
   players send are kept in the database for them.

## The loophole check

"Players can commit crimes against each other's empires in the game but not against the game."

| # | Question | Answer for Stage 7 | Tests |
| --- | --- | --- | --- |
| 1 | Can money be made from nothing? | No. Rank case fees move from the player to the prize pool; a counter-offer's bonus and empire-paid work move from the empire; a partner who leaves a founding gets back exactly what they put in. The ledger re-adds after every test of these, and after a ten-year run | the `sound(db)` check at the end of each of those tests; the economy run |
| 2 | Can a payment be collected twice? | No. One fee and one rank for a case; one bonus for an accepted offer; league points carry a reference and are counted once | `test_points_are_counted_once_...`; the reviewer's races (four at once: one succeeds) |
| 3 | Can somebody be paid without a payer who has the cash? | No. An offer the empire cannot pay does not go through; empire work is refused if the empire lacks the cash | `test_an_offer_the_empire_cannot_pay_does_not_go_through_and_the_letter_stands` |
| 4 | Can the reward be had without the work? | Closed after the review: one setting of a module a quarter (also enforced by the database); a rank case's answers are held back until the quarter closes; bonds in a case are priced at the case's own return; the leadership track needs an open empire or Level 40 | `tests/test_review7.py`: the first six tests |
| 5 | Can a player see what they should not? | No. An active case shows no answers; a weekend challenge shows no client before it is taken on; letters and offers go to the head and the writer only; legal records go to the head only; votes are cast by seat; the build table carries no identifiers | `test_a_resignation_and_an_offer_are_between_the_member_and_the_head`; `tests/test_rank_api.py` |
| 6 | Can a player act for another, or pass their limits? | No. The server works out the empire and the case from its own records. An offer lapses when the head who made it no longer leads. A CEO's caps apply only to somebody who earned the rank | `test_an_offer_lapses_when_the_head_who_made_it_no_longer_leads` |
| 7 | Can bad input break anything? | Closed after the review: a character that cannot be kept is refused, on the new requests and on the older hand-in | `test_a_character_that_cannot_be_kept_is_refused_not_a_fault` |
| 8 | Can one player stop the quarter or the bell for everybody? | No. The reviewer ran a full game year with a lapsed case, work in hand in every setting, everybody resigning, an open theft case and a pending offer: no fault | reviewer's `test_review7_held.py`; `test_a_case_not_handed_in_lapses_...` |
| 9 | Can a thief, or anybody, escape what the rules promise? | No. Resigning does not close the books; a letter does not stop a sacking; the sack ban follows the proved case; somebody leaving cannot be voted in; both sides of an unlawful pact lose league points | `test_a_theft_found_after_the_thief_has_left_...`, `test_being_sacked_overtakes_a_letter`, `test_somebody_who_is_leaving_cannot_be_voted_in_to_lead` |
| 10 | Are records permanent? | League points, year-end tables and reports are only added to. A judged case and a finished letter cannot be changed, even by somebody with access to the database | `test_the_new_records_are_permanent` |

### The independent review

A second reviewer, who did not write the code, attacked the stage with 35 tests of their own.
Nine loopholes were confirmed, none of which made or lost money. All are closed, each with a
test in `tests/test_review7.py`:

| Found | Fixed |
| --- | --- |
| The three settings of a module were often the same work: one set of answers, or one purchase, counted as learned, practised and proven and was paid three times (14 of the 36 older pieces) | One setting of each module a quarter, enforced in the database as well |
| A failed rank case showed its answers; parts not drawn on a company were the same on the retry and for a friend | Worked answers are held back until the quarter closes; the part that was the same paper for everybody is out of the Journalist's case; a bond in a case is priced at the case's own return |
| A counter-offer outlived the head who made it: a head voted out could leave the empire paying | The offer lapses when its maker no longer leads |
| One unprintable character in an answer was a server fault | Refused with an ordinary message |
| League growth points could be bought with a staged theft, repaid with its fine | Money taken and paid back with a fine is left out of growth |
| The leadership track could be opened with one kobo: begin a founding, take the work, cancel | It needs an open empire |
| Every member read in the log who had resigned and that an offer was made | Not written in the log until somebody actually leaves |
| A member working out their notice could be voted in as head | Refused |
| Reporting one's own unlawful pact cost the other side league points and the reporter none | Both sides lose the same |

Also closed from the reviewer's weaker observations: a member who was removed was still paid
by the empire for work in hand; a build could be changed with a rank case in hand; a weekend
challenge showed its client before the clock started; the trading form called the whole 0.50%
the exchange's fee; the Rank page had its hours and days written in instead of read from the
server.

### Two independent checks of the answers

Two further checkers, working separately and without reading the marking code first, solved
the new work from the wording a player sees and compared their answers with the server's:
about 800 instances of the seven new pieces between them, in all three settings, and 238 rank
cases across all seven tracks. **The arithmetic agreed in every instance of the new work.**
What they found was in the wording and at the edges, and is fixed:

| Found | Fixed |
| --- | --- |
| The contract, the portfolio review and the return-on-capital piece decided yes or no on figures rounded to one decimal, so a figure a hair over a limit was called inside it | The exact figure is tested, and a limit is never set within a tenth of the company's own figure |
| The acquisitions piece added a saving before tax to a profit after tax, and called the result "payback" | The saving is taxed first; the figure is named for what it is (years of profit); the debrief says the buyer also takes on the target's debts |
| The return-on-capital piece set the return against the cost of debt and called it the cost of capital | Worded as a first test, with the debrief saying owners' money costs more |
| The dividend test never said no: every company could afford it | Debt falling due within a year is taken off as well, and the board sometimes proposes a special dividend; both answers now occur |
| A rank case on a bank asked for figures that mean little for a bank | Cases are never set on banks or insurers |
| The income-statement piece did not say where interest earned goes | It says so |
| An overdue loan was shown as "ends Opening" | It reads "past its end date and still unpaid (overdue)" |
| One piece's "passed when" did not match its marking | It does |

## The economy still holds

Ten game years on fast-forward, one quarter at a time: inflation between 3.3% and 9.2%, the
Central Bank's rate between 11.5% and 14%, the Money Watch green in 37 quarters and amber in
3, no company's books out, and the ledger re-adding exactly at every close. These are the
same figures as Stage 6: nothing in this stage touches the economy when no players are in it.
The five computer-run empires end worth ₦6.1 billion each; with no players, each finishes one
or two tasks a year (10 to 15 league points) and nobody moves division.

## Honest limits

- **Empire and weekend work are the same skills in another setting.** The 85 new templates in
  those two settings are the 42 solo pieces done for a different payer or against a clock,
  each on its own draw of client and numbers. They are not 85 new kinds of work. The design's
  richer picture (the Risk Manager measures, the Accountant values, the Asset Manager acts, in
  one empire objective; a rival holding the opposite objective in a live event) needs the
  arena and live events of Stages 14 and 15. The empire task of Stage 6 is the one piece that
  already works that way.
- **Empire work in the market is judged on the player's own holdings**, not the empire's:
  several members trading one book could not be judged apart.
- **Proven means a weekend challenge, not yet a live event.** When live events exist they will
  count as proven too; nothing a player has earned will be lost.
- **Answers can still be passed between friends within a quarter** for work that is the same
  for everybody (the economy in four figures; a rate forecast; a bond drawn from the few on the
  desk). It was so in Stage 6. The work still pays only once each, and next quarter's figures
  are new.
- **A weekend challenge judged on holdings has no three-hour clock**: it is judged at the
  Closing Bells, like the solo piece.
- **The notice is carried out at the first Closing Bell after 14 days**, not to the minute.
- **The second and third bands of each syllabus have no modules yet** (see above).
- **An empire all of whose players have left** stays in its division, run by its staff.
- **Tolerances are generous**: a figure within half of one percent is marked right.
- **Qualified human review of the answers** has not happened; two AI checks and players'
  reports stand in, as you decided.

## Screenshots

In `docs/screenshots/stage-07/`: 01 work on your own; 02 and 04 work with your empire (without
and with a seat); 03 the league in divisions; 05 the weekend challenge, open; 06 work in hand;
07 the syllabus map and coverage tracker; 08 the gate at Level 20; 09 a rank case in hand;
10 the case passed; 11 the career above Level 20; 12 the desk; 13 and 14 the trading form for
shares and for bonds; 15 a resignation letter; 16 the head's "needs you now"; 17 the
counter-offer; 18 the offer to stay; 19 voting for a CEO; 20 voted in; 21 the Rank page of a
new player; 22 the Rank page on a phone.

## Run it

Your world is kept. The new tables are added when the server starts.

```powershell
cd $HOME\wall-street-beyond-the-market
git pull
docker compose up --build
```

Then open http://localhost:5173. The new pages are **Rank** in the menu on the left, the three
buttons on the **Work** page, and the **War Room** (the trading form, "Leaving the empire",
"Who leads", and the league).
