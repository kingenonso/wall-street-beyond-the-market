# The talent and funds stage, Part 3: Index funds and ETFs

The owner said "build" on 30 October 2026 for Part 3, the third step in the order in `notes/proposal-global-markets-2026-10-29.md`.
The question about 2x and inverse ETFs went unanswered, so the recommended answer was used: they are allowed, behind a Level gate and a warning.
This report covers:
- the game's family of indexes;
- ETFs, which copy an index and trade on the exchange all day;
- index funds;
- passive money;
- players' own ETFs, index funds and indexes.

Part 3 had ten loophole tests and an independent review. The review found 14 problems. Every one was fixed and tested.
The ten-year runs found eight more, all fixed and tested:
- **Indexes counted only price moves.** ETFs keep the dividends they are paid, so every quarter they ran about 2% ahead of their index. The share indexes now count dividends as if they were put straight back in, as real "total return" indexes do.
- **Bond indexes counted only prices too.** Meanwhile the bond funds collected the interest, so the bond ETF ended 92% ahead of its index. Bond indexes now count interest and repayments as if put back in.
- **A bond repaid at the quarter's close still showed its last price** until the next bell, so a fund could have bought a bond that no longer existed. It now leaves every fund's shopping list at once.
- **Index funds were valued at different prices from their index,** so they seemed to track it badly. They now use the same prices.
- **The passive share of the market was measured unevenly.** In a crash the market was valued at once, but ETFs at the last bell, so the passive share seemed to jump. Bond funds were also counted against the share market. Both sides now use the same prices, and only share funds count.
- **The tracking record missed the biggest day of each quarter.** That day is the bell after the quarter closes, when results and dividends move prices. It now counts.
- **Passive funds kept taking money they could not invest.** Once the market's dealers ran out of the largest companies, new money sat as cash: up to a fifth of some funds, so they fell behind their index. New cash now goes in only while the shares can be bought.
- **Funds could not reinvest their dividends** once the dealers had run out, and held up to a third of themselves in cash. Now, as a last resort, the founders and insiders sell to the funds, at 1% above the market price, as insiders do in real markets when funds keep buying. Their stake shrinks, so more of the company counts as freely traded.

One more problem turned up in an older part of the game while testing, and was fixed:
- **Companies' savings landed on a bank by chance.** A company with no lender picked a bank by its random ID. In about one test world in seven, a large insurer's ₦13.5 billion went to the smallest microfinance bank. That bank could not earn the interest it had to pay, and slid into a crisis. Companies now spread their savings in proportion to each bank's size, and the pick is fixed by the world's secret, so a world always repeats.

Nothing on Part 3's list was dropped or put off. Following the owner's standing rule, nothing new was added to the sidebar:
- **Indexes and ETFs** are a tab inside Markets.
- **Index changes, ETF news and big money flows** come as pop-ups.
- **An index fund** is launched from the Funds tab, as in Part 2.
- **Tracking records** appear on the factsheets and in Proven Talent.

Tests at the end: [[TESTS]]

## Things worth knowing, said plainly

1. **What an index is.**
   - A list of companies (or bonds) and one number that shows how they are doing together. Every index starts at 1,000.
   - **The eight indexes:**

     | Index | What it holds |
     |---|---|
     | BSX Top 30 | the 30 largest companies by the value of their freely traded shares |
     | BSX Banks | every listed bank |
     | BSX Oil & Gas | every listed oil and gas company |
     | BSX Consumer | every listed food, drinks and household goods company |
     | BSX High Dividend | the ten best dividend payers of the last year, for their size |
     | BSX Property | every listed property and construction company |
     | Federal Government Bond | every government bond and bill still to be repaid |
     | Company Bond | every company bond still to be repaid and not in default |

   - **Weighting:** each company counts by the value of its shares that are freely traded. Shares held by founders, or by any one owner with 30% or more, do not count.
   - **Cap:** no company is above 15% of an index. An index with fewer than seven members uses one and a half times an equal share instead.
   - **Dividends:** the share indexes count dividends as if they were put back in. A fund that keeps its dividends therefore follows its index.
2. **Index reviews.**
   - Every index is reviewed as each quarter closes.
   - Changes are announced at once and made at the third bell after.
   - Everybody sees the change coming, and index funds must buy what joins and sell what leaves. So **trading around an index change is lawful**, and players can profit from knowing passive money must move.
   - A share split does not move an index.
3. **What an ETF is.**
   - A fund that copies an index, whose units trade on the exchange all day like a share.
   - Its **value** (called iNAV) is shown live: what its holdings are worth, divided by its units. Its **price** is whatever buyers and sellers agree.
   - Dealing costs 0.05% each side, paid to the exchange.
   - **Market makers** (the pension funds) always quote a price to buy and to sell, about 0.2% either side of value, plus a "mood" (premium or discount) that moves each day.
