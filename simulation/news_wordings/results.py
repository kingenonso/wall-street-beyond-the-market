"""Wordings for the news that follows a quarter's accounts: results, credit ratings, unpaid debts, jobs, dividends, expansion, bank loan losses and the "in brief" columns."""

KINDS = (
    "results_strong", "results_weak", "company_loss", "back_in_profit", "rating_upgrade", "rating_downgrade",
    "default", "missed_payment", "job_cuts", "hiring", "dividend_cut", "expansion", "bank_loan_losses",
    "roundup_results", "roundup_jobs",
)

WORDINGS = {
    "results_strong": {
        "herald": [
            ("A good quarter for {company} as profit climbs {change}",
             "{company}, the {location} company in the {sector} business, earned {profit} after tax in {quarter}. "
             "That is up {change} on the {previous_profit} it made the quarter before. {cause}"),
            ("{location} firm {company} reports a sharp rise in profit",
             "There was good news in {location} for the people who work at {company} and those who supply it. "
             "The company took {sales} in sales in {quarter} and kept {profit} of it as profit after tax, "
             "up from {previous_profit}. {cause}"),
            ("Profit at {company} rises to {profit}",
             "{cause} That is how {company} explains a strong {quarter}. The {location} company made {profit} "
             "after tax, against {previous_profit} three months earlier, on sales of {sales}."),
        ],
        "ogene": [
            ("{company}: profit jumps {change}",
             "{company} reports a profit of {profit} for {quarter}, up {change}. {cause}"),
            ("{location}: {company} profit surges to {profit}",
             "Profit at {company} rises sharply, from {previous_profit} to {profit}. Sales for {quarter} "
             "stand at {sales}."),
            ("Strong quarter at {company} ({ticker})",
             "{cause} Profit after tax is up {change} at {profit}."),
        ],
        "ledger": [
            ("{company} ({ticker}) profit up {change} to {profit}",
             "Profit after tax at {company} was {profit} in {quarter}, against {previous_profit} the quarter "
             "before, a rise of {change}. Sales were {sales}. {cause}"),
            ("{profit} profit on {sales} of sales at {company}",
             "{company} ({ticker}) kept {profit} as profit after tax from sales of {sales} in {quarter}. The "
             "figure for the previous quarter was {previous_profit}. {cause}"),
            ("{ticker}: profit after tax rises {change} for {quarter}",
             "Investors in {company} have a sharply better quarter to read. Profit after tax rose {change}, "
             "from {previous_profit} to {profit}, with sales of {sales}. {cause}"),
        ],
    },
    "results_weak": {
        "herald": [
            ("A harder quarter for {company} as profit drops {change}",
             "{company}, the {location} company in the {sector} business, made {profit} after tax in {quarter}. "
             "That is down {change} from {previous_profit} the quarter before, though it is still a profit. "
             "{cause}"),
            ("{company} still earning, but far less than before",
             "{cause} That is the reason {company} gives for a weak {quarter}. The {location} company kept "
             "{profit} as profit after tax, where it had kept {previous_profit} three months earlier."),
            ("Profit at {location} firm {company} shrinks to {profit}",
             "Workers and suppliers of {company} in {location} have learned that the company's profit "
             "has fallen {change}. It took {sales} in sales in {quarter} and made {profit} after tax. {cause}"),
        ],
        "ogene": [
            ("{company}: profit falls {change}",
             "{company} reports a profit of {profit} for {quarter}, down {change}. {cause}"),
            ("{location}: {company} profit slides to {profit}",
             "Profit at {company} drops from {previous_profit} to {profit}. The company is still in profit."),
            ("Weak quarter at {company} ({ticker})",
             "{cause} Profit after tax is down {change} at {profit}, on sales of {sales}."),
        ],
        "ledger": [
            ("{company} ({ticker}) profit down {change} to {profit}",
             "Profit after tax at {company} was {profit} in {quarter}, against {previous_profit} the quarter "
             "before, a fall of {change}. Sales were {sales}. {cause}"),
            ("{company} keeps {profit} from {sales} of sales, down {change}",
             "{company} ({ticker}) kept only {profit} as profit after tax from sales of {sales} in {quarter}, "
             "down from {previous_profit}. The company remains profitable. {cause}"),
            ("{ticker}: profit after tax falls {change} for {quarter}",
             "Investors in {company} have a sharply weaker quarter to read. Profit after tax fell {change}, "
             "from {previous_profit} to {profit}, on sales of {sales}. {cause}"),
        ],
    },
    "company_loss": {
        "herald": [
            ("{company} slips into a loss of {profit}",
             "{company}, the {location} company in the {sector} business, lost {profit} in {quarter}. It had "
             "made a profit of {previous_profit} the quarter before. {cause}"),
            ("Bad quarter in {location} as {company} spends more than it earns",
             "{cause} That is how {company} explains a painful {quarter}. The company took {sales} in sales "
             "but its costs were higher still, leaving a loss of {profit}."),
            ("From profit to loss at {company}",
             "Three months ago {company} was {previous_profit} in profit. Its accounts for {quarter} show a "
             "loss of {profit} instead, news that matters to everyone in {location} who works for it or "
             "sells to it. {cause}"),
        ],
        "ogene": [
            ("{company}: loss of {profit}",
             "{company} reports a loss of {profit} for {quarter}. {cause}"),
            ("{location}: {company} falls into the red",
             "{company} is losing money. It reports a loss of {profit}, after a profit of {previous_profit} "
             "the quarter before."),
            ("{company} ({ticker}) swings to a loss",
             "{cause} The result is a loss of {profit} on sales of {sales}."),
        ],
        "ledger": [
            ("{company} ({ticker}) reports {profit} loss for {quarter}",
             "{company} made a loss after tax of {profit} in {quarter}, against a profit of {previous_profit} "
             "the quarter before. Sales were {sales}. {cause}"),
            ("{profit} loss on {sales} of sales at {company}",
             "Costs at {company} ({ticker}) ran ahead of its sales of {sales} in {quarter}, leaving a loss of "
             "{profit}. A loss is paid for out of the company's own cash or by borrowing. {cause}"),
            ("{ticker}: profit of {previous_profit} turns to loss of {profit}",
             "Investors and lenders to {company} have a loss to weigh for {quarter}. The company lost "
             "{profit}, where it had earned {previous_profit} three months earlier. {cause}"),
        ],
    },
    "back_in_profit": {
        "herald": [
            ("{company} is making money again",
             "{company}, the {location} company in the {sector} business, made a profit of {profit} in "
             "{quarter}. It had lost {previous_profit} the quarter before. {cause}"),
            ("Relief in {location} as {company} returns to profit",
             "{cause} That is how {company} explains its turn for the better. After a loss of "
             "{previous_profit}, the company took {sales} in sales in {quarter} and kept {profit} as profit "
             "after tax."),
            ("From loss to profit of {profit} at {company}",
             "Three months ago {company} was losing money. Its accounts for {quarter} show a profit of "
             "{profit}, welcome news for those in {location} who work for it or sell to it. {cause}"),
        ],
        "ogene": [
            ("{company}: back in profit",
             "{company} reports a profit of {profit} for {quarter}. {cause}"),
            ("{location}: {company} ends its losses",
             "{company} is out of the red. It reports a profit of {profit}, after a loss of {previous_profit} "
             "the quarter before."),
            ("{company} ({ticker}) swings to a profit of {profit}",
             "{cause} The result is a profit of {profit} on sales of {sales}."),
        ],
        "ledger": [
            ("{company} ({ticker}) returns to profit with {profit}",
             "{company} made a profit after tax of {profit} in {quarter}, against a loss of {previous_profit} "
             "the quarter before. Sales were {sales}. {cause}"),
            ("Sales of {sales} put {company} back in profit",
             "Sales of {sales} at {company} ({ticker}) more than covered its costs in {quarter}, leaving a "
             "profit of {profit}. The previous quarter ended in a loss of {previous_profit}. {cause}"),
            ("{ticker}: loss of {previous_profit} turns to profit of {profit}",
             "Investors and lenders to {company} have a recovery to weigh for {quarter}. The company earned "
             "{profit}, where it had lost {previous_profit} three months earlier. {cause}"),
        ],
    },
    "rating_upgrade": {
        "herald": [
            ("{company} judged a safer borrower",
             "{company} of {location} has had its credit rating raised from {old_rating} to {rating}. A credit "
             "rating is a published judgement of how safely a company can repay what it borrows. A better "
             "one usually means the company can borrow more cheaply."),
            ("Good marks for {location} firm {company}",
             "The credit rating of {company}, which is in the {sector} business, has moved up to {rating} "
             "from {old_rating}. The rating tells lenders how likely they are to get their money back, on a "
             "scale that runs from AAA, the safest, down to D."),
            ("{company} moves up the credit scale to {rating}",
             "Lenders now have more reason to trust {company}. Its credit rating, the published measure of "
             "how safely it can repay its loans, has been lifted from {old_rating} to {rating}. That is a "
             "sign of a company in {location} standing on firmer ground."),
        ],
        "ogene": [
            ("{company}: credit rating raised to {rating}",
             "{company} moves up from {old_rating} to {rating}. The rating measures how safely a company can "
             "repay what it borrows."),
            ("{location}: {company} wins a better rating",
             "{company} is now rated {rating}, up from {old_rating}. That marks it as a safer borrower."),
            ("Upgrade for {company} ({ticker})",
             "The credit rating of {company} rises to {rating}. A higher rating means lenders see less risk "
             "of not being repaid."),
        ],
        "ledger": [
            ("{company} ({ticker}) upgraded to {rating} from {old_rating}",
             "The credit rating of {company} has been raised from {old_rating} to {rating}. A credit rating "
             "is a published judgement of how safely a company can repay its borrowing, running from AAA, "
             "the safest, to D. Lenders usually charge less interest to companies with a higher rating."),
            ("{ticker}: rating lifted to {rating}",
             "{company}, in the {sector} business, is now rated {rating} against {old_rating} before. The "
             "rating is a measure of how likely the company is to repay what it owes. For lenders and "
             "investors the change signals a lower risk of loss."),
            ("Rating of {rating} for {company} points to cheaper borrowing",
             "{company} ({ticker}) of {location} has moved from {old_rating} to {rating} on the credit scale, "
             "which grades how safely a borrower can repay. A higher grade usually lowers the cost of new "
             "loans."),
        ],
    },
    "rating_downgrade": {
        "herald": [
            ("{company} judged a riskier borrower",
             "{company} of {location} has had its credit rating lowered from {old_rating} to {rating}. A credit "
             "rating is a published judgement of how safely a company can repay what it borrows. A worse "
             "one usually means the company must pay more to borrow."),
            ("Poorer marks for {location} firm {company}",
             "The credit rating of {company}, which is in the {sector} business, has moved down to {rating} "
             "from {old_rating}. The rating tells lenders how likely they are to get their money back, on a "
             "scale that runs from AAA, the safest, down to D."),
            ("{company} moves down the credit scale to {rating}",
             "Lenders now have less reason to trust {company}. Its credit rating, the published measure of "
             "how safely it can repay its loans, has been cut from {old_rating} to {rating}. Workers and "
             "suppliers in {location} will want to see the company steady itself."),
        ],
        "ogene": [
            ("{company}: credit rating cut to {rating}",
             "{company} moves down from {old_rating} to {rating}. The rating measures how safely a company "
             "can repay what it borrows."),
            ("{location}: {company} loses its {old_rating} rating",
             "{company} is now rated {rating}, down from {old_rating}. That marks it as a riskier borrower."),
            ("Downgrade for {company} ({ticker})",
             "The credit rating of {company} falls to {rating}. A lower rating means lenders see more risk "
             "of not being repaid."),
        ],
        "ledger": [
            ("{company} ({ticker}) downgraded to {rating} from {old_rating}",
             "The credit rating of {company} has been lowered from {old_rating} to {rating}. A credit rating "
             "is a published judgement of how safely a company can repay its borrowing, running from AAA, "
             "the safest, to D. Lenders usually charge more interest to companies with a lower rating."),
            ("{ticker}: rating lowered to {rating}",
             "{company}, in the {sector} business, is now rated {rating} against {old_rating} before. The "
             "rating is a measure of how likely the company is to repay what it owes. For lenders and "
             "investors the change signals a higher risk of loss."),
            ("Rating of {rating} for {company} points to dearer borrowing",
             "{company} ({ticker}) of {location} has moved from {old_rating} to {rating} on the credit scale, "
             "which grades how safely a borrower can repay. A lower grade usually raises the cost of new "
             "loans."),
        ],
    },
    "default": {
        "herald": [
            ("{company} fails to repay {amount}",
             "{company}, the {location} company in the {sector} business, has failed to repay {amount} of "
             "borrowing that fell due. Its credit rating, the published judgement of how safely it can "
             "repay what it borrows, has dropped to D, the lowest there is."),
            ("Hard days in {location} as {company} cannot pay its lenders",
             "The money was due and {company} did not have it. The company has failed to repay {amount} it "
             "had borrowed, a serious blow for the people in {location} who work for it and the businesses "
             "that supply it. It is now rated D, the mark given to a borrower that has failed to repay."),
            ("{company} breaks its promise to lenders",
             "A loan is a promise to pay back. {company} has broken that promise on {amount} of borrowing, "
             "and now carries a credit rating of D, the bottom of the scale. Those who lent the money must "
             "now wait to learn how much of it they will see again."),
        ],
        "ogene": [
            ("{company}: fails to repay {amount}",
             "{company} does not repay {amount} of borrowing that has fallen due. Its credit rating drops to "
             "D, the lowest grade."),
            ("{location}: {company} defaults on its debts",
             "{company} defaults, meaning it fails to repay money it borrowed. The sum is {amount}."),
            ("{company} ({ticker}) rated D after failing to repay",
             "Lenders to {company} are left unpaid. The company owes them {amount} that was due."),
        ],
        "ledger": [
            ("{company} ({ticker}) defaults on {amount}",
             "{company} has defaulted, which means it failed to repay borrowing when it fell due. The sum "
             "unpaid is {amount}. Its credit rating is now D, the grade for a borrower that has failed to "
             "repay."),
            ("{amount} goes unpaid at {company}",
             "Lenders to {company}, in the {sector} business, did not receive {amount} that was owed to them "
             "on time. The company is now rated D, the lowest point on the scale that grades how safely a "
             "borrower can repay. Lenders may have to accept that part of the money is lost."),
            ("{ticker}: rated D after {amount} of borrowing is not repaid",
             "{company} of {location} could not repay {amount} of borrowing that came due. A rating of D "
             "tells lenders and investors that the company has failed to pay what it owes. New borrowing "
             "is very hard to obtain at that grade."),
        ],
    },
    "missed_payment": {
        "herald": [
            ("{company} falls behind on {amount} of payments",
             "{company}, the {location} company in the {sector} business, could not pay {amount} of bills "
             "and loan instalments this quarter. It still owes the money. The company has not failed, but "
             "those waiting to be paid will have to wait longer."),
            ("Unpaid bills pile up at {location} firm {company}",
             "Suppliers and lenders to {company} are owed {amount} that the company could not find this "
             "quarter. The debt has not gone away and must still be paid. For a business in {location} that "
             "others depend on, it is a sign that cash is short."),
            ("{company} short of cash to pay what it owes",
             "A company that cannot pay on time is a company under strain. {company} missed {amount} of "
             "payments on its bills and loans this quarter and carries the debt forward. It is still "
             "trading and has not failed outright."),
        ],
        "ogene": [
            ("{company}: misses {amount} of payments",
             "{company} cannot pay {amount} of bills and loan instalments this quarter. The money is still "
             "owed."),
            ("{location}: {company} runs short of cash",
             "{company} is behind on {amount} it owes. The company is still trading."),
            ("{company} ({ticker}) fails to pay bills on time",
             "Unpaid bills and loan instalments at {company} reach {amount}. The company has not failed "
             "outright."),
        ],
        "ledger": [
            ("{company} ({ticker}) misses {amount} of payments",
             "{company} was unable to pay {amount} of bills and loan instalments this quarter. The sum "
             "remains owed. The company has not defaulted, which would mean failing outright to repay "
             "borrowing that had fallen due."),
            ("{amount} overdue at {company}",
             "Cash at {company}, in the {sector} business, did not cover what it had to pay this quarter. "
             "It is {amount} behind on bills and loan instalments. Lenders and suppliers will watch whether "
             "the company clears the sum next quarter."),
            ("{ticker}: {amount} of bills and instalments unpaid",
             "{company} of {location} ended the quarter owing {amount} that it should already have paid. "
             "Missed payments are an early warning for lenders, because they show a company spending cash "
             "faster than it comes in."),
        ],
    },
    "job_cuts": {
        "herald": [
            ("{company} cuts {jobs} jobs in {location}",
             "{company}, the {location} company in the {sector} business, has cut {jobs} jobs. It now employs "
             "{staff} people. For the families who relied on those wages, the search for new work begins."),
            ("Workers in {location} lose their jobs as {company} shrinks",
             "The workforce at {company} is smaller this quarter by {jobs} jobs. That leaves {staff} people "
             "on its payroll. Fewer wages in {location} also means less money spent in its shops and "
             "markets."),
            ("{company} lets staff go",
             "There are {jobs} fewer jobs at {company} than there were three months ago. The company, one of "
             "the employers in {location}, now has {staff} staff."),
        ],
        "ogene": [
            ("{company}: {jobs} jobs cut",
             "{company} cuts {jobs} jobs. Its workforce is now {staff}."),
            ("{location}: job losses at {company}",
             "{company} is shedding staff. It cuts {jobs} jobs this quarter."),
            ("{company} ({ticker}) shrinks its workforce to {staff}",
             "The company removes {jobs} jobs. Workers in {location} are affected."),
        ],
        "ledger": [
            ("{company} ({ticker}) cuts {jobs} jobs",
             "{company} reduced its workforce by {jobs} jobs this quarter and now employs {staff} people. "
             "A smaller workforce lowers the company's wage bill, one of its main costs."),
            ("Workforce at {company} down to {staff}",
             "{company}, in the {sector} business, ended the quarter with {staff} staff after cutting {jobs} "
             "jobs. Investors will look to the next accounts to see how far the lower wage bill helps "
             "profit."),
            ("{ticker}: {jobs} jobs removed to lower costs",
             "{company} of {location} has cut {jobs} jobs, leaving {staff} employees. Fewer staff means lower "
             "costs, though it can also mean the company expects to produce or sell less."),
        ],
    },
    "hiring": {
        "herald": [
            ("{company} adds {jobs} jobs in {location}",
             "{company}, the {location} company in the {sector} business, has added {jobs} jobs. It now "
             "employs {staff} people. For the families of those taken on, that means a new wage coming "
             "home."),
            ("Work for more people in {location} as {company} grows",
             "The workforce at {company} is larger this quarter by {jobs} jobs. That puts {staff} people on "
             "its payroll. More wages in {location} also means more money spent in its shops and markets."),
            ("{company} takes on more staff",
             "There are {jobs} more jobs at {company} than there were three months ago. The company, one of "
             "the employers in {location}, now has {staff} staff."),
        ],
        "ogene": [
            ("{company}: {jobs} jobs added",
             "{company} adds {jobs} jobs. Its workforce is now {staff}."),
            ("{location}: {company} is hiring",
             "{company} is taking on staff. It adds {jobs} jobs this quarter."),
            ("{company} ({ticker}) grows its workforce to {staff}",
             "The company creates {jobs} jobs. Workers in {location} stand to benefit."),
        ],
        "ledger": [
            ("{company} ({ticker}) adds {jobs} jobs",
             "{company} increased its workforce by {jobs} jobs this quarter and now employs {staff} people. "
             "A larger workforce raises the company's wage bill, one of its main costs."),
            ("Workforce at {company} up to {staff}",
             "{company}, in the {sector} business, ended the quarter with {staff} staff after adding {jobs} "
             "jobs. Investors will look to the next accounts to see whether sales grow enough to cover the "
             "higher wage bill."),
            ("{ticker}: {jobs} jobs created as wage bill grows",
             "{company} of {location} has added {jobs} jobs, bringing it to {staff} employees. More staff "
             "means higher costs, though it usually means the company expects to produce or sell more."),
        ],
    },
    "dividend_cut": {
        "herald": [
            ("{company} holds back money from its owners",
             "{company}, the {location} company in the {sector} business, has paid its owners less than "
             "usual this quarter. The payment a company makes to its owners out of its earnings is called "
             "a dividend. The company kept part of it to protect its cash."),
            ("Smaller payout for those who own shares in {company}",
             "People who own a share of {company} normally receive a regular payment from it, known as a "
             "dividend. This quarter the {location} company held part of that payment back. The "
             "money stays in the business to protect its cash."),
            ("{location} firm {company} keeps more of its cash",
             "{company} has trimmed its dividend, the sum it usually hands to its owners. Keeping that money "
             "leaves the company with more cash for wages, bills and loans, but it leaves its owners with "
             "less in their pockets."),
        ],
        "ogene": [
            ("{company}: payout to owners cut",
             "{company} holds back part of its dividend, the regular payment to its owners. The aim is to "
             "protect its cash."),
            ("{location}: {company} trims its dividend",
             "Owners of {company} get less this quarter. The company keeps the money to guard its cash."),
            ("{company} ({ticker}) keeps cash, pays owners less",
             "{company} reduces the payment it normally makes to its owners. It is saving cash."),
        ],
        "ledger": [
            ("{company} ({ticker}) cuts its dividend to protect cash",
             "{company} has held back part of its dividend, the payment a company normally makes to its "
             "owners from its earnings. The purpose is to protect the company's cash."),
            ("{ticker}: owners receive a reduced payout",
             "Shareholders in {company}, in the {sector} business, were paid less than the normal dividend "
             "this quarter. A dividend is the share of earnings a company pays to its owners. Cutting it "
             "keeps more cash inside the company to meet costs and repay lenders."),
            ("Dividend reduced at {company} as cash comes first",
             "{company} of {location} has chosen cash over its usual payout. It withheld part of its "
             "dividend, the regular payment to those who own its shares. Lenders tend to welcome such a "
             "step, while owners receive less income."),
        ],
    },
    "expansion": {
        "herald": [
            ("{company} borrows {amount} to grow",
             "{company}, the {location} company in the {sector} business, has borrowed {amount} from its bank "
             "to expand. A bigger business can mean more work and more trade in {location}, but the loan "
             "must be repaid with interest."),
            ("Growth plans in {location} as {company} takes a loan",
             "{company} is getting bigger. The company has taken a bank loan of {amount} to pay for its "
             "expansion. Its workers and suppliers in {location} will hope the growth brings more business "
             "their way."),
            ("{company} bets on a bigger future",
             "With {amount} borrowed from its bank, {company} is setting out to expand. The company is in "
             "the {sector} business. Like any borrower, it will need the extra sales to cover the "
             "repayments."),
        ],
        "ogene": [
            ("{company}: {amount} loan to expand",
             "{company} borrows {amount} from its bank. The money pays for expansion."),
            ("{location}: {company} is expanding",
             "{company} takes a bank loan of {amount} to grow its business."),
            ("{company} ({ticker}) borrows to grow",
             "A loan of {amount} funds the expansion. The company must repay it with interest."),
        ],
        "ledger": [
            ("{company} ({ticker}) borrows {amount} for expansion",
             "{company} has taken a bank loan of {amount} to expand. The borrowing adds to what the company "
             "owes, and to the interest it pays each quarter."),
            ("{amount} bank loan to fund growth at {company}",
             "{company}, in the {sector} business, has borrowed {amount} from its bank to pay for expansion. "
             "Investors will judge the move by whether the added sales outweigh the cost of the loan."),
            ("{ticker}: debt rises by {amount} as company expands",
             "{company} of {location} is expanding on borrowed money. Its bank has lent it {amount}. The loan "
             "raises the company's debt, which lenders weigh when judging how safely it can repay."),
        ],
    },
    "bank_loan_losses": {
        "herald": [
            ("{company} gives up on {amount} of loans",
             "{company} has written off {amount} of loans. To write off a loan is to accept that the money "
             "lent is not likely to be paid back. It is a loss the bank must carry itself."),
            ("Borrowers who cannot repay cost {company} {amount}",
             "Some of the companies that borrowed from {company} are no longer expected to "
             "repay. The bank has struck {amount} of such loans from its books. A bank that loses money on "
             "old loans tends to be more careful about making new ones."),
            ("{amount} lost on bad loans at {company}",
             "When a borrower cannot pay, the bank takes the loss. {company} has now counted {amount} of "
             "its lending as lost. That may make it harder for shop owners and families to get a loan "
             "from the bank."),
        ],
        "ogene": [
            ("{company}: {amount} of loans written off",
             "{company} writes off {amount} of loans. It no longer expects that money to be repaid."),
            ("{company} loses {amount} on bad loans",
             "The bank accepts that {amount} of its lending is lost. Borrowers have not repaid."),
            ("Bad loans cost {company} ({ticker}) {amount}",
             "{company} gives up on {amount} of loans. The loss falls on the bank."),
        ],
        "ledger": [
            ("{company} ({ticker}) writes off {amount} of loans",
             "{company} has written off {amount} of loans, meaning it no longer expects them to be repaid. "
             "The sum is counted as a loss and reduces the bank's profit."),
            ("{amount} loan loss at {company}",
             "Loans worth {amount} have been removed from the books of {company} as unlikely to be repaid. "
             "Losses of this kind eat into the bank's own funds, the cushion that protects those who "
             "keep money with it."),
            ("{ticker}: {amount} of lending judged lost",
             "{company} has accepted a loss of {amount} on loans that borrowers are not expected to repay. "
             "Banks that suffer such losses usually lend more cautiously afterwards, which can make "
             "credit harder to get."),
        ],
    },
    "roundup_results": {
        "herald": [
            ("In brief: how {count} more companies fared in {quarter}",
             "Not every set of accounts makes the front page. There were {count} quieter results for "
             "{quarter}, among them {list}."),
            ("Company results in brief for {quarter}",
             "Here is the rest of the news from the companies that filed their accounts for {quarter}. "
             "Smaller changes in profit came from {count} of them, including {list}."),
            ("The quieter results: {count} companies in {quarter}",
             "For workers and customers of these companies, {quarter} brought no great shocks. The smaller "
             "moves in profit included {list}."),
        ],
        "ogene": [
            ("Results in brief: {count} companies report for {quarter}",
             "The other results for {quarter} are in. They include {list}."),
            ("{quarter}: the smaller results",
             "Smaller profit moves come from {count} companies. Among them are {list}."),
            ("Business in brief: profits for {quarter}",
             "Also reporting this quarter: {list}."),
        ],
        "ledger": [
            ("Results in brief for {quarter}: {count} smaller moves",
             "Smaller changes in profit after tax were reported for {quarter} by {count} companies. They "
             "included {list}."),
            ("{quarter} accounts: {count} companies with modest changes",
             "The remaining accounts filed for {quarter} showed modest movements in profit. The companies "
             "concerned included {list}."),
            ("Other company results, {quarter}",
             "Investors had {count} further sets of accounts to read for {quarter}, none with a sharp change "
             "in profit. The list includes {list}."),
        ],
    },
    "roundup_jobs": {
        "herald": [
            ("In brief: smaller changes in jobs in {quarter}",
             "Staff numbers changed at {count} more companies in {quarter}, in smaller numbers than those in the "
             "larger stories. They include {list}."),
            ("Jobs in brief for {quarter}",
             "For anyone looking for work, here are the smaller changes in staff numbers for {quarter}. "
             "There were {count} of them, including {list}."),
            ("Smaller staff changes at {count} companies",
             "Workforces shifted a little in {quarter}. The companies that took on or let go of smaller "
             "numbers of people included {list}."),
        ],
        "ogene": [
            ("Jobs in brief: {count} companies change staff numbers",
             "The other jobs news for {quarter} is in. It includes {list}."),
            ("{quarter}: the smaller job moves",
             "Smaller staff changes come from {count} companies. Among them are {list}."),
            ("Work in brief: staff changes for {quarter}",
             "Also changing their workforce this quarter: {list}."),
        ],
        "ledger": [
            ("Staff numbers in brief for {quarter}: {count} smaller changes",
             "Smaller changes in workforce were recorded for {quarter} at {count} companies. They included "
             "{list}."),
            ("{quarter} payrolls: {count} companies adjust staff",
             "The remaining changes in staff numbers for {quarter} were modest. The companies concerned "
             "included {list}."),
            ("Other workforce changes, {quarter}",
             "Wage bills moved slightly at {count} further companies in {quarter} as staff numbers "
             "changed. The list includes {list}."),
        ],
    },
}
