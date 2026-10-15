# Stage 8: land, property, the Auction House and headquarters

The owner approved this stage with "build" on 12 October 2026. Every item on the checklist in
`notes/stage-8-plan.md` was built, and nothing was dropped or put off.

Tests at the end of the stage: **1,078 on the server**, 13 on the order-matching engine and 23 on the
website. All of them pass.

## Checklist

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| A1 | Districts in five cities (Lagos, Abuja, Port Harcourt, Kano, Aba), with buildings, small units and plots | Yes: 25 districts and 300 properties | `test_a_new_world_has_districts_in_all_five_cities_owned_by_the_property_companies` |
| A2 | Rents paid by the households and companies of each city, through the city's real spending | Yes | `test_an_owner_is_paid_rent_and_pays_tax_and_upkeep_at_the_close`, `test_a_property_company_that_still_owns_everything_earns_its_rent_inside_its_business` |
| A3 | Bubbles allowed | Yes: overpaying inflates a district, and the extra fades by a fifth each quarter | `test_buyers_who_overpay_inflate_a_bubble_that_then_fades` |
| A4 | Mortgages limited by salary: at most 4 years of salary, a 20% deposit; an empire may borrow up to 60% | Yes | `test_a_mortgage_is_limited_to_four_years_of_salary_and_needs_a_fifth_paid_down`, loophole 4 |
| A5 | Repossession | Yes: after two missed payments the bank sells the property, with no lowest price | `test_two_missed_mortgage_payments_and_the_bank_sells_the_property` |
| A6 | Property tax 1% a year and land tax 0.5% a year. Unpaid tax grows, and the Government sells a property once the arrears reach a tenth of its value | Yes | the rent test; `test_computer_bidders_join_a_forced_sale_...` |
| A7 | Building, renovating and wear | Yes | `test_building_on_a_plot_makes_a_building_that_earns_rent`, `test_without_upkeep_a_building_wears_five_times_faster_and_renovation_restores_it` |
| A8 | Players and empires both own property, and it counts in what they are worth | Yes | `test_a_bid_at_or_above_the_reserve_buys_it_...` (equity), the empire bidding test (worth) |
| B1 | Live timed auctions: 24 hours, and a bid in the last 5 minutes adds 5 more | Yes | `test_a_late_bid_adds_five_minutes_and_a_leading_bid_cannot_be_withdrawn` |
| B2 | Land, buildings and distressed property first | Yes: the companies' weekly listings, owners' sales, and forced sales for unpaid mortgages and tax | the tests above |
| B3 | Partners (consortiums), mortgage financing, walking away | Yes | `test_partners_share_a_bid_and_then_the_property`, loophole 10 |
| B4 | Rival computer bidders | Yes: two property companies bid at every sale that is not one of their own | the forced-sale test |
| B5 | Desk checks before an empire bids (Legal Counsel checks the title, the Accountant values the lot, the Risk Manager sets the top price, the Investment Banker arranges the money), then the head decides | Yes | `test_an_empire_bids_only_after_every_desk_has_checked_the_lot_...`, loophole 5 |
| B6 | Bid cash held in escrow; sealed limits never shown | Yes | loopholes 2 and 3 |
| C1 | Headquarters Levels 1–120. Each level costs more and does a little less | Yes | `test_the_cost_of_a_level_grows_...` |
| C2 | Seats beyond 13: one more seat for every ten levels | Yes | `test_a_headquarters_adds_seats_as_it_rises_and_teaches_more` |
| C3 | City benefits | Yes: see the table below | the same test |
| C4 | Upkeep and insurance are on the Risk Manager's screen, and the head approves | Yes | `test_an_approved_upkeep_keeps_the_headquarters_standing` |
| C5 | Collapse with warnings: the building is lost, insurance pays, benefits stop, extra seats freeze, and those who ignored the warnings lose reputation. Members are unharmed | Yes | `test_a_neglected_headquarters_is_warned_and_then_collapses_and_the_insurance_pays`, review finding 11 |
| D | Work for each build, with "How to do this" | Yes: six new pieces, one per build, each alone, with the empire and as a weekend challenge (18 in all) | `tests/test_builds.py`, `tests/test_mastery.py` |
| E | Screens: the Property section (city map, listings, my property, rents, mortgages, the Auction House with live countdowns), a headquarters page in Empire, a property panel on the Economy page, and news | Yes | screenshots below |
| F | Ledger checks, the loophole check, the independent review, the ten-year run, full tests, screenshots, this report, merge, project note | Yes | this report |

