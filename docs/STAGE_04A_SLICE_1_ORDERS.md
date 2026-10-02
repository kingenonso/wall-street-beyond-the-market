# Stage 4, Part A, slice 1: the order-matching engine and orders

**Status: built and tested.** 437 automated server tests, 13 engine tests and 12 website tests pass.
This is the first of five slices of Stage 4 Part A.
Two players can now trade a share on the Broad Street Exchange.

Words used below:

- **Order**: an instruction to buy or sell a number of shares.
- **At my price** (a limit order): buy at this price or cheaper, sell at this price or dearer. It waits until somebody matches it.
- **At the best price now** (a market order): trade at once with whoever is waiting. What cannot be matched is handed back.
- **Order book**: the list of orders waiting for each share.
- **Held**: when you place an order, the exchange holds the cash (to buy) or the shares (to sell) until the order is done or cancelled.

## What this slice does

| Promised for this slice | Done | Proved by (`tests/test_market.py`, or the engine's own tests) |
| --- | --- | --- |
| The pairing engine, in Rust | Yes | 13 tests inside `engine/`; `test_the_engine_agrees_with_the_rules_on_a_thousand_random_books` |
| Orders: at my price, or at the best price now | Yes | `test_two_players_trade_a_share_and_everything_that_moves_is_in_the_ledger`, `test_an_order_at_the_best_price_available_takes_what_there_is...` |
| Buying pressure raises the price, selling lowers it | Yes | `test_buying_pressure_raises_the_price_and_selling_pressure_lowers_it` |
| Trading fees on every trade | Yes | same first test; `test_splitting_a_trade_into_many_small_ones_does_not_make_the_fee_smaller` |
| The daily price limit of 10% | Yes | `test_nothing_can_be_ordered_or_traded_more_than_a_tenth_from_yesterdays_last_price` |
| Market hours and the opening auction | Yes | `test_orders_placed_while_the_market_is_closed_wait_for_the_opening_auction` and two more |
| A basic order form | Yes | `test_two_players_trade_through_the_website`; screenshots in `docs/screenshots/stage-04a/` |

Still to come in Part A: computer-run investors and the "Why?" record (slice 2), the
Market page, charts, portfolio, index, watchlist and investor numbers (slice 3), the
Closing Rush and Closing Bell (slice 4), the independent review and report (slice 5).

**Until slice 2, nobody but players places orders.** On your own computer a buy order
will simply wait, because no computer-run investor is selling yet.

## How it works, in plain words

1. **You place an order** on a company's page. The exchange at once holds what the
   order needs: the cash for a buy (the price times the shares, plus the fee), or the
   shares for a sale. The same cash or shares cannot be promised to two orders.
2. **The engine pairs it.** The engine is a small separate program written in Rust. It
   is given the waiting orders and the new one, and answers who trades with whom. Its
   rules: the best price goes first; at the same price, first come first served; the
   trade happens at the price of the order that was waiting.
3. **The server checks the engine's answer**, then settles each trade through the
   ledger in one step: shares to the buyer, cash to the seller, fees out.
4. **What is left** waits in the order book, or is handed back if it was "at the best
   price now". An order still unmatched after seven days is handed back.

**Fees.** Buyer and seller each pay 0.5% of the trade: 0.3% to the exchange and 0.2% to
the Government as stamp duty. The fee is worked out on the whole of an order, so
splitting one trade into many small ones does not make it cheaper.

**The daily price limit.** A share cannot be ordered or traded more than 10% above or
below the last price of the day before.

**Market hours.** Orders can be placed at any time. While the market is closed they wait.
At 12:00 Lagos time the opening auction runs: every waiting order that can trade does so
at one price, the price at which the most shares change hands. From 12:00 to 22:00
orders are matched the moment they arrive.

**Dividends.** A player who owns shares is paid dividends like any other owner. Shares
held by the exchange for a sell order still earn their dividend for the seller.

## Decisions I made that you did not specify

1. Fees of 0.5% each side. One line to change.
2. Orders last seven real days (one game quarter), then are handed back.
3. A player may have at most 50 orders waiting.
4. Trading with yourself is allowed, costs fees twice, and is recorded. It harms other
   players, not the game, so it is left for the law stages to punish.
5. Each share is listed at the owners' funds behind it (about ₦20 for most), never
   below ₦1. This is a stand-in: in slice 2 investors value each company from its profits.
6. Only players and computer-run investors may trade. Companies, the Government and
   the exchange itself cannot place orders.

## The loophole check

The ten questions were applied. Automated attacks in `tests/test_market.py`:

- **Money or shares from nothing:** after every one of 1,000 random orders and cancels,
  every naira and share is accounted for, and the exchange holds exactly what its open
  orders say. The same check runs at the end of every game quarter; if it ever failed,
  the quarter would not close.
- **Promising the same thing twice:** the same cash cannot back two orders, nor the same
  shares two sales, including when sent at the same instant.
- **Two at once:** six buyers rushing for the same 100 shares get 100 between them.
- **A wrong engine:** if the engine ever answered wrongly, the server refuses to act and
  nothing is left half-done.
- **Made-up requests:** 14 kinds of bad order from a browser are refused, including
  extra fields such as somebody else's account.
- **Rewriting history:** an order cannot be altered once placed; trades cannot be changed
  or deleted.
- **Other people's orders:** a player cannot cancel or see another player's order.
  Nothing public says who is behind an order or a trade.
- **Dodging fees or limits:** splitting trades does not cut fees; nothing trades outside
  the day's limits, even an old order left over from a day when prices were different.

**A fault the tests caught:** the dividend on shares held for a sell order was being paid
to the exchange. The end-of-quarter check refused to close the quarter, which is how it
was found. It is fixed and tested.

The independent reviewer runs at the end of Part A (slice 5), as agreed.

## Honest limits

- **The order book is read from the database for every order.** That is simple and safe,
  and fast enough for the trial. A very busy share would need the book kept in memory.
- **The first build takes longer.** Docker now also downloads the Rust tools to build
  the engine, once.
- **Stamp duty stays with the Government's reserve** for now; it is not yet spent.

## Run it

```
git pull
docker compose down -v
docker compose up --build
```

Open any company. The new panel **Trade this share** is at the top.
