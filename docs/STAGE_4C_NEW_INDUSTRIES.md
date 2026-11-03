# The talent and funds stage, Part 4c: new industries

**This is not yet the report working rule 7 asks for.** The stage is built in part and committed
(`677c618`, 3 November 2026), but seventeen of its thirty-two build items have no test yet, and the
independent review, the ten-year run and the screenshots have not been done. The loophole check is now
answered: its ten tests are written and read through against the code, though not yet run. What follows
records what is genuinely finished, what is built but untested, and what is still missing. It should be
rewritten as a proper report once those are done.

The owner approved the six industries and the twenty-four company names on 3 November 2026 in
`docs/PART_4C_NEW_INDUSTRIES_PROPOSAL.md`, and the item list sits in `docs/PART_4C_CHECKLIST.md`.

## What is built

- **The world.** Six industries and twenty-four companies, each with a full Nigerian balance sheet:
  employees, wages, bank loans, audited accounts, credit ratings, and the ordinary rules for takeover
  and rescue. Eighteen are listed and six are private, bought through deals like the private companies
  in Part 2A.
- **The economy.** The six industries are wired into the machinery that already existed — what each
  industry buys from the others, which purchases are paid for abroad, which sales are exports, and the
  forces each industry leans on.
- **News and events.** Eight new kinds of event, each with its own wording, reaching players as
  headlines and as pop-ups.
- **The exchange.** Six new baskets, one per industry, which index funds and ETFs can copy by rule.
  No futures or options on any of them — see "The two decisions", below.
- **Work for the builds.** One new piece of work for each of the six builds, at Level 5, so the four
  modules a new player starts with are untouched.

## The twenty-four companies

Opening revenue is in millions of naira a year, as the owner approved it.

| Ticker | Company | Industry | Headquarters | Opening revenue | Listed |
|---|---|---|---|---:|---|
| OGP | Ogbomoso Pharma | Medicines and healthcare | Lagos | 95,000 | yes |
| OVP | Osun Valley Pharmaceuticals | Medicines and healthcare | Lagos | 210,000 | yes |
| YBM | Yaba Medicare | Medicines and healthcare | Abuja | 140,000 | yes |
| ILD | Ilesa Diagnostics | Medicines and healthcare | Port Harcourt | 28,000 | no |
| WSG | Wuse Grocers | Groceries and retail | Abuja | 260,000 | yes |
| GBF | Gboko Fresh Markets | Groceries and retail | Kano | 75,000 | yes |
| ADK | Aduke Stores | Groceries and retail | Lagos | 22,000 | no |
| OTG | Otukpo Grocers | Groceries and retail | Aba | 45,000 | yes |
| ZGP | Zanga Pay | Technology and payments | Lagos | 180,000 | yes |
| OJD | Oja Digital | Technology and payments | Lagos | 120,000 | yes |
| NMS | Nembe Softworks | Technology and payments | Abuja | 38,000 | yes |
| IKS | Ikere Cloud Services | Technology and payments | Lagos | 26,000 | no |
| GDS | Gidi Screen | Film and entertainment | Lagos | 88,000 | yes |
| ILP | Ilorin Pictures | Film and entertainment | Abuja | 34,000 | yes |
| UFS | Uyo Film Studios | Film and entertainment | Port Harcourt | 15,000 | yes |
| OTS | Otun Sounds | Film and entertainment | Lagos | 9,000 | no |
| KDG | Kaduna Goldfields | Solid minerals and mining | Abuja | 145,000 | yes |
| BTM | Bauchi Tin Mines | Solid minerals and mining | Kano | 62,000 | yes |
| ECM | Enugu Coal Mines | Solid minerals and mining | Aba | 40,000 | yes |
| OMM | Omu Minerals | Solid minerals and mining | Lagos | 18,000 | no |
| WRU | Warri Urea | Fertilisers and agro-chemicals | Port Harcourt | 195,000 | yes |
| GMF | Gombe Fertilisers | Fertilisers and agro-chemicals | Kano | 110,000 | yes |
| KAC | Katsina Agro-Chemicals | Fertilisers and agro-chemicals | Abuja | 30,000 | yes |
| ICS | Ijebu Crop Science | Fertilisers and agro-chemicals | Aba | 21,000 | no |

