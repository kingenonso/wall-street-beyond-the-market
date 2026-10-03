# Stage 4, the rest: the Closing Bell, bonds, share offers, votes and takeovers

This report covers everything in Stage 4 after the first three slices: slice 4 (the
Closing Rush, the Closing Bell and what an investor reads), the extra screens agreed
from the Wall Street Raider excerpts, Part B (companies and the Government using the
market), the starting grant paid in parts, and the independent loophole review.

The first three slices have their own reports: `STAGE_04A_SLICE_1_ORDERS.md`,
`STAGE_04A_SLICE_2_INVESTORS.md`, `STAGE_04A_SLICE_3_SCREENS.md`.

Tests at the end of the stage: **576 on the server**, 13 on the order-matching engine,
12 on the website. All pass.

## Checklist

### Slice 4

| Agreed | Done | Proved by (`tests/test_closing.py`) |
| --- | --- | --- |
| The Closing Rush: the last ten minutes of the trading day | Yes | `test_the_closing_rush_is_the_last_ten_minutes_of_the_trading_day` |
| Fees reduced in the rush (halved) | Yes | `test_fees_are_halved_in_the_closing_rush_and_full_before_it`, `test_an_order_filled_partly_before_the_rush...`, `test_splitting_an_order_in_the_rush_never_makes_its_fees_smaller` |
| Large orders shown as they arrive, size but no name | Yes | `test_a_large_order_in_the_rush_is_shown_to_everybody_without_a_name` |
| The Closing Bell: winner, loser, boldest move, what is next | Yes | `test_the_closing_bell_names_the_days_winner_loser_and_boldest_move_from_real_records` |
| The daily market advisory inside it | Yes | the same test |
| A price ticker across the top of every screen | Yes | `test_the_ticker_carries_every_share_and_the_index`, screenshot 09 |
| A personal advisory summary and a net worth chart | Yes | `test_the_personal_advisory_points_at_idle_cash...`, `test_the_bell_writes_down_what_each_player_is_worth_and_the_portfolio_charts_it` |
| Profit per share, with its chart | Yes | `test_profit_per_share_is_filed_profit_divided_by_filed_shares` |
| Results compared with the same quarter a year ago (news and company page) | Yes | `test_results_are_compared_with_the_same_quarter_a_year_ago`, `test_results_news_compares_profit_with_the_same_quarter_a_year_ago` |
| Cash outlook: in or out, and an estimate three months ahead | Yes | `test_the_cash_outlook_is_todays_cash_plus_the_average_change_of_the_past_year` |
| Highest and lowest price of the year; date of next results | Yes | `test_the_years_high_and_low_come_from_real_trades_and_the_next_results_date_from_the_clock` |

### The extra screens

| Agreed | Done | Proved by |
| --- | --- | --- |
| Market heat map | Yes | screenshot 12; figures from `test_every_industry_shows_its_growth...` |
| Growth by industry | Yes | the same test, `test_industry_growth_is_not_shown_until_two_years_are_filed` |
| Companies ranked by share of their industry | Yes | the same test |
| A written results report for each company each quarter, from filed figures only | Yes | `test_the_written_results_report_says_only_what_was_filed` |

### Part B

