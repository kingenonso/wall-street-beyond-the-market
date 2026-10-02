"""Wordings for the news of companies using the stock market: takeover offers and how they end, sales of new shares, share splits, bonds, shareholder votes and how a takeover works out afterwards."""

KINDS = (
    "takeover_bid", "takeover_hostile", "takeover_won", "takeover_failed", "rights_issue", "share_offer",
    "offer_result", "share_split", "bond_issue", "government_bonds", "vote_result", "integration_good",
    "integration_bad",
)

WORDINGS = {
    "takeover_bid": {
        "herald": [
            ("{bidder} offers to buy {target}, and the board says yes",
             "{bidder} wants to own {stake} of {target} and is offering {price} for each share, {premium} above "
             "the price in the market. The directors of {target} advise its owners to accept. A purchase like "
             "this is called a takeover, and the owners have until the end of the quarter to decide."),
            ("Owners of {target} shares are offered {price} a share",
             "Anyone holding shares in {target} has a choice to make before the quarter ends. {bidder} is "
             "offering {price} for each one, which is {premium} more than the market was paying, and the "
             "company's own board recommends the offer. It goes through only if the owners of more than half "
             "the shares agree."),
            ("A new owner may be coming for {target}",
             "{bidder} has put {value} on the table to take control of {target}, a move known as a takeover. "
             "It is offering {price} a share so as to end up with {stake} of the company. The board of {target} "
             "supports the offer, but the last word belongs to the shareholders."),
        ],
        "ogene": [
            ("{bidder}: {value} offer for {target}",
             "{bidder} bids {price} a share for {target}, {premium} above the market price. The board of "
             "{target} backs the offer."),
            ("{target} ({ticker}): takeover offer on the table",
             "{bidder} wants {stake} of {target}. A takeover is one company buying control of another. "
             "Shareholders decide by the end of the quarter."),
            ("{bidder} moves to buy control of {target}",
             "The offer is {price} for each share, {value} in all. It needs the owners of more than half the "
             "shares to say yes."),
        ],
        "ledger": [
            ("{bidder} offers {price} a share for {stake} of {target} ({ticker})",
             "{bidder} has offered {price} a share to own {stake} of {target}, at a total cost of {value}. The "
             "price is {premium} above the last market price. The board of {target} recommends the offer, and "
             "shareholders have until the end of the quarter to accept."),
            ("{value} takeover offer for {ticker} comes {premium} above the market",
             "A takeover is the purchase of enough shares to control a company. {bidder} proposes to pay "
             "{value} for {stake} of {target}, or {price} a share, which is {premium} more than the shares "
             "last traded for. The directors of {target} advise acceptance."),
            ("{ticker}: board recommends {price} offer from {bidder}",
             "Investors in {target} are being asked to sell at {price} a share, {premium} more than the market "
             "price. {bidder} would spend {value} and hold {stake} of the company. The offer succeeds only if "
             "owners of more than half the shares accept before the quarter ends."),
        ],
    },
    "takeover_hostile": {
        "herald": [
            ("{target} board says no, so {bidder} asks the owners instead",
             "The directors of {target} have turned down an offer from {bidder} to buy the company. {bidder} "
             "is now putting the same offer straight to the shareholders: {price} for each share, {premium} "
             "above the market price. This is what is meant by a hostile takeover, one made against the "
             "board's wishes."),
            ("A tug of war over who should own {target}",
             "{bidder} wants {stake} of {target} and is ready to spend {value} to get it. The board of {target} "
             "has rejected the offer, but the board does not own the company. Its shareholders do, and each of "
             "them must now choose whether to sell at {price} a share before the quarter ends."),
            ("Shareholders of {target} must choose between board and buyer",
             "People who own shares in {target} are hearing two different things. {bidder} is offering them "
             "{price} a share, {premium} more than the market price. Their own directors tell them not to "
             "sell. The offer succeeds only if owners of more than half the shares accept."),
        ],
        "ogene": [
            ("{target} ({ticker}): board rejects offer, {bidder} presses on",
             "{bidder} goes over the board's head and offers shareholders {price} a share. That is a hostile "
             "takeover: an attempt to buy a company whose directors say no."),
            ("{bidder}: {value} offer for {target} goes straight to owners",
             "The board of {target} refuses the offer. {bidder} now asks shareholders directly for {stake} of "
             "the company."),
            ("{target} directors say no to {bidder}, owners to decide",
             "The board refuses the offer. {bidder} still offers {price} for each share, {premium} above the "
             "market price. Shareholders decide by the end of the quarter."),
        ],
        "ledger": [
            ("{bidder} takes rejected {price} offer for {ticker} to shareholders",
             "The board of {target} has rejected an offer of {price} a share from {bidder}, {premium} above the "
             "last market price. {bidder} is making the offer to shareholders directly, which is called a "
             "hostile takeover. It seeks {stake} of the company at a cost of {value}."),
            ("{value} offer for {target} proceeds without board support",
             "{bidder} wants to buy {stake} of {target} for {value}, or {price} a share. The directors of "
             "{target} advise shareholders to refuse. The decision rests with the shareholders, and the offer "
             "needs the owners of more than half the shares before the quarter ends."),
            ("{ticker}: directors oppose offer priced {premium} above the market",
             "Investors in {target} must weigh {price} a share from {bidder} against their board's advice to "
             "hold on. An offer made against a board's wishes is known as hostile. If it succeeds, {bidder} "
             "will pay {value} and own {stake} of {target}."),
        ],
    },
    "takeover_won": {
        "herald": [
            ("{bidder} now owns {stake} of {target}",
             "The takeover of {target} has gone through. Enough shareholders agreed to sell at {price} a share "
             "for {bidder} to end up with {stake} of the company, at a cost of {value}. Staff and customers of "
             "both firms will now see the two businesses joined up."),
            ("{target} has a new owner in charge",
             "Shareholders have had their say, and {bidder} has taken control of {target}. It paid {value} for "
             "{stake} of the shares. {target} will still be listed on the stock exchange, so anyone who kept "
             "shares can go on buying and selling them."),
            ("Enough owners sell, and {target} passes to {bidder}",
             "A takeover succeeds when the owners of more than half a company's shares accept the offer. That "
             "has now happened at {target}. {bidder} paid {price} for each share and holds {stake} of the "
             "company. The work of joining the two businesses begins."),
        ],
        "ogene": [
            ("{bidder} wins control of {target}",
             "The takeover succeeds. {bidder} now owns {stake} of {target} after paying {value}."),
            ("{target} ({ticker}): takeover goes through",
             "Shareholders accept {price} a share from {bidder}. {target} stays on the stock exchange."),
            ("{bidder}: {value} paid, {target} is now under its control",
             "{bidder} holds {stake} of {target}. The two businesses will now be joined up."),
        ],
        "ledger": [
            ("{bidder} completes {value} purchase of {stake} of {target} ({ticker})",
             "{bidder} now owns {stake} of {target} after shareholders accepted its offer of {price} a share. "
             "The purchase cost {value}. {target} remains listed on the exchange, and the two businesses will "
             "be combined."),
            ("{ticker}: offer of {price} a share succeeds",
             "Owners of enough shares in {target} accepted the offer for it to succeed. {bidder} paid {value} "
             "in all and holds {stake} of the company, which gives it control. Shareholders who did not sell "
             "keep their shares, and those shares still trade."),
            ("{stake} of {target} now held by {bidder}",
             "The takeover of {target} is complete at a cost to {bidder} of {value}, or {price} for each share "
             "bought. Investors will now watch how well the two businesses are joined, since that decides "
             "whether the money was well spent."),
        ],
    },
    "takeover_failed": {
        "herald": [
            ("{target} stays as it is after takeover offer falls short",
             "{bidder} has not managed to buy {target}. Owners of only {accepted} of the shares agreed to sell "
             "at {price}, and more than half was needed. The offer has ended, and every shareholder keeps the "
             "shares they had."),
            ("Too few owners agree to sell {target} to {bidder}",
             "A takeover needs the owners of more than half a company's shares to say yes. At {target} only "
             "{accepted} did. The offer of {price} a share from {bidder} therefore falls away, and nothing "
             "changes for the people who hold the shares."),
            ("{bidder} walks away from {target} empty-handed",
             "The attempt by {bidder} to take control of {target} is over. Shareholders were offered {price} "
             "for each share, but the owners of just {accepted} of them accepted. Nobody has sold anything: "
             "all the shares stay with their owners."),
        ],
        "ogene": [
            ("{bidder}: offer for {target} fails",
             "Only {accepted} of the shares are offered. More than half is needed. The takeover does not go "
             "ahead."),
            ("{target} ({ticker}): takeover offer ends without a sale",
             "The offer of {price} a share from {bidder} is finished. Shareholders keep their shares."),
            ("{target} shareholders turn down {bidder}",
             "Owners of {accepted} of the shares accept {price} a share. That is not enough, and the offer "
             "ends."),
        ],
        "ledger": [
            ("{bidder} offer for {target} ({ticker}) lapses with {accepted} accepted",
             "The offer by {bidder} of {price} a share for {target} has lapsed, which means it has ended "
             "without effect. Owners of {accepted} of the shares accepted, and the offer needed more than "
             "half. All shareholders keep their shares."),
            ("{ticker}: only {accepted} of shares offered to {bidder}",
             "{bidder} did not reach the level of acceptance it needed to take control of {target}. Its offer "
             "of {price} a share drew the owners of {accepted} of the shares, short of the half required. No "
             "shares change hands and no money is paid."),
            ("{price} offer for {target} falls short of half the shares",
             "Investors holding {accepted} of the shares in {target} were willing to sell to {bidder} at "
             "{price}. A takeover offer must win the owners of more than half the shares, so this one has "
             "ended. {target} carries on under its present owners."),
        ],
    },
    "rights_issue": {
        "herald": [
            ("{company} asks its own shareholders for {amount}",
             "{company} of {location} wants to raise {amount}, and it is turning first to the people who "
             "already own it. They are offered {terms}, at {price} a share, which is {discount} below the "
             "market price. This is called a rights issue. Owners who do not buy will hold a smaller slice of "
             "the company afterwards."),
            ("New shares at {price} for those who already own {company}",
             "Shareholders of {company} are being offered new shares at {discount} below the market price: "
             "{terms}. The {location} company hopes to bring in {amount} this way. The owners must vote on the "
             "plan before it can go ahead."),
            ("{location} firm {company} turns to its owners for fresh money",
             "A rights issue is a sale of new shares offered only to a company's existing owners. {company} "
             "plans one to raise {amount}, offering {terms} at {price} each. Those who take part keep their "
             "share of the company. Those who stay out see it shrink."),
        ],
        "ogene": [
            ("{company}: {amount} sought from shareholders",
             "{company} offers its owners {terms}, at {price} a share. That is {discount} below the market "
             "price."),
            ("{location}: {company} plans a rights issue",
             "A rights issue means new shares sold to existing owners. {company} wants {amount}. Shareholders "
             "vote on it."),
            ("{company} ({ticker}) offers owners new shares at {price}",
             "The aim is to raise {amount}. Owners who do not buy end up with a smaller part of the company."),
        ],
        "ledger": [
            ("{company} ({ticker}) to raise {amount} from owners at {price} a share",
             "{company} plans to raise {amount} from its existing shareholders, offering {terms}. The new "
             "shares are priced at {price}, {discount} below the market price. Shareholders who do not take "
             "part will own a smaller part of the company. The plan goes to a vote."),
            ("{ticker}: {amount} rights issue priced {discount} below the market",
             "A rights issue gives existing owners the first chance to buy new shares. {company} is offering "
             "{terms} at {price} each to raise {amount}. The price is set below the market to encourage "
             "owners to take part."),
            ("{amount} sought by {company} on the basis of {terms}",
             "Investors in {company}, a {location} company in the {sector} business, are asked to put in "
             "{amount} of new money. Each new share costs {price}, {discount} less than the market price. "
             "Shareholders must approve the plan by vote."),
        ],
    },
    "share_offer": {
        "herald": [
            ("{company} puts {shares} new shares on sale to everyone",
             "Anybody may now buy a piece of {company}, the {location} company in the {sector} business. It is "
             "selling {shares} new shares at {price} each and hopes to raise {amount}. Because there will be "
             "more shares in all, each present owner's slice of the company becomes a little smaller."),
            ("New shares in {company} go on sale at {price}",
             "{company} of {location} is creating {shares} new shares and offering them to the public. The "
             "company expects the sale to bring in {amount} of fresh money. Savers and traders who have never "
             "owned the shares can buy them alongside those who already do."),
            ("{location} firm {company} looks to the public for {amount}",
             "Rather than borrow, {company} is raising money by selling new shares to whoever wants them. "
             "There are {shares} on offer at {price} each. People who already hold shares keep them, but "
             "their part of the whole company shrinks slightly."),
        ],
        "ogene": [
            ("{company}: {shares} new shares on sale",
             "{company} sells new shares to the public at {price} each. It aims to raise {amount}."),
            ("{location}: {company} seeks {amount} from new share sale",
             "Anyone can buy. The price is {price} a share. Existing owners' slices get a little smaller."),
            ("{company} ({ticker}) opens share sale at {price}",
             "{shares} new shares are on offer. The company wants {amount} of fresh money."),
        ],
        "ledger": [
            ("{company} ({ticker}) offers {shares} new shares at {price}",
             "{company} is selling {shares} new shares to the public at {price} each, to raise {amount}. The "
             "sale is open to any investor. Existing shareholders will own a slightly smaller part of the "
             "company once the new shares exist."),
            ("{ticker}: {amount} to be raised from sale of new shares",
             "{company}, a {location} company in the {sector} business, plans to bring in {amount} by issuing "
             "{shares} shares at {price}. Money raised from shares does not have to be repaid, but it spreads "
             "the ownership of the company across more shares."),
            ("{amount} share sale opens at {company}",
             "Investors may buy new shares in {company} at {price} each. With {shares} on offer, a full sale "
             "would raise {amount}. Each existing share will then stand for a smaller part of the company."),
        ],
    },
    "offer_result": {
        "herald": [
            ("{company} raises {amount} from its share sale",
             "The sale of new shares in {company} has closed. Buyers took {taken} of the shares on offer, and "
             "the company has {amount} of new money as a result."),
            ("Buyers take {taken} of the new {company} shares",
             "{company} set out to sell new shares, and the count is now in. Buyers were found for {taken} of "
             "them, which brought the company {amount}."),
            ("Share sale at {company} ends with {amount} raised",
             "People who bought new shares in {company} now own part of the company. Between them they took "
             "{taken} of what was on offer and paid {amount} in all."),
        ],
        "ogene": [
            ("{company}: share sale brings in {amount}",
             "The sale is over. {taken} of the new shares find buyers."),
            ("{company} ({ticker}) closes its share sale",
             "{company} raises {amount}. Buyers take {taken} of the shares on offer."),
            ("{taken} of new {company} shares sold",
             "The company's sale of new shares ends. It collects {amount}."),
        ],
        "ledger": [
            ("{company} ({ticker}) raises {amount}, {taken} of offer taken up",
             "{company} has completed its sale of new shares and raised {amount}. Investors bought {taken} of "
             "the shares on offer."),
            ("{ticker}: {taken} of new shares find buyers",
             "The share sale at {company} is finished. It brought in {amount}, with {taken} of the new shares "
             "taken by investors. That money now sits with the company to spend or to keep in hand."),
            ("{amount} raised as {company} share sale closes",
             "Investors took {taken} of the new shares that {company} put on sale. The total raised was "
             "{amount}."),
        ],
    },
    "share_split": {
        "herald": [
            ("{company} splits its shares, and nobody gains or loses",
             "{company} is dividing its shares into smaller pieces: {terms}. The price of one share moves from "
             "about {old_price} to about {new_price}. Each owner holds more shares, each worth less, so the "
             "total value of what they own stays the same."),
            ("More shares, lower price: {company} announces a split",
             "Think of changing one large note for smaller ones. {company} is splitting its shares on the "
             "basis of {terms}, which takes the price from about {old_price} to about {new_price}. No owner is "
             "richer or poorer for it."),
            ("A share in {company} will cost about {new_price} after a split",
             "Shareholders of {company} will soon see more shares in their names and a lower price beside "
             "each one. The company is carrying out a share split: {terms}. The price was about {old_price}. "
             "The worth of each person's holding does not change."),
        ],
        "ogene": [
            ("{company}: share split announced",
             "{company} splits its shares, {terms}. The price goes from about {old_price} to about "
             "{new_price}."),
            ("{company} ({ticker}) cuts its share price by splitting",
             "Owners get more shares, each worth less. Nobody is richer or poorer."),
            ("{ticker}: price moves to about {new_price} after split",
             "A share split cuts each share into smaller ones. At {company} the terms are {terms}. The old "
             "price is about {old_price}."),
        ],
        "ledger": [
            ("{company} ({ticker}) splits shares: about {old_price} becomes about {new_price}",
             "{company} is splitting its shares on the basis of {terms}. The price adjusts from about "
             "{old_price} to about {new_price}. A split changes the number of shares and the price of each, "
             "but not the value of the company or of any holding."),
            ("{ticker}: share split on the basis of {terms}",
             "Investors in {company} will hold more shares at a lower price each, about {new_price} against "
             "about {old_price} before. The company raises no money from a split and no owner's part of the "
             "company changes."),
            ("Share split at {company} takes price to about {new_price}",
             "The terms of the split at {company} are {terms}. The share price falls from about {old_price} "
             "only because there are more shares, each standing for a smaller part of the same company."),
        ],
    },
    "bond_issue": {
        "herald": [
            ("{company} borrows {amount} from investors",
             "{company}, the {location} company in the {sector} business, has sold {bond} to raise {amount}. A "
             "bond is a loan from investors that can afterwards be bought and sold. The company will pay "
             "{rate} interest a year on it."),
            ("{location} firm {company} raises {amount} by selling a bond",
             "Instead of going to a bank, {company} has borrowed from investors. It sold {bond}, and it will "
             "pay them {rate} a year in interest. The money, {amount} in all, has to be paid back, unlike "
             "money raised from selling shares."),
            ("Investors lend {company} {amount} at {rate} a year",
             "A bond is a promise to repay a loan with interest. {company} of {location} has sold {bond} and "
             "taken in {amount}. Those who lent the money can keep the bond and collect the interest, or "
             "sell it on to someone else."),
        ],
        "ogene": [
            ("{company}: {amount} borrowed through a bond",
             "{company} sells {bond}. It pays {rate} interest a year."),
            ("{location}: {company} borrows {amount} from investors",
             "A bond is a loan from investors that can be bought and sold. {company} pays {rate} a year on "
             "this one."),
            ("{company} ({ticker}) sells bond at {rate}",
             "The company raises {amount} by selling {bond}. The money must be repaid with interest."),
        ],
        "ledger": [
            ("{company} ({ticker}) raises {amount} at {rate} a year",
             "{company} has borrowed {amount} from investors by selling {bond}, paying interest of {rate} a "
             "year. A bond is a loan that investors can trade among themselves."),
            ("{ticker}: {amount} bond sold, interest set at {rate}",
             "{company}, a {location} company in the {sector} business, sold {bond} and raised {amount}. The "
             "interest of {rate} a year is a new yearly cost for the company, and the sum borrowed must be "
             "repaid."),
            ("{rate} interest on {amount} borrowed by {company}",
             "Lenders to {company} have a new debt to count. The company raised {amount} by selling {bond}, "
             "at {rate} a year. Borrowing this way leaves the ownership of the company unchanged, since no "
             "new shares are created."),
        ],
    },
    "government_bonds": {
        "herald": [
            ("Government borrows {amount} more from investors",
             "The Government has raised {amount} by selling bonds, which are loans from investors that can be "
             "bought and sold. It will pay about {rate} a year in interest. Its bonds now add up to {total} "
             "owed in all."),
            ("Government debt on bonds reaches {total}",
             "When the Government spends more than it collects, it borrows the difference. It has just "
             "borrowed {amount} by selling bonds at about {rate} a year. The interest on that borrowing is "
             "paid out of public money."),
            ("Another {amount} borrowed in the public's name",
             "Savers and investors have lent the Government {amount} by buying its bonds. A bond is a promise "
             "to repay a loan with interest, here about {rate} a year. The Government now owes {total} on all "
             "its bonds together."),
        ],
        "ogene": [
            ("Government: {amount} borrowed through bonds",
             "The Government sells bonds worth {amount}. It pays about {rate} a year. Total owed on bonds: "
             "{total}."),
            ("Government bond debt now {total}",
             "A fresh {amount} is borrowed from investors at about {rate} a year. A bond is a loan that can "
             "be bought and sold."),
            ("Government sells bonds at about {rate}",
             "The sale raises {amount}. The Government's bond debt stands at {total}."),
        ],
        "ledger": [
            ("Government raises {amount} at about {rate}, bond debt {total}",
             "The Government borrowed {amount} by selling bonds, paying about {rate} a year. Its total debt on "
             "bonds is now {total}. A bond is a loan from investors that can be traded."),
            ("{total} now owed on Government bonds",
             "A sale of {amount} of bonds at about {rate} a year has taken the Government's bond debt to "
             "{total}. The rate the Government pays is closely watched, because lenders measure other "
             "borrowers against it."),
            ("Government bond sale: {amount} at about {rate} a year",
             "Investors lent the Government {amount} in its latest sale of bonds. The interest, about {rate} a "
             "year, is a cost to the public purse for as long as the bonds run. Total bond debt is {total}."),
        ],
    },
    "vote_result": {
        "herald": [
            ("{company} shareholders have voted: proposal {outcome}",
             "The owners of {company} were asked to vote on {matter}. It was {outcome}, with {support} of the "
             "votes cast in favour. Each share carries a vote, so those who own more of the company have "
             "more say."),
            ("Owners of {company} give their answer",
             "Big decisions at a company go to the people who own it. Shareholders of {company} have now "
             "voted on {matter}, and {support} of the votes were in favour. The proposal was {outcome}."),
            ("Proposal at {company} is {outcome} with {support} in favour",
             "The ballot at {company} has been counted. Shareholders were deciding on {matter}. Of the votes "
             "cast, {support} supported it, and the result is that it was {outcome}."),
        ],
        "ogene": [
            ("{company}: shareholder vote result is in",
             "Shareholders vote on {matter}. It is {outcome}, with {support} in favour."),
            ("{company} ({ticker}): proposal {outcome}",
             "The vote was on {matter}. Of the votes cast, {support} are in favour."),
            ("{ticker}: {support} of votes in favour, proposal {outcome}",
             "The owners of {company} have decided. The question before them was {matter}."),
        ],
        "ledger": [
            ("{company} ({ticker}) vote: {support} in favour, proposal {outcome}",
             "Shareholders of {company} voted on {matter}. The proposal was {outcome}, with {support} of the "
             "votes cast in favour."),
            ("{ticker}: proposal to shareholders {outcome} on {support} support",
             "The matter put to investors in {company} was {matter}. Votes in favour came to {support} of "
             "those cast, and it was {outcome}."),
            ("{support} of votes back proposal at {company}",
             "{company} has published the result of its shareholder vote on {matter}. With {support} of the "
             "votes cast in favour, the proposal was {outcome}."),
        ],
    },
    "integration_good": {
        "herald": [
            ("{bidder} and {target} are settling in well together",
             "There is encouraging news since {bidder} took over {target}. {detail} Joining two companies "
             "means putting their staff, suppliers and ways of working together, and it does not always go "
             "smoothly."),
            ("Good early signs after the takeover of {target}",
             "{detail} That is the latest word on how {bidder} is getting on with its purchase of {target}. "
             "For the workers and customers of both firms, it suggests the joining is going to plan."),
            ("Takeover of {target} begins to pay off for {bidder}",
             "When one company buys another, the hard part comes afterwards: making the two work as one. At "
             "{bidder} and {target} that work is going well. {detail}"),
        ],
        "ogene": [
            ("{bidder}: joining with {target} goes well",
             "Good news after the takeover of {target}. {detail}"),
            ("{target} ({ticker}): good progress after takeover",
             "The joining of {bidder} and {target} is on track. {detail}"),
            ("{bidder} reports progress at {target}",
             "{detail} The two businesses are being joined after the takeover."),
        ],
        "ledger": [
            ("{bidder} reports gains from combining with {target} ({ticker})",
             "{detail} The figures concern the joining of {bidder} and {target} after the takeover. Progress "
             "of this kind is what a buyer counts on to earn back what it paid."),
            ("{ticker}: joining of the two businesses is ahead",
             "Investors in {bidder} have a favourable report on its purchase of {target}. {detail}"),
            ("Combination of {bidder} and {target} is on course",
             "The records show the two businesses coming together well. {detail} A takeover is judged by "
             "whether the combined company does better than the two did apart."),
        ],
    },
    "integration_bad": {
        "herald": [
            ("{bidder} and {target} are finding it hard to work as one",
             "The takeover of {target} by {bidder} is proving difficult. {detail} Joining two companies means "
             "putting their staff, customers and ways of working together, and here it is not going "
             "smoothly."),
            ("Trouble after the takeover of {target}",
             "{detail} That is the latest word on how {bidder} is getting on with its purchase of {target}. "
             "For the workers and customers of both firms, it is an unsettling time."),
            ("Takeover of {target} gives {bidder} a headache",
             "Buying a company is one thing. Making it work alongside your own is another, and {bidder} is "
             "struggling with that at {target}. {detail}"),
        ],
        "ogene": [
            ("{bidder}: joining with {target} runs into trouble",
             "Bad news after the takeover of {target}. {detail}"),
            ("{target} ({ticker}): problems after takeover",
             "The joining of {bidder} and {target} is going badly. {detail}"),
            ("{bidder} reports setbacks at {target}",
             "{detail} The two businesses are still being joined after the takeover."),
        ],
        "ledger": [
            ("{bidder} reports setbacks in combining with {target} ({ticker})",
             "{detail} The figures concern the joining of {bidder} and {target} after the takeover. Setbacks of "
             "this kind make it harder for a buyer to earn back what it paid."),
            ("{ticker}: joining of the two businesses is behind",
             "Investors in {bidder} have an unfavourable report on its purchase of {target}. {detail}"),
            ("Combination of {bidder} and {target} is off course",
             "The records show the two businesses coming together poorly. {detail} A takeover is judged by "
             "whether the combined company does better than the two did apart."),
        ],
    },
}
