# Stage 12 — Commodities: the goods themselves, and the desk that deals in them

Two doors into the same machinery. **The investor's door**: buy gold, oil, farm produce
and building materials, pay to store them, take delivery of a futures contract that has
run out, and sell them back. **The firm's door**: run a commodities desk at a bank, quote
hedges to the companies that need them, hedge yourself on the exchange, earn the spread,
and lose money when a gap outruns your hedge.

Crypto is not in this stage and is not planned for it.

## What already exists, and is not rebuilt

The exchange already lists futures on oil, metals, farm produce and building materials
(ten barrels a contract, and ₦10,000 a point for the other three), with margin, an order
book, a clearing house and a default fund. The economy already produces four commodity
price indexes (`energy_bps`, `metals_bps`, `agriculture_bps`, `materials_bps`), and oil
already has a world dollar price carried into naira through the exchange rate. There are
commodity ETFs that follow oil and metals.

What is missing is the goods. Nothing in the game owns a gram of gold or a barrel of oil.
This stage adds exactly that, and hangs the desk on top of it.

## The goods, and their units

Each good is measured in the unit a person would use, and its spot price is fixed to the
contract the exchange already lists — so the price of the goods and the price of a future
cannot drift apart, and nobody can buy one and sell the other for nothing.

| Good | Index it follows | Unit a player buys | Units in one futures contract | Price at par |
|---|---|---|---|---|
| Gold (and other metals) | `metals_bps` | one gram | 1,000 g | ₦100,000 a gram |
| Oil | world oil price × the naira | one barrel | 10 barrels | ₦112,500 a barrel |
| Farm produce | `agriculture_bps` | one 50 kg bag | 2,000 bags (100 tonnes) | ₦50,000 a bag |
| Building materials | `materials_bps` | one tonne | 1,000 tonnes | ₦100,000 a tonne |

A player with the ₦500,000 starting grant can buy five grams of gold, four barrels of oil,
ten bags of produce or five tonnes of materials. The rich buy by the container.

## The market

The market's dealers stand on both sides all day, the way the pension funds' desk already
stands behind options and futures. They sell at an ask above the true price and buy at a
bid below it: 25 basis points a side for gold, 50 for oil, 100 for produce and materials.
Everything the dealers own is held in one place, and every naira still moves through the
ledger. The dealers start with a large stock of each good and a real cash balance. When a
good's stock runs out the market says so and stops selling that good until somebody sells
some; when the dealers run out of cash they stop bidding. No money is created.

Gold is the good that will matter most to a Nigerian player, because it is priced in
dollars and paid for in naira: when the naira falls, the gold in the vault rises without
the world's gold price moving at all.

## Storage, and why holding costs money

Goods do not sit in the air. A player leases space from the market's warehouse operator:
a vault for metal, a tank farm for oil, a silo for produce, a yard for materials. Space is
bought in units, paid for once as a lease, and rented by the quarter. Each kind of space
holds so much and charges so much:

| Space | Holds | Rent a quarter | Insurance a quarter |
|---|---|---|---|
| Vault | 1,000 g of gold | 0.5% of its value | 0.2% |
| Tank farm | 1,000 barrels | 2% of its value | 0.2% |
| Silo | 20,000 bags | 3% of its value | 0.2% |
| Yard | 1,000 tonnes | 2% of its value | 0.2% |

Rent and insurance come out of the holder's cash at the quarter's close. A holder who
cannot pay has goods sold at the bid to cover it, and if that is not enough the lease is
cancelled and the goods are seized. Uninsured goods can be lost — to fire, a leaking tank,
rats or thieves — a small chance each quarter. Insured goods are paid for out of the
insurance pool, which is fed by the premiums; if the pool cannot cover a claim, the holder
carries the shortfall, as in life.

## Delivery: when a future stops being a bet

A player holding a long futures contract in gold, oil, produce or materials can ask, before
its quarter closes, to **take delivery**. At the close the contract does not settle in cash:
the goods arrive in the holder's space, and the holder pays their full value. The final
night's move is still settled as usual, so the holder's total cash out is exactly the price
of the goods. If there is no room in the space, or not enough cash, the contract settles in
cash after all, and the player is told why.

This is the seam between the two halves of the stage. A jeweller who wants metal in the
vault, an airline that wants barrels, a miller who wants bags — all of them are now taking
delivery rather than guessing at a cash payout.

## Carry and contango

A future's price already carries the interest cost of waiting. To that this stage adds
**storage**: the far month costs more than the near month by what it costs to keep the
goods safe in between. That is contango, and it has a real cause in the game rather than a
number someone chose.

But commodity prices in this game drift back towards the general price level — the economy
already does this, at 15% a quarter. So when a shortage spikes the spot price, the future
does not follow it all the way up; and when the spot is high and the curve is flat or
falling, that is **backwardation**, and it is a real signal that the goods are scarce now
and expected to be easier later. A player who can see the shape of the curve can trade it,
and a player who owns the goods can decide whether storing them is worth the rent.

## The desk: the firm's door

A bank can open a commodities desk. Its clients are the companies that already exist in
the game and already have the exposure: the airlines, shipping lines, hauliers, power
companies, mines and fertiliser makers buy fuel; the oil and gas producers sell it;
jewellers and builders want metal and materials.

Each quarter the desk quotes those companies a hedge. A company that accepts pays the desk
a fee and a spread, and gets certainty on its price. The desk does not carry that risk
itself: it hedges on the exchange, through the same clearing house everything else uses.
What the desk keeps is the fee and the spread. What can hurt the desk is the gap between
the two — the client's contract and the exchange contract are not the same thing, the
client can fail before it pays, and a violent move can outrun the hedge. The firm's own
money is at stake, and the head sets the desk's limit.

Nobody gets a seat they are not hired into: the desk belongs to the firm, any member of it
can work the book, and the head decides who may and how much risk the desk may run.

## Where it sits in the game's cycle

At each **closing bell**: the night's marks, and the storage leases looked at.
At each **quarter's close**, in this order: futures settled first (as now), then delivery,
then rent, insurance and loss, then the desk's quarter (quotes, clients, hedges, fees).
Audited with everything else, and a player's holdings counted in their net worth — so
buying gold is never mistaken for losing money.

## The screens

One screen, two faces. The investor sees the four goods, their prices and their curves,
what they hold and where it is stored, and what the space costs. The desk sees the client
book, what has been quoted, what has been accepted, what is hedged and what is not. Both
sit in the terminal's clothes, with the always-on left column, in the same style as every
other screen in the game.

## What will be tested

Every promise above becomes a test: the spot price agrees with the contract price; buying
and selling moves whole kobo through the ledger and nothing else; a player cannot hold more
than their space or sell what they do not hold; rent is charged, unpaid rent is covered by
selling goods, and a lease can be lost; uninsured goods can be lost and insured ones are
paid for; delivery happens only with room and cash, and settles in cash otherwise; the far
contract costs more than the near one by the cost of storage; a desk cannot quote more than
its limit; a client's failure lands on the desk and not on the game; and no player can end
up with naira or goods that came from nowhere.

Then the ten loophole questions, each with a test, and a second AI that did not write the
code, told to break it.
