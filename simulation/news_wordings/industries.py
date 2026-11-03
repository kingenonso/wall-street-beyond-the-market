"""Wordings for news that happens to the six industries added in Part 4c.

These are the trouble and the luck of the medicine makers, the miners, the film and music
houses and the payments firms. A wording may use only the facts its kind carries: for a whole
industry, the industry's name, how severe it is and which companies it touched; for one
company, its name, its ticker, where it is, its industry and how severe it is.
"""

KINDS = ("drug_shortage", "bad_batch", "bumper_harvest", "mine_accident", "seam_runs_out",
         "film_flops", "film_hit", "payments_outage")

WORDINGS = {
    "drug_shortage": {
        "herald": [
            ("Medicine supplies run short across {sector}",
             "Pharmacies and clinics are working through a shortage of supplies. Those affected include "
             "{companies}. The shortage is described as {severity}."),
            ("A hard week for the {sector} trade as supplies dry up",
             "Shipments have failed to arrive and the {sector} companies are buying what they can. "
             "{companies} report that prices have risen. The shortage is rated {severity}."),
            ("Patients wait longer as {sector} supplies fall short",
             "Patients are waiting longer for their medicines. Those caught up in the shortage include "
             "{companies}, and it is described as {severity}."),
        ],
        "ogene": [
            ("Medicine shortage bites: {companies} affected",
             "Supplies of medicines are running short in shops and hospitals. The shortage is rated {severity}."),
            ("Supplies fail: {sector} firms running short",
             "Shipments have not arrived and {companies} are affected. It is described as {severity}."),
            ("{sector} firms caught by a supply gap",
             "Pharmacies report thin shelves. Affected: {companies}. The shortage is rated {severity}."),
        ],
        "ledger": [
            ("{sector} supplies short: costs expected to rise",
             "A shortage of supplies is expected to raise costs for the {sector} companies. Affected: "
             "{companies}. The shortage is rated {severity}."),
            ("Supply gap puts {sector} margins at risk",
             "With shipments failing to arrive, {companies} face higher prices. The shortage is described "
             "as {severity}."),
            ("{sector} makers pay more as supplies run short",
             "Buying what they can is costing more. Those affected include {companies}. The shortage is rated "
             "{severity}."),
        ],
    },
    "bad_batch": {
        "herald": [
            ("Bad batch forces a recall at {company}",
             "A batch of goods has been taken back after complaints from customers. The company works in "
             "{sector} and is based in {location}."),
            ("{company} pulls a batch after complaints",
             "Shops have been asked to return the goods. {company} works in {sector} and is based in "
             "{location}. The matter is described as {severity}."),
            ("A bad batch puts {company} on the back foot",
             "The {ticker} company has recalled a batch of its goods. Customers in {location} complained "
             "first. It is rated {severity}."),
        ],
        "ogene": [
            ("Breaking: {company} recalls a batch",
             "The {sector} company, based in {location}, has pulled goods from shops. Rated {severity}."),
            ("{company} pulls goods off shelves",
             "Complaints led to a recall. The company works in {sector} and is based in {location}."),
            ("{company} hit by a bad batch",
             "A recall is under way. The {sector} company is based in {location}. Rated {severity}."),
        ],
        "ledger": [
            ("{company} recalls a batch as sales and costs both suffer",
             "The {sector} company, listed as {ticker}, has recalled goods. It is based in {location}. "
             "Rated {severity}."),
            ("Recall at {company} ({ticker}) puts the quarter at risk",
             "Goods have gone back to the maker. The {sector} company is based in {location}. Rated {severity}."),
            ("Investors watch {company} after a recall",
             "A bad batch has cost {company} sales and added cost. The company is based in {location}. "
             "Rated {severity}."),
        ],
    },
    "bumper_harvest": {
        "herald": [
            ("A good season on the farms lifts the {sector} trade",
             "Farmers who had a strong harvest are buying more. Those with goods to sell include {companies}. "
             "The season is described as {severity}."),
            ("Farmers buy more {sector} after a strong harvest",
             "Money from a good crop is going back into the ground. {companies} report busier weeks, and the "
             "season is rated {severity}."),
            ("A bumper crop means busy weeks for {sector}",
             "Demand has risen since the harvest came in. Affected: {companies}. The season is described as "
             "{severity}."),
        ],
        "ogene": [
            ("Good harvest lifts {sector} demand",
             "Farmers are buying again. The busiest of them: {companies}. Rated {severity}."),
            ("Farms buying: {sector} trade busy",
             "A strong season has put money in farmers' hands. Affected: {companies}."),
            ("Strong season for {sector}",
             "Orders are up after a good harvest. Affected: {companies}. Rated {severity}."),
        ],
        "ledger": [
            ("{sector} sales rise after a good harvest",
             "Farmers are spending on their next crop. Those selling to them include {companies}. The season "
             "is rated {severity}."),
            ("A good harvest puts money in {sector}'s hands",
             "Demand has climbed since the crop came in. Affected: {companies}. Rated {severity}."),
            ("Demand for {sector} climbs after a strong season",
             "The harvest has lifted orders. Affected: {companies}. The season is rated {severity}."),
        ],
    },
    "mine_accident": {
        "herald": [
            ("Accident at a mine run by {company}",
             "Work has stopped at one of the company's sites. {company} works in {sector} and is based in "
             "{location}. The accident is described as {severity}."),
            ("Work stops at {company} after a mine accident",
             "Digging has halted at one site. The {sector} company is based in {location}. The accident is "
             "rated {severity}."),
            ("A bad day at {company} as an accident halts digging",
             "One of its mines has stopped. The {ticker} company is based in {location}. Rated {severity}."),
        ],
        "ogene": [
            ("Breaking: accident at a {company} mine",
             "Work has stopped. The {sector} company is based in {location}. Rated {severity}."),
            ("{company} halts work after an accident",
             "Digging has stopped at one site. The company is based in {location} and works in {sector}."),
            ("Accident stops digging at {company}",
             "The {ticker} company has halted one of its mines. Based in {location}. Rated {severity}."),
        ],
        "ledger": [
            ("{company} ({ticker}) loses output after a mine accident",
             "Work has stopped at one of its sites. The {sector} company is based in {location}. Rated "
             "{severity}."),
            ("Mine accident cuts {company}'s quarter",
             "Output has stopped and repairs will cost money. Based in {location}. Rated {severity}."),
            ("Output and repair bills hit {company}",
             "A stoppage at one of its mines has cost the company output. It is based in {location}. Rated "
             "{severity}."),
        ],
    },
    "seam_runs_out": {
        "herald": [
            ("Ground gives out at a mine run by {company}",
             "The company has moved to poorer ground. {company} works in {sector} and is based in {location}. "
             "Rated {severity}."),
            ("{company} moves to poorer ground as a seam runs out",
             "The easy ore is gone at one of its mines. The {sector} company is based in {location}. Rated "
             "{severity}."),
            ("Thinner ground for {company} as a seam ends",
             "Digging the same amount now costs more. The {sector} company is based in {location}. Rated "
             "{severity}."),
        ],
        "ogene": [
            ("Seam runs out at {company}",
             "The company is moving to poorer ground. Based in {location}. Rated {severity}."),
            ("{company}: mine ground gives out",
             "One of its seams is finished. The {ticker} company is based in {location} and works in {sector}."),
            ("Poorer ground for {company}",
             "Ore is harder to reach. The company is based in {location}. Rated {severity}."),
        ],
        "ledger": [
            ("{company} ({ticker}) digs poorer ground as a seam ends",
             "The {sector} company is working ground that yields less. Based in {location}. Rated {severity}."),
            ("A seam runs out: {company} faces higher costs",
             "Costs will rise as the good ground is exhausted. Based in {location}. Rated {severity}."),
            ("Lower grade ore puts pressure on {company}",
             "The company must dig more for the same output. Based in {location}. Rated {severity}."),
        ],
    },
    "film_flops": {
        "herald": [
            ("A quiet opening for {company}'s new release",
             "Cinemas were half empty in the first week. The {sector} company is based in {location}. Rated "
             "{severity}."),
            ("{company}'s big release fails to find an audience",
             "Few tickets were sold in {location} and elsewhere. The {sector} company is rated {severity}."),
            ("Slow ticket sales for {company}",
             "The new release has taken less than hoped. The {sector} company is based in {location}."),
        ],
        "ogene": [
            ("{company}'s release flops",
             "Cinemas were quiet in {location}. Rated {severity}."),
            ("Poor opening for {company}",
             "The new release drew small crowds in {location}. Rated {severity}."),
            ("{company}: the crowds stayed away",
             "Ticket sales are weak. The {ticker} company is based in {location} and works in {sector}."),
        ],
        "ledger": [
            ("{company} ({ticker}) takes less than hoped at the box office",
             "The {sector} company's new release drew small crowds in {location}. Rated {severity}."),
            ("A flop costs {company} dear",
             "Ticket sales are weak and the cost was high. Based in {location}. Rated {severity}."),
            ("Weak takings put {company}'s quarter at risk",
             "The new release has not found its audience. Based in {location}. Rated {severity}."),
        ],
    },
    "film_hit": {
        "herald": [
            ("{company} has a hit on its hands",
             "Cinemas were full in the first week. The {sector} company is based in {location}. Rated "
             "{severity}."),
            ("Crowds turn out for {company}'s new release",
             "Ticket sales have been strong in {location} and elsewhere. The {sector} company is rated "
             "{severity}."),
            ("A strong opening for {company}",
             "The new release has taken more than expected. The {sector} company is based in {location}."),
        ],
        "ogene": [
            ("Hit release for {company}",
             "Crowds are filling cinemas in {location}. Rated {severity}."),
            ("{company} packs the cinemas",
             "The new release is drawing crowds. The {sector} company is based in {location}. Rated {severity}."),
            ("Big opening for {company}",
             "Ticket sales are strong. The {ticker} company works in {sector} and is based in {location}."),
        ],
        "ledger": [
            ("{company} ({ticker}) beats expectations at the box office",
             "The {sector} company's new release drew crowds in {location}. Rated {severity}."),
            ("A hit lifts {company}'s quarter",
             "Strong ticket sales have come at the right time. Based in {location}. Rated {severity}."),
            ("Strong takings for {company}",
             "The new release has found its audience. Based in {location}. Rated {severity}."),
        ],
    },
    "payments_outage": {
        "herald": [
            ("Payments fail as the systems go down",
             "Shoppers were turned away and tills stopped working. The {sector} companies affected include "
             "{companies}. The outage is described as {severity}."),
            ("Shoppers turned away as payments stop working",
             "Cards and transfers failed for hours. Those affected include {companies}. The outage is rated "
             "{severity}."),
            ("A day of failed payments for customers and shops",
             "Tills and transfers stopped working. The {sector} companies caught up in it include {companies}. "
             "Rated {severity}."),
        ],
        "ogene": [
            ("Payments down: transactions failing",
             "Cards and transfers are failing. Affected: {companies}. Rated {severity}."),
            ("Outage stops payments",
             "Shops cannot take payment. The {sector} firms affected include {companies}."),
            ("Payments fail across the country",
             "Transfers and card payments are down. Affected: {companies}. Rated {severity}."),
        ],
        "ledger": [
            ("Payments outage hits the {sector} firms",
             "Transactions failed for hours. Those affected include {companies}. The outage is rated "
             "{severity}."),
            ("Failed payments put a quarter's fees at risk",
             "The {sector} companies earn a fee on every payment. Affected: {companies}. Rated {severity}."),
            ("Outage costs {sector} firms sales",
             "Payments stopped, and the fees with them. Affected: {companies}. The outage is rated {severity}."),
        ],
    },
}