`tests/test_part4c.py` writes this table out as the stage's contract with the owner rather than reading
it back from the code, so a company quietly renamed or moved fails a test.

## One database change, worth knowing

Only one thing in the database had to change, and without it the stage would have failed at the first
event. The `events` table names every kind of event it may hold, in a check written when the table was
first made (`008_macro.sql`). A world holding this stage's events would have been stopped by the
database the first time a drug shortage or a mine accident happened — not a lost headline, a failed
quarter. `042_part4c_industries.sql` rewrites that list with the eight kinds added.

The sectors needed nothing, because they are written from the catalogue when a world is made. The news
wire needed nothing either, because a story's kind has no list to keep up to date. The catch is that a
world made before this stage keeps its own rows, which is why it has to be remade before players meet the
new companies.

## How they move the economy

**The medicines makers** buy their ingredients from the manufacturing industry and, through it, from
abroad. That one entry on the imported list is the industry's whole story: a weak naira raises their
costs, and the accounts show it.

**The miners** sell for dollars and pay their wages in naira, so a weak naira helps them. They are the
only new industry added to the non-oil export list.

**The fertiliser makers** take most of their cost from gas, which ties them to the existing oil and gas
industry, and a bumper harvest lifts their sales.

**The grocers** live off wages and household spending, so a squeeze on households reaches them first.

**Technology** leans hardest on the long interest rate of any industry, so its shares fall most when
rates rise and rise most when they fall.

Each industry also runs cheaper in its natural city, on the table the existing industries already use.
The miners may borrow in dollars through Eurobonds; the miners and the fertiliser makers may hedge fuel;
technology may issue preferred shares.

## News and events

| Kind | Touches | What it does |
|---|---|---|
| drug_shortage | the medicines industry | supplies dearer and thinner |
| bad_batch | one medicine maker | a recall |
| bumper_harvest | the fertiliser industry | sales up |
| mine_accident | one miner | sales down, and damage to repair |
| seam_runs_out | one miner | it moves to poorer ground |
| film_hit | one studio | sales up |
| film_flops | one studio | sales down |
| payments_outage | the technology industry | sales down |

Each has three wordings in each of the game's voices, so a headline does not repeat.

## The two decisions

**No futures or options on the six baskets.** The weighting rule lifts the 15% cap to one and a half
times an equal share whenever a basket has fewer than seven members, so in a four-name basket one
company can be 37.5% of the index. With a contract settling at ₦100 a point, one player leaning on one
name would move everybody's settlement. The baskets still back index funds and ETFs, and futures on a
sector are already taught by oil and gas.

**Entertainment is a subject for the journalist, not an employer.** A journalist employed by the studio
he reports on is the conflict of interest the build exists to teach. The piece is a story about a
studio's quarter, with and without the hit.

## The items, one by one

This is what could be checked from the code on 3 November 2026. "Tested" means the test the checklist
names exists in `tests/`; it does not yet mean it has been run and seen to pass, because there was no
test runner available where this report was written.

