# Floor extras

The owner said "build" on 17 November 2026, choosing Floor extras over personal life, which he dropped because it
strays from the game's purpose. Everything is inside the existing Trading floor tab.

## Plan, in slices
1. **Flash storms and the risk engine** (this slice).
2. **The bank desk:** bankers lend to clients on the Floor, such as short-term money to cover a big order. They judge
   the risk and price the interest.
3. **The wealth desk:** asset managers look after rich computer clients' money on the Floor, each with goals and
   limits, and are judged on how well they serve them.
4. **Bonus day:** at the year's end, the Floor's best are paid by their record: profit, fair dealing and clients kept.
   Cheating or losing clients cuts it.

## Slice 1: flash storms

- **When.** Each ten-minute slot of an open market has one chance in 15 of a storm, drawn from the world's secret so
  nobody knows in advance. That is about one every two and a half hours. There is never one in the floor hour or a
  closed market.
- **What happens.** For 10 minutes the computer clients call every open player desk, and the calls are:
  - four times as often;
  - three times as big;
  - on 15-second countdowns;
  - seven in ten of them in one share: the day's biggest mover (2% or more), or, on a quiet day, a share drawn at random
    "on a rumour".
- **Where it shows.** A red banner across the Trading floor says why the clients are rushing, and a note goes to the
  Floor's news feed. Every open desk is pinged.
- **Afterwards.** The best three banks (by what their prices earned against the market's middle) and the best three
  player clients (by what they saved against the exchange) are named. They earn their empires league points: 3, 2 and 1.

## Slice 1: the risk engine

Every bank's desk has three limits, as at a real bank:
- **the largest single deal** it may price (the Floor's own: ₦300m);
- **the most it may hold in one share** from today's Floor deals (₦800m). That is what it bought from clients, less what
  it sold;
- **the most it may lose in a day** (₦50m): today's Floor deals, marked to the market's price now.

**What the limits do.**
- **A price that would break** the deal or share limit is refused, saying which limit and by how much. The share limit
  only stops a price that would add to the holding. A block is cleared on its own, and a basket is many small deals, so
  neither meets these two limits, but both count towards the day's loss.
- **A day's loss past the limit freezes the desk.** It closes, its live prices are withdrawn, the Floor's news says so,
  and it cannot reopen until the next trading day.

**Who sets them.** The empire's Risk Manager, or its head, sets each of the empire's bankers' limits, up to five times
the Floor's own. A banker with no empire works to the Floor's own limits.

**On screen** (the "Risk engine" panel on the Trading floor):
- **a banker** sees meters for today's loss and the biggest holding in one share against the limits, the one-deal limit,
  and who set them;
- **a Risk Manager or head** sees every banker in the empire, with the same meters and a form to set limits.

**Website.** `GET /api/floor/risk` and `POST /api/floor/limits` (`{banker_id, deal_most, name_most, day_loss_most}`, in kobo).
Migration `068_floor_storms_risk.sql`.

**Tests** (`tests/test_floor_extras.py`):
- a storm floods the open desks (in its share, with short countdowns) and is scored once;
- there is no storm in the floor hour or a closed market;
- a price past the deal or share limit is refused;
- a day's loss past the limit freezes the desk until the next day;
- only the empire's Risk Manager or head sets limits, up to five times the Floor's;
- the routes need a login and good input.
