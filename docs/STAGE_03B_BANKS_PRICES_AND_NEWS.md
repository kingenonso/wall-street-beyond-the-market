# Stage 3, Part B: banks, prices, the Central Bank, events, the Money Watch and the news wire

**Status: built and tested.** 384 automated server tests and 12 website tests pass.
The stage test passes: five game years with inflation inside the Central Bank's band,
and twenty game years (80 quarters) without the economy seizing up, every balance
sheet balancing and every naira accounted for.

Stage 4 (the stock market) is **not started**. It waits for your go-ahead.

Words used below:

- **Inflation**: how much prices have risen over the past year.
- **The Central Bank's rate**: the one interest rate it sets each quarter. Every bank loan follows it.
- **Write off**: a lender stops counting on a loan being repaid, and records the loss.
- **Event**: something that happens on a day: a flood, a strike, a contract won.

## The checklist, item by item

| # | Promised | Done | Proved by (`tests/test_macro.py` unless named) |
| --- | --- | --- | --- |
| 9 | Banks lend for real: households and companies borrow, pay interest set by their credit rating, and banks lose money when borrowers fail | Yes | `test_households_pay_interest_repay_and_borrow_through_the_ledger`, `test_every_bank_loan_carries_the_central_banks_rate_plus_an_amount_for_the_borrowers_rating`, `test_a_lender_loses_money_when_a_borrower_fails`, `test_a_bank_may_lend_only_what_its_own_funds_support` |
| 10 | Insurance: insurers collect premiums and pay claims after floods, fires and other events | Yes | `test_after_a_flood_insurers_pay_for_what_was_destroyed`, `test_insurers_pay_only_what_they_can_afford` |
| 11 | The Central Bank's rate moves by a published rule to keep inflation in its band, and reaches every loan | Yes | `test_the_central_bank_raises_its_rate_when_prices_run_hot_and_cuts_when_they_cool`, `test_each_quarters_rate_is_the_one_the_rule_set_and_the_reason_is_published` |
| 12 | Prices and inflation: a price level measured each quarter | Yes | `test_a_price_level_is_measured_every_quarter`, `test_prices_rise_faster_when_households_spend_more_than_the_economy_can_supply` |
| 13 | Commodity prices that move and feed into company costs | Yes | `test_a_price_shock_moves_the_commodity_and_reaches_the_companies_that_buy_it`, `test_commodity_moves_in_one_quarter_are_bounded` |
| 14 | The ten kinds of computer-run people, each deciding differently | Yes | `test_there_are_ten_mindsets_and_each_location_has_its_own_mix`, `test_each_mindset_decides_differently`, `test_the_same_news_moves_two_cities_differently` |
| 15 | Real causes of good and bad quarters, shown under "Why?"; local events hit companies based there (the half of Part A's item 6 that was left) | Yes | `test_an_event_is_a_named_cause_in_the_filings_of_the_companies_it_touches`, `test_a_local_event_reaches_only_companies_based_there`, `test_good_and_bad_quarters_both_happen` |
| 16 | The Money Watch, first version | Yes | `test_the_money_watch_takes_a_reading_every_quarter`, `test_the_money_watch_warns_when_money_outgrows_the_economy`, and three more below |
| + | The automatic news wire | Yes | all of `tests/test_news.py` |
| 17 | Economy page: inflation, interest rate, commodity prices, Money Watch | Yes | `test_the_economy_page_shows_prices_rates_commodities_and_the_money_watch`, screenshots |
| Stage test | 20 quarters with inflation in band; 80 quarters, books balanced, no naira without a payer | Yes | `test_twenty_game_years_run_and_inflation_stays_in_its_band_for_the_first_five` |

Screenshots are in `docs/screenshots/stage-03b/`.

## How it works, in plain words

**Prices.** Each quarter the game compares what households spent with what the economy
can supply (which grows half a percent a quarter). Sellers expect prices to rise about
6% a year and mark up accordingly; they go faster when spending runs ahead of supply,
slower when it falls short. A commodity getting dearer pushes prices up a little too.
Wages keep pace with prices and never fall.

**The Central Bank.** It aims for prices to rise 6% a year and accepts 3% to 9%. Its
rule is public: one point above its neutral rate of 13% for each point inflation is
above target, a quarter point for each point spending runs ahead of supply. It moves
at most half a point a quarter and holds when its rule points within half a point of
today's rate. The reason for each decision is published in one sentence.

**Banks.** A household's loan costs the Central Bank's rate plus 6 points. A company's
loan costs the Central Bank's rate plus an amount for its credit rating: 2 points for
AAA up to 18 for D. So when the rate moves, every loan moves. Households repay 5% of
what they owe each quarter and borrow again: more when the rate is low and they are
confident, less when it is high or when they already owe more than about three
quarters' income. A bank may lend at most eight times its owners' funds. When a loan
passes its repayment date unpaid, the lender writes off a tenth of it each quarter.

**Where new money comes from.** In one way only: when a bank is short of cash to lend,
it borrows from the Central Bank, which creates the naira. When the bank repays, those
naira go out of existence. The Central Bank lends a bank at most eight times its
owners' funds, and nothing to a bank that has none. The interest banks pay on these
loans goes to the Government, which spends it.

**Events.** There are 23 kinds: floods, power failures, security incidents, port
disruption, pipeline incidents, drought, local booms, strikes, demand surges, good
harvests, network outages, new competition, scandals, contracts won, fires, product
recalls, new products, and jumps or falls in energy, metals and building material
prices. A quarter's events are decided when the quarter before closes, from the world's
secret, and each has a day. Nothing shows until that day. An event changes how many
customers a company draws, its costs, or destroys part of its buildings and machines.
The company's own accounts then follow through the ledger, and its filing names the
event under "Why?".

**Insurance.** Insurers pay 70% of buildings and machines destroyed, and a small sum to
the households of a city struck by something severe. They pay from their own cash and
only what they can afford. After a costly year, the price of cover rises.

**The ten mindsets.** Optimistic, pessimistic, risk-averse, risk-seeking, herding,
contrarian, loyal, fearful, sceptical and opportunistic. Each city has its own mix:
Lagos has more optimists and risk-seekers, Kano more loyal and risk-averse people.
Each mindset reacts in its own way to income, jobs, the interest rate, prices and local
events, so the same news moves each city's spending and borrowing differently.

**The Money Watch.** Every quarter it measures all the money in existence and gives a
reading. Amber: money is growing more than 10% a year and five points faster than the
economy, or prices are rising more than 12% a year, or one group's share of all money
has risen six points in a year, or the Treasury's reserve is running low. Red: money
growing more than 20% a year and fifteen points faster than the economy, or prices
rising more than 20%. On amber the Central Bank adds half a point to its rate; on red a
full point, and new lending is halved the next quarter. It never takes money from
anybody. Separately, any player account that gains more than ₦50 million in a quarter
is put on a private list for a person to look at.

**The news wire.** 60 kinds of news, 9 wordings each (540 in all), in three newspapers'
voices: The Lagoon Herald (people and streets), Ogene News Network (short and fast) and
The Naira Ledger (figures first). Every item is written from a recorded fact and dated
the day it happened. The bigger the story, the more papers carry it. A paper never uses
the same wording twice running for one kind of news. A flood is followed, next quarter,
by its bill under the same story. Small items are gathered into "in brief" columns.
Twenty game years produced about 2,500 items with about 2,200 different headlines. Full articles
written from these facts come in Stage 10, as agreed.

## The long runs

Seven different worlds, five game years each: inflation stayed between 3.5% and 9.1%.
One world touched 9.1% for one quarter after an energy price jump. The Central Bank's
rate moved between 11.5% and 14%.

One world, twenty game years:

| | Start | Year 5 | Year 10 | Year 20 |
| --- | --- | --- | --- | --- |
| Company sales a quarter | ₦2.3tn | ₦4.1tn | ₦5.8tn | ₦13.0tn |
| Jobs at the 50 companies | 536,000 | 625,000 | 694,000 | 855,000 |
| Inflation | 5.9% | 5.7% | 5.2% | 5.8% |
| Central Bank rate | 13% | 12% | 12.5% | 13.5% |
| Money in existence | ₦7.6tn | ₦8.4tn | ₦11.3tn | ₦23.8tn |
| Money Watch | green | green | green | green |

Over those twenty years inflation ranged from 3.5% to 8.5%. Every balance sheet
balanced in every quarter and the ledger's end-of-quarter check never failed.

## Decisions I made that you did not specify

1. Inflation target 6%, accepted band 3% to 9%, neutral interest rate 13%. These are
   close to Nigeria's own official targets in calmer years. One line each to change.
2. New money is created only by Central Bank loans to banks. Stage 2's rule "no naira
   appears after day one" is replaced by "all money is the opening money plus what
   banks owe the Central Bank", checked at the end of every quarter.
3. Wages follow prices fully. Without this, twenty years of 6% inflation made workers
   18% poorer and companies richer.
4. The Money Watch's list of suspect accounts is private and does not change the
   reading. Your design said red when "an account looks like an exploit". The reviewer
   showed two players could then turn the whole country's lending off by passing money
   back and forth. See finding 1 below.
5. News of a company's results comes out over the first three weeks of the next
   quarter, at most four sharp rises and four sharp falls as full stories, the rest "in
   brief". Without the cap, seasonal swings produced a dozen near-identical stories a quarter.
6. While there are fewer than 20 players, their money is counted with "Private
   investors" on the Economy page, so no line shows the players' money alone.

## Stand-ins still in place

- **Bank deposits** are still one fixed figure on each bank's balance sheet. They become
  real accounts when players can bank (Stage 5).
- **Insurance premiums** are still part of what companies buy from each other, not a
  policy with a price. The published "price of cover" is not yet charged.
- **Government** still spends exactly what it collects (Stage 12 gives it a budget).
- **Pension funds** still hold their money until the market opens (Stage 4).
- **A company rated D stays in business.** Winding one up belongs to the law stages.
- **News is written from the true record.** Today the filed record is the same. When
  companies can misreport (later stages), news must be written from what was filed.

## The loophole check

The ten questions were applied to every feature. New automated attacks in
`tests/test_macro.py` and `tests/test_news.py` include: making money for a made-up
reason, a bank lending itself money, destroying money, rewriting past prices or news,
reading news before its day, reading the stored facts behind an item, writing news
from a browser, and odd filter values on the news page.

### What the independent reviewer found

A second reviewer that did not write the code was told to break it and ran its own
attacks. It found twelve things. Nothing was reachable from a browser today, because
Part B adds only two read-only pages, but several would have become live in Stage 4.
All are fixed, each with a test.

| # | What it did | What happened | Fix |
| --- | --- | --- | --- |
| 1 | Two players passed ₦500,000 back and forth 101 times | Money Watch went red, lending was halved, sales fell 15% | The suspect list is private and changes nothing; it counts what an account gained, not what passed through |
| 2 | Paid a player ₦60bn with no quarter number on the payment | Not noticed | The check goes by when a payment was recorded |
| 3 | Caused a slump | Money Watch read "money growing far too fast" (sales had fallen), and made the slump deeper | Warns only when money itself is growing fast |
| 4 | Emptied every bank each quarter | The Central Bank refilled them without limit; money more than doubled; inflation 43%; Money Watch stayed green | Central Bank lending capped by the bank's own funds; Money Watch also watches prices |
| 5 | Paid out new naira as a "share issue"; destroyed naira by paying the Central Bank | Accepted | Each reason is allowed only in its place; the quarter-end check now counts all money against the loan records |
| 6 | Read the "Other" line on the Economy page with one player | It was that player's balance to the kobo | Players are counted with private investors until there are 20 |
| 7 | Compared a visible item's wording with the expected one | Proved a hidden event of that kind was coming, 16 times in 201 quarters | News is written in date order and looks only backwards |
| 8 | Read the news with inflation below zero | "Prices rose 4.8%" when they had fallen 4.8%; "21th"; four wordings that claimed more than the records hold | Fixed |
| 9 | Stored an event of an unknown kind | Every later quarter failed to close | The database refuses unknown kinds |
| 10 | Read story names | They carried internal ids | They carry the market code |
| 11 | Timed it | News lookups had no index | Indexes added |
| 12 | Looked ahead to Stage 4 | Filings are readable before the news about them | Recorded for Stage 4: computer-run traders must react to the filing, not the news |

What it attacked that held: closing a quarter under every odd state it could build
(households drained, all companies drained, insurers empty, extreme events), the money
count after every quarter, loan write-offs, the news page on every day and filter, every
other page for hints of coming events, the randomness of events, and the website's
handling of server text.

## Honest limits

- **Good times outlast bad ones.** After eight quarters the ratings are spread (3 AAA,
  4 AA, 14 A, 18 BBB, 2 BB, 4 B, 3 CCC, 2 D). After twenty years most companies are rated A or better,
  because inflation shrinks old debts and profits pile up. Real pressure comes when
  player-run empires compete with them (Stage 6) and failed companies are wound up.
- **Some banks weaken over twenty years.** Their costs rise with prices faster than
  their income. Two of seven were making small losses by year 20.
- **Inflation can touch the edge of the band.** One of seven trial worlds reached 9.1%
  for a quarter. A real central bank misses too, and the news reports it.
- **The stage test uses one fixed world** so that it repeats exactly. The seven-world
  check above was run by hand.
- **I pushed the fast-forward with one failing test** (`test_world_clock_is_public_and_complete`
  did not know about the new "weeks ahead" figure). The game was not affected. It is fixed here.
- **Closing a quarter takes 2 to 4 seconds** and slows as the ledger grows. It needs
  attention before the trial (Stage 16).
- **The read-only pages have no rate limit** yet (Stage 16).

## Run it

```
git pull
docker compose down -v
docker compose up --build
```

`down -v` throws away the old world: this part changes the database, so a new world is
needed. Then, in a second terminal, move ahead four quarters at a time:

```
docker compose exec server python -m simulation.fast_forward 4
```

Open **News** for the papers and **Economy** for prices, the interest rate, commodity
prices and the Money Watch.
