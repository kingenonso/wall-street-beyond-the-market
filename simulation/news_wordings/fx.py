"""News wordings for the talent and funds stage, Part 4a: the currency desk and money from abroad."""

KINDS = ("fx_devalued", "fx_floated", "fx_repegged", "fx_defended", "fx_reserves_low", "fx_backlog", "fx_gap", "fx_eurobond")

WORDINGS = {
    "fx_devalued": {
        "herald": [
            ("The naira is devalued to {rate}",
             "The Central Bank moved its official rate from {before} to {rate} a dollar, closing the gap with the market. Its reserves cover {cover} quarters of imports."),
            ("Central Bank cuts the naira's value",
             "From {quarter} a dollar costs {rate} at the official window, up from {before}. Importers will pay more."),
            ("A weaker official naira",
             "After months of a widening gap, the official rate is now {rate} a dollar. It was {before}."),
        ],
        "ogene": [
            ("The naira devalued", "Official rate now {rate}. It was {before}."),
            ("Dollar dearer at the window", "{rate} a dollar from {quarter}, up from {before}."),
            ("The window catches up", "The official rate moves to {rate}, near the street."),
        ],
        "ledger": [
            ("Official rate reset to {rate}",
             "The Central Bank devalued from {before}. Reserves cover {cover} quarters of imports. Dollar debts grow in naira terms."),
            ("Devaluation: {before} to {rate}",
             "The official window reprices at {rate} from {quarter}. Firms with dollar borrowings book currency losses."),
            ("The official naira rate is cut",
             "A move from {before} to {rate} narrows the gap between the window and the street."),
        ],
    },
    "fx_floated": {
        "herald": [
            ("The naira floats",
             "With reserves down to {cover} quarters of imports, the Central Bank has stopped setting the rate. A dollar now costs about {rate}."),
            ("Central Bank lets the market price the naira",
             "The official window follows the street from {quarter}. The dollar was {before} at the window."),
            ("No more managed naira",
             "The Central Bank can no longer defend the rate. The market now decides, at about {rate} a dollar."),
        ],
        "ogene": [
            ("The naira set free", "The market sets the rate now. About {rate}."),
            ("Float!", "The window follows the street from {quarter}."),
            ("Reserves too low to defend", "Only {cover} quarters of imports left. The naira floats."),
        ],
        "ledger": [
            ("The naira moves to a float",
             "Reserves at {cover} quarters of imports forced the change. The official rate unifies with the market at about {rate}."),
            ("Exchange rate unified",
             "The official window now tracks the street. The previous official rate was {before}."),
            ("Float announced for {quarter}",
             "Dollar demand will clear at market prices. The gap between window and street should close."),
        ],
    },
    "fx_repegged": {
        "herald": [
            ("The Central Bank takes the naira back in hand",
             "Reserves have recovered to {cover} quarters of imports, and the Central Bank manages the rate again, at {rate} a dollar."),
            ("A managed naira returns",
             "From {quarter} the official window sets the rate once more: {rate} a dollar."),
            ("Reserves rebuilt, the naira is managed again",
             "The Central Bank says it can steady the currency now. The official rate is {rate}."),
        ],
        "ogene": [
            ("The naira managed again", "Official rate {rate}."),
            ("Central Bank back in charge", "Reserves at {cover} quarters of imports."),
            ("The window sets the rate", "{rate} a dollar from {quarter}."),
        ],
        "ledger": [
            ("Return to a managed rate",
             "Reserves at {cover} quarters of imports allow the Central Bank to manage the naira again, at {rate}."),
            ("Official rate re-established at {rate}",
             "The float ends with {quarter}. Expect a gap with the street to open again if dollars grow scarce."),
            ("Managed exchange rate resumes",
             "The Central Bank resumes setting the official rate. It was {before} on the last floating day."),
        ],
    },
    "fx_defended": {
        "herald": [
            ("The Central Bank steps in for the naira",
             "It will sell {amount} of its reserves on the street this quarter to hold the naira near {rate} a dollar."),
            ("Dollars sold to steady the naira",
             "The Central Bank plans to sell {amount} from its reserves. It has {cover} quarters of imports left."),
            ("Holding the line at {rate}",
             "The Central Bank is spending dollars to stop the street running away from the official rate."),
        ],
        "ogene": [
            ("CBN sells dollars", "{amount} to defend the naira."),
            ("Defending the naira", "Official rate {rate}. Reserves {cover} quarters."),
            ("Dollars to the street", "The Central Bank sells {amount}."),
        ],
        "ledger": [
            ("Central Bank intervention: {amount}",
             "Dollar sales on the street aim to narrow the gap with the official rate of {rate}. Reserves cover {cover} quarters of imports."),
            ("FX intervention planned for {quarter}",
             "The Central Bank will supply {amount} to the street. Reserves fall as it does."),
            ("Reserves deployed to support the naira",
             "Sales of {amount} are planned. Watch reserves, now {cover} quarters of imports."),
        ],
    },
    "fx_reserves_low": {
        "herald": [
            ("Reserves run low",
             "The Central Bank's dollars would pay for only {cover} quarters of imports. Dollars at the official window will be scarcer."),
            ("Fewer dollars in the vault",
             "Reserves have fallen to {cover} quarters of imports. The street is likely to pay more for dollars."),
            ("Warning lights on the reserves",
             "At {cover} quarters of imports, the Central Bank has less room to defend the naira."),
        ],
        "ogene": [
            ("Reserves down", "Only {cover} quarters of imports."),
            ("Dollar squeeze ahead", "Reserves at {cover} quarters."),
            ("CBN vault thinner", "{cover} quarters of imports left."),
        ],
        "ledger": [
            ("Reserve cover falls to {cover} quarters",
             "Lower reserves limit window supply and intervention. Expect a wider street premium."),
            ("Reserves below the comfort line",
             "Cover of {cover} quarters of imports raises the risk of devaluation."),
            ("Reserve adequacy weakens",
             "The Central Bank's dollar buffer is down to {cover} quarters of imports."),
        ],
    },
    "fx_backlog": {
        "herald": [
            ("Foreign investors stuck waiting for dollars",
             "{amount} of their money could not leave this quarter. The waiting scares new investors away."),
            ("A dollar backlog builds",
             "Foreign investors who want to sell up are queuing for dollars: {amount} is waiting."),
            ("Money that cannot leave",
             "The Central Bank could not supply dollars for {amount} of foreign investors' money."),
        ],
        "ogene": [
            ("FX backlog", "{amount} waiting to leave."),
            ("Stuck naira", "Foreign investors cannot get out. {amount} waits."),
            ("Queue for dollars", "{amount} in the backlog."),
        ],
        "ledger": [
            ("Repatriation backlog: {amount}",
             "Foreign portfolio investors could not convert {amount}. Expect weaker appetite for Nigerian assets."),
            ("FX backlog emerges",
             "Unmet dollar demand from foreign investors stands at {amount}."),
            ("Foreign exits delayed",
             "{amount} is awaiting dollars. Backlogs tend to deter new inflows."),
        ],
    },
    "fx_gap": {
        "herald": [
            ("The street pays {gap} more for dollars",
             "A dollar costs {street} on the street against {official} at the official window."),
            ("A wide gap opens on the naira",
             "The street is {gap} above the official rate of {official}."),
            ("Two prices for one dollar",
             "Official: {official}. Street: {street}. The gap is {gap}."),
        ],
        "ogene": [
            ("Street dollar {street}", "Window: {official}. Gap {gap}."),
            ("Gap widens", "{gap} between street and window."),
            ("Dollar on the street", "{street}, against {official} officially."),
        ],
        "ledger": [
            ("Parallel market premium hits {gap}",
             "Street rate {street} against an official {official}. A wide premium signals dollar scarcity."),
            ("FX premium widens",
             "The gap between the street ({street}) and the window ({official}) is now {gap}."),
            ("Street-official spread at {gap}",
             "Such gaps tempt round-tripping, which the rules block."),
        ],
    },
    "fx_eurobond": {
        "herald": [
            ("{issuer} borrows {amount} abroad",
             "It sold a dollar Eurobond paying {coupon} a year. The dollars go into the Central Bank's reserves."),
            ("A new dollar bond",
             "{issuer} raised {amount} from foreign investors, at {coupon} a year."),
            ("Dollars borrowed to shore up reserves",
             "{issuer} sold {amount} of Eurobonds paying {coupon}."),
        ],
        "ogene": [
            ("New Eurobond", "{issuer}: {amount} at {coupon}."),
            ("Borrowing in dollars", "{amount} raised at {coupon}."),
            ("Eurobond sold", "{issuer} raises {amount}."),
        ],
        "ledger": [
            ("Eurobond priced: {amount} at {coupon}",
             "{issuer} tapped dollar markets. Proceeds add to reserves. Anyone holding dollars can buy the bond."),
            ("{issuer} issues a dollar bond",
             "Size {amount}, coupon {coupon}. The yield reflects reserve cover and country risk."),
            ("Dollar debt issuance",
             "{issuer} sold {amount}. Debt service will be paid in dollars from the reserves."),
        ],
    },
}