## What it does, in plain words

**The property market.** Each city has five districts: a business district, homes, shops and
markets, industry, and farmland. Each district has big buildings, small units and empty plots.
At the start the property companies own everything. Rent comes from what the city's households
and companies really spend. When a player buys a building, the rent it earns moves from the
company to the player, so no rent is made up. A building's value is the rent it earns in a year,
divided by the return investors want. That return rises and falls with the Central Bank's rate.
Run-down buildings are worth less, and a district's "bubble" is added on top.

**Bubbles.** If buyers at the Auction House pay more than buildings are worth, the district's prices
rise further. The extra fades by a fifth each quarter unless buyers keep overpaying. The opposite
happens too: forced sales that go cheap pull prices down.

**Owning.** Owners are paid rent at each quarter's close. Tax and upkeep are taken at the same time.
Without upkeep a building wears five times faster, and a run-down building loses tenants.
Renovating costs 5% of the building's value and restores 25 points of condition. A plot can be
built on. Building always costs more than it adds, so no one can build and sell straight away for
a profit (loophole 7).

**Mortgages.** A bank lends a player up to four years of their salary, less what they already owe.
Mortgages promised behind bids that are still open count against that limit too. The bank wants a
fifth of the price paid down. Interest is the Central Bank rate plus 4%, and the loan is repaid
over 40 quarters. Two missed payments and the bank sells the property.

**The Auction House.** Each lot runs for 24 hours, and a bid in its last five minutes adds five more.
A bidder names the most they will pay, and the Auction House bids for them only as high as it must
to keep them in the lead. Nobody ever sees anybody else's top price. A seller may set a lowest price
that nobody sees either. While the auction runs, the page shows only whether the leading bid has met
it ("✓ The leading bid meets it"); the lot then sells at that lowest price. A bidder's share of the
price is held while the bid stands, and it comes straight back when they are outbid or the auction
ends. A partner can take a share of a bid and then owns that share of the property. Title flaws are
real: about 8% of properties have one. A buyer who skipped the title search loses that part at the
next close.

**Empires.** Before an empire bids, four desks must check the lot:

- Legal Counsel searches the title. The fee is charged once per lot and recorded in the empire's books.
- The Accountant values the lot.
- The Risk Manager sets the top price.
- The Investment Banker arranges the money.

Only after that may the head bid, and never above the Risk Manager's price. When nobody sits at a
desk, the head does that check. An empire never buys from its own members, and a member never buys
the empire's property for themselves.

**Headquarters.** An empire makes a building it owns outright into its headquarters, then raises
its level:

- **Cost.** Level 20 costs about ₦150 million in Lagos, Level 60 about ₦2.5 billion, and Level 120
  about ₦15 billion.
- **Learning.** The headquarters adds 0.3% × √level to what members learn from empire work, doubled
  for work on a client in the city's own industries.
- **Seats.** It adds one seat for every ten levels, in turn across the six builds, up to 12 more.
- **Upkeep.** Upkeep is 1% a quarter of what has been spent on the building. The Risk Manager asks
  for it and the head approves it.
- **Wear and warnings.** Without upkeep the building loses 8 points of condition a quarter, with
  warnings at 50, 30 and 15.
- **Collapse.** Below 15 it may fall down. If it does:
  - its benefits stop and its extra seats freeze;
  - insurance (bought on the Risk tab) pays for the building;
  - members keep their seats and their money;
  - if the warnings were ignored, whoever ignored them loses 5 reputation. That is the Risk
    Manager if they never asked for upkeep, and the head if they refused it.
- **Losing the building.** If a forced sale or a title claim takes the building, the headquarters
  must move to another building the empire owns. A move costs a tenth of what was spent, and the
  level goes with it.