| Agreed | Done | Proved by |
| --- | --- | --- |
| The full bond range | Yes | `tests/test_bonds.py` (37 tests) |
| Government bills: interest on idle cash | Yes | `test_a_bill_bought_today_is_repaid_in_full_when_the_quarter_closes`, `test_a_bill_earns_only_for_the_time_it_is_held` |
| A first sale of shares to the public (IPO) | Built and tested; see "Honest limits" | `test_a_company_not_yet_on_the_exchange_lists_its_shares...` |
| Later sales of shares, and rights issues | Yes | `tests/test_corporate.py` |
| Share splits | Yes | `test_a_split_gives_every_owner_more_shares_each_worth_less_and_nobody_gains` |
| Shareholder votes | Yes | `test_a_large_issue_needs_the_owners_vote...`, `test_a_vote_counts_for_the_shares_held_when_it_is_counted...` |
| Takeovers, agreed and hostile | Yes | `test_a_player_accepts_a_takeover_offer...`, `test_a_low_offer_the_board_rejects_can_fail...` |
| What follows a takeover (integration) | Yes | `test_after_a_takeover_the_joining_is_worked_out_once_a_quarter...` |
| One Trade menu grouped by kind of asset | Yes | the Market section's tabs, screenshots 09 to 13 |
| Who controls each company | Yes | `test_who_controls_a_company_is_whoever_holds_more_than_half`, screenshot 13 |
| The index adjusts for new shares | Yes | `test_new_shares_do_not_move_the_index` |
| The starting grant paid in parts | Yes | `tests/test_grants.py` (9 tests) |

### The stage test from the design

*Two test players trade a share. Buying pressure raises the price. "Why?" shows the cause.*
It passes (slices 1 and 2).

## What each part does, in plain words

**The Closing Rush.** From 21:50 to 22:00 Lagos time each side of a trade pays 0.25%
instead of 0.5%. Any order of ₦250,000 or more that a player places in those ten
minutes appears on a public list: the share, buy or sell, how many. Never who.

**The Closing Bell.** At 22:00 the server writes one broadcast for the day from the
day's trades: the index, the biggest winner and loser, the largest single trade, the
day's main headlines, a market advisory and what comes next. The advisory reads the
Central Bank's rate, inflation and growth from published figures. Nothing dated later
in the quarter can appear in it.

**Quick facts and the results report.** Each company page now shows profit per share
by quarter, sales and profit against the same quarter a year ago, where its cash is
heading, its highest and lowest price over the past game year, when it next reports,
its place in its industry and who controls it. Below that is a report of the latest
quarter in sentences, built only from what the company filed.

**Bonds.** A bond is a loan that can be bought and sold. Each is repaid at ₦1,000.

| Kind | What it is |
| --- | --- |
| Government bill | A three-month loan to the Government. No interest payments: bought for less than ₦1,000, repaid at ₦1,000 |
| Government bonds | Two, five and ten years, paying the same interest each quarter |
| Floating-rate | Its interest moves with the Central Bank's rate |
| Inflation-linked | Its face value rises with prices |
| Company bond | A loan to a company; "high-yield" if the company was rated below BBB |
| Convertible | A company bond its holder can swap for shares |
| Project and green | Raised for one named project |
| Distressed debt | Any bond whose company is rated CCC or D, or behind with its debts |

Every bond shows two prices: a fair value worked out in the open, and what the bond
desk will sell and buy it for. The Government sells its own bills and bonds itself, as
many as are asked for. Company bonds are bought from the pension funds, who hold them.
Everything is sold back to the pension funds. The yield curve (what lending to the
Government pays, by length of loan) and credit spreads are published on the page.

**The Government borrows.** It now spends about 3% more than it collects and borrows
the difference by selling bonds to the pension funds. What its borrowing costs comes
out of what it spends. Its reserve is not touched.

**Share offers.** A company announces a sale of new shares when a quarter's results
are filed. Players apply during the following quarter; the cash is held. When that
quarter closes the shares are issued and unused cash comes back. In a rights issue
only whoever holds the shares at the close may buy, in proportion.

**Share splits.** A share costing ₦100 or more is split after a vote. Every owner
holds more shares, each worth less. Price history and portfolios are restated.

**Votes.** New shares worth more than a tenth of the company, splits and very large
purchases go to a vote. A vote counts for the shares held when it is counted.

**Takeovers.** About one quarter in three, a strong company offers to buy 60% of a
smaller one in its industry at 20% to 45% above the market price. If the target's
board thinks it too low the bid is hostile and goes straight to shareholders. It
succeeds if owners of more than half the shares accept. Afterwards the two businesses
are joined over eight quarters: the planned savings can be cut by staff leaving,
customers lost, a clash of working cultures, the regulator, or the buyer's own debts.

