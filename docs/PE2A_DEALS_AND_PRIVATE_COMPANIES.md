# Private equity stage, Part 2A: deals and private companies

What this part adds: thirty private companies (and start-ups founded during the game), the whole road
to buying one (the data room, six desks' checks, the sale agreement argued clause by clause, sealed
bids or an auction, partners and a buyout loan), running it (the dials, assets that wear, managers,
the airline's routes, the 100-day plan), trouble (pay pressure, the company doctor, administration),
and getting out (another empire, the pension funds, or a listing), with the gain shared and the deal
league. The build names and the menu were changed as you decided on 8 October.

The stage test is
`tests/test_deals.py::test_the_stage_test_a_company_is_checked_by_six_desks_bought_with_a_buyout_loan_run_and_sold_at_a_gain`.
In it the Investment Banker brings a company, Legal Counsel signs the confidentiality agreement,
every desk does its check, Legal Counsel strikes the seller's escape clauses and asks for money to be
held back, the head bids with a buyout loan, the quarter closes and the empire owns the company, its
dials change its next quarter, and it is sold to the pension funds.

Tests at the end of this part: **TESTS_TOTAL on the server** (of which 51 are new: 11 in
`tests/test_deals.py`, 11 in `tests/test_deals_more.py`, 10 in `tests/test_deals_loopholes.py`,
19 in `tests/test_deals_review.py`), 13 on the order-matching engine, 12 on the website. All pass.

## Checklist

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| 1 | Legal Counsel, Financial Journalist, the Intelligence desk | Yes, everywhere a player reads it (codes inside stay the same, so nobody loses progress) | the screens; `firm.DESK_LABELS` |
| 2 | One "Empire" section with tabs | Yes: Overview, Desks, Requests and votes, Deals, Companies, Money, People, Work and events, Risk, Board, War Room. The old addresses still open the right tab | screenshot 01 |
| 3 | A market of private companies, with accounts, debts, market share and management; new ones appear; gems and traps | Yes. Founders put a few up for sale each quarter; the pension funds buy some and sell them on after two years; a start-up is founded each year with the founders' own money | `test_thirty_private_companies_...`, `test_a_start_up_is_founded_...` |
| 4 | 25 to 50 more companies, new industries | 30, in 13 industries, three of them new: airlines, hotels and leisure, shipping and ports | `test_the_world_has_the_new_industries_...` |
| 5 | The data room after a confidentiality agreement by Legal Counsel | Yes | `test_q1_nothing_private_is_seen_without_the_confidentiality_agreement` |
| 6 | The six-build chain of checks; the head approves | Yes: background (Intelligence desk), accounts against the bank (Accountant), valuation (Investment Banker), stress test and site inspection (Risk Manager), ownership and contracts (Legal Counsel); the head bids | the stage test; `test_a_badly_done_check_finds_nothing_...` |
| 7 | Rival bids: sealed, or the seller's auction | Yes. Other empires, the computer-run empires and the pension funds bid | `test_the_auction_is_open_and_each_bid_must_beat_the_highest`, `test_a_bid_that_loses_hands_back_every_kobo_held` |
| 8 | Buyouts with borrowed money, rate by risk, covenants; the bank may call the loan or take control | Yes | `test_the_bank_tests_its_promises_calls_the_loan_and_takes_the_company` |
| 9 | Co-investment and syndicates | Yes: other empires pledge money, held in escrow; each owns its share | `test_partners_put_in_money_and_own_their_share_of_the_company` |
| 10 | The seller's promises; a false one claimed against | Yes, with money held back in escrow | `test_a_false_promise_is_claimed_against_the_money_held_back` |
| 11 | Negotiating clause by clause with the other side's Legal Counsel | Yes (founders and computer-run sellers answer at once; a selling empire's Legal Counsel answers) | `test_f13_...`, `test_f16_...` |
| 12 | Fairness opinion before a large deal; valuation of what has no market price | Yes: above ₦20 billion; every private company is valued each quarter | `firm_deals._prepare("fairness")` |
| 13 | A deal needs all three; each answers for it later | Yes: no bid until all three have signed; each check is a signed opinion judged a year later | the stage test |
| 14 | Dials each quarter | Yes: prices, staff, pay rise, marketing, technology, upkeep, dividend, borrowing, new assets | the stage test; `test_f08_...` |
| 15 | Assets with a life | Yes: they age, wear faster when not kept up, break down, are repaired, sold or replaced | `test_a_neglected_asset_wears_out_and_is_grounded`, `test_f17_...` |
| 16 | Managers | Yes: three candidates a quarter; better costs more and runs it better | screenshot 08 |
| 17 | Competitors answer prices; customers from the consumer groups | Yes: rivals follow a price cut by its size in the industry; how far each city's customers move depends on its mix of the ten kinds of people | `test_rivals_answer_an_owned_companys_price_cut`, `test_customers_weigh_prices_...` |
| 18 | The airline in full | Yes: planes, hangars, routes between the five cities, fares against rivals on the same route | `test_an_airline_flies_routes_...` |
| 19 | The 100-day plan | Yes: six improvements, each with a cost, a time and a chance of failing | `test_the_100_day_plan_costs_money_at_once_and_may_fail` |
| 20 | Company doctor, paid on success | Yes | `test_a_company_doctor_is_paid_only_if_the_rescue_works` |
| 21 | Pay pressure | Yes: pay falling behind the going rate brings slow work, then walkouts (in the news) | `test_pay_that_falls_behind_prices_...` |
| 22 | Company bankruptcy | Yes: assets sold, creditors paid in order, owners last | `test_a_company_that_cannot_pay_its_way_is_wound_up_...` |
| 23 | Sell to an empire, to a computer buyer, or list | Yes, all three | `test_selling_to_another_empire_and_listing_on_the_exchange`, the stage test |
| 24 | The gain split; deal fees | Yes: owners are paid by their shares; on a gain the empire pays the banker who brought the deal and each player who did a check | `firm_owned.exited` |
| 25 | League table of deals and bankers; Deal of the Year | Yes, public | `test_the_league_tables_are_public_...` |