| City | What the headquarters brings | Building costs |
| --- | --- | --- |
| Lagos | the best deals and recruits (members join with 5 less reputation needed), but the dearest land | 150% |
| Abuja | lobbying, stored now and used when the Government stage comes | 120% |
| Port Harcourt | energy deals (double learning on energy clients) | 110% |
| Kano | the cheapest land, trade and farming | 70% |
| Aba | manufacturing | 90% |

**The new work.** There is one new piece of work for each build:

- the Asset Manager judges whether a building is worth its price for its rent;
- the Accountant follows a mortgaged building's cash for a quarter;
- the Investment Banker puts the money for a purchase together (own cash, then a loan, then a partner);
- the Risk Manager stress-tests a mortgage against a fall in prices;
- Legal Counsel reads a title before the client pays;
- the Financial Journalist reports a district's quarter.

Each has its "How to do this". With these, each build's syllabus map has seven modules, so the
later rank gates ask for seven to be proven.

**Existing worlds.** No fresh world is needed. A world made before Stage 8 gets its districts and
property at its next quarter close. This was proved on a copy of the development world: after one
close it had 25 districts, 300 properties, 12 lots open and a clean ledger. It is also covered by
`test_a_world_made_before_stage_8_gets_its_property_at_its_next_close`.

## Money: the ledger

Every naira that moves goes through the double-entry ledger, using these new kinds:

- `rent`
- `property_tax`
- `mortgage_loan`, `mortgage_interest` and `mortgage_repayment`
- `auction_hold` and `auction_release`
- `property_sale`, plus `asset_sale` for companies

Two new holding accounts are used. `property:rents` holds rent between the city's spending and
the owners. `auction:held` holds bid cash, and it ends every run at zero. Mortgages count in the
banks' lending and income. Property tax counts as Government income. A property company's sale
appears in its accounts as an asset sale, against its book value. A company's purchase at the
Auction House appears as capital spending.

## The ten-question loophole check

Each question has a test in `tests/test_property_loopholes.py`. All of them pass.

1. Can a seller bid up their own lot, or buy it back cheaply at a forced sale? No.
2. Can anyone see a lowest price, another bidder's limit, a title flaw, a company's book value, or
   who is bidding? No. The test reads the whole Property page.
3. Can bidding, walking away or being outbid make or lose a kobo? No.
4. Can one salary back mortgages on many bids at once? No. Live bids count against the limit.
5. Can an empire bid without the checks, above the Risk Manager's price, or other than through its
   head? No.
6. Can an empire buy a member's property and so carry its money out? No.
7. Can a player build on a plot and sell at once for a profit? No. Building costs more than it adds.
8. Can a member take a headquarters seat while the headquarters is down? No.
9. Can a leading bidder walk away, or anyone bid after the end? No.
10. Can a partner's cash be held for ever? No. It comes back when the auction ends.

## The independent review: twelve findings, all fixed and tested

The tests are in `tests/test_property_review.py`.

1. **Rounding at settlement.** A price at the winner's top limit could be one or two kobo more
   than the cash held. That could stop the quarter's close. Now:
   - the buyer pays the difference;
   - the last seller takes what rounding leaves;
   - one lot that cannot settle is ended unsold instead of stopping the others.

   The Closing Bell had also been moved under the Auction House by mistake. It is back where it
   belongs.
2. **Late partner answers.** A partner could agree after an auction had ended, and their cash was
   then held for ever. That is now refused, and any asks still waiting are released at the end.
3. **Empires as partners.** An empire could be made a partner without its four checks. An empire
   partner now needs the same checks and the same top price, and never shares a bid on a member's
   property.
4. **Lowest price.** A lone bid at or above the seller's lowest price did not buy. It now buys at
   that lowest price, and the price itself is still never shown.
5. **Closing Bell net worth.** Property was missing from the Closing Bell's net worth because one
   module replaced the list of holdings. It now adds to the list instead.
6. **Title searches.** Legal Counsel could run the title search again and again at the empire's
   cost. It is now charged once per lot and recorded in the books.
7. **Members buying empire property.** A head could buy the empire's property for themselves.
   Members are now refused.
