# The Floor's features and events, 16 November 2026

Built on the owner's "ok build" after The Floor, on the branch `floor-events`, in the order agreed with him: duels on the
Floor, then big client orders and the live deal tape, then the Archegos moment.

## Duels on the Floor

The owner chose a duel on the Floor in the real world over the October idea of a private copy of the world.

- **The challenge.** An empire's head challenges another empire for the next live event, until ten minutes before its
  bell. An empire the computer runs always accepts; a player-run empire's head accepts or declines. One duel for an
  empire at each bell.
- **The score.** For each side: what the event did to its money (its event result, which counts its trades and Floor
  deals in the touched shares), plus what its members earned as banks on the Floor during the event, both as a share of
  what the empire was worth at the bell, so a small empire can beat a big one. Both see the score live, split into
  the event's part and the Floor's.
- **Points.** The winner gets 8 league points; a draw gets 3 each. Once only.
- **Declines.** Free, but three in a season (not answering by the bell counts) are shown beside the empire's name, as
  the owner decided. No point penalty.
- **Where.** The Floor → Duels (a tab), and `DUEL` on the desk's command line.

Where: migration `058_floor_duels.sql`; `simulation/duels.py`; settings `DUEL_*`; routes `GET /api/floor/duels`,
`POST /api/floor/duels/challenge|answer|withdraw`; `web/src/Duels.tsx`. Tests: `tests/test_duels.py` (3).

## Big client orders, and the deal tape

- **Big client orders.** Now and then a computer pension fund or insurer hands a free asset manager a big order: buy so
  many shares of a company. At a live event's bell every free asset manager is offered one in the featured share. The
  manager has five minutes to take it on or turn it down, then thirty minutes (or until the live event ends) to buy the
  shares, with their own cash, on the exchange or from the banks on the Floor. It is worth up to 60% of their free cash.
  At the deadline the fund takes what they bought for it (never more than it asked for) at the market's average price
  over the window (every trade on the exchange and the Floor, weighted by size) and pays 0.15% commission. Buying below
  the average is the manager's gain; above it, their loss. Scored as the manager's average against the market's, and
  counted on Proven Talent's "On the Floor" (orders, done in full, average against the market).
- **The deal tape.** A strip along the top of the trading floor: every deal on the Floor and every exchange trade of
  ₦10 million or more, newest first. A computer bank is named; a player's desk is "a desk"; a client never is. Blocks are
  marked.
- **The squawk.** A switch on the tape: the Floor's notes (the bell, halfway, big moves, the floor hour) are read out
  loud as they come. Off at first; remembered in the player's own browser.

Where: migration `059_floor_mandates.sql`; `simulation/floor.py` (`mandates_tick`, `answer_mandate`, `settle_mandate`,
`tape`); settings `FLOOR_MANDATE_*`, `FLOOR_TAPE_EXCHANGE_NAIRA`; the route `POST /api/floor/mandate`. Tests:
`tests/test_floor.py` (1 more).

**Honest limit:** big client orders are orders to buy only, for now. An order to sell would need the fund to hand the
manager its shares first; it can come later.

## The Archegos moment

Modelled on Archegos Capital, March 2021, when the banks that sold first lost little and the last out lost billions.

- **Prime brokerage.** Now and then a computer hedge fund (Kestrel Capital, Obsidian Bay Partners and others) asks every
  open bank desk to hold shares of one company for it on a swap: up to 30% of the desk's free cash. A banker who takes it
  on buys the shares at the market price with their own cash and holds them; the fund posts 20% of the value with the
  bank as margin. The banker has ten minutes to answer. **Each bank sees only its own swap**: never how much the fund
  asked of the others, nor whether it will blow up.
- **Most close quietly.** When its time is up (three to eight hours), the fund buys the shares back at the market price,
  takes its margin back and pays 3% interest.
- **Some blow up.** About a third, decided from the world's secret when the fund starts. The fund misses its margin
  call: the banks keep its margin and are left with its shares. The share falls 12% at once, another 20% ten minutes
  later, and bounces 5% twenty minutes after that. Every banker holding it gets a red pop-up wherever they are in the
  game: sell before the next fall, or be the last out. The Floor's notes call each fall, and how many banks were still
  holding at the second: the last out. Each bank's record shows whether it got out before the first fall, the second,
  or not at all.

Where: migration `060_floor_prime.sql`; `simulation/prime.py`; settings `FLOOR_FUND_*`, `FLOOR_SWAP_*`,
`FLOOR_BLOWUP_*`; the route `POST /api/floor/swap`; the "Prime brokerage" panel and the red pop-up. Tests:
`tests/test_prime.py` (2).

**Honest limits:** the computer banks are not in the fund's swaps (only players' desks); and the fall is set by the
game's rule, on top of whatever the banks' own selling does to the price, rather than coming only from that selling.

## Prediction markets (The Floor → Predictions)

Players bet Yes or No on things the game itself decides. A winning share pays ₦100; a losing one pays nothing.
The price of Yes is the crowd's chance that it happens: if Yes costs ₦70, the crowd says 70%.

**The questions** (opened by the tick, one per subject):
- Will the Central Bank raise the policy rate at this quarter's close?
- Will each of the six largest companies make a bigger profit this quarter than last?
- Will the next live event be a bank run?
- In a live event, will the featured share end lower than it started? (Open while players can still predict.)

**The price.** The computer makes the market by a fixed rule (the logarithmic market scoring rule, depth 2,000 shares),
so there is always a price, and every purchase moves it. Money goes between the player and the public-investors account,
which acts as the house. Buyers' costs round up and sellers' proceeds round down, so the house never pays for rounding.

**Answers** come only from the game's own books: the economy's results, the companies' results and the live events' end
prices. Nobody can rig them. A question that cannot be answered (an event that never came) is void and stakes are handed back.

**Limits.** One player may have at most ₦5,000,000 in one question. The Government Leader may not bet on the rate,
because they can set it by decree. Sell back any time before the close at the price then.
