# Stage 4, Part A, slice 2: computer-run investors, prices that move for a reason, and "Why?"

**Status: built and tested.** 458 automated server tests, 13 engine tests and 12 website tests pass.
This is the second of five slices. **The Stage 4 Part A test now passes:** two test players
trade a share, buying pressure raises the price, and "Why?" shows the cause.

Words used below:

- **NPV** (net present value): what a company's future profits are worth in today's money.
- **Investor**: here, one of the three computer-run owners of shares: the pension funds, the small investors and the founders.
- **In a hurry**: a buyer who takes a seller's waiting offer, or a seller who accepts a buyer's waiting bid, is "in a hurry". The one who was waiting is not.

## What this slice does

| Promised for this slice | Done | Proved by (`tests/test_investors.py`) |
| --- | --- | --- |
| Computer-run investors that trade | Yes | `test_investors_keep_orders_waiting_in_every_share_on_both_sides` |
| Prices that move for a reason | Yes | `test_two_players_trade_buying_pressure_raises_the_price_and_why_shows_the_cause`, `test_selling_pressure_lowers_the_price_and_why_says_so` |
| The "Why?" record | Yes | the same two tests; `test_trading_pauses_for_half_an_hour...` |
| **The stage test** | Yes | `test_two_players_trade_buying_pressure_raises_the_price_and_why_shows_the_cause` |
| What each company is worth (NPV), from its filed accounts | Yes | `test_a_company_is_worth_the_value_today_of_its_future_profits`, `test_every_company_is_valued_at_every_filing_from_public_figures_alone` |
| Pension funds start investing | Yes | they are one of the three investors |
| Investors react to filings, not to the news about them | Yes | `test_investors_take_their_orders_off_at_the_instant_new_reports_are_filed` |
| The pause when the whole market falls sharply | Yes | `test_trading_pauses_for_half_an_hour_when_the_whole_market_falls_five_percent` |

Still to come in Part A: the Market page, charts, portfolio, index, watchlist, and the
company page's valuation, NPV, advisory summary and shares in circulation (slice 3); the
Closing Rush and Closing Bell (slice 4); the independent review and report (slice 5).

## How it works, in plain words

**What a company is worth.** Each time a company files its accounts, the game works out
its worth from public figures only:

1. Take its profit after tax over the past year.
2. Expect it to grow for five years: about as fast as prices are rising, plus 2 points,
   adjusted for how its own sales have been growing.
3. After that, expect it to grow only at the Central Bank's 6% target, for ever.
4. Count each future year for less than a naira today. The yearly return investors want
   is the Central Bank's rate, plus an amount for the company's credit rating (2 points
   for AAA up to 18 for D), plus 3 points because a share is riskier than a loan.
5. Add it up and divide by the number of shares.

A company making losses is valued at half the owners' funds left in it, never below ₦1 a share.
So a rise in the Central Bank's rate lowers what every company is worth, and a credit
downgrade lowers one company's. Example: Idanre Cement comes out at about ₦39 a share
after two years, against ₦20 of owners' funds behind each share.

**The investors.** Pension funds, small investors and founders own every share when the
world begins. Each keeps a few orders to buy just below its price and a few to sell just
above, in every share. Each takes its own view of what a company is worth, a little
different each day: small investors' views wander most, founders' least. Small investors
also mark a share up or down on the day's news. Where two investors' views overlap, they
trade with each other. That is why prices move even when no player is trading.

**How buying pressure raises a price.** Buy from an investor and it has fewer shares and
more cash than it wanted. So it raises the prices it will sell and buy at: half a percent
for each order's worth it has sold. Sell to it and it lowers them. Half of the push fades
each trading day.

**"Why?"** On each company's page, under the order form: today's move, whether buyers or
sellers were in the greater hurry and what they paid, what each investor did about it, and
what changed the investors' view of its worth at its last results.

**The pause.** If the whole market falls 5% in a day, trading stops for 30 minutes, once
a day. Orders already waiting can still be cancelled.

**Fees go round again.** Stamp duty, and what the exchange earns in fees, go to the
Government, which spends them like its other income.

## Decisions I made that you did not specify

1. The valuation method and its numbers above. Each is one line to change.
2. An investor's orders are sized to the company: four millionths of its total value
   each, never under ₦500,000 or over ₦20 million. A single new player can move a small
   company's price a little; it takes many players together to move a large one.
3. A share that has never traded starts at what it is worth, not at its owners' funds.
   Once it has traded, only trading moves its price.
4. Investors look at the market every five minutes while it is open.
5. The exchange hands its fees to the Government each quarter. This is a stand-in until
   the exchange is an institution with owners of its own.

## The loophole check

- **Milking the investors.** A player buys enough to push a price up, lets the investors
  react, and sells everything back: at once, or one, two or three days later. Tried at
  six sizes and waits. It loses money every time, because buying from an investor always
  costs more than selling back to it.
- **Painting a price.** Two accounts trade a few shares at the day's top price to make the
  last price jump. While investors' orders are in the book it cannot be done: a buyer is
  always given the cheapest shares first. With the book empty it can, but the investors go
  by what a company is worth and what they themselves have bought and sold, never by the
  last price, so it gains nothing.
- **Reading reports first.** Investors' orders leave the exchange at the same instant the
  new reports are filed, and return within half a minute at new prices. Nobody can read a
  filing and trade against prices set before it.
- **News still to come.** Small investors react to events that have happened, never to
  those decided for later in the quarter.
- **Hidden views.** Each investor's own view comes from the world's secret. Nothing about
  it is sent to players.
- **A year of trading days and four quarter-ends** leaves every naira and share accounted for.

**Two faults the tests caught.** The investors could stay away for up to five minutes
after reports were filed; they now return at the server's next look. And several of my own
tests were trading on the wrong day; fixed.

The independent reviewer runs at the end of Part A (slice 5), as agreed.

## Honest limits

- **Investors lose a little to patient players.** Their views wander from day to day, so
  a player who buys when they are gloomy and sells when they are cheerful can gain a few
  percent. The money comes from the investors, not from nowhere, and their cash is limited.
  It is how real markets treat people who trade on whims.
- **A price far from a company's worth takes days to get there,** because of the 10% daily
  limit. After a surprising set of results a share can sit at its limit for several days.
- **The investors are simple.** They do not yet build positions, chase trends or panic
  together. The ten mindsets shape small investors' reaction to news only.
- **The first look at the market takes about five seconds** (about 800 orders). After that
  a look takes a fraction of a second unless something has changed.

## Run it

```
git pull
docker compose down -v
docker compose up --build
```

Open a company. Under **Trade this share** you now see buyers and sellers waiting, and
**Why is the price where it is?** Trading happens between 12:00 and 22:00 Lagos time; at
other times orders wait for the next opening auction.
