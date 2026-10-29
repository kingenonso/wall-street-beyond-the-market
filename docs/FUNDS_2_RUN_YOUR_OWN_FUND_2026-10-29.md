# The talent and funds stage, Part 2: Run Your Own Fund

The owner said "build" on 29 October 2026 for Part 2, the next step in the order in `notes/proposal-global-markets-2026-10-29.md`.
This report covers open investment funds:
- An Asset Manager of Level 20 launches a fund and runs it, and anybody can put money into it.
- The computer runs four funds of its own from the start, so every player's fund has rivals to be measured against.

Part 2 had ten loophole tests and an independent review. The review found 13 problems. Every one was fixed and tested.
Two more problems turned up in the ten-year run and were fixed:
- **The computer's bond fund earned almost nothing.** It could not find enough Government bills to buy, so it held mostly cash. It now buys them from the Treasury, as a player can.
- **Fund records showed no benchmark** for a fund that had closed.

Nothing on Part 2's list was dropped or put off. Following the owner's standing rule, nothing new was added to the sidebar:
- **The funds** are a tab inside Markets.
- **A fund's news** comes as a pop-up.
- **A manager's track record** is a section in Proven Talent.

Tests at the end: 1,406 server tests in 85 files pass on both runners (each file run once, split between them; the three files fixed at the end were run again in full), with cargo test (13) and vitest (23). Two older tests needed updating for this part (the news count and the list of things that count in net worth), and one older test now allows households moving their savings between banks, which happens only when trust in a bank moves.

## Things worth knowing, said plainly

1. **What a fund is.**
   - A fund pools many people's money, and a manager invests it.
   - Investors buy **units**. A unit is worth the fund's value divided by the number of units.
   - The first unit costs ₦1.
2. **You never know the exact price you deal at.**
   - Money in and money out is dealt at the next closing bell's price.
   - An order placed after the market closes (22:00 Lagos) waits for the bell after that.
   - So nobody can buy into a rise they have already seen.
   - Once the market has closed, an order waiting for that night's bell can no longer be taken back.
3. **Coming in and leaving cost a little, and that money stays in the fund.**
   - Coming in costs 0.25% above the price, and leaving gets 0.25% below it.
   - Those who stay therefore do not pay for those who come and go.
   - Coming straight in and out again always loses money.
4. **Who can launch a fund.**
   - An Asset Manager of Level 20 or above, and only one fund at a time.
   - Registration is ₦2 million (to the prize pool), plus at least ₦5 million of the manager's own money.
   - While running the fund, the manager keeps at least 1% of it, or everything they put in.
5. **Fees.**
   - A yearly fee of at most 2%, taken a little each day.
   - A performance fee of at most 20% of gains above the fund's best price so far (its "high-water mark"), taken as the quarter closes.
   - Fees can be lowered later, never raised.
6. **The rules every fund keeps.** The game checks these on every order.
   - **One holding:** at most 10% of the fund in any one company. Orders still waiting count too, so several small orders cannot add up past the limit.
   - **Cash:** at least 5% of the fund.
   - **Strategy:**
     - a shares fund holds no bonds;
     - a banks fund keeps 80% of what it holds in banks;
     - a bonds fund holds no shares;
     - a balanced fund holds at most 70% in either shares or bonds.
   - **Price:** the fund deals within 2% of the market price.
   - **No buying while investors wait:** a fund buys nothing while investors are waiting to be paid.
7. **When many investors leave at once.**
   - A fund may borrow at most a tenth of itself, only to pay leavers, and repays the loan as cash comes in.
   - It sells bonds at once and offers its biggest shareholdings on the exchange.
   - The manager may put up a **gate**: leavers are paid at most a tenth of the fund at each bell, for at most a game quarter. Everybody is told.
   - A gate cannot go straight back up once it comes down.
8. **Runs.**
   - The computer's own investors (the households) ask for their money back, bell after bell, in two cases: the fund falls 15% from its recent high, or the banks panic.
   - In the ten-year run the banks fund had 11 runs during the two staged bank crises, and shrank from ₦8 billion to almost nothing.
9. **Stars.**
   - Each quarter every fund gets one to five stars, for its return over the last year against the risk it took.
   - The comparison is with funds of the same kind. With fewer than five of those, it is with the fund's benchmark:
     - the BSX 50 for share funds;
     - the Central Bank's rate for bond funds;
     - a 60/40 mix of the two for balanced funds.
   - The households' money follows the stars: five-star funds draw money each quarter, and one-star funds lose it.
