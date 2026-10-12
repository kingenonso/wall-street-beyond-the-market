"""News wordings for the rest of the world (economy upgrade): the oil price, the naira, and foreign investors."""

KINDS = (
    "oil_up", "oil_down",
    "naira_weaker", "naira_stronger",
    "foreign_buying", "foreign_selling",
)

WORDINGS = {
    # ------------------------------------------------------------------ The oil price
    "oil_up": {
        "herald": [
            ("Oil climbs to {price} and fuel may follow",
             "The world price of oil rose {change} this quarter, from {previous} to {price}. Oil companies in Port "
             "Harcourt earn more on every barrel sold abroad, and the Government's oil income rises. Fuel and "
             "transport could cost more at home."),
            ("Good news for the oil towns: a barrel now fetches {price}",
             "Oil rose {change} in a quarter, up from {previous}. Workers in the oil companies and the Government's "
             "purse both gain. Families who buy fuel may feel the other side of it."),
            ("Dearer oil: up {change} to {price}",
             "What the world pays for a barrel of oil went from {previous} to {price}. Every company that burns fuel "
             "faces a bigger bill, while oil producers and the Government take in more."),
        ],
        "ogene": [
            ("Oil up {change}: {price} a barrel",
             "The world oil price jumps from {previous} to {price}. Oil producers earn more abroad. Fuel costs at home "
             "go up."),
            ("Barrel price rises to {price}",
             "Oil is {change} dearer than last quarter, when it stood at {previous}. The Government's oil income grows."),
            ("Oil climbs again, now {price}",
             "Up {change} on the quarter from {previous}. Energy gets dearer for every business."),
        ],
        "ledger": [
            ("World oil benchmark at {price}, up {change}",
             "The world oil price closed the quarter at {price} a barrel against {previous}. Export earnings of the "
             "oil and gas producers rise with it, as does the Government's royalty. Higher fuel costs feed into "
             "transport, power and factory costs."),
            ("Oil rises {change} to {price}: exporters and the Treasury gain",
             "A barrel fetched {previous} a quarter ago and {price} now. A dearer barrel tends to strengthen the naira, "
             "since the country earns more abroad, but it raises energy costs for every company at home."),
            ("Energy costs set to rise as oil reaches {price}",
             "The oil price moved up {change} from {previous}. Companies that buy fuel and power should expect "
             "dearer supplies next quarter, and oil producers should expect stronger sales abroad."),
        ],
    },
    "oil_down": {
        "herald": [
            ("Oil falls to {price} and the oil towns feel it",
             "The world price of oil dropped {change}, from {previous} to {price}. Oil companies earn less abroad and "
             "the Government's oil income shrinks. Fuel at home may get a little cheaper."),
            ("Cheaper oil: a barrel now fetches only {price}",
             "Oil fell {change} in a quarter, down from {previous}. Port Harcourt's producers and the Government both "
             "lose income, while transport and factory owners save on fuel."),
            ("Oil price slides {change} to {price}",
             "What the world pays for a barrel went from {previous} to {price}. A blow to the oil companies, some "
             "relief for anyone who buys fuel."),
        ],
        "ogene": [
            ("Oil down {change}: {price} a barrel",
             "The world oil price falls from {previous} to {price}. Oil producers earn less abroad. Fuel gets cheaper "
             "at home."),
            ("Barrel price drops to {price}",
             "Oil is {change} cheaper than last quarter, when it stood at {previous}. The Government's oil income falls."),
            ("Oil slips again, now {price}",
             "Down {change} on the quarter from {previous}. Energy gets cheaper for every business."),
        ],
        "ledger": [
            ("Oil benchmark at {price}, down {change}",
             "The world oil price closed the quarter at {price} a barrel against {previous}. Export earnings of the "
             "oil and gas producers fall with it, as does the Government's royalty. Lower fuel costs ease transport, "
             "power and factory costs."),
            ("Oil falls {change} to {price}: exporters and the Treasury lose",
             "A barrel fetched {previous} a quarter ago and {price} now. A cheaper barrel tends to weaken the naira, "
             "since the country earns less abroad, but it lowers energy costs for every company at home."),
            ("Energy costs set to ease as oil drops to {price}",
             "The oil price moved down {change} from {previous}. Companies that buy fuel and power should expect "
             "cheaper supplies next quarter, and oil producers should expect weaker sales abroad."),
        ],
    },
    # ------------------------------------------------------------------ The naira
    "naira_weaker": {
        "herald": [
            ("The naira slips to {rate} a dollar",
             "One US dollar now costs {rate}, up from {previous}: the naira is {change} weaker. Anything bought "
             "abroad, from machines to medicines, gets dearer. The main cause: {cause}."),
            ("Imported goods dearer as the dollar reaches {rate}",
             "Traders who buy abroad will pay more. The naira lost {change} against the dollar this quarter, from "
             "{previous} to {rate}, mostly because of {cause}."),
            ("A weaker naira: {previous} becomes {rate}",
             "The dollar is dearer and so is everything priced in it. Farmers and factories who sell abroad gain a "
             "little. The naira fell {change}, mostly on {cause}."),
        ],
        "ogene": [
            ("The naira down {change}: {rate} to the dollar",
             "The naira weakens from {previous} to {rate}. Imports cost more. Main cause: {cause}."),
            ("Dollar now {rate}",
             "One dollar costs {rate}, against {previous} last quarter. Goods from abroad get dearer."),
            ("The naira slips again on {cause}",
             "Down {change} to {rate} a dollar. Exporters gain and importers pay more."),
        ],
        "ledger": [
            ("The naira weakens {change} to {rate} per dollar",
             "The exchange rate moved from {previous} to {rate}, chiefly on {cause}. Companies that import supplies "
             "face higher costs, and some of that will reach shop prices. Non-oil exporters become more competitive."),
            ("Dollar at {rate}: import costs rise",
             "A {change} fall in the naira against {previous} last quarter raises the cost of every imported input. "
             "The main cause was {cause}. Expect the effect in next quarter's margins of heavy importers."),
            ("The naira at {rate} a dollar, weaker than {previous}",
             "The naira fell {change}. The leading cause was {cause}. Goods bought abroad become dearer, which pushes "
             "prices at home up a little."),
        ],
    },
    "naira_stronger": {
        "herald": [
            ("The naira firms to {rate} a dollar",
             "One US dollar now costs {rate}, down from {previous}: the naira is {change} stronger. Goods bought "
             "abroad get a little cheaper. The main cause: {cause}."),
            ("Cheaper imports as the dollar falls to {rate}",
             "Traders who buy abroad will pay less. The naira gained {change} against the dollar this quarter, from "
             "{previous} to {rate}, mostly because of {cause}."),
            ("A stronger naira: {previous} becomes {rate}",
             "The dollar is cheaper and so is everything priced in it. Farmers and factories who sell abroad earn a "
             "little less. The naira rose {change}, mostly on {cause}."),
        ],
        "ogene": [
            ("The naira up {change}: {rate} to the dollar",
             "The naira strengthens from {previous} to {rate}. Imports cost less. Main cause: {cause}."),
            ("Dollar down to {rate}",
             "One dollar costs {rate}, against {previous} last quarter. Goods from abroad get cheaper."),
            ("The naira gains on {cause}",
             "Up {change} to {rate} a dollar. Importers save and exporters earn less."),
        ],
        "ledger": [
            ("The naira strengthens {change} to {rate} per dollar",
             "The exchange rate moved from {previous} to {rate}, chiefly on {cause}. Companies that import supplies "
             "see lower costs, which eases prices at home. Non-oil exporters become less competitive."),
            ("Dollar at {rate}: import costs ease",
             "A {change} rise in the naira against {previous} last quarter lowers the cost of every imported input. "
             "The main cause was {cause}. Heavy importers' margins should benefit next quarter."),
            ("Exchange rate: {rate} a dollar, from {previous}",
             "The naira rose {change}. The leading cause was {cause}. Goods bought abroad become cheaper, which "
             "holds prices at home down a little."),
        ],
    },
    # ------------------------------------------------------------------ Foreign investors
    "foreign_buying": {
        "herald": [
            ("Foreign money flows in: {amount} this quarter",
             "Investors from abroad brought {amount} into the country to buy shares. With the Central Bank's rate "
             "at {rate}, money here pays them well. Their buying can lift share prices."),
            ("Overseas investors bring {amount} to Broad Street",
             "Foreign investors like what Nigeria pays. They sent in {amount} this quarter, with the interest rate "
             "at {rate}. Expect them on the exchange as buyers."),
            ("Money from abroad: {amount} arrives for shares",
             "Foreign buyers are coming in. They see a good return with the rate at {rate} and brought {amount} "
             "this quarter."),
        ],
        "ogene": [
            ("Foreign investors bring in {amount}",
             "Money from abroad arrives for the share market. Interest rate: {rate}."),
            ("{amount} of foreign money for shares",
             "Investors abroad are buying. They like a rate of {rate}."),
            ("Inflow: {amount} from foreign investors",
             "Foreign buyers return to Broad Street with the rate at {rate}."),
        ],
        "ledger": [
            ("Foreign portfolio inflow of {amount}",
             "Foreign investors brought {amount} into the country this quarter. With the policy rate at {rate}, "
             "Nigerian returns beat what lending abroad pays even after the naira's expected fall. They tend to "
             "buy the larger shares first."),
            ("Offshore investors add {amount} as a {rate} rate attracts them",
             "The return over lending abroad remains wide enough to draw money in. Foreign investors trade through "
             "ordinary orders on the exchange, so their buying shows in prices."),
            ("Inflows: {amount} from foreign investors",
             "Money came in from abroad this quarter, drawn by a {rate} interest rate. Foreign demand can support "
             "prices of the biggest listed companies."),
        ],
    },
    "foreign_selling": {
        "herald": [
            ("Foreign money leaves: {amount} this quarter",
             "Investors from abroad took {amount} out of the country. With the Central Bank's rate at {rate}, they "
             "think money pays better elsewhere once the naira's fall is counted. Their selling can weigh on shares."),
            ("Overseas investors pull {amount} from Broad Street",
             "Foreign investors are heading for the door. They took out {amount} this quarter, with the interest "
             "rate at {rate}. Expect them on the exchange as sellers."),
            ("Money leaves for abroad: {amount} withdrawn",
             "Foreign sellers are going. They do not like the return with the rate at {rate} and took out {amount} "
             "this quarter."),
        ],
        "ogene": [
            ("Foreign investors take out {amount}",
             "Money leaves for abroad. Interest rate: {rate}."),
            ("{amount} of foreign money withdrawn",
             "Investors abroad are selling. A rate of {rate} is not enough for them."),
            ("Outflow: {amount} to foreign investors",
             "Foreign sellers leave Broad Street with the rate at {rate}."),
        ],
        "ledger": [
            ("Foreign portfolio outflow of {amount}",
             "Foreign investors took {amount} out of the country this quarter. With the policy rate at {rate}, "
             "Nigerian returns no longer beat lending abroad once the naira's expected fall is counted. They sell "
             "through ordinary orders on the exchange."),
            ("Offshore investors withdraw {amount} as a {rate} rate is too low for them",
             "The return over lending abroad has narrowed. Foreign selling shows in prices, mostly in the larger "
             "listed companies."),
            ("Outflows: {amount} to foreign investors",
             "Money left for abroad this quarter, with the interest rate at {rate}. Foreign selling can weigh on "
             "prices of the biggest listed companies."),
        ],
    },
}
