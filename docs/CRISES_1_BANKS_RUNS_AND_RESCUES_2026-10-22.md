# The crises stage, Part 1: money at named banks, trust, bank runs and rescues

The owner said "ok build" on 22 October 2026 to the list in `notes/crises-stage-plan.md`. The list's five questions were
not answered, so the suggested answers were used:
- the stage is built in two parts;
- the deposit guarantee is ₦5 million per saver per bank;
- Black Swans come about once every two game years (they are in Part 2);
- the Government's crisis response is run by the computer until the Government stage;
- pulling your own money out of a bank is lawful even if it starts a run, while spreading a false story to start one is
  kept for the courts.

This report covers Part 1: the groundwork, how a crisis grows, bank runs and failures, who responds, Crisis Reports,
banking and confidence crises, and the Crisis Watch.

Part 1 had ten loophole tests and an independent review. The review found six serious problems, six smaller ones and some
minor points. Every one was fixed and tested, apart from the few minor points listed at the end of the review section.
Nothing on Part 1's list was dropped or put off.

Tests at the end: __TESTS__.

## Things worth knowing, said plainly

1. **Money kept at real, named banks.** A bank's savers used to be one fixed number in its accounts. Now every naira kept
   as savings is a claim on that bank, written in the ledger. What the bank owes its savers is exactly what its savers hold.
   - **Households** keep the savings the banks already held for them, city by city.
   - **Companies** keep half of their cash above what they like to hold as savings, spread over the trusted banks.
   - **Players and empires** can put money into savings at any of the six banks and take it out again. Only the head moves
     an empire's money, and no more in a quarter than they may sign for.
   - **Interest.** Savings pay more than cash in hand, on the least kept through the whole quarter. Putting money in for a
     moment before pay day earns nothing.
   - **What counts as yours.** Savings count in what a player or empire is worth. They count as cash for a loan. When a debt
     must be paid by force, they are taken before anything is sold.
2. **The guarantee.** The Deposit Guarantee Fund makes sure the first ₦5 million each saver has at each bank is safe. The
   banks pay it a small premium every quarter. When the fund needs more, it borrows from the Treasury, and the loan is on
   the record.
3. **Trust.** Every game day each bank's trust (0 to 100) moves part of the way towards where its public signals put it.
   - **The signals:**
     - its owners' funds against its loans;
     - loans gone bad;
     - its cash against its savers' money;
     - its credit rating;
     - savers leaving over the last three days;
     - what the papers have said in the last five days (an unconfirmed report of trouble costs more than a confirmed story);
     - its share price;
     - trouble at other banks (more if they are in the same city);
     - the Government's guarantee;
     - emergency help, which counts against it when borrowed and for it when new money comes in.
   - **The levels:**
     - below 45 the biggest savers (above the guarantee) start to leave;
     - below 35 it is a run;
     - below 20 it is panic.
   - **Where the money goes.** Seven-tenths of what frightened savers draw out goes the same day to the banks people trust
     most. The rest is kept at home and comes back as calm returns.
4. **Who fights back:**
   - **The Central Bank** lends to a bank in a run, at three points above its rate. It lends only against its loans (up to
     three-fifths of them), and only while the bank is sound. In a crisis past its tipping point, it leans a point lower
     when it sets its rate.
   - **The Securities Regulator** stops new short sales in a bank's shares while its savers queue.
   - **The bank's own owners.** A bank in a run for three days raises new money: its big owners buy new shares at a discount.
   - **The Government** (computer-run for now) promises that every saving is safe, whatever its size, when two banks run at
     once or trust in the banks taken together falls to 35. It lifts the promise at a close once trust is back above 60.
5. **When a bank cannot pay**, or its losses have eaten its owners' funds, the Central Bank closes it:
   - **The hole.** Savers above the guarantee bear their share of the hole (unless every saving is guaranteed). The
     Deposit Guarantee Fund fills the rest. That money goes straight into the bank's own funds: it is not profit, so it pays
     no tax and no dividend.
   - **While it is closed**, savings there are frozen and its shares cannot be traded, borrowed, shorted or used as security.
   - **The Auction House sells it** to whoever puts in the most new money, paid into the bank itself. The winner owns 95%
     of it. The old owners keep 5%, or more if the bank still had owners' funds of its own. Sound banks bid, and players
     and empires may too.
   - **If nobody bids**, it is taken into public hands (the fund puts in the money) and sold again a year later.
   - **When it reopens**, it is judged on where it stands now, with the new money, and its savers give it fifteen game days.
