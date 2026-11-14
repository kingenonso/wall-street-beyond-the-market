# Insurance: the stage checklist

Written 9 November 2026, for the owner's approval before any code is written (working rule 1).

The design was settled in `docs/REFERENCE_SPEC_2026-11-07.md` under "INSURANCE: what it should be": four
policies, premium as expected loss plus a loading, a no-claims record, and a rating benefit that makes cover worth
its price even when it never pays. This file turns that into work. Every policy below is tied to a loss the game
**already inflicts** — nothing here invents a new disaster to justify a premium. Where the spec named a loss that
the engine does not yet have, this checklist says so and marks it as a decision for you rather than quietly
building it.

---

## 1. Where it lives

A page under **Money**, as a fourth tab beside Portfolio and savings, Borrow and Retirement. Never a sidebar
entry (your standing rule). The items wear the house grammar: **Buy a policy** green, **Cancel a policy** red,
**Review your cover** and **Claim** cyan.

Three things come with it that are not on the page:

* a **Policy account** in the ledger at `insurance:pool` — premiums in, claims out, and nothing else. It is an
  escrow like the goods insurance pool at `commodity:insurance`, which already exists and pays claims properly;
* a **quarterly step** in the world's close that charges premiums, ages the no-claims record and expires cover;
* the **rate on a player's loan** stops being `policy rate + a fixed spread` and starts reading the player's cover.

---

## 2. What it sells, and the loss each policy answers

### Policy 1: Property and premises

**The loss it answers.** The engine already wears buildings down: `condition` falls every quarter by
`data.WEAR_WITH_UPKEEP` when upkeep is paid and by a larger figure when it is not, and a building below
`data.POOR_CONDITION` loses occupancy in proportion, which is lost rent. A property with no upkeep falls to zero
condition and stops earning.

**What cover does.** The policy pays to restore condition — the repair less an excess — at the quarter close,
automatically, up to the limit of the sum insured. Premium is set by district, building type and the building's
own worth; the conditional loss (condition below the threshold) is the expected loss that prices it.

**What it does not do.** It does not pay rent, does not stop wear, and does not cover a property that was already
below the threshold when the policy was bought beyond the excess — otherwise insuring a wreck is free money.

### Policy 2: Directors' and officers'

**The loss it answers.** The court module already makes a player the **defendant personally** for insider dealing,
market manipulation (which includes ramping), a hidden stake and a naked short — the defendant in `_wrongs()` and
in `courts.open_case()` is always a player id, never the empire and never the company (`simulation/courts.py`,
the `"defendant_id": row["player_id"]` lines). The judgment is `disgorgement + damages + fine + costs`, paid
from the player's own account by `courts.pay()`, which takes what it can each quarter.

**What cover does.** It pays the **damages, costs and the fine's share** on your behalf, up to the limit, once a
year's worth of premiums has been met. It does **not** pay the disgorgement: money you were never entitled to is
never insurable, because paying it back is not a loss, it is the correction of a gain. It does not pay a fine
for a wrong you committed deliberately after the policy was written (see question 2).

**What it does not do.** It does not defend you: the court's finding stands and the record stays on your legal
record. It buys the money, not the verdict.

### Policy 3: Income protection

**The loss it answers.** Exists, but narrowly. A player is only ever dismissed by `simulation/newsroom.py`
(`careers._leave(..., "dismissed: ...")`) — repeated late corrections costing the paper its readers, below
`data.DISMISS_BELOW_CREDIBILITY`. Every other ending of a job is the player's own choice: resigned, changed
build, moved employer. The base game has **no inflation, no recession that sheds jobs, and no dismissal for
anything else.**

**What cover does.** Pays a share of the last salary each quarter for a set number of quarters after a dismissal,
and covers the gap while the next job is found.

**The decision this forces on you.** As the game stands, income protection insures against one narrow trigger,
and the honest reading is that it would almost never pay. There are two ways to make it a real policy and both
change the game, so neither can be mine to pick:

* **(a) Build the dismissal.** Add a reason for a company to let a player go — a loss-making employer shedding
  staff, a build whose work has dried up — which is a real feature of its own and makes income protection
  meaningful; or
* **(b) Sell it narrow.** Leave it as cover against the newsroom's dismissal only, priced accordingly, and say so
  plainly on the page so nobody buys it expecting something the game cannot do to them.

My recommendation is (b) for this stage and (a) as its own stage later, because (a) changes what a job is and
deserves a checklist of its own.

### Policy 4: Personal umbrella

**The loss it answers.** Claims against you personally that fall outside the other three. In the engine, that is
one thing today: **a court case you bring and lose**, where the bond you posted is returned but your own costs are
not — and, beyond that, nothing the engine does to a player's person rather than their property.

**What cover does.** A top-up above a limit you choose, in layers of cover with a premium per layer, at the same
length as the others.

**The decision this forces.** The spec says "claims against you personally that fall outside the other three", and
there is very little in the engine that is against the player personally and outside directors' and officers'.
I recommend selling the umbrella as a **top-up that raises the limits of whichever policy responds first**, rather
than a fourth independent loss — otherwise it is a fourth page of prose describing a loss that never happens.

---

## 3. How it is priced

Premium is the expected loss plus a loading, and every figure is read from the game's own record — never a number
printed on the page:

| Policy | Expected loss it is priced on | Where the figure comes from |
| --- | --- | --- |
| Property and premises | wear and lost occupancy in the building's district over the last four quarters | `property_results` |
| Directors' and officers' | court judgments against players, by kind of case, over the last four quarters | `court_cases` |
| Income protection | dismissals recorded in careers, over the last four quarters | `career_events` |
| Personal umbrella | the cost of lost cases, over the last four quarters | `court_cases` |

**The no-claims record.** Every game year without a claim takes a set percentage off the premium; a claim resets
the record. It is stored per player and per policy, and it is what turns four static prices into a relationship.

**Why you buy it anyway.** Your cover improves the rate on your own borrowing. Today the personal loan rate is
`policy rate + data.PERSONAL_LOAN_SPREAD_BPS`, flat, for everybody. With insurance in the world, an insured
player's spread narrows, in proportion to how much of their liability is covered, and the page must show both the
rate it is today and the rate it would be, so the trade is visible rather than discovered.

**The honest limit.** A premium that is expected loss plus a loading **always loses money in the long run**. It
must be said plainly on the page, and the rating benefit must be worth more than the loading or nobody should buy
it. This is checked by a test that values both sides with the same figures.

---

## 4. What a claim looks like

A claim is opened only by the engine or by the player, never by the page's own arithmetic:

1. The quarter close finds a covered loss. It writes a claim against the policy: what the loss was, the evidence
   (the wear, the judgment, the dismissal), the excess and the amount payable.
2. The claim is **investigated** before it is paid. What the investigator reads is the same record the court
   already reads: who caused the loss, and whether it was the claimant.
3. Where the loss was **caused by the claimant** — a building left without upkeep and then claimed for, a case
   that only arose because the player broke the law — the claim is refused, the premium is kept, and the incident
   opens a **court case** for attempting to claim on a loss you caused. Reputation takes the damage.
4. A **second attempt ends the policy permanently** and no insurer writes another, for the whole game. That is
   stored, not inferred.

Nothing is paid out of the policy pool that was not first written as a ledger transfer. The pool can be short: if
the premiums taken in have not covered what is claimed, the claim is paid **out of what the pool holds** and the
shortfall is recorded — the policy does not promise money that does not exist, and the page says so.

---

## 5. The ten loophole questions, one test each

Each is a test in `tests/test_insurance_loopholes.py`, named for the question.

1. **Can a player claim on a loss they caused?** No. A building left to fall without upkeep and then claimed for
   is refused, and the refusal opens the court case.
2. **Can a player insure a wreck?** No. A property already below the repair threshold at the date of purchase is
   covered only above the excess, and the expected loss for it is priced at the rate a wreck actually wears.