**The starting grant.** ₦100,000 on joining. Four further parts of ₦100,000: a first
trade with somebody else; holding a share through a quarter's close; holding a
Government bill or bond through a close; taking part in a company decision. At most
one part in twenty hours.

## Decisions I made that you did not specify

| Decision | Why |
| --- | --- |
| Bonds trade at a desk, not on the order book | It is how bond markets work, and it gives every bond a buyer and a seller from the first day |
| Everything a company does on the market is settled at a quarter's close | It is the one moment the computer-run investors have no orders standing, so nobody can trade against a stale price |
| A "large order" in the rush is ₦250,000 or more, players only | Half a full grant. The investors' own standing orders would otherwise flood the list |
| In a rights issue nobody gets more than their own rights | Shares below the market price for whoever asks would be free money |
| A sale of new shares to anybody is at the market price | The buyer saves the trading fee, nothing more |
| A target stays on the exchange after a takeover, with the buyer owning most of it | Common in Nigeria. Folding two companies into one is left for when players run companies |
| The four grant steps and the twenty-hour gap | You asked me to set them |
| Corporate announcements also appear as "Notices from the exchange" | A permanent official record beside the newspapers' stories |

## The loophole check

### The independent review

A second reviewer, who did not write the code, was told to break Stage 4. It ran real
attacks in its own copy of the game. It found five serious holes, one medium and four
small ones. All are fixed, and each attack is kept as a test in `tests/test_review4.py`.

| # | The attack | What happened | The fix |
| --- | --- | --- | --- |
| 1 | Bought a convertible bond after the share had risen, swapped it, sold the shares | ₦500,000 became about ₦955,000 in a quarter, every quarter | The desk never sells the right to swap for less than the shares are worth |
| 2 | Bought a takeover target's shares from the investors and handed them to the bidder | ₦500,000 became ₦625,000. The investors were pricing in an offer only for the first company in the alphabet (a slip of mine) | Fixed. The same attack now loses money |
| 3 | Bought bills in the seconds after a quarter ended, before the server closed it | A full quarter's interest for holding 25 seconds | Nothing is sold in that gap |
| 4 | Bought a bill every 0.2 seconds while a quarter was closing | The close failed about half the time and had to be retried | A purchase now waits for a close that is running |
| 5 | Made one 1-share trade in a share | Its price froze for ever once its worth moved more than a tenth; its rights issue then raised nothing | A price stuck beyond the day's limit steps to the limit once a day; new shares are priced from the lower of price and worth |
| 6 | Bought the inflation-linked bond just before each close | A steady edge of about 1.3% a week | Its value no longer sags and jumps |
| 7 | Voted while holding no shares | Earned a grant part | Only a shareholder can vote |
| 8 | Bought Government bonds from the Treasury | Lifted what the pension funds paid | Treasury purchases no longer move the desk's prices |
| 9 | Read a bill's "outstanding" figure with two players | It was the other player's holding | Hidden while players are fewer than twenty |
| 10 | Four leads the reviewer could not prove | | Closed anyway: public offers at the market price; a CCC or D company's bond is not replaced at full value; what players have offered a bidder does not move the investors' prices |

**What the reviewer tried that held:** fourteen quarters with six players holding odd
positions of every kind (every close succeeded, every check clean); 26 splits in one
close; bond round trips of every size; nine applications at the same moment; 472 random
orders through a Closing Rush; odd values on every request; one player trying to read
another's applications, votes, bonds and net worth.

### The ten questions

