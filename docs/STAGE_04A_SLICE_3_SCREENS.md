# Stage 4, Part A, slice 3: the market screens

**Status: built and tested.** 481 automated server tests, 13 engine tests and 12 website tests pass.
This is the third of five slices.

Words used below:

- **Index**: one number for the whole market. Ours is the BSX 50.
- **NPV** (net present value): what a company's future profits are worth in today's money.
- **Dividend**: the part of its profit a company pays to its owners.

## What this slice does

| Promised for this slice | Done | Proved by (`tests/test_marketview.py`) |
| --- | --- | --- |
| The Market page: every share, its price and today's move | Yes | `test_the_market_page_lists_every_share_and_the_index_starts_at_one_thousand` |
| The BSX 50 index, with its chart | Yes | the same, and `test_the_index_rises_when_a_large_companys_price_rises...` |
| Price charts | Yes | `test_price_history_and_index_history_are_the_trades_day_by_day` |
| Your portfolio, with dividends | Yes | `test_a_portfolio_shows_what_was_paid_what_it_is_worth_and_the_gain`, `test_dividends_received_show_in_the_portfolio_by_company` |
| A watchlist with price alerts under "Needs you now" | Yes | `test_a_watched_share_raises_an_alert_when_it_reaches_the_players_price`, `test_a_watchlist_has_its_limits` |
| The numbers investors use, each explained in one line | Yes | `test_the_investors_page_gives_valuation_npv_advice_and_who_owns_the_shares` |
| **Valuation** (you asked for this) | Yes | the same test |
| **NPV** (you asked for this) | Yes | the same test |
| **Advisory summary** (you asked for this) | Yes | the same, `test_the_advice_follows_the_price_and_never_says_buy_or_sell`, `test_a_troubled_company_is_judged_on_its_assets...` |
| **Shares in circulation** (you asked for this) | Yes | the same, `test_with_few_players_no_line_shows_what_one_player_holds` |

Screenshots are in `docs/screenshots/stage-04a/` (04 to 07).

Still to come in Part A: the Closing Rush and Closing Bell (slice 4); the independent
review and report (slice 5).

## What is on screen

**Market** (new, in the menu). The BSX 50 with its chart, what all fifty companies are
worth, shares traded today, and a table of every share: price, today's move, shares
traded, the whole company's value, credit rating, and a Watch button. It can be sorted by
size, today's move, shares traded or name.

**Portfolio** (new, in the menu). What you are worth in all; cash you can use and cash
held for your buy orders; each holding with what it cost you, what it is worth and the
gain or loss; dividends received; your waiting orders with a Cancel button; your latest
finished orders.

**Each company's page** has a new panel, **For investors**:

- **Valuation.** What the whole company costs at today's price. Its price against its
  yearly profit, with the market's figure beside it. Its dividend as a share of the
  price. Its price against the owners' funds in it. Each with one line saying what it means.
- **The share price, day by day.**
- **NPV.** What its profits are worth today, per share, beside the price on the exchange
  and the gap between them. Then the sum itself: the past year's profit, the profit
  expected in each of the next five years and what each is worth today, the years after
  that, and the total. The assumptions are stated in a sentence.
- **Advisory summary.** One line (looks cheap, looks about fairly priced, looks
  expensive, or judged on its assets), the reasons, and what could go wrong.
- **Shares in circulation.** How many shares there are, and how many the founders,
  pension funds, small investors and players hold.
- **Watch this company**, with a price to be told at on the way up, on the way down, or both.

**Your desk.** A price alert you set appears first under "Needs you now" once the price
gets there. Your watchlist is in the right-hand column.

## How the figures are worked out

- **The BSX 50** stood at 1,000 when each share was first listed. It is every company at
  its present price against its listing price, each counted by its number of shares, so a
  large company moves it more than a small one.
- **What your shares cost you** is the average-cost method: every purchase adds its cost
  and fee; every sale takes away the average cost of the shares sold.
- **The advisory summary** compares the share price with the NPV. Within a tenth either
  way is "about fairly priced"; more than a tenth below is "cheap"; more than a tenth above
  is "expensive". A company making losses has no profits to value, so it is "judged on its
  assets". The risks are read from its filing: a weak credit rating, overdue debts, a loss,
  heavy borrowing, falling profit.

Every figure comes from what the company filed, its credit rating, the Central Bank's
rate and prices on the exchange. Nothing hidden is used.

## Decisions I made that you did not specify

1. "Advisory summary" is an analyst's note on the share. You were asked whether you meant
   something else and did not object.
2. The note never says "buy" or "sell" and promises nothing. It is deliberately not always
   right: the investors each take their own view around the NPV, so a share can stay
   "cheap" or "expensive" for a while. A test checks the wording on all fifty companies.
3. A watchlist holds at most 30 companies. An alert stays on your desk for as long as the
   price is past it; change or remove it on the company's page.
4. While there are fewer than 20 players, their shares are counted with the small
   investors, as on the Economy page.

## The loophole check

- **Other people's portfolios and watchlists.** A player sees and changes only their own.
  Another player cannot read or remove a watchlist entry.
- **A single player's holding.** The company page used to list every account that held
  the share, one line each. That would have shown each player's holding once players
  owned shares. It now shows owners by kind only. This was a fault from slice 1, found
  here and fixed with a test.
- **The exchange as an owner.** Shares the exchange holds for a sell order were being
  shown as owned by the exchange. They count as their seller's.
- **Made-up requests.** Eight kinds of bad watchlist request are refused, including a
  made-up player id.
- **Nothing hidden is shown.** The pages carry no account, no player name and none of the
  investors' own views.
- **Strangers.** Every new page refuses anybody not logged in.

The independent reviewer runs at the end of Part A (slice 5), as agreed.

## Honest limits

- **Charts need two trading days** before they draw a line.
- **Alerts are checked when you open your desk.** Nothing is sent to your phone or email.
- **The index does not yet adjust for new shares** being issued. That matters when
  companies raise money in Part B, and will be handled there.
- **The price history is worked out from the trades each time.** Fine for the trial;
  a busy market would keep a daily summary.

## Run it

```
git pull
docker compose down -v
docker compose up --build
```

Then open **Market** and **Portfolio** in the menu, and any company's page.
