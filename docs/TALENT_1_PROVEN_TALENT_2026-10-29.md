# The talent and funds stage, Part 1: Proven Talent

The owner said "build" on 29 October 2026 to the plan in `notes/talent-and-funds-plan.md`, with the answers in
`notes/talent-and-funds-decisions.md`. Two follow-up questions went unanswered, so the suggested answers were used:
- tax evasion is the only crime against the game that is allowed (Part 9);
- the four extras (mobile money, startup funding rounds, digital coins, crisis replay) stay on the "maybe later" list.

This report covers Part 1: a verified record of what each player has really done, badges, a page the player can share,
firms' challenges, the talent board, invitations, firm accounts, and the checks that keep the record honest.

While Part 1 was being built, the owner asked for two changes to the screen, and both are in:
- **Top bar.** It is one tidy row again.
- **Sidebar.** It is down to seven sections: My desk, Work, Empire, Markets, Money, News and Economy. Each section's pages are tabs along the top of the page.

The owner also set a standing rule: a new feature never gets its own sidebar item. Proven Talent lives in the menu under
the player's picture.

Part 1 had ten loophole tests and an independent review. The review found 13 problems. Every one was fixed and tested.
Two smaller problems turned up along the way and were fixed too:
- **Options and futures.** A contract whose quarter had ended was force-closed at a bell before the close, which stopped the ten-year run.
- **A blank pill.** A style from the crises stage had blanked the Money Watch's reading.

Nothing on Part 1's list was dropped or put off.

Tests at the end: 1,363 server tests in 82 files pass on both runners (each file run once, split between them), with cargo test (13) and vitest (23).

## Things worth knowing, said plainly

1. **The record cannot be faked, edited or bought.** After every closing bell the game works each player's record out
   afresh from its own books: the ledger, the closing prices and its own registers. Nobody can type any of it in,
   including the player and the administrator. Only percentages and counts are shown, never how much money anybody has.