4. **Why the price stays close to value: approved dealers.**
   - An empire worth ₦500 million or more, with a clean record, can be approved as a dealer.
   - A dealer makes new units, or hands units back, in blocks of 10,000:
     - against a basket of the shares the ETF holds (0.05% fee);
     - or against cash (0.25%), with the ETF buying the basket.
   - When the price is above value, a dealer makes units cheaply and sells them. When it is below, they buy units and hand them back. That pulls the price back to value, and the dealer keeps the gap.
   - Making units for cash works only while the shares can be bought (from the pension funds, the small investors, or as a last resort the founders). When they cannot, the dealer is told to use a basket.
5. **Special ETFs.**
   - **Top 30 2x (TOPL)** moves twice the index each day. **Top 30 Inverse (TOPI)** moves the opposite way. Both reset daily, so over many days they do not simply double or reverse the index.
   - **Oil (OILX)** and **Gold & Metals (MTLX)** follow the commodity prices.
   - To buy or make 2x and inverse units, a player must be Level 15 or above in any build and must first read and accept a warning.
   - Their market makers quote wider (0.5%), and their price may stray further from value (1.5% before dealers step in, against 0.75%).
6. **The computer's own funds.**

   | Fund | Copies | Yearly fee |
   |---|---|---|
   | Broad Street Top 30 ETF (TOPX) | Top 30 | 0.20% |
   | Broad Street Banks ETF (BNKX) | Banks | 0.30% |
   | Broad Street Oil & Gas ETF (OGX) | Oil & Gas | 0.35% |
   | Broad Street High Dividend ETF (DIVX) | High Dividend | 0.35% |
   | Broad Street Government Bond ETF (GBND) | Government bonds | 0.15% |
   | Top 30 2x Daily (TOPL) and Inverse Daily (TOPI) | Top 30 | 0.75% |
   | Oil (OILX) and Gold & Metals (MTLX) | commodities | 0.50% |
   | Broad Street Top 30 Index Fund | Top 30 | 0.25% |
   | Broad Street Bond Index Fund | Government bonds | 0.20% |

7. **Launching your own.**
   - An Asset Manager of Level 20 or above can launch an ETF or an index fund (one fund at a time, with Part 2's registration of ₦2 million and at least ₦5 million of their own money).
   - The manager chooses the index (a game index, or their own), the fee (at most 1% a year), and the method:
     - **full copy:** every member;
     - **sampling:** the largest members, up to 80% of the index.
   - An ETF still worth under ₦50 million at two quarter ends running (after its first two) is closed.
   - Fees can be lowered later, never raised.
8. **Your own index.**
   - A Level 20 Asset Manager can publish up to three indexes of their own, each with 5 to 30 companies.
   - Its members can change once a quarter. Holders are told, and no orders are placed ahead of the change, so nobody can trade ahead of it.
9. **Passive money.**
   - The households put a growing share of the share market into index funds and ETFs: 3% at the start, 3% more each game year, up to 35%.
   - Each quarter they move a quarter of the way to that target. They pick the cheapest, closest-copying funds first.
   - They put in only what the funds can actually invest.
   - The game shows the "passive share" of the market.
10. **Tracking.**
    - Every quarter, each fund's return is set against its index:
      - the **difference** is how far behind or ahead it ended;
      - the **tracking error** is how much the daily gaps swing.
    - Both are published on the factsheet and decide where the households' money goes.
11. **Futures and options** on the Top 30, Banks and Oil & Gas indexes, alongside the BSX 50's.
12. **News and pop-ups.**
    - Index changes, for holders and followers.
    - An ETF closing 1% or more from its value.
    - Record money flowing into or out of a fund.
    - New ETFs launched.
13. **Where it shows.**
    - **Net worth and Portfolio:** ETF units count, valued at the lower of their price and their value.
    - **Proven Talent:** a manager's tracking record, and a new "Tight tracker" badge.

## Honest limits

- The funds buy and sell their shares directly with the market's dealers (the pension funds and the public) at the latest price, not through the exchange. Passive money therefore does not push prices up as it would in real life. The 1% the founders ask is the only sign of it.
- Founders who sell to the funds have fewer votes on their boards over the years.
- A player who bought up every spare share of a large index member could stop new units being made for cash until shares were available again. Making units against a basket still works.

## The ten-year run (40 quarters, with the earlier stages running)

[[RUN]]

## Screenshots (docs/screenshots/etfs-3/)

1. An index change pops up
2. The Indexes & ETFs tab in Markets
3. An ETF: its price against its value, and its basket
4. A 2x ETF and its warning
5. An index: its rules and members
6. The ETF you run
7. Publishing your own index
8. Futures and options on the Top 30
9. and 10. On a phone: indexes and ETFs, and an ETF
11. and 12. Light theme: indexes and ETFs, and an ETF

The accessibility check (axe) found nothing on any of them.