3. **Can cover be bought after the loss happened?** No. Every quarter is closed before the page can act in it,
   and a claim is judged against the policy in force when the loss was written.
4. **Can the disgorgement be insured?** No. Only damages, costs and the fine are payable; disgorgement never is.
5. **Can a player escape a fine by holding cover?** Only for a wrong committed before the policy was written:
   a fine for a wrong committed after it is excluded, and the exclusion is tested.
6. **Can the no-claims record be reset by cancelling and buying again?** No. The record is per player, not per
   policy, and survives a cancellation.
7. **Can the rating benefit be had without paying premiums?** No. The rate reads cover **in force and paid up**;
   a lapsed policy buys nothing.
8. **Can two players split a loss between them to claim twice?** No. A claim names the account that bore the loss,
   and a loss is claimed once against one policy.
9. **Can the pool be drained, or claims paid beyond it?** A claim can empty the pool and never overdraw it; a
   shortfall is recorded and shown, and no claim is paid from another policyholder's property.
10. **Can the page decide any amount?** No. Every premium, excess, claim and payout figure is the server's; the
    page prints it. A test asserts that no figure on the insurance payload is computed only on the screen.

Scripting the **policy pool** badly is the one attack that would let a player profit from the fund itself, so it
gets the second AI as its own brief: the pool, not the page.

---

## 6. What has to be built, in order

| # | Where | What |
| --- | --- | --- |
| 1 | `database/migrations/046_insurance.sql` | `insurance_policies` (player, kind, limit, excess, premium, started, ends, state, no-claims years), `insurance_claims` (policy, kind, loss, evidence, excess, payable, state, refusal reason), `insurance_refusals` (player, kind, at, whether the policy ended for good) |
| 2 | `simulation/insurance.py` | the four policies, the pricing from the record, the quarterly step (charge, age, expire), the claim, the investigation, the referral to the courts, and the pool — every naira through `simulation/ledger.py` (rule 8) |
| 3 | `simulation/lending.py` | the personal loan spread reads cover in force and paid up; `data.PERSONAL_LOAN_SPREAD_BPS` becomes the uninsured spread, with a second constant for the insured one |
| 4 | `simulation/courts.py` | a new kind of case, `insurance_fraud`, opened by the investigation; a second attempt ends cover for good |
| 5 | `simulation/world_data.py` | the loadings, the excess thresholds, the no-claims step, the disclaimer's wording |
| 6 | `server/insurance_routes.py`, `server/schemas.py`, `server/main.py` | the page's read and its four actions, each with the server deciding |
| 7 | `web/src/Insurance.tsx` | the page, plus an Insurance band cell on the Money overview that says whether you are covered |
| 8 | `tests/test_insurance.py`, `tests/test_insurance_loopholes.py` | one test per promise, one per loophole question above, and the pricing-is-not-a-random-number test |
| 9 | second AI | told to break the pool and the claim, with a test for each attack it lands |
| 10 | `docs/STAGE_INSURANCE_*.md` | the stage report: every line above ticked against its test, with screenshots |

The one thing I cannot verify here: the Python suite does not run in this sandbox (3.10 against 3.12 packages,
no package index, no PostgreSQL). The web side can be built and read; the backend cannot be proven until you run
`python -m pytest` and paste the failures.

---

## 7. What I need from you before any code

1. **Income protection:** (a) build dismissal as its own feature, or (b) sell the narrow policy and say so?
2. **Personal umbrella:** (a) a real fourth policy, or (b) a top-up that raises the limits of another?
3. **The rating benefit's size:** does insured cover narrow the loan spread by a set step (recommended: one step
   for any cover in force, a second for cover worth more than half your liabilities), or in proportion to cover?
4. **Whether the four policies are all four,** or whether the umbrella waits until there is a loss for it to answer.

Answer those four and I will build it in the order in section 6, one step at a time, and bring you the report
with the tests behind every line.
