"""News wordings for the talent and funds stage, Part 3: index changes and ETFs."""

KINDS = ("index_change", "etf_launched", "etf_off_value", "etf_flows")

WORDINGS = {
    "index_change": {
        "herald": [
            ("{index} changes its line-up",
             "The index provider says {adds} will join {index}, and {drops} will leave. Funds that copy the index must buy and sell on the day."),
            ("Who is in and who is out of {index}",
             "Joining {index}: {adds}. Leaving: {drops}. Traders expect busy dealing when the change is made."),
            ("A reshuffle for {index}",
             "The quarter's review brings in {adds} and drops {drops}. The change is made at the third closing bell from now."),
        ],
        "ogene": [
            ("{index} review",
             "In: {adds}. Out: {drops}."),
            ("Changes to {index}",
             "{adds} join. {drops} leave."),
            ("{index} line-up shifts",
             "Index funds will buy {adds} and sell {drops}."),
        ],
        "ledger": [
            ("{index} rebalance announced",
             "Additions: {adds}. Deletions: {drops}. Passive funds tracking the index will trade at the effective close, and the announcement is public."),
            ("Index review: {index}",
             "The provider adds {adds} and removes {drops}. Expect index buying in the newcomers and selling in the leavers."),
            ("{index}: constituents change",
             "{adds} enter and {drops} exit at the third bell from now. Weights are reset to the published rules at the same time."),
        ],
    },
    "etf_launched": {
        "herald": [
            ("A new ETF: {etf}",
             "{manager} has launched {etf}, which copies {index}. Its units trade on the exchange under the code {code}."),
            ("{code} starts trading",
             "Savers can now buy the whole of {index} in one go, through {etf}, run by {manager}."),
            ("{manager} launches {etf}",
             "The new fund copies {index} and trades all day like a share, under the code {code}."),
        ],
        "ogene": [
            ("New ETF: {code}",
             "{etf} copies {index}."),
            ("{etf} launched",
             "Run by {manager}. Trades as {code}."),
            ("{code} on the board",
             "A new way to buy {index}."),
        ],
        "ledger": [
            ("{etf} ({code}) lists",
             "{manager} launched an exchange-traded fund tracking {index}. Approved dealers can create and redeem units against the basket."),
            ("New tracker: {code}",
             "{etf} gives investors {index} in a single unit. Its basket and value are published through the day."),
            ("{manager} brings {code} to market",
             "The fund replicates {index}. Tracking error and fees will decide how much money it draws."),
        ],
    },
    "etf_off_value": {
        "herald": [
            ("{code} trades {gap} {side} its worth",
             "{etf} closed {gap} {side} the value of what it holds. Dealers who can make and unmake units may close the gap."),
            ("A gap opens at {etf}",
             "Units of {etf} ended the day {gap} {side} their true value, a chance for the quick-footed."),
            ("{etf} drifts from its value",
             "Buying and selling pushed {code} {gap} {side} the value of its shares."),
        ],
        "ogene": [
            ("{code}: {gap} gap",
             "Closed {gap} {side} value."),
            ("{etf} off its value",
             "{gap} {side} at the bell."),
            ("Gap at {code}",
             "Price {gap} {side} what it holds."),
        ],
        "ledger": [
            ("{code} at a {gap} gap to NAV",
             "{etf} closed {gap} {side} net asset value. Authorised dealers can arbitrage the gap through creations or redemptions."),
            ("{etf}: price and value part",
             "The closing price sat {gap} {side} the fund's value per unit. Watch for dealers stepping in."),
            ("NAV gap widens at {code}",
             "Flows left {etf} {gap} {side} its iNAV at the close. Such gaps rarely last."),
        ],
    },
    "etf_flows": {
        "herald": [
            ("{amount} moves {side} {fund}",
             "Savers moved {amount} {side} {fund} this quarter, as money follows funds that simply copy the market."),
            ("Big money {side} {fund}",
             "{fund} saw {amount} move {side} it over the quarter."),
            ("Savers and {fund}",
             "This quarter {amount} went {side} {fund}."),
        ],
        "ogene": [
            ("{amount} {side} {fund}",
             "Index money on the move."),
            ("Flows: {fund}",
             "{amount} {side} it this quarter."),
            ("{fund} flows",
             "{amount} moved {side} it."),
        ],
        "ledger": [
            ("Record flows: {fund}",
             "{amount} moved {side} {fund} this quarter, as the passive share of the market keeps changing."),
            ("{fund} sees {amount} of flows",
             "Passive allocations moved {amount} {side} the fund. Index vehicles compete on fees and tracking."),
            ("Passive money and {fund}",
             "Quarterly flows {side} {fund} reached {amount}, driven by households' allocations to index funds."),
        ],
    },
}