2. **What the record shows.**
   - **Investing.**
     - What it measures: the return with money from outside taken out (salary, fees, gifts, a fund manager's own fee, money moved in from an empire), compared with the market index.
     - The figures shown: a year at this pace, how much it swung, the return for each unit of risk, the worst fall from a high, and quarters beating the market, with a chart.
     - Money brought in just before the bell barely counts in that day's sums, so it cannot water down a losing day.
   - **Work and levels:** levels reached, and work passed and failed.
   - **Calls put in writing:** calls made for an empire, and how many turned out right.
   - **Audits:** people rightly named, people wrongly named, and wrongdoing missed that was proved later.
   - **Journalism:** stories, scoops, leads that held up, leads proved false, and corrections.
   - **Leadership:** decisions as an empire's head that turned out well or badly.
   - **Bank crises:** crises lived through, money pulled out in time, savings lost, and rescues won.
   - **Firm challenges:** challenges entered, wins and places.
   - **Conduct:** what was proved and when, never the sums.
3. **Badges** are earned from the record, never bought.
   - Some are kept for good: beating the market four quarters running, steady hand, a level reached, a challenge won.
   - Three rest on staying clean and can be lost again: clean record, clean audits, stories that held up.
   - A badge shows only where the part of the record it comes from is shown.
4. **Sharing.** The record is private until the player shares it.
   - A shared record has its own unguessable address, opens without logging in, and can be printed or saved as a PDF.
   - The player chooses which parts are shown. Conduct is always shown and cannot be hidden.
   - "Make a new address" kills the old one at once.
   - The link works for people outside only once the game is hosted online. The owner accepted this.
5. **Firms.**
   - Signing up:
     - A firm signs up on its own page (`#/firms`), with its own login that can never be used as a player's.
     - It proves its email address with a code.
     - An administrator then approves it (`python -m simulation.talent_admin approve "Firm name"`).
   - A firm has no powers in the world: it cannot trade, own, vote or message players there.
6. **Challenges.** Five kinds. The first four are sealed: nothing an entrant does in them touches the live world.
   - **Paper portfolio:**
     - Everyone starts with the same paper cash and deals while the market is open, at the average price paid across the day so far.
     - It can never buy more in a day than the real market could have supplied.
     - It is valued at each day's average price, never the last trade, which one small real trade could move.
   - **Value a company:** scored against the game's own valuation from the accounts filed at the quarter's end, so the answer cannot be copied from figures already out.
   - **Find the weakest bank:** scored on savers' trust in the bank chosen when the challenge ends. A tie goes to whoever answered first.
   - **Forecast a profit:** scored against the profit the company files.
   - **Real record:** the entrants' real investing record over the challenge's weeks. Entrants must join before it starts.
   - Ending and visibility:
     - A challenge waiting for figures that never come is closed after two weeks with nobody placed.
     - The firm sees only the best finishers who agreed to be seen. Everyone else appears as "a player who chose not to be seen".
7. **The talent board and invitations.**
   - Who appears: only players who chose to be on the board, with at least two game quarters of record, and not held back by the honesty checks.
   - What a firm sees: only the parts each player chose to show.
   - Invitations:
     - A firm can invite a player once at a time, at most 30 a day, and not again within 30 days of a refusal.
     - A player's contact details reach the firm only if they accept and type them in.
     - A player can block a firm for good.
8. **Keeping it honest (never shown to players).**
   - **Deals at odd prices between accounts run by players** (their own, their empires' and the funds they manage):
     - shares 5% or more from what the market paid that day;
     - options and futures 20% or more from the dealers' own price;
     - buildings sold privately 20% or more from their value.

     The value handed over is taken out of the receiver's record as a gift. This includes an empire selling cheaply to its own head.
   - **Linked players:** players who deal like that again and again, or at all from one device, are linked. They are kept off the board and out of challenge places until an administrator looks (`python -m simulation.talent_admin flags`, `clear`). A cleared pair can be linked again by what they do afterwards.
   - **One device:** two entrants from the same device in one challenge are scored but not placed. A device is recognised by a keyed fingerprint, never the address itself, and kept for two days.
   - **Not wrong on their own:** sharing a device (families do), or meeting on the open order book at the market's price.

## The checklist (Part 1)

| # | Item | Built | Where tested |
| --- | --- | --- | --- |
| 1 | Verified record from the books (investing, deals and calls, audits, risk warnings, journalism, law, leadership, crisis conduct, conduct) | Yes; law shows as conduct until the courts stage, and calls hold the risk warnings and deals | `test_talent.py` (investing, outside money, quarters), `test_talent_review.py` r3, r5, r6, r11 |
| 2 | Skill badges, never bought, no exam bodies' names | Yes | `test_a_fall_and_quarters_...earn_badges`, r12 |
| 3 | Profile page and share link, private by default, print or PDF | Yes | `test_a_shared_record_shows_only_what_the_player_chose...`, L8 |
| 4 | Firm challenges: themed, start and end, scoreboard, sealed by default, live for the "real record" kind, no advantage in the world | Yes | `test_a_paper_portfolio_challenge_...`, `test_valuation_forecast_and_weakest_bank_...`, L3 to L7, r7 |
| 5 | Talent board: opt-in, filters, invitations, contact only if shared | Yes | `test_firms_see_only_the_board...`, L7, L10, r2 |
| 6 | Firm accounts: separate login, no player powers, approved by an administrator | Yes; email proved first | `test_the_website_for_players_the_public_and_firms`, L9, r13 |
| 7 | Anti-cheat: odd deals taken out, minimum record length, worked out from the books, several accounts flagged | Yes | L1, L2, L5, r4, r9, `test_players_from_one_device_...` |

## Ten loophole questions (`tests/test_talent_loopholes.py`)

1. An empire selling shares cheaply to its own head: a gift, not a return.
2. Shares given from outside: not a return.
3. One small real trade at the end lifting a paper portfolio: it doesn't, because the day's average price is used.
4. Paper money buying more than the market could supply, even a piece at a time: refused.
5. Several entries from one device: scored but not placed.
6. Copying a valuation from figures already out: scored only on the next quarter's valuation.
7. A firm reading names off a scoreboard, or a record after the player left the board: refused.
8. Typing figures into a request, or changing the stored record: refused, and put right the next time the record is worked out. Conduct always shows.
9. A firm trading or voting, or carrying on after being suspended: refused. A suspended firm is logged out and its challenges called off.
10. A firm pestering a player: one invitation at a time, a 30-day wait after a refusal, a daily limit, and blocking.

## The independent review (`tests/test_talent_review.py`)

1. Conduct showed the sums, fines and debts behind a proved wrong. Now it shows only what was proved and when.
2. The board and the badges showed figures from parts of the record a player had hidden. Now only the parts shown are used, for the figures, the badges and the board's filters.
3. A fund manager's fee counted as investing return. It is now pay for work. A fee a player pays, as an investor in a fund, still counts against their return.
4. A building, an option or a future could be sold between players far from its value without being noticed. Now these are checked like share trades.
5. Money brought in just before the bell watered down a losing day. Now each day counts money only for the part of the day it was there.
6. A forced buy-in after a short squeeze vanished from the record as "money taken out". It is now a loss. Shares from a new issue and bonds bought from the Treasury also count as investing.
7. Paper deals could be made at a last price that one trade had moved, and a challenge could end before its last day was priced. Now deals are at the day's average so far, and portfolios are valued on the trading day that ends with or after the challenge.
8. Requests were not all-or-nothing: two at once could get round the paper buying limit, answer an invitation twice, or score a challenge twice. Now every request and every scoring is saved whole or not at all, and two at once take turns.
9. Innocent players could be linked just for sharing a network and meeting on the order book. And a pair once cleared could never be linked again. Now one device needs odd-price dealing too, a cleared pair can be linked again by new dealing, and device marks are deleted after two days.
10. One record that could not be worked out could stop the rest, and the auctions. Paper portfolios were re-marked on every turn of the server's loop. Now each record is worked out on its own, a fault never holds up the auctions, and each portfolio is marked once a day.
11. "Beat the market 4 quarters running" could be earned with gaps in between. A quarter sat out now breaks the run.
12. The crisis badge went to a player who lost savings, ties on the weakest bank went to whoever joined first, and a challenge waiting on figures that never came stayed open for ever. All three fixed.
13. A firm's email address was never proved. Now it is proved with a code before an administrator can approve the firm.

## The ten-year run

Forty quarters (ten game years), with ten computer players doing every kind of work, a firm (Lagoon Capital) setting
challenges every year, and the players joining and dealing in them. The bank shocks of the crises stage were staged in
year 5 and year 8 as before.

| What | After ten years |
|---|---|
| Records | 272 counted trading days each. Returns +6% to +194%, against an index up about 177%. Worst falls 1% to 23%. Return for each unit of risk 0.15 to 1.55 |
| Badges | every player earned "steady hand", "beat the market 4 quarters running", "came through a bank crisis" and "clean record"; four grew their money by half; one empire head earned "trusted head" |
| Challenges | 30 run and scored (paper, real record, weakest bank), 100 places each kind; the firm's limit of three at a time kept its valuation and forecast challenges from starting (they are tested on their own) |
| Honesty checks | 12 odd-price share deals between the computer players flagged and taken out of their records; nobody linked |
| Working out the records | 0.34 seconds after each bell on average, 1.9 at most, for ten players |
| Crises | the two staged bank crises ran their course as before; both banks sold to sound banks; no saver lost money |
| Books | audit clean every quarter; the same two "outside its normal business" entries from the staged shocks as before |

The run first stopped in year 2 on an old fault in the options and futures: when a quarter had ended but not yet closed,
the nightly margin check tried to force-close a contract that had already reached its end. Such contracts are now left to
be settled at the quarter's close.

## Honest limits

- **Large numbers of players.** The records are worked out afresh for every player after every bell. That is about 0.03 seconds a player: fine for hundreds or a few thousand, but it will need to be made incremental for tens of thousands.
- **Shares nobody else trades.** If two colluding players are the only traders of a share for days, its reference price follows theirs. Computer investors trade nearly every share every day, so this is rare.
- **Devices** are recognised by the address and browser the server sees. Behind a shared network, two strangers can look like one device. That alone never holds anybody back.
- **The weakest-bank challenge** can be nudged a little by entrants pulling their own savings out of the bank they chose, which is lawful.
- **Paper deals** at the day's average so far can gain slightly from a late-day trend.
- **The courts stage.** "Law: cases won and lost" will appear when that stage is built. Until then, proved wrongdoing shows under Conduct.
- **The share link** works for people outside only once the game is hosted online.
- **An older test** (`test_redesign_loopholes.py`, question 3) used today's date and had stopped working; it now uses a fixed date.

## Screenshots

`docs/screenshots/talent-1/`. The accessibility check found one thing: the firms' page had no main heading. It now has one, and the check is clean.
- your record (01);
- firms' challenges for players (02);
- an invitation from a firm (03);
- sharing and the talent board (04);
- a shared record anyone can open (05);
- a firm signing up and confirming its email (06, 07);
- the talent board for firms (08);
- setting a challenge (09);
- the finishers who agreed to be seen (10);
- a firm reading a record (11);
- the phone (12 to 14);
- the light theme (15, 16).