| Question | Answer for this stage | Tests |
| --- | --- | --- |
| 1. Something for nothing? | No. Every bond, share and naira issued has a payer; the database refuses any other reason | `test_the_database_itself_refuses_bonds_or_money_made_for_the_wrong_reason` |
| 2. Over and over for gain? | Bond round trips always lose; fee splitting never helps | `test_no_run_of_buying_and_selling_at_the_desk_ever_makes_money`, `test_two_accounts_working_together_cannot_milk_the_desk` |
| 3. Two requests at once? | One grant part is paid once | `test_two_requests_at_the_same_moment_pay_a_part_once` |
| 4. Odd values? | Refused | `test_the_desk_refuses_what_cannot_be_done`, `test_an_application_can_be_changed_or_withdrawn...`, the server tests |
| 5. Seeing what one must not? | No names, no single player's holdings, nothing dated later | `test_the_closing_bell_never_hints_at_an_event_that_has_not_happened_yet`, `test_the_bond_page_does_not_show_what_a_few_players_hold_between_them` |
| 6. Acting as somebody else? | Only players trade, apply, vote and accept | the "cannot take part" and "cannot trade" checks |
| 7. Timing? | The gap after a quarter's end is closed; rights go with shares held at the close | `test_nothing_is_sold_in_the_moments_after_a_quarter_ends...`, `test_rights_go_with_the_shares_held_when_the_offer_closes` |
| 8. Altering records? | Trades, bells, notices and index levels are permanent | `test_the_closing_bell_cannot_be_rewritten` |
| 9. Made or destroyed? | Checked at every close: the ledger, the exchange's books and the offers' books | `test_after_eight_quarters_the_bond_market_is_whole`, `test_over_two_years_companies_use_the_market...` |
| 10. Slow or stuck? | See honest limits | |

## The economy still holds

Ten game years on fast-forward with all of this running: inflation between 3.8% and
8.7%; the Central Bank's rate between 12% and 14%; the ledger and both sets of books
clean at every close; the Treasury's reserve unchanged. In that run companies made 16
rights issues and 10 public offers, split 4 shares, issued or replaced 43 bonds and made 11
takeover offers (8 succeeded).

## Honest limits

- **No IPO will happen yet.** The machinery is built and tested, but all 50 companies
  are already listed. The first real IPO comes when players found companies (Stage 6).
- **Players cannot yet make a takeover offer.** Companies make them; players accept,
  refuse and vote. Player bids come with empires (Stage 6).
- **Rights cannot be sold on their own.** They go with the shares.
- **Full merger of two companies into one, spin-offs and selling a division** are not
  built. They are in the design's "what companies can do" but not in Stage 4's list.
- **In a new world's first quarter the pension funds have no cash**, so a player cannot
  yet sell a bond back to them. Their cash arrives at the first close.
- **Two accounts of one person can earn "first trade" by trading with each other.**
  The reviewer noted it. The twenty-hour gap slows it; a phone check would stop it.
- **The heat map's tile sizes are rough.** Larger companies get larger tiles, not exact areas.
- **A quarter's close takes longer than before** (about 2 to 3 seconds each), and
  read-only pages still have no rate limit. Both are Stage 16 work.
- **Personal tax is not built.** The design lists tax on investment gains, a yearly tax
  deadline and a Tax Authority. It belongs with the Government (Stage 12). Everything
  it will need is already on record: gains made, dividends and interest received.
- **Left out on purpose, as agreed:** a "Buy" or "Sell" rating; pause, speed and
  cheats; starting as a tycoon; crypto; the other game's look and wording.

## Screenshots

In `docs/screenshots/stage-04/`: 08 the desk with the Closing Bell and the grant; 09 the
Market with the ticker; 10 bonds and bills; 11 offers, votes and bids; 12 the heat map
and industries; 13 who owns what; 14 a company's quick facts and results report; 15 the
portfolio; 16 industries on a phone.

## Run it

```
git pull
docker compose down -v
docker compose up --build
```

In a second PowerShell window, to move a test world eight quarters ahead:

```
docker compose exec server python -m simulation.fast_forward 8
```
