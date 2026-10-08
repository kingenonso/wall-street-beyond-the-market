"""Wordings for the news of private companies: start-ups, companies put up for sale and bought, staff
walking out, companies failing, and the deal of the year."""

KINDS = ("startup", "company_for_sale", "walkout", "private_deal", "administration", "deal_of_the_year")

WORDINGS = {
    "startup": {
        "herald": [
            ("A new company opens its doors in {city}",
             "{company} has been founded in {city}, a new name in {sector}. Its founders have put {amount} of their own "
             "money into it. It is privately owned: its shares are not sold on the exchange."),
            ("{company}: founders bet {amount} on a fresh start",
             "Founders in {city} have started {company}, which will compete in {sector}. They put in {amount}, and the "
             "first thing the company did was buy its buildings and machines from other businesses."),
            ("New in {sector}: {company}",
             "There is a new competitor in {sector}. {company}, based in {city}, opens with {amount} from its founders. "
             "Customers will decide whether there is room for it."),
        ],
        "ogene": [
            ("{company} launches in {city}",
             "A new private company enters {sector}. Founders put in {amount}."),
            ("Start-up {company} opens with {amount}",
             "{company} begins trading in {city}. It is privately owned and competes in {sector}."),
            ("{sector}: a new rival, {company}",
             "Founders launch {company} in {city} with {amount} of their own money."),
        ],
        "ledger": [
            ("{company} founded with {amount} of founders' capital",
             "{company}, a private company in {sector} based in {city}, has been founded with {amount} of capital from "
             "its founders. It is not listed. Its first spending went on buildings and equipment."),
            ("New private entrant in {sector}: {company}",
             "The founders of {company} have committed {amount}. The company, headquartered in {city}, adds capacity "
             "to {sector} and will take customers from established names."),
            ("{city} start-up {company} raises {amount} from founders",
             "{company} begins operations in {sector}. All {amount} of its opening capital came from its founders; no "
             "money was borrowed."),
        ],
    },
    "company_for_sale": {
        "herald": [
            ("{company} is for sale",
             "The owners of {company}, a private company in {sector}, have put it up for sale {how}. They are asking "
             "{amount}. Buyers who want to see its accounts must first sign a promise to keep them secret."),
            ("Who will buy {company}?",
             "{company} is on the market, {how}, with an asking price of {amount}. The sale is decided when the quarter "
             "closes. Its papers may not tell the whole story, so buyers will be digging."),
            ("Founders put {company} on the block",
             "After years in private hands, {company} is being sold {how}. The asking price is {amount}. Empires with "
             "the money and the nerve are expected to take a look."),
        ],
        "ogene": [
            ("{company} up for sale: {amount}",
             "{company} ({sector}) is sold {how}. The sale closes at the end of the quarter."),
            ("Sale opens: {company}",
             "Owners ask {amount} for {company}, a private company in {sector}. It is sold {how}."),
            ("{sector}: {company} on the market",
             "{company} is for sale {how}. Asking price: {amount}."),
        ],
        "ledger": [
            ("{company} offered for sale at {amount}",
             "The shareholders of {company}, a private company in {sector}, have opened a sale {how}. The asking price "
             "is {amount}. Access to the data room requires a confidentiality agreement."),
            ("Private sale: {company}, asking {amount}",
             "{company} is being sold {how}. Bidders will want to test the accounts, the assets and the contracts "
             "before committing; the sale is decided at the quarter's close."),
            ("{sector} asset on the market: {company}",
             "A sale of {company} has been launched {how}, with {amount} asked. Buyers may borrow part of the price "
             "against the company itself."),
        ],
    },
    "walkout": {
        "herald": [
            ("Staff walk out at {company}",
             "Workers at {company} in {city} downed tools for part of the quarter. They say their pay has fallen "
             "behind prices. Customers found the doors shut and went elsewhere."),
            ("Angry workers stop work at {company}",
             "Pay at {company} has not kept up with the cost of living, its staff say, and they stopped work in protest. "
             "Rival businesses in {city} picked up the customers."),
            ("{company}: no service while staff protest",
             "A walkout at {company} left customers in {city} without service. Workers want pay that keeps up with prices."),
        ],
        "ogene": [
            ("Walkout at {company}",
             "Staff at {company} in {city} stop work over pay."),
            ("{company} staff down tools",
             "Workers in {city} protest pay that trails prices. Customers turn to rivals."),
            ("Pay row stops work at {company}",
             "Staff of {company} walk out in {city}."),
        ],
        "ledger": [
            ("{company} hit by staff walkout",
             "A walkout over pay disrupted {company}'s operations in {city} this quarter. Sales were lost to competitors. "
             "Pay at the company has fallen behind the wage index."),
            ("Labour unrest costs {company} sales",
             "{company} lost part of a quarter's trading in {city} to a walkout. Its owners face a choice between "
             "raising pay and further disruption."),
            ("{company}: pay gap triggers stoppage",
             "Staff at {company} stopped work after pay fell behind prices. The cost will show in the company's sales."),
        ],
    },
    "private_deal": {
        "herald": [
            ("{buyer} buys {company}",
             "{company} has a new owner. {buyer} paid {amount} for it, {how}. Its new owners will now decide its prices, "
             "its staff and its future."),
            ("{company} changes hands for {amount}",
             "The sale of {company} is over: {buyer} won it {how}, paying {amount}. Staff and customers will be watching "
             "what the new owners do first."),
            ("New owners for {company}",
             "{buyer} is the new owner of {company}, bought {how} for {amount}."),
        ],
        "ogene": [
            ("{buyer} wins {company}",
             "{buyer} pays {amount} for {company}, {how}."),
            ("Sold: {company}, {amount}",
             "{company} goes to {buyer} {how}."),
            ("{company} sold to {buyer}",
             "The price: {amount}. The sale was won {how}."),
        ],
        "ledger": [
            ("{buyer} acquires {company} for {amount}",
             "{buyer} has completed the purchase of {company} for {amount}, {how}. Part of the price may have been "
             "borrowed against the company; lenders will watch its cash closely."),
            ("{company} sold: {amount}",
             "The sale of {company} has closed with {buyer} as the winning bidder, {how}. The price was {amount}."),
            ("Private deal: {buyer} takes {company}",
             "{buyer} paid {amount} for {company}. The new owner takes control of its pricing, staffing and investment."),
        ],
    },
    "administration": {
        "herald": [
            ("{company} collapses",
             "{company} of {city} could not pay what it owed and has gone into administration. It owed {owed}. Selling "
             "what it owned raised {recovered}, shared out among those it owed in the order the law sets."),
            ("The end for {company}",
             "Administrators have wound up {company}. Lenders and staff were paid first from the {recovered} its assets "
             "fetched; of the {owed} it owed, much will never be paid. Its owners get nothing."),
            ("{company} fails, owing {owed}",
             "{company} has failed. Its assets were sold for {recovered}, against debts of {owed}."),
        ],
        "ogene": [
            ("{company} in administration",
             "{company} of {city} fails owing {owed}. Assets sold for {recovered}."),
            ("{company} wound up",
             "Creditors of {company} share {recovered}. It owed {owed}."),
            ("Collapse at {company}",
             "{company} cannot pay its debts. Owners are wiped out."),
        ],
        "ledger": [
            ("{company} enters administration owing {owed}",
             "{company}, based in {city}, has been placed in administration. Asset sales realised {recovered} against "
             "liabilities of {owed}. Secured lenders rank first, then staff, then tax, then other creditors; "
             "shareholders receive nothing."),
            ("Creditors recover {recovered} from {company}",
             "The administration of {company} has concluded. Of {owed} owed, {recovered} was raised from the sale of "
             "its assets and distributed by rank."),
            ("{company} wound up after failing to pay its debts",
             "{company} could no longer meet its obligations. Its assets fetched {recovered}; its debts stood at {owed}."),
        ],
    },
    "deal_of_the_year": {
        "herald": [
            ("{empire} wins Deal of the Year",
             "The deal of {year} belongs to {empire}, which made {gain} buying and selling {company}. Rival empires will "
             "be studying how it was done."),
            ("{gain} made on {company}: the deal of {year}",
             "When {empire} sold {company}, it walked away {gain} richer than when it bought. No deal in {year} did better."),
            ("Best deal of {year}: {empire} and {company}",
             "{empire} is named for the best deal of {year}: its time owning {company} made it {gain}."),
        ],
        "ogene": [
            ("Deal of the Year: {empire}",
             "{empire} makes {gain} on {company} in {year}."),
            ("{empire} tops {year}'s deals",
             "Its sale of {company} brought a gain of {gain}."),
            ("{year}'s best deal: {company}",
             "{empire} earns {gain} from buying and selling it."),
        ],
        "ledger": [
            ("{empire} takes Deal of the Year for {company}",
             "{empire}'s investment in {company} produced a gain of {gain}, the best of any deal completed in {year}."),
            ("League tables: {empire} leads {year} with {company}",
             "The year's deal league is headed by {empire}, whose exit from {company} returned a gain of {gain}."),
            ("Deal of the Year: a {gain} gain on {company}",
             "{empire} bought, ran and sold {company}, and the result was the strongest of {year}."),
        ],
    },
}