| # | Item | Status |
|---|---|---|
| 1 | Six industries in the catalogue | built, tested |
| 2 | Twenty-four companies placed | built, tested |
| 3 | Their books balance | built, tested |
| 4 | They sell into the real economy | built, tested |
| 5 | A fresh world starts with them | built, tested |
| 6 | Each leans on the right forces | built, tested |
| 7 | A weak naira costs the medicine makers | built, tested |
| 8 | A weak naira helps the miners | built, tested |
| 9 | Fertilisers follow the gas price | built, tested |
| 10 | Shops follow household money | built, tested |
| 11 | Rising rates hurt technology most | built, tested |
| 12 | Each industry has a home city | built, tested |
| 13 | Miners may borrow in dollars | built, tested |
| 14 | Miners and fertilisers may hedge fuel | built, tested |
| 15 | Technology may issue preferred shares | built, tested |
| 16 | A plain English name per industry | built, no test yet |
| 17 | The eight new event kinds | built, no test yet |
| 18 | Events reach news and players once | built, no test yet |
| 19 | The newsroom finds the six | not checked, no test yet |
| 20 | Six baskets with their rules | built, no test yet |
| 21 | Funds and ETFs copy the baskets | relies on existing machinery, no test yet |
| 22 | A small basket values sensibly | relies on existing machinery, no test yet |
| 23 | Futures: decided, not half-built | settled (none), no test yet |
| 24 | Work for every build | built, no test yet |
| 25 | One new piece per industry | built, no test yet |
| 26 | The industry insight counts four-company industries | not checked, no test yet |
| 27 | A company page names its industry | not checked, no test yet |
| 28 | Markets lists the six baskets | not checked, no test yet |
| 29 | Economy shows the six industries | not checked, no test yet |
| 30 | Net worth counts the new shares | not checked, no test yet |
| 31 | A new company can be taken over | relies on existing machinery, no test yet |
| 32 | A private one can be bought and listed | relies on existing machinery, no test yet |

**Items 33 to 38 are not done.**

33. **The loophole check.** The ten applicable questions now have one automated test each, in
    `tests/test_part4c_loopholes.py`: `test_q1_...` to `test_q10_...`, in the checklist's order. They
    have not been run, only read through against the code they test. The answers are set out below, and
    no question needed a change to the game's own code. No second AI has yet been asked to break the
    feature (item 34).
34. **The independent review.** Not run.
35. **The ten-year run.** Not run. Nothing here reports a ledger audit, a market speed or the fate of the
    new companies over forty quarters.
36. **Screenshots and accessibility.** None taken; axe not run.
37. **The whole test suite.** Not run. Twenty-five files changed in this part and the older tests that
    count kinds of company, news wordings, holdings in net worth and requests that change something
    have not been seen to pass together.
38. **The report and the push.** This file is a draft of the report. Nothing has been pushed.

## The loophole check, question by question

Working rule 3 asks ten questions of every feature. Six are about the new industries themselves and four
are about the money and the shops they touch. Every answer is "no", and each answer has a test in
`tests/test_part4c_loopholes.py` that reads the same tables the game reads, so an answer cannot quietly
stop being true without the test failing.

The rule underneath all ten: a player may do damage to another player, never to the game. Cheating a
rival out of a company is play; conjuring money, or reading a secret, is not.

