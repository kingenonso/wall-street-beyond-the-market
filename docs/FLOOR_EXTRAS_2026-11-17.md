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

## Slice 2: the bank desk

The owner said "go on" on 17 November 2026. Bankers lend short money on the Floor, as a bank's money desk does.

- **Asking.** A client asks for ₦1m to ₦2bn, for 1, 3, 7 or 14 game days (a game day is about 1 hour 52 minutes), from one
  to five banks (the computer banks and the open player desks), giving them 15 to 60 seconds. A player may borrow on the
  Floor at most what they are worth after their debts, and not while a loan of theirs is in default. Three requests may
  wait at once.
- **The credit file.** Every bank sees a grade from A to D and the purpose. For a player the grade comes from what they
  owe against what they are worth: A owes a quarter or less, B as much or less, C up to twice, D more than that, or worth
  nothing, or a loan in default, or a Floor loan not repaid. The banker also sees the worth, the debts and the Floor
  history. Each grade has a chance of failing over a year (A 2%, B 8%, C 25%, D 60%); a loan's chance is that times its
  days over 360. The panel shows it, and the expected yearly loss after the 40% recovered.
- **Pricing.** A bank answers with a yearly rate, at most 90%. A computer bank asks the Central Bank's rate, plus twice
  the expected loss, plus 3%, give or take 1%. A player banker may undercut or charge more as they judge the risk, and may
  change their rate until the countdown ends. A loan is one deal under the desk's one-deal limit, and the banker lends
  their own cash, so a frozen desk, or one short of the cash, cannot price.
- **Taking.** A player client takes a rate within 30 seconds of the countdown's end. A computer client takes the cheapest
  at the end. The lender pays the money over at once.
- **Repaying.** On the due day the borrower pays back the money and the interest. A player may repay early, paying at
  least a day's interest. A player who cannot pay all of it owes the rest as a debt in default, collected from their
  cash, shares and bonds each quarter (the game's existing shortfall rules). A computer client fails by chance, drawn
  from the world's secret: it pays back 40% of the money, the lender bears the loss, and the Floor's news says so.
- **The books.** A loan lent counts in the lender's worth until repaid; a loan owed counts in the borrower's debts.
  Interest earned and losses on loans closed today count in the desk's day's result, so a big failure can freeze a desk.
- **Computer clients** ask each open player desk for ₦20m to ₦250m about once every 20 minutes, with two computer banks
  as rivals, for one of five purposes (a big order before its own money comes in, a margin call, redemptions and so on).

**On screen.** A "Bank desk" panel on the Trading floor: "Borrow" (your file, the form, the rates coming in, your loans
with "Repay now") and, for a banker, "Lend" (requests at your desk with the file and a rate box, and the loan book with
its record).

**Website.** `GET /api/floor/bank`; `POST /api/floor/bank/ask` (`{amount, days, seconds, desks}`), `/quote` (`{ask_id,
rate_bps}`), `/take` (`{ask_id, quote_id}`), `/repay` (`{loan_id}`). Migration `069_floor_bank.sql`.

**Tests** (`tests/test_floor_bank.py`):
- a client borrows, the computer banks price from the grade, a banker undercuts and lends, and it is repaid with interest
  on the due day;
- a player who cannot repay owes the rest in default and may not borrow again;
- a computer client borrows from the cheapest desk and may fail, paying back 40%, which counts towards the day's loss;
- amounts, terms, rates, the one-deal limit, the banker's cash and the borrower's worth are all checked, and an
  untaken request expires;
- a player repays early, paying at least a day's interest;
- the routes need a login and good input.

**Not in this slice:** borrowing for an empire's account (the player's own account only), and league points for lending.

## Slice 3: the wealth desk

The owner said "Ok go ahead" on 17 November 2026. Asset managers look after rich computer clients' money on the Floor
and are judged on how well they serve them.

