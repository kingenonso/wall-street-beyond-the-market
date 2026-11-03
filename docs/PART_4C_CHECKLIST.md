# Part 4c checklist: new industries

**Built in part on 3 November 2026, committed as `677c618`. Items 1 to 15 are built and tested; items 16
to 32 are built or rely on machinery that already exists, but the tests this page names for them have not
been written; items 33 to 38 are not done. `docs/STAGE_4C_NEW_INDUSTRIES.md` is a draft of the closing
report that sets out exactly what is missing.**

Written 3 November 2026, after the owner approved the company names in
`docs/PART_4C_NEW_INDUSTRIES_PROPOSAL.md`.

Following working rule 1, this is the checklist the owner approved before any code was written. Each item
says what it does and names the automated test that proves it. When the stage is finished, the report
`docs/STAGE_4C_NEW_INDUSTRIES.md` will tick every item here against its test, with screenshots.

## What the owner has already decided

- Six new industries, twenty-four companies, eighteen listed and six private.
- The industries: medicines and healthcare, groceries and retail, technology and payments, film and
  entertainment, plus solid minerals and mining, plus fertilisers and agro-chemicals.
- The names, as approved on 3 November 2026.
- The five recommendations in the proposal are taken as accepted, because the owner approved the file they
  sit in: baskets for all six, a full set of objectives for each, the private six owned by founders and
  bought through deals, and failure and rescue unchanged from the existing rules.

## What this part is

Part 4c is the third and last piece of Part 4. Part 4a built the currency desk, Part 4b built the markets
abroad, and Part 4c adds six industries to Nigeria itself — new companies, new ways for the existing
economy to move, and new work for the players' three builds.

Nothing on the list is dropped or put off. There is nothing this part needs from the multi-region items
the trial excludes, so nothing is being deferred for that reason either.

**One difference from Part 4b worth saying plainly now.** The foreign companies are simple: sales, profit
and dividends, no wages, loans or balance sheets. These twenty-four are Nigerian companies, so each one
gets the full treatment the other eighty already have — a balance sheet that must balance, employees and
wages, bank loans, audited accounts, credit ratings, and the ability to be taken over or rescued. This is
a bigger build than Part 4b, not a repeat of it.

## The items

### A. The world

| # | What it does | The test that proves it |
| --- | --- | --- |
| 1 | Six industries added to the catalogue, each with its own balance-sheet shape: how much cash and borrowing is usual, how much of its profit it pays out, how much it spends on fixed assets. | `test_the_world_has_the_six_new_industries` |
| 2 | Twenty-four companies added, each with a headquarters, an opening yearly revenue, a bank that holds its loan, and marked listed or private. | `test_the_new_companies_are_counted_and_placed` |
| 3 | Every new company's opening accounts balance, its loan sits with a named bank, and no naira appears without a recorded payer. | `test_the_new_companies_books_balance` |
| 4 | The six industries sell into the real economy: medicines and groceries to households, fertiliser and crop chemicals to farms, mining abroad for dollars, technology to everyone. | `test_the_new_industries_sell_into_the_economy` |
| 5 | A fresh world begins with the new companies already trading, so a new game has them from day one. | `test_a_new_world_starts_with_the_new_industries` |

### B. How the economy moves them

| # | What it does | The test that proves it |
| --- | --- | --- |
| 6 | Each industry leans on the right common forces: shops on household spending, fertiliser on gas and farming, mining on metals and the economy, technology on the economy. | `test_the_new_industries_lean_on_the_right_forces` |
| 7 | A weak naira raises the medicine makers' costs, because they buy their ingredients abroad. This is the industry's whole story and it must be visible in the accounts. | `test_a_weak_naira_costs_the_medicine_makers` |
| 8 | A weak naira helps the miners, because they sell for dollars and pay in naira. | `test_a_weak_naira_helps_the_miners` |
| 9 | The fertiliser makers' costs follow the gas price, which ties them to the existing oil and gas industry. | `test_the_fertiliser_makers_follow_the_gas_price` |
| 10 | The shops' sales follow wages and household spending, so a squeeze on households reaches them before anyone else. | `test_the_shops_follow_household_money` |
| 11 | Technology shares fall most when the long interest rate rises, and rise most when it falls. | `test_rising_rates_hurt_the_technology_shares_most` |
| 12 | Each industry runs cheaper in its natural city, added to the existing city-cost table. | `test_each_new_industry_has_a_home_city` |
| 13 | The miners may borrow in dollars through Eurobonds, as the largest oil and telecoms companies already do. | `test_the_miners_may_borrow_in_dollars` |
| 14 | The miners and fertiliser makers can hedge fuel, as transport and power already do. | `test_the_new_industries_can_hedge_fuel` |
| 15 | Technology may issue preferred shares. | `test_who_may_issue_preferred_shares` |