6. **Every crisis has a record**, from its first warning sign to its place in history:
   - It follows the design's ten steps, shown as the owner's five phases: Warning, Trigger, Spread, Crisis, Recovery.
   - Most warnings fade. A crisis that runs its course ends with a permanent **Crisis Report**: what made it possible (its
     hidden weakness, kept back until it ends), what stopped it, who was hit, who came through, and a lesson.
   - "Why?" follows the causes through the Ripple.
7. **The Crisis Watch** is read at every close. It has eleven signs, each green, amber or red with its figure and the reason:
   - company debt;
   - household debt;
   - the lowest bank cash;
   - bad loans;
   - lending in one place;
   - jobs;
   - prices;
   - house prices against incomes;
   - shortages;
   - Government debt;
   - confidence in the banks.

   A sign turning red is news. It changes nothing by itself.
8. **Spreading a false story to start a run** is recorded. The bad stories printed in the five days before a run, and who
   planted any rumour they carried, are kept for the courts (Stage 11). They are never shown to players. Pulling your own
   money out is lawful.
9. **The admin crisis test.** `python -m simulation.crisis_test KCB --loss 12 --days 20` gives a bank a shock in a sealed
   copy of the world and prints what happens day by day. Then it throws the copy away: nothing is kept.
10. **Screens.**
    - A new "Banks & crises" section with four tabs:
      - **The banks:** trust, what moves it, the last days, and banks at the Auction House.
      - **Your savings:** put in, take out, take it all out, for yourself or the empire.
      - **Crisis Watch.**
      - **Crises on the record:** phases, report and "Why?".
    - Elsewhere:
      - a Crisis Watch panel on the Economy page;
      - a desk card when a bank holding your savings has savers leaving;
      - a count on the menu;
      - twelve new kinds of news, each in three papers' voices.
11. **Honest limits.**
    - **Banks rarely get into trouble on their own.** Healthy banks stay calm. In the ten-year run, the only crises that
      went beyond a warning came from two shocks staged on purpose (as the admin test does). Shocks that arrive on their own
      (Black Swans, a housing crash, the outside world) are Part 2.
    - **The staged shocks left two "outside its normal business" entries.** They wrote the loss into the bank's filed
      accounts only, so at the next close the bank's real loan book "came back" and showed as other sales. This is an
      artefact of staging, not of the crisis rules.
    - **Companies' savings and interest.** Companies draw their savings back into cash as they close each quarter and put
      them back after, so a bank's filed accounts always include them. Interest on a company's savings is paid as it closes.
    - **Household cash.** Money households keep at home after a run is still their cash, and some of it is spent.
    - **The Government's response** is a rule-based stand-in until the Government stage.

## The checklist (Part 1)

| # | Item | Built | Where tested |
| --- | --- | --- | --- |
| 1 | Money kept at real, named banks (households, companies, players, empires) | Yes | `test_every_banks_savers_are_written_into_the_ledger_and_add_up`, `test_a_player_saves_...` |
| 2 | Trust for each bank and for the banks together | Yes | `test_a_weak_bank_loses_trust_...`, `test_trust_is_made_only_of_public_signals_...` |
| 3 | Crisis Watch | Yes | `test_the_crisis_watch_reads_every_sign_at_the_close_...` |
| 4 | Ten steps, five phases | Yes | the run and stopping tests |
| 5 | Most warnings fade | Yes | `test_most_warnings_fade_...` |
| 6 | Permanent Crisis Report | Yes | `test_most_warnings_fade_and_an_ended_crisis_leaves_a_permanent_report` |
| C | Banking and confidence crises (the other six types are Part 2) | Yes | the run tests |
| 15 to 18 | Bank runs, contagion, stopping a run, failures, the guarantee fund, insurers' failures (the same rules apply to any bank) | Yes | `test_a_bank_whose_losses_ate_...`, `test_with_no_buyer_...` |
| 21 to 24 | Central Bank, Regulator, Government response, crisis test in a copy | Yes | `test_the_government_guarantees_...`, `test_the_crisis_test_runs_in_a_sealed_copy_...` |
| J | Screens for Part 1 | Yes | screenshots below |
| K | Stage test: a run spreads to a second bank and is stopped, with no naira created or lost | Yes | `test_a_weak_bank_loses_trust_its_savers_run_the_central_bank_lends_and_the_run_spreads_and_is_stopped` |

The design's own test for this ("a test housing crisis spreads and can be stopped") needs the housing crisis, which is in
Part 2.

## Ten loophole questions (`tests/test_crises_loopholes.py`)

