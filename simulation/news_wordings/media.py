"""News wordings for Stage 10, Part 2: media titles sold at the Auction House."""

KINDS = ("title_for_sale", "title_sold")

WORDINGS = {
    "title_for_sale": {
        "herald": [
            ("{title} goes under the hammer",
             "The Government is selling {title}, the {city} title, at the Auction House. Its readers will be watching who buys it."),
            ("For sale: {title}",
             "One of {city}'s own titles, {title}, is up for auction. The Government says it is time it had a private owner."),
            ("Who will own {title}?",
             "Bidding opens at the Auction House for {title} of {city}. An owner earns from its readers."),
        ],
        "ogene": [
            ("{title} for sale",
             "Government auctions the {city} title."),
            ("Auction: {title}",
             "Bids open for the {city} title."),
            ("{title} up for grabs",
             "The Government sells; {city} waits."),
        ],
        "ledger": [
            ("Auction House: {title}, {city}",
             "A title's value rests on its readers: sales and advertising, less staff, paper and print. The big houses are expected to bid."),
            ("Government sells {title}",
             "The sale of the {city} title opens at the Auction House. Bidders should value it on the profit its readers bring."),
            ("{title} offered at auction",
             "A {city} title changes hands. Its audience, and what is printed in it, will decide what it earns its new owner."),
        ],
    },
    "title_sold": {
        "herald": [
            ("{title} has a new owner: {buyer}",
             "{buyer} has bought {title} at the Auction House for {price}."),
            ("{buyer} buys {title}",
             "The hammer fell at {price}. Readers will see what the new owner does with it."),
            ("Sold: {title}, to {buyer}",
             "{title} changed hands at the Auction House for {price}."),
        ],
        "ogene": [
            ("{buyer} takes {title}",
             "Sold for {price}."),
            ("{title} sold",
             "{buyer} pays {price}."),
            ("New owner for {title}",
             "{buyer}, at {price}."),
        ],
        "ledger": [
            ("Auction: {title} to {buyer} at {price}",
             "The price will be judged against the profit its readers bring each quarter."),
            ("{buyer} acquires {title} for {price}",
             "A title earns from its audience; its new owner may also print in it."),
            ("{title} sold for {price}",
             "The buyer is {buyer}."),
        ],
    },
}
