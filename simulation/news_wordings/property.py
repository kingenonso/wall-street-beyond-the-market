"""News wordings for land and property (Stage 8): district booms and falls, forced sales, title disputes, a fallen headquarters."""

KINDS = (
    "property_up", "property_down", "property_forced_sale", "title_dispute", "hq_collapse",
)

WORDINGS = {
    "property_up": {
        "herald": [
            ("Property prices jump {change} in {district}, {city}",
             "Owners in {district} saw their buildings rise {change} in value this quarter. Tenants may feel it next in their rent."),
            ("{district} is the place to own: prices up {change}",
             "Buyers are paying more for homes, shops and offices in {district}, {city}. Prices rose {change} in a quarter."),
            ("Rising rents and keen buyers lift {district} by {change}",
             "A quarter of strong demand in {city} pushed property in {district} up {change}. Some buyers are paying more than rents justify."),
        ],
        "ogene": [
            ("{district} property up {change}",
             "Prices in {district}, {city}, rise {change} this quarter."),
            ("Boom in {district}: {change} up",
             "Buyers pay more for property in {district}. {city} demand is strong."),
            ("{city}: {district} prices climb {change}",
             "Property in {district} gains {change} in one quarter."),
        ],
        "ledger": [
            ("{district} property index rises {change}",
             "Property values in {district}, {city}, rose {change} on the quarter, on firmer rents and buyers bidding above fair value. "
             "Prices that run ahead of rents tend to come back."),
            ("Valuations in {district} up {change}: watch the gap to rents",
             "The district's prices rose {change}. Where buyers pay more than rents justify, the premium fades over the following quarters."),
            ("{city}'s {district} leads property gains at {change}",
             "Values in {district} climbed {change}. Higher rents support part of the rise, and the rest is buyers' enthusiasm."),
        ],
    },
    "property_down": {
        "herald": [
            ("Property prices fall {change} in {district}, {city}",
             "Owners in {district} saw their buildings lose {change} of their value this quarter. Some tenants have moved out."),
            ("A hard quarter for {district}: prices down {change}",
             "Homes, shops and offices in {district}, {city}, are worth {change} less than a quarter ago."),
            ("Empty buildings and weaker rents pull {district} down {change}",
             "Demand in {city} slipped, and property in {district} fell {change}."),
        ],
        "ogene": [
            ("{district} property down {change}",
             "Prices in {district}, {city}, fall {change} this quarter."),
            ("Slump in {district}: {change} off",
             "Buyers pay less for property in {district}. {city} demand is weak."),
            ("{city}: {district} prices slide {change}",
             "Property in {district} loses {change} in one quarter."),
        ],
        "ledger": [
            ("{district} property index falls {change}",
             "Property values in {district}, {city}, fell {change} on the quarter, on softer rents and fewer tenants. Owners with mortgages "
             "should check what they owe against what their buildings are now worth."),
            ("Valuations in {district} down {change}",
             "The district's prices fell {change}. A bubble that bursts leaves late buyers owing more than their property is worth."),
            ("{city}'s {district} leads property falls at {change}",
             "Values in {district} dropped {change}. Rents and occupancy both weakened."),
        ],
    },
    "property_forced_sale": {
        "herald": [
            ("{property} goes to auction after {why}",
             "The Auction House is selling {property} to the highest bidder, because {why}. There is no lowest price."),
            ("Forced sale: {property} up for auction",
             "{property} is being sold whatever the price, because {why}."),
            ("Bargain hunters, take note: {property} must be sold",
             "Because {why}, {property} is going under the hammer at the Auction House."),
        ],
        "ogene": [
            ("{property} for auction",
             "Sold whatever the price: {why}."),
            ("Forced sale of {property}",
             "The Auction House sells {property} because {why}."),
            ("Auction: {property}, no reserve",
             "{property} must be sold. The reason: {why}."),
        ],
        "ledger": [
            ("Forced sale of {property} at the Auction House",
             "{property} is being sold without a reserve because {why}. Forced sales often clear below fair value."),
            ("{property} to be sold: {why}",
             "The property goes to auction with no lowest price. Proceeds settle what is owed first."),
            ("Distressed lot: {property}",
             "Because {why}, {property} is up for auction. Bidders should check the title and the condition."),
        ],
    },
    "title_dispute": {
        "herald": [
            ("New owners of {property} lose {share} to a rival claim",
             "The buyers of {property} have found that the seller did not truly own all of it. A claimant has taken {share}."),
            ("Title row: {share} of {property} belongs to someone else",
             "A claim at the lands registry has cost the new owners of {property} {share} of the property."),
            ("Check the title first: {property} buyers lose {share}",
             "The people who bought {property} now own {share} less of it than they paid for."),
        ],
        "ogene": [
            ("{property}: {share} lost in title dispute",
             "A rival claim takes {share} of {property} from its new owners."),
            ("Title claim on {property}",
             "The seller did not own {share} of {property}. The buyers lose it."),
            ("{share} of {property} goes to the true owner",
             "A title flaw costs the buyers of {property}."),
        ],
        "ledger": [
            ("Defective title costs buyers {share} of {property}",
             "A claim at the lands registry has established that {share} of {property} was not the seller's to sell. A title search before "
             "bidding would have shown it."),
            ("{property}: {share} of the title belongs to another party",
             "The buyers' holding has been cut by {share}. The price they paid is not refunded."),
            ("Title failure at {property}",
             "{share} of the property passes to the true owner. Due diligence on title is the cheapest insurance in property."),
        ],
    },
    "hq_collapse": {
        "herald": [
            ("{empire}'s headquarters falls down in {city}",
             "{building}, the headquarters of {empire}, has collapsed. The empire loses its building's benefits until it rebuilds."),
            ("Neglect brings down {empire}'s home, {building}",
             "The headquarters of {empire} in {city} has fallen after warnings about its condition."),
            ("{building} collapses: {empire} must rebuild",
             "{empire}'s headquarters in {city} is down. Its members keep their seats."),
        ],
        "ogene": [
            ("{empire} headquarters collapses",
             "{building}, {city}, is down. Its members keep their seats."),
            ("{building} falls: {empire} hit",
             "The empire loses its headquarters' benefits until it rebuilds."),
            ("Collapse at {building}, {city}",
             "{empire}'s headquarters has fallen down."),
        ],
        "ledger": [
            ("{empire} loses its headquarters, {building}",
             "The building in {city} has collapsed after its upkeep lapsed. Its extra seats are frozen and its benefits stop until it is rebuilt."),
            ("Headquarters collapse at {empire}: a costly lesson in upkeep",
             "{building}, {city}, has fallen. Insurance, if bought, pays for the building lost."),
            ("{empire}'s {city} headquarters down",
             "{building} collapsed this quarter. Rebuilding costs as much as a new building."),
        ],
    },
}