## Decisions I made that you did not specify

- **The pension funds buy private companies too.** The computer-run empires are too small to buy most
  of them, so without another buyer almost every sale failed in the ten-year run. Now the pension funds
  bid a little below a company's worth about half the time, hold it two years, then sell it on.
- **A head may not sell the empire's company for less than 80% of its valuation, and nobody may bid more
  than 150% of a company's worth or its asking price.** Both stop money being moved out of an empire
  through a friendly deal.
- **An empire carries a private company at what it paid** in its worth and the public league, so its
  worth never reveals the company's private figures. Members see the valuation on the Companies tab.
- **A check that puts a problem in front of the empire counts as knowing it,** even if the check is
  answered wrongly. A buyer cannot claim for what it priced in.
- **The bank lends on the papers it is shown**, as the buyer does. A buyer of dressed-up accounts finds
  the bank's promises breaking soon after.

## The loophole check

Ten questions, one test each, in `tests/test_deals_loopholes.py`:

1. Can a player see private accounts or secrets without signing? No.
2. Can a deal create money? No: money in existence is unchanged; the escrow always balances.
3. Can the same cash back two bids? No: it is held in escrow.
4. Can a head sell the members' company to a friend for nothing? No: 80% of valuation at least.
5. Can a head overpay to move money out? No: 150% at most.
6. Can a buyer claim for a fault it found before buying? No.
7. Can a member act for another desk, or another empire's file? No.
8. Can a bid be placed after the quarter ended, before it closed? No.
9. Can a check done badly reveal the right answer? No.
10. Can private shares be traded on the exchange, or counted at a pumped-up value? No.

## The independent review

A second reviewer that did not write the code found 19 problems; all are fixed, each with a test in
`tests/test_deals_review.py`. The two most serious: an auction re-bid with partners would have left the
escrow out of balance and stopped every later quarter from closing; and a resale reset the new owner's
cost to nothing, inflating its gain and its deal fees. Others: claims for problems seen in a check
answered wrongly on purpose; worn-asset claims growing with the buyer's own neglect; an ownership claim
paid twice; failed companies keeping a value; players in computer-run empires running their companies;
one-off dials repeating and passing to a new owner; private figures leaking through a refusal, the bank's
offer and the market share; forced sales at better prices than willing ones; rescue-fee farming; one
small company dragging a whole industry's prices; computer sellers never answering clauses; listing
while on sale; two bids borrowing twice the room; seller answers after the bid; upkeep counted twice;
the dividend stop leaving dial rows; escrow released later missing from the seller's gain.

## The economy still holds

A ten-year run (40 quarters) with the private companies: inflation stayed between 3.5% and 8.6%, the
Central Bank's rate between 11.5% and 14%, jobs grew from 572,000 to 743,000, the ledger audit was clean
and no money moved outside normal business. 13 private companies were sold (to the pension funds),
two failed and were wound up, ten start-ups were founded.

## Honest limits

- When an empire sells its stake through a sale, partners keep their shares with the new owner; when it
  sells to the pension funds, partners sell alongside.
- Marketing and technology are bought from the media and telecoms companies at large; an empire that owns
  one of those may receive some of its own company's spending.
- Part 2B (the banker's deal-making, audit firms, block trades, firms players found, truces and joint
  bids, merging empires, and the fair-play rules around them) is next.

## Screenshots

`docs/screenshots/pe2a/`: 01 the one Empire section; 02 companies for sale; 03 the data room; 04 a
check open; 05 the sale agreement; 06 the bid with the bank's offer; 07 the file; 08 the company owned
(dials, assets, routes, managers, the 100-day plan, ways out, the deal league); 09 bought; 10 on a phone.

## Run it

```powershell
cd $HOME\wall-street-beyond-the-market
git pull
docker compose down -v
docker compose up --build
```

`down -v` starts a fresh world: the private companies are part of how the world begins.
