# The ten-year run and the merge, 14 November 2026

Everything built since Stage 12 is now on `main`: the three builds, the insurance and commodities fix, the trim to 106
kinds of work, Competition (Parts 1 and 2), and Government (Parts 1 and 2). All 108 test files pass on the code that was
merged. Then a test world was run for ten game years.

## How to update your copy

```powershell
cd $HOME\wall-street-beyond-the-market
git pull
docker compose up --build
```

The server applies the new database changes (migrations 045 to 053) by itself when it starts. Then open
http://localhost:5173.

## The ten-year run

A fresh test world, closed forty quarters by the game's own rules, with three shocks staged:

| Quarter | Shock |
| --- | --- |
| 17 | A run on Harmattan Bank (trust 35 of 100) |
| 24 | Oil from 102 to 153 dollars a barrel |
| 29 | A run on Ikenga Bank (trust 30 of 100) |

**The books passed at every one of the forty closes**: the ledger re-adds to zero, every balance matches its entries,
and no account is overdrawn. The whole run took 10.7 minutes.

| | When the world began | After ten years |
| --- | --- | --- |
| Price index | 100 | 183.7 (about 6.3% a year) |
| Naira to the dollar | 1,500 | 1,927 |
| Oil, dollars a barrel | 75 | 99 |
| Central Bank rate | 13.0% | 13.0% (between 11.5% and 14.0% all the way) |
| Companies trading | 114 | 110 (4 wound up) |
| Banks closed | | none |
| Crises recorded | | 2, both banking crises, at the two staged runs |

The oil shock came through the economy as it should: prices rose twice as fast that quarter (yearly inflation 4.0% to
8.0%), the Central Bank answered with a higher rate the year after (14.0% in quarter 28), and oil drifted back to its usual
level over four quarters (153, 144, 139, 119, 112, 108).

## Found by the run, and fixed

**The oil shock had never been staged.** The run's own program changed a quarter's oil price before that quarter's price
existed, so the shock was skipped without a word, in this run and in earlier ones. It now puts the shock on the price the
quarter starts from, and says so plainly if it ever cannot stage a shock.

## Found by the tests, and fixed (before the merge)

- **Swaps inside an empire could never be approved.** The draft step had gone from the Lawyer to the same banker who
  proposed the swap, and nobody decides their own request. The banker now drafts as they propose.
- **An Asset Manager could audit the books again and again in one quarter.** The once-a-quarter rule still named the
  Accountant. It holds again (migration 053), for every audit from now on.
- **The head took one of their own build's two seats**, so an empire headed by an Asset Manager had room for only one more.
  The head now has a chair of their own: seven places, as you settled (migration 052).
- **The newsroom, investigations and sources were still locked to the old journalist build.** They are open to every
  build, as you settled. The empire's press office is the head or its Investment Banker, which is how the newsroom's
  questions to an empire already worked.
- **One leadership task was refused for nothing**: when its three companies earned too alike, it gave up. It now tries the
  next three.
- Smaller: the money table's "Other" line (the commodity market's cash), "0 of 12 seats" in the league (it is 7), the
  desk's money list showing raw codes, and "Legal Counsel" in messages.

## For you to decide

**Taxes only fall when nobody is elected.** With no players standing, the stand-in governed all ten years. It is drawn by
lot each year, and this run drew only "steady" (keeps every rate) and "dove" (cuts every rate a step when the Treasury
grew over the year). The Treasury spends its taxes back into the economy, so it grows a little most years, and the dove
cut every time it came up: income tax from 12% to 8%, company tax from 30% to 26%. A "hawk" (raises rates when the
Treasury runs down) was never drawn.

Three ways to go:

1. **Leave it.** It is chance, and a hawk will come up in other worlds. Players who stand for election can change it.
2. **A dove cuts only when the Treasury grew by a real amount** (say, more than a tenth over the year), and **a hawk
   raises when it fell at all.** Taxes would then move both ways on their own.
3. **The stand-in pulls rates back towards where they started** after it has moved them a long way.

## Not changed, and worth knowing

- The trim to 106 kinds of work retired three of the six industry pieces (retail, film and medicines). Those industries
  have no work of their own now. Say if you want any back.
- Competition's forecasts and mandates, and the Government's elections, levies and lobbying, need players. In a world of
  computers only, every mandate lapses and the stand-in governs, as here.