A note on items 7 to 9, so the owner knows what is being asked for. Three pieces of machinery already
exist and this part plugs the new industries into them rather than inventing anything:

- **What each industry buys.** Every industry already has a published list of what it spends on other
  industries, as a share of its sales. The medicine makers get their ingredients from the manufacturing
  industry and, through it, from abroad; the fertiliser makers get most of their cost from gas; the shops
  get theirs from farms, food makers and haulage.
- **What counts as imported.** A short list already decides which purchases are paid for in dollars. Adding
  the medicine makers' ingredients to it is what makes a weak naira hurt them.
- **What is sold abroad.** Non-oil exports are already shared between the farms and the factories by a
  published weighting. The miners join that list, which is what makes a weak naira help them — and it comes
  with the exchange-rate effect the game already applies to exports, so no new mechanism is needed.

The interest-rate effect in item 11 needs no new code either: the technology industry is simply given the
heaviest lean on the money force of any industry, and the existing valuation rule does the rest.

### C. News, events and the newsroom

| # | What it does | The test that proves it |
| --- | --- | --- |
| 16 | Every new industry has a plain English name for headlines. This one is not optional: the existing code looks this up directly, so a missing entry would crash rather than fall back. | `test_every_industry_has_a_plain_english_word` |
| 17 | New kinds of event, each with its own wording: a drug shortage, a bad batch at a medicine maker, a bumper harvest lifting fertiliser demand, a mine accident, a seam running out, a film that flops, a film that breaks records, a payments outage. | one test per kind, `test_event_<kind>` |
| 18 | The same events reach the player as news and as pop-ups, worded the same way each time so no headline repeats. | `test_the_new_events_reach_the_news_and_the_player_once` |
| 19 | The newsroom can find stories about all six industries, and the intelligence objectives that scan industries include them. | `test_the_newsroom_finds_the_new_industries` |

### D. The exchange

| # | What it does | The test that proves it |
| --- | --- | --- |
| 20 | Six baskets, one per industry, published with their rules in plain words beside the existing four. | `test_each_new_industry_has_a_basket` |
| 21 | Index funds and ETFs can copy the new baskets with no new code, because they already copy any basket by rule. | `test_a_player_can_run_a_fund_of_the_shops` |
| 22 | A basket with fewer than the usual number of companies still values sensibly, since each new industry has only four and some are private. | `test_a_small_basket_still_values_sensibly` |
| 23 | Futures and options: decided below, not left half-built. | `test_which_indexes_have_futures` |

### E. Work for the players' builds

| # | What it does | The test that proves it |
| --- | --- | --- |
| 24 | Each of the six industries gets a full set of objectives, so no build is left out. Accountants and lawyers already work for every company; the investment banker, risk manager and asset manager work through the banks; the journalist through the media houses. The new industries must not leave the financiers with nothing new to do. | `test_every_industry_has_work_for_every_build` |
| 25 | A new objective per industry for the best-paid build that touches it, drawn from the same learning modules as the rest. No exam body is named and no question paper appears. | one test per objective, `test_objective_<name>` |
| 26 | The industry insight that objectives read from counts four-company industries, which it currently skips below three. | `test_the_industry_insight_counts_the_new_industries` |

### F. What the player sees

No new sidebar item. Following the owner's standing rule, everything below lives inside pages that already
exist.

| # | What it does | The test that proves it |
| --- | --- | --- |
| 27 | A company page shows its industry, and for the private ones says it is not for sale until someone asks. | `test_a_new_company_page_names_its_industry` |
| 28 | The Markets page lists the six new baskets beside the existing four. | `test_the_markets_page_lists_the_new_baskets` |
| 29 | The Economy page's industry panel shows the six new industries with their sales and fortunes. | `test_the_economy_page_shows_the_new_industries` |
| 30 | Proven Talent's investing record counts the new shares in net worth, and the older tests that count kinds of holding are brought up to date. | `test_net_worth_counts_the_new_shares` |

### G. Trouble, as for every other company