8. **Investment Banker paper.** Every case needed a partner. The cash range is now wider, so some
   cases do and some do not.
9. **Legal Counsel paper.** The wording of the claim did not match the marking. It now says the
   claim is on "the seller's share".
10. **Title claims on a headquarters.** A title claim on a headquarters building left its benefits
    in place. It now stops them until the headquarters moves.
11. **Blame for a collapse.** A Risk Manager who asked for upkeep was blamed when the head refused
    it. Blame now falls on whoever ignored the warning.
12. **Two bids at once.** Two bids placed at the same moment could each miss the other's mortgage.
    One bidder's bids are now placed one at a time.

The ten-year run found one more problem: a property company buying at a forced sale did not show
the purchase in its accounts, which stopped the close. It is fixed and tested in
`test_a_property_company_that_buys_at_auction_books_it_as_capital_spending_and_the_close_balances`.

## The ten-year run (40 quarters)

The run used a fresh world with six players bidding at the Auction House, some with mortgages,
every half day.

| Quarter | Sold | Unsold | Lots players own | Mortgages open | Repossessed | Rate | Inflation | Price index: Lagos · Abuja · PH · Kano · Aba |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 13 | 35 | 13 | 5 | 0 | 12.0% | 4.85% | 103.0 · 107.0 · 113.7 · 90.3 · 90.8 |
| 10 | 27 | 81 | 27 | 14 | 0 | 12.0% | 5.83% | 115.2 · 114.9 · 127.2 · 95.5 · 94.0 |
| 15 | 46 | 127 | 37 | 13 | 5 | 13.5% | 7.28% | 126.5 · 132.7 · 142.9 · 103.6 · 104.9 |
| 20 | 55 | 183 | 37 | 11 | 10 | 12.5% | 6.25% | 140.8 · 146.5 · 157.4 · 111.7 · 112.3 |
| 25 | 62 | 239 | 38 | 11 | 13 | 12.5% | 6.03% | 152.3 · 161.4 · 169.7 · 124.1 · 121.6 |
| 30 | 76 | 293 | 37 | 7 | 21 | 12.5% | 5.68% | 168.5 · 179.2 · 191.6 · 131.6 · 132.3 |
| 35 | 82 | 350 | 38 | 7 | 24 | 12.5% | 6.05% | 187.0 · 201.2 · 210.1 · 147.8 · 143.6 |
| 40 | 90 | 406 | 38 | 6 | 28 | 12.0% | 6.8% | 203.9 · 221.4 · 234.2 · 157.8 · 152.2 |

Ledger audit: clean. Held for bids at the end: ₦0. Rent payments 1,310 (₦243 million), tax payments 1,293. News: 29 forced sales, 6 district rises, 3 title disputes.

What the run shows:

- The ledger audit is clean.
- The held-bids account ends at zero.
- No company had money it could not explain.
- Rent was paid about 1,200 times, and tax about 1,150 times.
- Prices roughly doubled over ten years, as rents followed spending (inflation was about 6% a year).
- Repossessions happened when buyers over-borrowed.
- Forced sales, title disputes and rising districts all made the news.

**Honest limits.**

- Kano and Aba property is weaker than the other cities. This follows their household spending,
  which falls in the base economy. Stage 8 did not cause it.
- The simulated buyers paid around fair value, so bubbles stayed small. Players who overpay will
  make them bigger.
- Many company listings go unsold, because the companies' lowest price is 85–95% of value and no
  computer bids at their own sales. That leaves room for players.

## Screenshots (`docs/screenshots/stage-08/`)

1. The Auction House: live countdowns, "you lead" and "outbid" notices, and partner requests.
2. The districts map, with arrows and border styles as well as colour, and a district's buildings.
3. My property, with its mortgage.
4. Bidding for an empire, with the four desks' checks.
5. The headquarters: level, condition, warnings, upkeep, raising and moving.
6. The real seats, including those the headquarters adds.
7. The Economy page's property panel.
8. The portfolio, with property in what the player owns.
9. On a phone: the Auction House.
10. On a phone: the districts.
11. Light mode.

The accessibility check (axe) found no problems on any of these pages.