| # | The question | The answer, and what holds it | The test |
|---|---|---|---|
| 1 | Can a player see a private company's true figures before buying? | No. A private company is shut to both screens that could show one — its own page and its facts page both answer "there is no company with that code" — and it is left out of the market list itself, so the refusal is the whole of it and not a filter on one door. A buyer is shown the company's published worth and the papers in the data room, which are signed for first. | `test_q1_...` |
| 2 | Can a player move value between a company they own and one they do not? | No, in either direction. Overpaying is refused at the bid: no price above 150% of what the company is worth and of its asking price (`firm_deals.OVERPAY_MOST_BPS`). Underpaying is refused at the close: the seller has a reserve — 85% of the asking price — beneath which no bid wins, and the bidder's money, held in escrow while the bid stood, comes back to the kobo. | `test_q2_...` |
| 3 | Can a basket too thin to defend itself be gamed? | No, because there is nothing to lean on. The six new baskets carry no futures and no options — a settled contract on a three-name basket would let one player move everyone's settlement — and the weighting rule holds the largest name at half the index however much of it is bought. | `test_q3_...` |
| 4 | Can a miner's dollar borrowing be used to dodge the naira? | No. The miner sells the dollars it borrows to the Central Bank at once, so it holds naira and cannot sit on the dollars; what it owes stays in dollars. When the naira falls, the quarter's revaluation is the miner's own loss in its own accounts. The currency risk cannot be handed to anybody else. | `test_q4_...` |
| 5 | Can a film hit be forecast from anything a player is shown? | No. What happens in a quarter is drawn from the world's secret — no secret, no draw — and the draw is a fixed scramble of the secret, the quarter, the kind and the company, so it is the same answer every time it is asked and cannot be re-rolled by asking again. Across many worlds it lands both ways for the same company and the same quarter, which it could not do if it followed the ticker or the date. | `test_q5_...` |
| 6 | Can the fertiliser-to-farm link be arbitraged? | No. The link is a published share of what farms spend, in the same table every industry uses, and the fertiliser maker's own cost runs back to gas. It is a chain of costs between two companies, not two prices to trade against each other, and neither end is something a player can buy into or out of at will. | `test_q6_...` |
| 7 | Can wages be avoided by moving staff into a new industry? | No. All twenty-four pay wages out of their own running costs, and the employer's pension contribution rides on top at the same rate as everywhere else. There is no kind of company a player can be put in to escape them. | `test_q7_...` |
| 8 | Can a private company be made to pay its owner twice? | No. A dividend is one transaction: what leaves the company is never less than what reaches its owners, the difference is kobo of rounding that stays with the company, and a second payment in the same quarter would have to be a second transaction, of which there is none. | `test_q8_...` |
| 9 | Can a rescue of a new company be turned into free money? | No. A rescue fee is paid by the company being rescued, or owed by it, so it is a cost of that company and never money from nowhere. With a quarter closed over all of it, the ledger still balances, the crisis desk's own books still hold, and every naira that should exist does. | `test_q9_...` |
| 10 | Can a new basket's index be moved single-handed? | No. Two limits bound it: the largest name is half the index, and no share may move more than a tenth in a session, both measured by the exchange's own rules rather than the test's. Together the most one player can pull a basket in a day is 5%. With no futures on the six, there is also no contract to lean on while moving it. | `test_q10_...` |

One thing the tests turned up, worth knowing rather than fixing: the checklist's note on the futures
decision does its arithmetic on a **four**-name basket (37.5% for one company). The baskets the build
actually creates hold the **three** listed companies of each industry, so the ceiling is 50%, as items 3
and 10 now check. The decision itself — no futures on these six — is untouched by that, and is if
anything better supported by it.

## What is needed to close the stage

In order, the shortest path:

1. Write the seventeen missing tests the checklist names — the ones for items 16 to 32. The loophole
   check, which is item 33 and sits outside those seventeen, is already written in
   `tests/test_part4c_loopholes.py`.
2. Run the whole suite and fix what falls over, listing each older test brought up to date.
3. Run the ten-year run with the staged oil shock and the two bank shocks, and fix what it finds.
4. Take the screenshots, in dark and light theme, and on a phone for the markets and a company page.
   Run axe on every one.
5. Rewrite this file as the finished report — tick marks, run results, findings from the run and the
   review — then push.

## Honest limits

- Nothing in this file has been seen to pass. The fifteen tests in `tests/test_part4c.py` were
  byte-compiled, not run, when this was written, and the ten loophole tests have only been compiled and
  read through against the code they test.
- Reading the loophole tests against that code changed one of them: the test for moving value out of a
  company first expected a bid far *below* the asking price to be refused at the bid, and it is not —
  a low bid is allowed to stand and is refused at the close by the seller's reserve. The test now says
  so. No game code was changed by the check.
- The six industries appear in the game's data and machinery, but the screens have not been looked at.
  "Not checked" in the table means exactly that.
- The private companies of Part 2A are owned by founders and bought through deals; these six follow the
  same route, but nobody has yet bought one and taken it public.
- As in Part 4b, the world has to be rebuilt before players meet the new companies: `docker compose down
  -v` deletes every player and all history.
