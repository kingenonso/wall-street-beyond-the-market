# Insurance and commodities: what was wrong, and what was fixed

Written 14 November 2026, on the branch `builds-three` (the three-builds merge).

## Insurance

The insurance brought in from the Windows copy could not run. These were the faults:

| Fault | What it did |
|---|---|
| Its SQL used the word `limit` unquoted | Every query failed, so every personal loan failed with it |
| The premium was charged from the server's main loop | It would have charged every few seconds, not once a quarter |
| The policy account `insurance:pool` was never made | The first premium failed |
| A claim named its own amount and its own "evidence" in words | A player could claim ₦1 billion for a fire that never happened |
| No-claims grew a year every quarter, and the loading was 20% of the cover every quarter | The prices were wrong by a factor of about 50 |
| A refused claim opened two tribunal cases, one of them repeated every quarter for ever | |
| Migration 043 was edited in place | A database that had already run it would never get the change |
| The personal loan code was moved outside its transaction | Two loans could be taken at once |
| The routes called functions that did not exist, and no page existed | |

Rebuilt so that it works and cannot be gamed:

- **Four policies**, as the owner's spec says:
  - property and premises;
  - directors' and officers';
  - income protection;
  - the personal umbrella (a top-up over the others).
- **Claims are made against losses the game recorded**: a building's wear, a dismissal, a tribunal judgment. The page
  never names an amount. A loss is claimed once, and each owner claims only their own share of it.
- **The premium** is the expected loss read from the last year of the record, plus a fifth, plus 0.1% of the cover a
  quarter. Each clean year takes 5% off, up to 25%. The no-claims record survives cancelling and buying again.
- **Cover can never be more than there is to lose**: the value of your buildings, half a year's salary, or ₦50 million
  of directors' cover.
- **Once a quarter, at the close**:
  - next quarter's premium is charged, or the cover lapses;
  - the no-claims record is aged;
  - income protection is paid.
- **A claim on a loss you caused** (a building left without upkeep, a job you resigned) is refused, and the premium is
  kept. The insurer refers it to the tribunal as insurance fraud. The second refusal ends all cover for good.
- **What it never covers**:
  - the fine and the disgorgement;
  - a wreck bought into;
  - a loss from before the cover began.
  
  Directors' cover answers only cases opened two years after it began, as long as the tribunal looks back, so a past
  wrong cannot be insured after the fact.
- **Cheaper borrowing**: cover in force and paid takes 2 points off the personal loan spread when it is at least half
  your debt, and 4 when it is all of it. The rate is set again each quarter.
- **The insurers' account** starts with ₦200 million of capital from the pension funds, so the first claims are not
  paid out of a handful of premiums. It pays only what it holds, and a claim larger than that is paid in part, with the
  shortfall shown.
- **A page under Money → Insurance.** It shows:
  - each policy and what its premium is made of;
  - your losses, with a Claim button;
  - your claims;
  - your loan spread with and without cover.

**Decisions taken for the owner to confirm:**

1. Directors' cover pays the tribunal's costs and damages, never the fine. The 9 November checklist allowed the fine
   for a wrong done before the policy, but that is the same as buying cover after the loss, which its own loophole
   question 3 forbids.
2. The insurers start with ₦200 million of capital.
3. Income protection stays narrow (the checklist's option b). In this game only the newsroom dismisses anyone, and
   the page says so.

## Commodities

The page called `/api/commodities`, which did not exist. The routes are now there:

- the page;
- buy and sell;
- take a lease, give one up, and insure one.

The page names a good and a number of units, never a price, and nothing can be done while a quarter's books are
closing.

The loophole tests only checked that functions existed, called a quarter close that does not exist, and bought goods
with nowhere to keep them. They are rewritten to test what the code does:

- the price is the futures contract divided by its units;
- goods need space, and no more can be held than the space holds;
- a round trip costs exactly the spread;
- rent is charged, and unpaid rent is taken from the goods;
- uninsured goods are lost, and insured ones are paid for from the pool;
- delivery needs room and otherwise settles in cash;
- a short future cannot take delivery;
- a lease is its holder's alone;
- the page cannot name a price.

## Tests

- `tests/test_insurance.py` (9) and `tests/test_insurance_loopholes.py` (10, one per checklist question).
- `tests/test_commodities_loopholes.py` (10).
- All 30 pass, along with the courts and lending tests.
