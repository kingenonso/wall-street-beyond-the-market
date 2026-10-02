"""Wordings for things that happen to one company, to commodity prices, and for insurers' bills afterwards."""

KINDS = (
    "company_strike", "scandal", "contract_win", "factory_fire", "product_recall", "new_product",
    "energy_price_jump", "energy_price_fall", "metals_price_jump", "metals_price_fall", "materials_shortage",
    "commodity_up", "commodity_down", "insurance_claims", "event_aftermath",
)

WORDINGS = {
    "company_strike": {
        "herald": [
            ("Workers at {company} down tools in {location}",
             "Staff at {company} in {location} stopped work today. Nothing is being made or sold while they stay "
             "out, and families who depend on those wages are waiting for news. The disruption is described as "
             "{severity}."),
            ("Gates quiet at {company} as staff stay away",
             "It was a quiet day at {company} in {location}, where the company's own workers have gone on strike. "
             "Customers may have to wait for their orders. Early word is of {severity} disruption to its business."),
            ("{location} families watch as {company} strike begins",
             "A strike began today at {company}, one of the {sector} companies in {location}. Every day without "
             "work is a day without sales for the company. How much it will cost is not yet known."),
        ],
        "ogene": [
            ("{location}: staff walk out at {company}",
             "Workers at {company} are on strike. The disruption is described as {severity}."),
            ("{company}: strike halts work",
             "Work stops at {company} in {location} as its staff down tools. The cost is not yet known."),
            ("Strike hits {company} in {location}",
             "Staff at {company} stay away from work today. Sales are being lost while the strike lasts."),
        ],
        "ledger": [
            ("{company} ({ticker}) loses sales as its staff strike",
             "Staff at {company} ({ticker}) went on strike today in {location}. The company loses sales for as "
             "long as work is stopped. The disruption is described as {severity}, and the full cost is not yet "
             "known."),
            ("Strike at {ticker}: disruption rated {severity}",
             "A strike by its own workers has stopped work at {company}, which is in the {sector} business. "
             "Lost working days mean lost sales and less cash coming in. Investors and lenders will not see the "
             "cost until the company reports its quarter."),
            ("Stoppage at {company} puts the quarter's sales at risk",
             "{company} ({ticker}), based in {location}, faces a strike by its own staff from today. The effect "
             "on its sales is described as {severity}. No figure has yet been put on the loss."),
        ],
    },
    "scandal": {
        "herald": [
            ("Trouble at {company} sets {location} talking",
             "{company} of {location} found itself at the centre of a scandal today. Customers and staff are "
             "waiting to hear more. The harm to the company's good name is described as {severity}."),
            ("Customers left wondering as scandal hits {company}",
             "A scandal broke around {company} today. When trust is shaken, shoppers and business partners tend "
             "to hold back, and that costs a company sales. The damage so far is described as {severity}."),
            ("A hard day for {company} and the people who work there",
             "Workers at {company} in {location} went home today with a scandal hanging over their employer. "
             "Details are still few. What it will cost the company is not yet known."),
        ],
        "ogene": [
            ("{company}: scandal breaks",
             "A scandal hits {company} of {location}. The damage to its name is described as {severity}."),
            ("{location}: {company} under a cloud",
             "{company} is caught up in a scandal today. Details are few and the cost is not yet known."),
            ("Scandal shakes {company}",
             "Trust in {company} takes a knock as a scandal breaks. Customers may hold back."),
        ],
        "ledger": [
            ("Scandal at {company} ({ticker}) puts its sales at risk",
             "{company} ({ticker}) was hit by a scandal today. The harm to its standing with customers is "
             "described as {severity}. A damaged name usually means weaker sales, but no figure is yet known."),
            ("{ticker}: damage from scandal described as {severity}",
             "A scandal broke today at {company}, which is in the {sector} business and based in {location}. "
             "Investors and lenders will want to see how far customers pull back. The full cost will show only "
             "in the company's next results."),
            ("Investors weigh the cost of a scandal at {company}",
             "{company} ({ticker}) of {location} faces a scandal. Lost trust can cost a company customers and "
             "cash. Early reports call the damage {severity}."),
        ],
    },
    "contract_win": {
        "herald": [
            ("Good news in {location} as {company} wins new contract",
             "There were smiles at {company} in {location} today after the company won a new contract. More "
             "orders mean more work to go round. The lift to its business is described as {severity}."),
            ("{company} lands a new contract",
             "{company}, one of the {sector} companies in {location}, has won a new contract. For its workers "
             "and the traders who supply it, that means busier days ahead. The gain is described as {severity}."),
            ("Busier days ahead for workers at {company}",
             "A new contract was won today by {company} of {location}. The extra orders should bring in more "
             "sales. Just how much more is not yet known."),
        ],
        "ogene": [
            ("{company}: new contract won",
             "{company} of {location} wins a new contract. The boost to its sales is described as {severity}."),
            ("{location}: {company} signs up new work",
             "A new contract lands at {company} today. More orders and more sales are on the way."),
            ("Contract win lifts {company}",
             "{company} has fresh work on its books. The size of the gain is not yet known."),
        ],
        "ledger": [
            ("{company} ({ticker}) wins contract, sales set to rise",
             "{company} ({ticker}) won a new contract today. The effect on its sales is described as {severity}. "
             "The value of the work has not been made known."),
            ("{ticker}: boost from new contract described as {severity}",
             "A new contract has been won by {company}, which is in the {sector} business and based in "
             "{location}. More orders mean more sales and more cash coming in. The figures will show in the "
             "company's coming results."),
            ("New work for {company} should add to its sales",
             "{company} ({ticker}) of {location} has added a new contract to its order book, the list of work "
             "it has agreed to do. Early reports call the gain {severity}. No figure is yet known."),
        ],
    },
    "factory_fire": {
        "herald": [
            ("Fire at {company} site in {location}",
             "Fire broke out today at a site belonging to {company} in {location}. "
             "Early reports call the damage {severity}, and work there has been disrupted."),
            ("Work stops after fire at {company}",
             "A fire damaged one of the sites of {company} in {location} today. "
             "Staff do not yet know when normal work will return. The cost of the damage has still to be "
             "counted."),
            ("{location} wakes to news of a fire at {company}",
             "People in {location} heard today that fire had struck a site owned by {company}. Buildings and "
             "machines were damaged, and the company will sell less until they are put right. The damage is "
             "described as {severity}."),
        ],
        "ogene": [
            ("{location}: fire at {company}",
             "Fire strikes a {company} site. Early reports call the damage {severity}."),
            ("{company}: site damaged by fire",
             "A fire disrupts work at {company} in {location}. The cost is not yet known."),
            ("Fire halts work at {company}",
             "A site owned by {company} is damaged by fire today. The damage is described as {severity}."),
        ],
        "ledger": [
            ("Fire damages {company} ({ticker}) site, cost not yet known",
             "A fire damaged a site of {company} ({ticker}) in {location} today. The damage is described as "
             "{severity}. The company loses sales while the site is out of use, and the bill for repairs has "
             "not yet been counted."),
            ("{ticker}: fire damage described as {severity}",
             "{company}, which is in the {sector} business, has lost the use of buildings and machines after a "
             "fire at one of its sites. Investors will want to know how much insurance will cover. That figure "
             "is not yet known."),
            ("{company} counts the cost after fire in {location}",
             "{company} ({ticker}) faces repair costs and lost sales after a fire at one of its sites. "
             "Early reports call the damage {severity}."),
        ],
    },
    "product_recall": {
        "herald": [
            ("{company} calls one of its products back from the shops",
             "{company} of {location} is taking one of its products off the shelves. Shop owners are being "
             "asked to send the goods back. The setback for the company is described as {severity}."),
            ("Shoppers told a {company} product is being withdrawn",
             "A product made by {company} was withdrawn from sale today. Customers who bought it and traders "
             "who stock it are waiting to hear what happens next. What it will cost the company is not yet "
             "known."),
            ("A product comes off the shelves, and {company} pays",
             "Traders in {location} and beyond are clearing a {company} product from their shelves after the "
             "company called it back. Sales are lost while it is gone. The damage to its business is described "
             "as {severity}."),
        ],
        "ogene": [
            ("{company}: product recalled",
             "{company} of {location} pulls one of its products from sale. The setback is described as "
             "{severity}."),
            ("{location}: {company} withdraws a product",
             "A {company} product is coming off the shelves today. The cost to the company is not yet known."),
            ("Recall at {company}",
             "{company} is calling one of its products back. Sales are lost while it is off the shelves."),
        ],
        "ledger": [
            ("{company} ({ticker}) recalls a product, sales to suffer",
             "{company} ({ticker}) called one of its products back from sale today. The effect on its sales is "
             "described as {severity}. The company also bears the cost of taking the goods back, and no figure "
             "is yet known."),
            ("{ticker}: cost of product recall not yet known",
             "A product has been withdrawn by {company}, which is in the {sector} business and based in "
             "{location}. A recall costs money twice: the goods come back, and sales stop. The full sum will "
             "show in the company's next results."),
            ("Recall puts a dent in sales at {company}",
             "{company} ({ticker}) of {location} has taken a product off the market. Early reports call the "
             "setback {severity}. Investors will look for the cost when the quarter's figures come out."),
        ],
    },
    "new_product": {
        "herald": [
            ("{company} brings a new product to market",
             "Shoppers have something new to look at: {company} of {location} launched a new product today. "
             "The company hopes it will win fresh customers. The lift to its sales is described as {severity}."),
            ("Something new from {company} reaches customers",
             "{company}, one of the {sector} companies in {location}, put a new product on sale today. For "
             "its workers that means more to make and more to sell. How well it sells will be seen in the "
             "weeks ahead."),
            ("{location} firm {company} unveils its latest product",
             "A new product from {company} went on sale today. Traders who carry its goods have something "
             "fresh to offer their customers. The boost to the company is described as {severity}."),
        ],
        "ogene": [
            ("{company}: new product launched",
             "{company} of {location} puts a new product on sale. The lift to its sales is described as "
             "{severity}."),
            ("{location}: {company} unveils a new product",
             "A new product from {company} goes on sale today. The company is counting on new customers."),
            ("New product out from {company}",
             "{company} has something new to sell. How much it adds to sales is not yet known."),
        ],
        "ledger": [
            ("{company} ({ticker}) launches product to lift its sales",
             "{company} ({ticker}) put a new product on sale today. The effect on its sales is described as "
             "{severity}. How much it adds will show in the company's coming results."),
            ("{ticker}: boost from new product described as {severity}",
             "A new product has been launched by {company}, which is in the {sector} business and based in "
             "{location}. A product that sells well brings in more cash from the same shops and staff. No "
             "sales figure is yet known."),
            ("New line from {company} aims at more sales",
             "{company} ({ticker}) of {location} has added a new product to what it sells. Early reports call "
             "the gain {severity}. Investors will look for proof in the quarter's sales."),
        ],
    },
    "energy_price_jump": {
        "herald": [
            ("Fuel and power to cost more as energy jumps {size}",
             "The price of {commodity} jumped by {size} today. Drivers, bus passengers, shop owners running "
             "generators and families paying for power will all feel it. Oil and gas companies, who sell it, "
             "stand to earn more."),
            ("Energy price leaps {size}, and every household will notice",
             "Energy became {size} dearer today. That reaches into every home and market stall, because almost "
             "everything has to be moved, cooked or powered. How long the higher price lasts is not yet known."),
            ("Commuters and traders brace as energy costs jump",
             "Energy costs rose sharply today, up {size}. Anyone who buys fuel or power pays more, from the "
             "commuter to the factory. The companies that produce oil and gas are the ones who gain."),
        ],
        "ogene": [
            ("Energy price jumps {size}",
             "The price of {commodity} is up {size} today. Fuel and power users pay more. Oil and gas "
             "companies gain."),
            ("Energy: {size} dearer today",
             "Energy costs leap. Every business that burns fuel or uses power faces a bigger bill."),
            ("Fuel and power bills set to climb as energy leaps",
             "Energy is up {size}. Sellers of oil and gas earn more, and everyone else pays."),
        ],
        "ledger": [
            ("Energy up {size}: costs rise for every fuel and power user",
             "The price of {commodity} rose by {size} today. Oil and gas companies earn more on what they "
             "sell. Every company that uses fuel and power faces higher costs, which leaves less profit unless "
             "it raises its own prices."),
            ("Rise of {size} in energy lifts oil and gas sellers",
             "Energy became {size} dearer today. The gain goes to oil and gas companies. The bill goes to "
             "transport, factories and anyone else who runs on fuel and power, and the full cost is not yet "
             "known."),
            ("Dearer energy to squeeze company costs",
             "A jump of {size} in the price of {commodity} was recorded today. Investors will look at who "
             "sells energy and who has to buy it. Dearer energy can also push up the prices shoppers pay."),
        ],
    },
    "energy_price_fall": {
        "herald": [
            ("Relief for drivers and families as energy falls {size}",
             "The price of {commodity} fell by {size} today. That is welcome news for anyone who buys fuel or "
             "pays for power, from commuters to shop owners. Oil and gas companies will earn less on what they "
             "sell."),
            ("Energy gets cheaper, down {size}",
             "Energy became {size} cheaper today. Households and traders who run on fuel and power should feel "
             "some ease. How long the lower price lasts is not yet known."),
            ("Cheaper fuel and power in sight as energy price drops",
             "Energy costs dropped today, down {size}. Moving goods, running generators and keeping the lights "
             "on all cost less. The companies that produce oil and gas are the ones who lose out."),
        ],
        "ogene": [
            ("Energy price falls {size}",
             "The price of {commodity} is down {size} today. Fuel and power users pay less. Oil and gas "
             "companies earn less."),
            ("Energy: {size} cheaper today",
             "Energy costs drop. Every business that burns fuel or uses power gets a smaller bill."),
            ("Fuel and power bills set to ease as energy drops",
             "Energy is down {size}. Buyers gain, and sellers of oil and gas take the hit."),
        ],
        "ledger": [
            ("Energy down {size}: costs ease for fuel and power users",
             "The price of {commodity} fell by {size} today. Oil and gas companies earn less on what they "
             "sell. Every company that uses fuel and power has lower costs, which leaves more profit from the "
             "same sales."),
            ("Fall of {size} in energy cuts into oil and gas sellers",
             "Energy became {size} cheaper today. The loss falls on oil and gas companies. Transport, "
             "factories and anyone else who runs on fuel and power pay less, and the full saving is not yet "
             "known."),
            ("Cheaper energy to ease company costs",
             "A drop of {size} in the price of {commodity} was recorded today. Investors will look at who "
             "sells energy and who has to buy it. Cheaper energy can also slow the rise in prices shoppers "
             "pay."),
        ],
    },
    "metals_price_jump": {
        "herald": [
            ("Metals jump {size}, and factory owners feel the pinch",
             "The price of {commodity} jumped by {size} today. Factories that turn metal into goods must now "
             "pay more for what they buy. In time, that can make the things they sell dearer too."),
            ("Dearer metals mean a harder week for manufacturers",
             "Metals became {size} dearer today. Workshop owners and factory managers are counting what it "
             "adds to their costs. How long the higher price lasts is not yet known."),
            ("Metal prices climb {size} in a day",
             "Metal prices rose sharply today, up {size}. The people who make things out of metal pay first. "
             "Shoppers may feel it later if makers pass the cost on."),
        ],
        "ogene": [
            ("Metals price jumps {size}",
             "The price of {commodity} is up {size} today. Manufacturers pay more for what they use."),
            ("Metals: {size} dearer",
             "Metal costs leap. Factories face a bigger bill for their materials."),
            ("Manufacturers hit as metals leap",
             "Metals are up {size}. Makers of goods must pay more or raise their own prices."),
        ],
        "ledger": [
            ("Metals up {size}: manufacturers face higher costs",
             "The price of {commodity} rose by {size} today. Manufacturers pay more for the metal they use. "
             "That leaves less profit on each item sold unless they raise their own prices."),
            ("Rise of {size} in metals adds to factory bills",
             "Metals became {size} dearer today. The cost falls on manufacturers, who buy metal to make their "
             "goods. The full effect on their profits is not yet known."),
            ("Dearer metals to squeeze manufacturers",
             "A jump of {size} in the price of {commodity} was recorded today. Investors will look at which "
             "companies buy the most metal. Their costs rise at once, while their sales do not."),
        ],
    },
    "metals_price_fall": {
        "herald": [
            ("Metals fall {size}, a welcome break for factory owners",
             "The price of {commodity} fell by {size} today. Factories that turn metal into goods now pay less "
             "for what they buy. In time, that can help keep the price of their goods down."),
            ("Cheaper metals bring some ease to manufacturers",
             "Metals became {size} cheaper today. Workshop owners and factory managers have a little more "
             "room in their costs. How long the lower price lasts is not yet known."),
            ("Metal prices slip {size} in a day",
             "Metal prices dropped today, down {size}. The people who make things out of metal save first. "
             "Shoppers may gain later if makers pass the saving on."),
        ],
        "ogene": [
            ("Metals price falls {size}",
             "The price of {commodity} is down {size} today. Manufacturers pay less for what they use."),
            ("Metals: {size} cheaper",
             "Metal costs drop. Factories get a smaller bill for their materials."),
            ("Manufacturers gain as metals drop",
             "Metals are down {size}. Makers of goods keep more of what they earn."),
        ],
        "ledger": [
            ("Metals down {size}: manufacturers' costs ease",
             "The price of {commodity} fell by {size} today. Manufacturers pay less for the metal they use. "
             "That leaves more profit on each item sold at the same price."),
            ("Fall of {size} in metals trims factory bills",
             "Metals became {size} cheaper today. The saving goes to manufacturers, who buy metal to make "
             "their goods. The full effect on their profits is not yet known."),
            ("Cheaper metals to help manufacturers",
             "A drop of {size} in the price of {commodity} was recorded today. Investors will look at which "
             "companies buy the most metal. Their costs fall at once, with no loss of sales."),
        ],
    },
    "materials_shortage": {
        "herald": [
            ("Building materials run short, and prices jump {size}",
             "Builders are struggling to find {commodity}, and the price has jumped by {size}. Anyone putting "
             "up a house or a shop will pay more. Cement makers, who sell what is scarce, stand to earn more."),
            ("Families building homes face dearer materials",
             "A shortage has made {commodity} {size} dearer. For a family building a home, the same money now "
             "buys less. How long the shortage lasts is not yet known."),
            ("Builders count the cost as materials grow scarce",
             "On building sites today the talk was of scarce supplies. The price of {commodity} is up {size}. "
             "Builders must pay it or wait, while the makers of cement gain from the higher price."),
        ],
        "ogene": [
            ("Building materials scarce: prices up {size}",
             "A shortage of {commodity} pushes prices up {size}. Builders pay more. Cement makers gain."),
            ("Shortage: building materials {size} dearer",
             "Supplies are tight today. Every building job now costs more."),
            ("Builders squeezed as materials run short",
             "The price of {commodity} leaps {size}. Building work gets dearer from today."),
        ],
        "ledger": [
            ("Building materials up {size} as supplies run short",
             "A shortage has pushed the price of {commodity} up by {size}. Builders face higher costs on every "
             "job. Cement makers earn more on what they sell."),
            ("Shortage lifts cement makers and raises builders' costs",
             "The price of {commodity} rose by {size} today because supplies are scarce. The gain goes to the "
             "makers of cement and other materials. The cost goes to builders, and the full sum is not yet "
             "known."),
            ("Scarce materials add {size} to the cost of building",
             "A jump of {size} in the price of {commodity} was recorded today. Investors will look at who "
             "makes the materials and who has to buy them. Builders' profits shrink unless they charge more."),
        ],
    },
    "commodity_up": {
        "herald": [
            ("Price of {commodity} ends the quarter {size} higher",
             "The price of {commodity} finished the quarter up {size}. Households and traders who buy it are "
             "paying more than they did three months ago. Those who sell it are earning more."),
            ("Three months on, the price of {commodity} is up {size}",
             "Over the quarter just ended, the price of {commodity} rose by {size}. Anyone who buys it has "
             "felt the difference in the market. Sellers have had the better of it."),
            ("Buyers of {commodity} pay more after a quarter of rises",
             "The quarter closed with the price of {commodity} up {size}. For the people and businesses who "
             "depend on it, that is money out of the pocket. For those who produce it, it is money in."),
        ],
        "ogene": [
            ("Quarter ends: {commodity} up {size}",
             "The price of {commodity} closes the quarter {size} higher. Buyers pay more. Sellers earn more."),
            ("Price check: {commodity} up {size} over the quarter",
             "The quarter is over and the price of {commodity} is higher than when it began."),
            ("Up {size}: {commodity} dearer at quarter's end",
             "The price of {commodity} is up over the quarter. Buyers face bigger bills."),
        ],
        "ledger": [
            ("Up {size}: price of {commodity} over the quarter",
             "The price of {commodity} ended the quarter {size} higher than it began. Companies that sell it "
             "took in more for the same goods. Companies that buy it had higher costs."),
            ("Quarter's figures: {commodity} price rises {size}",
             "A rise of {size} in the price of {commodity} was recorded over the quarter. Investors can expect "
             "it to show in the results of both sellers and buyers. Dearer supplies leave buyers less profit "
             "unless they raise prices."),
            ("Sellers of {commodity} gain as its price rises {size}",
             "Over the quarter, the price of {commodity} went up by {size}. That adds to the sales of those "
             "who produce it. It adds to the costs of everyone who uses it."),
        ],
    },
    "commodity_down": {
        "herald": [
            ("Price of {commodity} ends the quarter {size} lower",
             "The price of {commodity} finished the quarter down {size}. Households and traders who buy it "
             "are paying less than they did three months ago. Those who sell it are earning less."),
            ("Three months on, the price of {commodity} is down {size}",
             "Over the quarter just ended, the price of {commodity} fell by {size}. Anyone who buys it has "
             "felt some ease in the market. Sellers have had the harder time."),
            ("Buyers of {commodity} pay less after a quarter of falls",
             "The quarter closed with the price of {commodity} down {size}. For the people and businesses who "
             "depend on it, that is money saved. For those who produce it, it is money lost."),
        ],
        "ogene": [
            ("Quarter ends: {commodity} down {size}",
             "The price of {commodity} closes the quarter {size} lower. Buyers pay less. Sellers earn less."),
            ("Price check: {commodity} down {size} over the quarter",
             "The quarter is over and the price of {commodity} is lower than when it began."),
            ("Down {size}: {commodity} cheaper at quarter's end",
             "The price of {commodity} is down over the quarter. Buyers get smaller bills."),
        ],
        "ledger": [
            ("Down {size}: price of {commodity} over the quarter",
             "The price of {commodity} ended the quarter {size} lower than it began. Companies that sell it "
             "took in less for the same goods. Companies that buy it had lower costs."),
            ("Quarter's figures: {commodity} price falls {size}",
             "A fall of {size} in the price of {commodity} was recorded over the quarter. Investors can expect "
             "it to show in the results of both sellers and buyers. Cheaper supplies leave buyers more profit "
             "at the same prices."),
            ("Sellers of {commodity} lose as its price falls {size}",
             "Over the quarter, the price of {commodity} went down by {size}. That takes from the sales of "
             "those who produce it. It takes from the costs of everyone who uses it."),
        ],
    },
    "insurance_claims": {
        "herald": [
            ("Insurers pay out {amount} to help rebuild",
             "Business owners who lost buildings and machines received {amount} from insurers in the quarter "
             "just ended. The main cause was {cause}. The money was paid by {insurers}."),
            ("After the damage, the payouts: {amount} from insurers",
             "For owners counting their losses, help came in the quarter just ended, when insurers paid out "
             "{amount}. The largest single cause was {cause}. The money lets them repair and reopen."),
            ("Claims worth {amount} paid in a costly quarter for insurers",
             "It was a costly three months for {insurers}, who paid {amount} in claims. A claim is a request "
             "for the money an insurance policy promises. The biggest cause was {cause}."),
        ],
        "ogene": [
            ("Insurers pay out {amount}",
             "Insurance payouts for the quarter reach {amount}. The main cause is {cause}."),
            ("Claims bill: {amount}",
             "The quarter's payouts come from {insurers}. The biggest cause is {cause}."),
            ("Quarter's insurance payouts hit {amount}",
             "Insurers settle {amount} in claims, driven mainly by {cause}."),
        ],
        "ledger": [
            ("{amount} paid in insurance claims over the quarter",
             "Insurers paid {amount} in claims in the quarter just ended. The main cause was {cause}. The "
             "payments were made by {insurers}, and every naira paid out reduces what they earn."),
            ("Insurers' payouts for the quarter: {amount}",
             "Claims of {amount} were paid in the quarter by {insurers}. The largest share arose from "
             "{cause}. Investors in insurers will look at how this compares with the money they collected "
             "from customers."),
            ("Quarter's claims of {amount} weigh on insurers' profits",
             "The quarter's bill for insurers came to {amount}, mainly because of {cause}. Paying claims is "
             "what insurers are for, but a heavy quarter leaves them less profit. Those who paid were "
             "{insurers}."),
        ],
    },
    "event_aftermath": {
        "herald": [
            ("The damage is counted: {amount} lost",
             "The cost of {event} is now known. Buildings and machines worth {amount} were destroyed, and "
             "insurers paid {paid} of that. The losses fell on {companies}."),
            ("Owners learn what was lost: {amount}",
             "The counting is over for those hit by {event}. The destruction of buildings and machines "
             "came to {amount}, with insurers paying {paid}. Among those hit were {companies}."),
            ("Rebuilding begins with a bill of {amount}",
             "Workers and owners now know the size of the task after {event}: {amount} of buildings and "
             "machines destroyed. Insurance paid {paid}. Whatever it did not cover is left to the owners, "
             "among them {companies}."),
        ],
        "ogene": [
            ("Damage bill is in: {amount}",
             "The cost of {event} is {amount} in buildings and machines destroyed. Insurers pay {paid}."),
            ("Final count: {amount} destroyed",
             "The bill is in for {event}. Insurers cover {paid} of {amount}."),
            ("Insurers pay {paid} of {amount} lost",
             "The losses from {event} are counted. Those hit include {companies}."),
        ],
        "ledger": [
            ("{amount} destroyed, {paid} paid by insurers",
             "The final count of the damage from {event} is {amount} of buildings and machines destroyed. "
             "Insurers paid {paid}. Any part not covered must be met by the owners themselves, who include "
             "{companies}."),
            ("Final bill of {amount}: insurers cover {paid}",
             "Buildings and machines worth {amount} were lost in {event}, and insurers paid {paid} of the "
             "total. The companies hit were {companies}. Replacing what was lost will take cash that could "
             "have gone elsewhere."),
            ("Losses put at {amount}, with {paid} met by insurance",
             "A figure has now been put on {event}: {amount} of buildings and machines destroyed, of which "
             "insurers paid {paid}. Investors in the companies hit, and in the insurers, can now see the "
             "cost. The owners affected include {companies}."),
        ],
    },
}