- **Clients arrive.** While the market is open and an asset manager is playing, a client arrives about once every two
  hours (each half hour, one chance in four; at most three looking at once). It brings ₦200m to ₦2bn and is one of five kinds:

  | Kind | Wants | Most in shares | Least cash | Biggest fall | Goal a year | Will not hold |
  |---|---|---|---|---|---|---|
  | retired couple | steady income, savings safe | 30% | 15% | 8% | 12% | |
  | family office | growth over many years | 90% | 3% | 25% | 25% | |
  | church foundation | steady growth, clean | 60% | 5% | 15% | 18% | consumer goods and drinks, hotels and leisure, film |
  | doctors' pension scheme | a balance | 60% | 8% | 15% | 18% | |
  | young tech founder | fast growth, risk | 100% | 0% | 40% | 35% | oil and gas, mining |

- **Pitching.** For two game days asset managers pitch a yearly fee (at most 2%) and a share of the gain above the
  client's goal (at most 20%). The client works out what each pitch would cost it in a year (the fee, plus the share of an
  expected 4% beyond its goal) against each manager's record (how happy their clients were at reviews, less a point for
  every client lost), with a little chance, and picks the best. With no pitch it goes elsewhere. A manager looks after at
  most three clients. The money moves from the households into the client's own account.
- **Managing.** The manager trades the client's account on the exchange at prices they name. A share in an industry the
  client will not hold is refused. The client's order may not meet the manager's own or their empire's. A manager who
  dealt in a share for themselves just before the client did is noted by the Money Watch (never shown).
- **Breaches.** Every ten minutes of an open market the limits are looked at: too much in shares, too little cash, or a
  fall from its high past what it accepts. Each is recorded once a day (a fall once a quarter) and costs satisfaction
  (10 points, a fall 20, out of 100; a client starts at 60). Three in one quarter and the client leaves at once.
- **The quarter's review.** At each close the client judges the quarter against a fair benchmark: the share index for
  the part it would hold in shares, and a quarter of the Central Bank's rate for the rest. It pays the fees from its cash
  (a quarter of the yearly fee on what it is worth, and the share of any gain above a quarter of its goal), and its
  satisfaction moves by three times how far it beat or missed the benchmark (at most up 20 or down 30). Below 30 it
  leaves; below 45 it warns; at 75 or more after beating the benchmark it adds a tenth more money; otherwise it stays.
- **Leaving.** A client that leaves takes everything back: open orders are cancelled and its cash, shares and bonds go
  back to the households. The Floor's news says so. A manager may hand a client back; that counts as a client lost.

**On screen.** A "Wealth desk" panel on the Trading floor: the manager's record, each client looked after (worth, the
quarter, satisfaction, meters against its limits, holdings, a box to deal for it, orders waiting, limits broken, reviews,
and "Hand the client back"), and the clients looking for a manager, each with its limits and a pitch form.

**Website.** `GET /api/floor/wealth`; `POST /api/floor/wealth/pitch` (`{client_id, fee_bps, perf_bps}`), `/trade`
(`{client_id, ticker, side, quantity, limit_price}`), `/cancel` (`{client_id, order_id}`), `/hand-back` (`{client_id}`).
Migration `070_floor_wealth.sql`.

**Tests** (`tests/test_floor_wealth.py`):
- a client arrives, takes pitches and picks on cost, a record of clients lost outweighs a small saving in fees, and with
  no pitch it goes elsewhere;
- pitches are an asset manager's, within the fee limits and three clients;
- the manager trades the client's own account, never in a banned industry;
- breaches are recorded once a day, and three in a quarter and the client leaves with everything;
- at the close the client pays its fees, is reviewed once, and an unhappy one leaves;
- a very happy client adds money, and a manager may hand a client back;
- the routes need a login and good input.

**Not in this slice:** a manager misusing a client's money is noted by the Money Watch but is not yet a court case (the
courts' list of wrongs is also being changed on the juries branch, so that waits for the merge). Fees go to the
manager's own account, not their empire's.