1. Saving for a moment before the close to earn interest: it earns nothing.
2. Writing a bank's savers into the ledger again to make savings from nothing: the database refuses.
3. A member moving the empire's money, or a head moving more than they may sign for (even a piece at a time): refused.
4. A closed bank: no savings in or out, no trading, no cheap bid, no bid by itself, no partner.
5. Hiding money from a margin call in savings: savings count as security, and are taken first.
6. Selling a bank short in a run: the Regulator stops it.
7. A planted rumour before a run is kept for the courts; pulling your own money out is lawful.
8. The first ₦5 million is never written down; under the full guarantee, nothing is.
9. Working through a game day twice changes nothing.
10. Nothing private reaches the website: others' savings, an open crisis's weakness, auction reserves and others' limits,
    the stories kept for the courts. No route runs the crisis test.

## The independent review (`tests/test_crises_review.py`)

1. A bank with both ordinary and emergency Central Bank loans could stop every quarter's close (the books failed their
   check). The two are now kept apart, and the dearer emergency lending is repaid first.
2. A rescued bank was judged on its old accounts and could be closed again, its savers bearing the same hole twice. Now
   what has filled the hole or brought new money counts at once, and a reopened bank has fifteen days' grace.
3. What filled a closed bank's hole was counted as profit, taxed and paid out. It now goes straight to its owners' funds,
   and public-hands money buys shares.
4. A closed bank's shares could still be shorted, borrowed against or sold by force at the old price. Not any more.
5. A closure set off by a player's withdrawal was undone with the refusal. It now stands.
6. Companies drawing their savings at each close looked like savers leaving. Not counted any more, and companies' savings
   are spread over the trusted banks.
7. An empire's savings were out of its creditors' reach, and a wound-up company's were stranded. Now they are drawn first.
8. A bank still solvent but out of cash could be bought for its reserve. The old owners now keep a share in proportion to
   the funds that were already there.
9. A bank closed at a close was booked in the quarter already filed. It is now booked in the next one.
10. A bank auction that could not settle left the bank frozen for ever. It now goes into public hands.
11. Savings could move between a quarter's end and its close. Not any more.
12. Withdrawals during the daily run could clash. The run now takes the bank's lock.

Minor points fixed:
- interest and premium are no longer paid by a closed bank;
- "take it all out" is allowed, to the last kobo;
- the resale's opening price no longer gives its lowest price away;
- the empire's limits on bank auctions are matched by auction, not by position.

## The ten-year run

Forty quarters (ten game years) with computer players doing every kind of work. They saved at the banks and took their
money out when a bank looked shaky. Two shocks were staged on purpose, as the admin crisis test does: in year 5 Kainji
Commercial Bank found losses that left its owners' funds at 3% of its loans, and in year 8 Zuma Capital Bank, 1.5%.

| What | After ten years |
|---|---|
| Sound banks | stayed calm: lowest trust 59 to 69; the small microfinance bank 43 at worst |
| Crises on the record | 6: four warnings that faded (three at the microfinance bank), two that ran their course |
| Year 5 (KCB) | warning, then queues, then panic; the Central Bank lent ₦88.6bn in all; its owners put in ₦3.6bn; closed on day 9, bought by a sound bank for ₦66.3bn of new money (the old owners kept 37%: the bank still had funds of its own); recovery, then history in the next quarter |
| Year 8 (ZCB) | the same path: closed on day 6, rescued for ₦64.7bn; a short warning after it faded |
| Savers' losses | none: both banks were out of cash, not out of funds, so nobody above the guarantee lost money |
| The Government's full guarantee | never needed: one bank ran at a time |
| Deposit Guarantee Fund | ₦110bn of premiums built up (it was never needed), no loans outstanding |
| Savings interest | ₦63.4bn paid in 3,888 payments (mostly to companies) |
| Crisis Watch | never red; amber at times for house prices (14 quarters), shortages (10) and prices (2) |
| Inflation | 3.5% to 9.2%, the Central Bank's rate 11.5% to 14% (as before the stage) |
| Books | audit clean every quarter, the crisis checks clean; two "outside its normal business" entries, from the staged shocks (see Honest limits) |


## Screenshots

`docs/screenshots/crises-1/`:
- trust in the banks during a run, with one bank closed and the Government's guarantee (01);
- the closed bank at the Auction House (02);
- your savings (03);
- the Crisis Watch (04);
- a crisis's phases on the record (05);
- the desk warning that your savings are at risk (06);
- the Crisis Watch on the Economy page (07);
- the phone (08 to 10);
- the light theme (11, 12).

The accessibility check found one thing (a label on the Watch's dots), now fixed.
