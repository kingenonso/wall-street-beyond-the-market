"""Wordings for the news of empires making deals in the stock market: offers to buy control of a listed company and
how they end, higher offers, a board's defence, large holdings made public, big blocks of shares sold between
empires, empires joining or splitting, and an auditor refusing to sign a company's accounts."""

KINDS = (
    "empire_offer", "empire_offer_won", "empire_offer_failed", "offer_topped", "defence_published",
    "stake_disclosed", "block_trade", "empires_merge", "spinoff", "audit_refused",
)

WORDINGS = {
    "empire_offer": {
        "herald": [
            ("{bidder} wants control of {target} and offers {price} a share",
             "The investment house {bidder} is offering {price} for each share of {target}, {premium} more than the "
             "market was paying. It wants to end up owning {stake} of the company, at a cost of {value}. The board of "
             "{target} {board}. Shareholders have until the end of the quarter to decide whether to sell."),
            ("Owners of {target} have an offer to think about",
             "Anyone holding {target} shares can sell them to {bidder} for {price} each, which is {premium} above "
             "the market price. The extra paid over the market price is called a premium. {bidder} is ready to "
             "spend {value} to own {stake}. The board of {target} {board}."),
            ("An investment house bids {value} for a big share of {target}",
             "{bidder}, a house that invests its members' money, is after {stake} of {target}. It offers {price} a "
             "share, {premium} over the market. {target} would stay on the exchange under the new owner. The board "
             "of {target} {board}. More than half the shares must be offered for the deal to go ahead."),
        ],
        "ogene": [
            ("{bidder} bids {price} a share for {target}",
             "The offer is {premium} above the market price. {bidder} wants {stake}. The board of {target} {board}."),
            ("{target} ({ticker}): {value} offer from {bidder}",
             "{bidder} offers {price} a share to own {stake} of {target}. The board of {target} {board}."),
            ("{bidder} moves on {target}",
             "{price} a share, {premium} over the market, {value} in all. The board of {target} {board}. Owners "
             "decide by the quarter's end."),
        ],
        "ledger": [
            ("{bidder} offers {price} per share for {stake} of {target} ({ticker})",
             "{bidder} has made an offer of {price} per share for {target}, a premium of {premium} to the last "
             "market price, seeking a holding of {stake}. Total consideration is {value}. The board of {target} "
             "{board}. The offer lapses unless holders of more than half the shares accept by the quarter's close."),
            ("{ticker}: {premium} premium in {value} offer from {bidder}",
             "Holders of {target} are offered {price} a share by {bidder}, which aims to control {stake} of the "
             "company. {target} would remain listed. The board of {target} {board}."),
            ("{bidder} puts {value} behind a bid for {ticker}",
             "The offer values each {target} share at {price}, {premium} above where the shares last traded. "
             "{bidder} targets a {stake} holding. The board of {target} {board}."),
        ],
    },
    "empire_offer_won": {
        "herald": [
            ("{bidder} now controls {target}",
             "Enough owners of {target} shares sold to {bidder} at {price} each. The investment house paid {value} "
             "and now owns {stake} of the company, which means it has the biggest say in how it is run. {target} "
             "stays on the exchange, and anyone who kept their shares still owns them."),
            ("{target} has a new controlling owner: {bidder}",
             "The offer worked. {bidder} spent {value} buying {target} shares at {price} each and now holds {stake}. "
             "Owning more than half of a company's shares is called having control. Ordinary shareholders can "
             "still buy and sell {target} on the exchange."),
            ("Shareholders say yes, and {bidder} takes charge at {target}",
             "{bidder} has bought its way to {stake} of {target}, paying {value} in all. The new owner will choose "
             "the directors, but {target} keeps its place on the exchange."),
        ],
        "ogene": [
            ("{bidder} takes the reins at {target}",
             "It paid {value} and now owns {stake}. {target} stays listed."),
            ("Done: {bidder} holds {stake} of {target}",
             "Owners sold at {price} a share. {bidder} spent {value}."),
            ("{target} ({ticker}) changes hands",
             "{bidder} takes control with {stake}. The shares still trade on the exchange."),
        ],
        "ledger": [
            ("{bidder} secures {stake} of {target} ({ticker}) for {value}",
             "{bidder}'s offer of {price} per share has succeeded. It now holds {stake} of {target}, having paid "
             "{value}. {target} remains listed, and the shares not sold to {bidder} continue to trade."),
            ("{ticker}: offer succeeds at {price} a share",
             "Acceptances gave {bidder} a controlling holding of {stake} in {target}. The cost was {value}. The "
             "company keeps its listing and its minority shareholders."),
            ("Control of {target} passes to {bidder}",
             "With {stake} of the shares, bought at {price} each for a total of {value}, {bidder} can now appoint "
             "the board of {target}. The listing is unaffected."),
        ],
    },
    "empire_offer_failed": {
        "herald": [
            ("{bidder} fails to win control of {target}",
             "Not enough owners of {target} wanted to sell to {bidder} at {price} a share. Only the owners of "
             "{accepted} of the shares said yes, and more than half was needed. So the offer is off, and everybody "
             "keeps the shares they had."),
            ("Owners of {target} turn down {bidder}",
             "The offer of {price} a share has failed. Shareholders holding just {accepted} of {target} accepted it, "
             "short of the more than half it needed. No shares change hands."),
            ("No sale: {target} shareholders hold on to their shares",
             "{bidder} offered {price} a share for control of {target}, but only {accepted} of the shares were "
             "offered to it. The deal falls away and nothing changes for those who own {target}."),
        ],
        "ogene": [
            ("{bidder}'s offer for {target} fails",
             "Only {accepted} accepted. More than half was needed. Everyone keeps their shares."),
            ("{target} ({ticker}): owners say no",
             "The {price} offer from {bidder} wins just {accepted} of the shares."),
            ("Offer lapses at {target}",
             "{bidder} falls short with {accepted}. No shares change hands."),
        ],
        "ledger": [
            ("{bidder}'s {price} offer for {ticker} lapses",
             "Acceptances reached only {accepted} of {target}'s shares, below the majority required. The offer from "
             "{bidder} has lapsed and all holders retain their shares."),
            ("{ticker}: {accepted} acceptance leaves {bidder} short",
             "Holders of {target} declined to sell at {price} per share. With {accepted} accepting, {bidder} did not "
             "reach the more than half it needed, and no shares will transfer."),
            ("{target} stays out of {bidder}'s hands",
             "The offer at {price} a share closed with {accepted} acceptances. It has failed, and the register of "
             "{target} shareholders is unchanged."),
        ],
    },
    "offer_topped": {
        "herald": [
            ("{rival} beats {bidder} with a higher offer for {target}",
             "A second investment house has joined the race for {target}. {rival} is offering {price} for each "
             "share, more than {bidder} offered. Owners who already said yes to the earlier offer are counted as "
             "saying yes to this higher one, so nobody loses out."),
            ("Bidding war for {target}: {rival} offers {price}",
             "{rival} has topped the offer from {bidder}. The price for each {target} share is now {price}. When "
             "buyers compete like this it is called a bidding war, and it usually pushes the price up for the "
             "owners."),
            ("A better price for {target} owners",
             "{target} shareholders now have a higher offer of {price} a share, from {rival}. It replaces the lower "
             "one from {bidder}. Anyone who accepted before is treated as accepting the new price."),
        ],
        "ogene": [
            ("{rival} tops {bidder} for {target}",
             "New offer: {price} a share. Earlier acceptances move to the higher bid."),
            ("{target} ({ticker}): price goes up to {price}",
             "{rival} outbids {bidder}. A bidding war is on."),
            ("Higher bid for {target} from {rival}",
             "{rival} offers {price} a share, beating {bidder}."),
        ],
        "ledger": [
            ("{rival} trumps {bidder} with {price} offer for {ticker}",
             "{rival} has made a competing offer for {target} at {price} per share, above the terms from {bidder}. "
             "Acceptances already given to the earlier offer will be counted towards the higher one."),
            ("{ticker}: competing bid lifts offer price to {price}",
             "The contest for {target} has intensified. {rival} now offers {price} a share, superseding the offer "
             "from {bidder}. Shareholders who accepted earlier are carried over to the new terms."),
            ("Rival offer for {target} at {price} a share",
             "A higher offer from {rival} replaces that of {bidder}. Holders of {target} need take no action to "
             "move an existing acceptance across."),
        ],
    },
    "defence_published": {
        "herald": [
            ("{target} board says its shares are worth {worth}, not {price}",
             "The directors of {target} say the offer from {bidder} is too low. With help from an investment "
             "banker, an adviser who works out what companies are worth, they have put each share's value at "
             "{worth}. {bidder} is offering {price}. Owners must now decide whom to believe."),
            ("{target} fights back against {bidder}",
             "The board of {target} has published its own figures. It says each share is worth {worth}, well above "
             "the {price} that {bidder} is offering, and it tells shareholders not to sell for less."),
            ("Don't sell too cheap, {target} tells its owners",
             "{bidder} offers {price} a share for {target}. The board, advised by an investment banker, says the "
             "true value is {worth} and calls the offer too low."),
        ],
        "ogene": [
            ("{target} board: offer too low",
             "Directors value each share at {worth}. {bidder} offers {price}."),
            ("{target} ({ticker}) says it is worth {worth} a share",
             "The board rejects {bidder}'s {price} as too cheap."),
            ("{target} hits back at {bidder}",
             "Board publishes a value of {worth} a share against an offer of {price}."),
        ],
        "ledger": [
            ("{target} board values {ticker} at {worth} a share, rejecting {price} offer",
             "The board of {target}, advised by an investment banker, has published a valuation of {worth} per share. "
             "It says the offer of {price} from {bidder} undervalues the company and urges shareholders not to "
             "accept."),
            ("{ticker} defence document puts value at {worth}",
             "{target} has set out its case against {bidder}. Its advisers value the shares at {worth}, against an "
             "offer of {price}. A defence document is a board's published argument for rejecting an offer."),
            ("{target} says {bidder} offer of {price} is too low",
             "In its formal response, the board of {target} puts the value of each share at {worth} and advises "
             "holders to reject the offer."),
        ],
    },
    "stake_disclosed": {
        "herald": [
            ("{empire} now owns {stake} of {company}",
             "The investment house {empire} has told the market it holds {stake} of {company}. The law says anyone "
             "who owns 5% or more of a listed company must say so, and say so again at every further 5%. That way "
             "other shareholders know who is building up a big holding."),
            ("Who is buying {company}? {empire}, with {stake}",
             "{empire} has declared a holding of {stake} in {company}. Big holders must make themselves known, so "
             "that nobody can quietly gather control of a company."),
            ("{empire} reveals a {stake} holding in {company}",
             "Shareholders of {company} now know that {empire} owns {stake} of the company, after it made the "
             "announcement the law requires."),
        ],
        "ogene": [
            ("{empire} holds {stake} of {company}",
             "The law requires big holders to declare themselves at every 5% step."),
            ("{company} ({ticker}): {empire} declares {stake}",
             "{empire} makes its holding public."),
            ("{empire} builds a {stake} stake in {company}",
             "Declared to the market as the law requires."),
        ],
        "ledger": [
            ("{empire} discloses {stake} holding in {company} ({ticker})",
             "{empire} has notified the market that it holds {stake} of {company}. Holders of 5% or more of a "
             "listed company must disclose it, and again at each further 5%."),
            ("{ticker}: {empire} crosses the {stake} line",
             "A disclosure filed this quarter shows {empire} with {stake} of {company}. A stake is the part of a "
             "company's shares an investor owns."),
            ("Holding notice: {empire} at {stake} of {company}",
             "{empire} now owns {stake} of {company}'s shares, according to the notice it was required to file."),
        ],
    },
    "block_trade": {
        "herald": [
            ("{seller} sells {shares} {company} shares to {buyer}",
             "One investment house has sold a large bundle of {company} shares straight to another. {seller} sold "
             "{shares} shares to {buyer} for {amount}. A sale like this, done directly between a buyer and a "
             "seller rather than on the exchange's open list of orders, is called a block trade. The price was "
             "close to the market price."),
            ("{amount} deal moves {company} shares from {seller} to {buyer}",
             "{buyer} has bought {shares} shares of {company} from {seller}, paying {amount}. The deal was agreed "
             "between the two privately, near the market price, so it did not jolt the share price."),
            ("A big parcel of {company} shares changes owner",
             "{seller} has handed {shares} {company} shares to {buyer} in one go, for {amount}. Doing it in one "
             "private sale avoids pushing the price around on the exchange."),
        ],
        "ogene": [
            ("{seller} sells {company} block to {buyer}",
             "{shares} shares go for {amount}, near the market price."),
            ("{company} ({ticker}): {amount} block trade",
             "{buyer} buys {shares} shares from {seller}, off the exchange."),
            ("{buyer} picks up {shares} {company} shares",
             "Bought from {seller} for {amount} in one private deal."),
        ],
        "ledger": [
            ("{ticker} block: {shares} shares cross from {seller} to {buyer}",
             "{seller} has sold {shares} shares of {company} to {buyer} for {amount} in a block trade, a large "
             "negotiated sale arranged off the exchange's order book. The price was set near the prevailing market "
             "price."),
            ("{buyer} acquires {shares} {company} shares for {amount}",
             "The shares were bought directly from {seller} rather than through the order book, limiting the "
             "effect on {company}'s quoted price."),
            ("Block trade in {company}: {amount}",
             "{shares} {company} shares changed hands between {seller} and {buyer} in a single off-book sale, priced "
             "close to the market."),
        ],
    },
    "empires_merge": {
        "herald": [
            ("{other} joins {empire}",
             "Two investment houses are now one. The members of {empire} and of {other} voted for it, and the "
             "members and everything {other} owned are now part of {empire}. The name {empire} carries on."),
            ("{empire} and {other} come together",
             "Members of both houses said yes. From now on the people and holdings of {other} belong to {empire}, "
             "which carries on as the larger house."),
            ("A bigger {empire} after {other} folds in",
             "{other} has joined {empire} after a vote by the members of both. Its holdings move across to {empire}."),
        ],
        "ogene": [
            ("{empire} and {other} become one",
             "Members of both vote yes. {other} folds into {empire}."),
            ("{other} merges into {empire}",
             "Its members and holdings now sit inside {empire}."),
            ("Vote passes: {other} joins {empire}",
             "{empire} carries on, now larger."),
        ],
        "ledger": [
            ("{other} combines with {empire}",
             "Following votes by the members of both houses, the members and holdings of {other} have been "
             "transferred to {empire}, which continues as the combined investor."),
            ("{empire} absorbs {other} after members' vote",
             "The merger has been approved by both memberships. A merger is two organisations becoming one. The "
             "portfolio of {other} is now held by {empire}."),
            ("Combination complete: {empire} takes in {other}",
             "{empire} is the continuing house. The holdings and members of {other} move across to it."),
        ],
    },
    "spinoff": {
        "herald": [
            ("{empire} splits off {company} into a new house, {new_empire}",
             "Members of {empire} have voted to give {company}, a private company it controlled, a home of its own. "
             "It now belongs to a new investment house, {new_empire}, owned by the same investors. Splitting part "
             "of a business off like this is called a spin-off."),
            ("{company} gets a new owner of its own: {new_empire}",
             "{empire} has handed {company} to {new_empire}, a new investment house. The investors are the same "
             "people, now holding {company} through {new_empire}. The members of {empire} voted for the change."),
            ("{empire} members vote to spin off {company}",
             "From now on {company} will sit in {new_empire}, a new house owned by the investors of {empire}."),
        ],
        "ogene": [
            ("{empire} spins off {company}",
             "Members vote to move it into a new house, {new_empire}."),
            ("New house {new_empire} formed to own {company}",
             "Same investors as {empire}, after a members' vote."),
            ("{company} leaves {empire}",
             "It now belongs to {new_empire}, a spin-off owned by the same investors."),
        ],
        "ledger": [
            ("{empire} spins off {company} as {new_empire}",
             "Members of {empire} have approved the separation of {company}, a private company under its control, "
             "into a new house, {new_empire}. The new house is owned by the same investors."),
            ("Spin-off: {company} moves into {new_empire}",
             "Ownership of {company} has passed from {empire} to {new_empire} following a members' vote. The "
             "investors are unchanged, holding the company through the new vehicle."),
            ("{new_empire} created to hold {company}",
             "{empire} has separated {company} from the rest of its holdings. A spin-off puts part of an investor's "
             "holdings into a new, separate owner."),
        ],
    },
    "audit_refused": {
        "herald": [
            ("Auditor will not sign {company}'s accounts",
             "{firm}, the firm hired to check the accounts of {company}, has refused to sign them as true. An "
             "auditor's signature tells everyone the figures can be trusted. Without it, anyone thinking of buying "
             "{company} has reason to be careful."),
            ("Doubts over the figures at {company}",
             "The auditor {firm} has refused to put its name to the accounts of {company}. Buyers will take note "
             "of that."),
            ("{firm} says no to {company}'s accounts",
             "{company} has failed to get its accounts signed off. Its auditor, {firm}, would not say they are true, "
             "a warning sign to anyone who might buy it."),
        ],
        "ogene": [
            ("{firm} refuses to sign {company} accounts",
             "Buyers will take note."),
            ("No sign-off for {company}",
             "Auditor {firm} will not vouch for the figures."),
            ("Red flag at {company}",
             "{firm} refuses to sign the accounts as true."),
        ],
        "ledger": [
            ("{firm} declines to sign {company}'s accounts",
             "{firm}, the auditor of {company}, has refused to certify the company's accounts as a true picture of "
             "its affairs. Prospective buyers are likely to discount the figures accordingly."),
            ("Audit refused at {company}",
             "An audit is an independent check of a company's accounts. {firm} has declined to sign those of "
             "{company}, a serious mark against the reliability of its figures."),
            ("{company} accounts left unsigned by {firm}",
             "The auditor's refusal to sign means {company}'s reported numbers lack independent confirmation, which "
             "any buyer will weigh."),
        ],
    },
}