10. **What a fund holds is published one quarter late.** Nobody sees what a fund holds now. Nobody sees who else holds a fund, or how much.
11. **Closing and merging.**
    - **Closing:** everything is sold to the market's dealers and the money is shared out among the holders.
      - Shares in a company whose trading is stopped are not sold at their old price; the fund waits.
      - Nobody is paid until everything is sold, so everybody gets the same.
    - **Merging:** the other fund's manager must agree. Investors get three days to leave, and their units become units of the other fund worth the same.
      - Funds merge only with a fund of the same kind, or one that may hold anything.
    - **Too small:** a fund that stays under ₦50 million for two quarters (after its first two) is closed by the rules.
12. **The shadow side (a crime against other players, so it is allowed).**
    - A manager can sign for a cost that is not real and take the money: at most 1% of the fund a quarter.
    - The regulator audits the books every quarter, and again when a fund closes or merges, so closing is no escape.
    - If it is proved, the manager:
      - repays the money with a fine of half as much again;
      - is struck off and can never run a fund again;
      - and the regulator winds the fund down, charging no fee.
    - In the ten-year run, the manager who did this was caught in the first year.
13. **A manager cannot trade against their own fund.**
    - The fund never deals with the manager or the manager's empire.
    - The manager and their empire cannot sell into the fund's waiting orders, or buy from them.
    - A manager who buys a share for themselves just before their fund buys it is flagged in secret by the Money Watch.
14. **Where it shows.**
    - **Net worth and Portfolio:** units count in the player's net worth and in their Portfolio.
    - **Proven Talent:**
      - A new "Funds managed" section shows each fund the player has run: its return against its benchmark, its stars, and whether it came through a run.
      - Three new badges can be earned there: Five-star fund, Kept a fund through a run, and Fund ahead of its benchmark.
      - Proved theft from a fund appears under Conduct.

## Honest limits

- A manager sees how much money is waiting to come in or go out at the next bell, as real fund managers do. They could trade for themselves ahead of a forced sale. If they do, the Money Watch flags it in secret, but nothing stops it.
- The computer's funds buy and sell their mix directly with the pension funds (the market's dealers) at the last price, not through the exchange. They hold the largest companies in proportion to their size, with no company above 9.5%.
- Players' funds launched with only their manager's money (₦40 million in the ten-year run) were closed for being too small once the rules allowed, after about two years. A new manager has to attract outside money to keep going.

## The ten-year run (40 quarters, with the earlier stages running)

| Fund | Kind | Unit price after 10 years | Size at the end | Stars (lowest to highest) |
|---|---|---|---|---|
| Broad Street Equity Fund | shares | ₦3.53 | ₦90 billion | 2 to 5 |
| Harmattan Balanced Fund | balanced | ₦3.15 | ₦35 billion | 1 to 5 |
| Niger Delta Bond Fund | bonds | ₦2.57 | ₦14 billion | 2 to 3 |
| Lagoon Banks Fund | banks | ₦1.45 | almost nothing (runs in both bank crises) | 1 to 5 |
| Harbour Growth Fund (a player's) | shares | ₦1.22 when closed | closed as too small | 1 |
| Marina Balanced Fund (a player's) | balanced | closed | manager struck off for a false cost | — |

The rest of the run:
- **Orders:** 323 payments in and 203 withdrawals were dealt.
- **Loans:** 7 short loans were taken to pay leavers.
- **Alerts:** 44 star changes, 157 published holdings, and 11 runs.
- **Speed:** the funds' work at each bell took 0.8 seconds on average (2.2 at most).
- **Checks:** the books audit was clean, and the fund registers always added up. The two odd company results are the two staged shocks, as in earlier runs.

## Screenshots (docs/screenshots/funds-2/)

1. A fund's news pops up for its holders and followers
2. The Funds tab in Markets, best-rated first in each kind
3. A fund's factsheet: its price against its benchmark, stars, what it held, its rules
4. The manager's desk
5. Launching a fund
6. An investor's view of a player's fund
7. Proven Talent: funds managed
8. Funds in the Portfolio
9. and 10. On a phone: the funds and a factsheet
11. and 12. Light theme: the funds and the manager's desk

The accessibility check (axe) found nothing on any of them.