| # | What it does | The test that proves it |
| --- | --- | --- |
| 31 | A new company can be audited, named in the shadow feature, taken over, and rescued from failure, on the same rules as the rest. Nothing about them is special-cased. | `test_a_new_company_can_be_taken_over` |
| 32 | A private one of the six can be bought by an empire, run, and later listed. | `test_a_private_new_company_can_be_bought_and_listed` |

### H. The checks every feature gets

| # | What it does |
| --- | --- |
| 33 | **The loophole check** (working rule 3, design section 19). The ten questions are answered for each feature, an automated test written for every question that applies, and the answers listed in the stage report. The applicable areas for this part: can a player see a private company's true figures before buying; can a player move value between a company they own and one they do not; can a new industry's basket be gamed by trading a thin four-company set; can a miner's dollar borrowing be used to dodge the naira; can a film company's "hit" be forecast from anything the player is shown; can the fertiliser-to-farm link be arbitraged; can wages be avoided by moving staff into a new industry; can a private company be made to pay its owner twice; can a rescue of a new company be turned into free money; can a new basket's index be moved single-handed. |
| 34 | **The independent review.** A second AI that did not write the code is told to break it. Every finding is fixed, given its own test, and listed in the report, as in Parts 1, 2, 3, 4a and 4b. |
| 35 | **The ten-year run.** Forty quarters with all earlier stages running, a staged oil shock and two bank shocks, as in Part 4b. The books must pass the ledger audit at the end and the markets' work must stay quick. Every oddity found is fixed, and most get a test. |
| 36 | **Screenshots and accessibility.** A screenshot of every new screen or panel, in dark and light theme, and on a phone for the markets and a company page. The accessibility check (axe) must find nothing. |
| 37 | **The whole test suite.** Everything already passing must still pass (1,532 server tests in 93 files, the engine's 13, the website's 23). Older tests that count kinds of company, news wordings, holdings in net worth or requests that change something will need bringing up to date, and each such change is listed in the report. |
| 38 | **The report and the push.** `docs/STAGE_4C_NEW_INDUSTRIES.md` written in the house style, then pushed to GitHub. |

Expected size: about fifty new tests, in line with the other pieces of Part 4 (Part 4a added 37, Part 4b
added 49).

## Two costs that came with this part

1. **The current test world will be wiped.** New companies are part of how a world begins, exactly as the
   thirty private companies were in Part 2A. An existing world does not pick them up. So the stage ends
   with `docker compose down -v`, which deletes every player and all history. If you have a test game you
   want to keep, play it out before this stage starts.
2. **The ten-year run will take about an hour.** Part 4b's took 57 minutes with 80 companies. Twenty-four
   more companies, each with a full balance sheet, will make it slower, and the run may need resuming from
   saved points as it did in Part 4b.

## Decisions taken

Two questions were open when this checklist was written. Both were settled as recommended and the code is
built that way. They are recorded here, with the reasoning, so that nobody reopens them from this page.

1. **No futures and options on the six new baskets.** Only the Top 30, banks and oil and gas carry futures
   beside the BSX 50. The arithmetic decides it: the weighting rule lifts the 15% cap to one and a half
   times an equal share whenever a basket has fewer than seven members
   (`simulation/indexes.py:141`), so in a four-name basket one company can be 37.5% of the index. A
   contract settles at ₦100 a point, so a single player leaning on one name moves everyone's settlement —
   which is the very loophole item 33 exists to catch. Nothing is lost: the six baskets still back index
   funds and ETFs, and futures on a sector are already taught by oil and gas. The decision is recorded in
   the code at `simulation/world_data.py:1448`.
2. **Entertainment is a subject for the journalist, not an employer.** Film and music companies are
   natural subjects for a reporter and incoherent employers for one: a journalist employed by the studio
   he reports on is the conflict of interest the build exists to teach. Journalists keep the media houses
   as employers, and the entertainment industry's piece (`jn_film_quarter`, in
   `simulation/objectives_industries.py`) is a story about a studio's quarter, with and without the hit,
   for the media build.

## What happens next

The items above are built. Three things close the stage:

1. The ten-year run against the new world, resuming from saved points if it needs to, as Part 4b's did.
2. The report, `docs/STAGE_4C_NEW_INDUSTRIES.md`, ticking every item here against its test, with
   screenshots.
3. `docker compose down -v` before the new companies appear in a playable world — see the first cost
   above, which wipes every player and all history.
