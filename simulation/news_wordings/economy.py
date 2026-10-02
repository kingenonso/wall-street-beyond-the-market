"""News wordings for the whole economy: the Central Bank's rate, prices, the Money Watch, borrowing, jobs and growth."""

KINDS = (
    "rate_rise", "rate_cut", "rate_hold",
    "inflation_high", "inflation_low", "inflation_rising", "inflation_easing", "inflation_steady",
    "money_watch_amber", "money_watch_red", "money_watch_green",
    "household_borrowing_up", "household_borrowing_down",
    "jobs_report_up", "jobs_report_down",
    "economy_growing", "economy_slowing",
    "bank_central_borrowing",
)

WORDINGS = {
    # ------------------------------------------------------------------ The Central Bank
    "rate_rise": {
        "herald": [
            ("Loans get dearer as Central Bank lifts its rate to {rate}",
             "Families and shop owners who borrow will pay more. The Central Bank raised its interest rate from "
             "{old_rate} to {rate}, {run}. Every bank loan follows that rate."),
            ("Borrowers face bigger bills after rate goes from {old_rate} to {rate}",
             "Anyone with a bank loan should expect to pay more interest. The Central Bank says prices rose "
             "{inflation} over the past year, and it wants that figure close to {target}."),
            ("Central Bank raises its rate to {rate} to slow rising prices",
             "The cost of a bank loan is going up for traders, workers and families alike. The Central Bank moved "
             "its interest rate up from {old_rate}, {run}. Prices rose {inflation} over the past year against a "
             "target of {target}."),
        ],
        "ogene": [
            ("Central Bank: rate up to {rate}",
             "The Central Bank raises its interest rate from {old_rate} to {rate}, {run}. Bank loans cost more "
             "from now."),
            ("Rate rise: {old_rate} becomes {rate}",
             "Borrowing gets dearer. Prices are up {inflation} over the past year and the Central Bank's target "
             "is {target}."),
            ("Loans dearer: Central Bank moves to {rate}",
             "The interest rate goes up from {old_rate}, {run}. Every bank loan follows it."),
        ],
        "ledger": [
            ("Central Bank rate rises to {rate} from {old_rate}",
             "The Central Bank raised its interest rate under its published rule to {rate}, {run}. Prices rose "
             "{inflation} over the past year against a target of {target}. Lenders pass the higher rate on to "
             "every loan."),
            ("Rate set at {rate} with prices up {inflation} against a {target} target",
             "The Central Bank's interest rate moved up from {old_rate}. Companies and households that borrow "
             "will pay more interest, which leaves them less cash for other things."),
            ("Cost of borrowing up: Central Bank sets {rate}",
             "The rate was {old_rate} last quarter and is now {rate}, {run}. The bank's rule raises the rate when "
             "prices rise faster than its target of {target}. They rose {inflation} over the past year."),
        ],
    },
    "rate_cut": {
        "herald": [
            ("Cheaper loans ahead as Central Bank cuts its rate to {rate}",
             "There is some relief for families and traders who borrow. The Central Bank lowered its interest "
             "rate from {old_rate} to {rate}, {run}. Every bank loan follows that rate."),
            ("Rate comes down from {old_rate} to {rate}, easing the load on borrowers",
             "People repaying bank loans should soon pay less interest. The Central Bank says prices rose "
             "{inflation} over the past year, and its target is {target}."),
            ("Central Bank lowers its rate to {rate} as prices rise slowly",
             "Shop owners thinking of a loan for new stock will find it cheaper. The Central Bank brought its "
             "interest rate down from {old_rate}, {run}. Prices rose {inflation} over the past year against a "
             "target of {target}."),
        ],
        "ogene": [
            ("Central Bank: rate down to {rate}",
             "The Central Bank cuts its interest rate from {old_rate} to {rate}, {run}. Bank loans get cheaper."),
            ("Rate cut: {old_rate} becomes {rate}",
             "Borrowing costs less. Prices are up {inflation} over the past year and the Central Bank's target "
             "is {target}."),
            ("Loans cheaper: Central Bank moves to {rate}",
             "The interest rate comes down from {old_rate}, {run}. Every bank loan follows it."),
        ],
        "ledger": [
            ("Central Bank rate falls to {rate} from {old_rate}",
             "The Central Bank lowered its interest rate under its published rule to {rate}, {run}. Prices rose "
             "{inflation} over the past year against a target of {target}. Lenders pass the lower rate on to "
             "every loan."),
            ("Rate cut to {rate} with prices up {inflation} against a {target} target",
             "The Central Bank's interest rate moved down from {old_rate}. Companies and households that borrow "
             "will pay less interest, which leaves them more cash for other things."),
            ("Cost of borrowing down: Central Bank sets {rate}",
             "The rate was {old_rate} last quarter and is now {rate}, {run}. The bank's rule lowers the rate when "
             "prices rise slower than its target of {target}. They rose {inflation} over the past year."),
        ],
    },
    "rate_hold": {
        "herald": [
            ("No change for borrowers as Central Bank keeps its rate at {rate}",
             "Families and traders with bank loans will pay much the same interest as before. The Central Bank "
             "left its rate at {rate}, {run}."),
            ("Central Bank leaves its rate alone at {rate}",
             "Loan costs stay where they are for shop owners and workers. Prices rose {inflation} over the past "
             "year, and the Central Bank's target is {target}."),
            ("Rate stays at {rate}, so loan costs hold steady",
             "The Central Bank made no change to its interest rate this quarter, {run}. Every bank loan follows "
             "that rate, so borrowers should see no change in what they pay. Prices rose {inflation} over the "
             "past year."),
        ],
        "ogene": [
            ("Central Bank: rate stays at {rate}",
             "The Central Bank holds its interest rate at {rate}, {run}. Loan costs do not move."),
            ("No move: rate still {rate}",
             "The Central Bank leaves its interest rate alone. Prices are up {inflation} over the past year and "
             "the target is {target}."),
            ("Rate held: borrowers still pay on {rate}",
             "No rise and no cut from the Central Bank, {run}. Bank loans cost the same."),
        ],
        "ledger": [
            ("Central Bank rate unchanged at {rate}",
             "The Central Bank kept its interest rate at {rate} under its published rule, {run}. Prices rose "
             "{inflation} over the past year against a target of {target}."),
            ("Rate held at {rate} with prices up {inflation} against a {target} target",
             "The Central Bank made no change this quarter. Lenders have no new rate to pass on, so the interest "
             "that companies and households pay on loans stays as it was."),
            ("Cost of borrowing steady: Central Bank stays at {rate}",
             "The rate was {old_rate} before the decision and is {rate} after it, {run}. Borrowers and lenders can "
             "plan on the same interest costs for another quarter."),
        ],
    },
    # ------------------------------------------------------------------ Prices
    "inflation_high": {
        "herald": [
            ("Prices up {inflation} in a year as shoppers feel the squeeze",
             "Money is buying less at the market. Prices rose {inflation} over the past year, up from {previous} "
             "a quarter ago. The main cause is {driver}."),
            ("Cost of living climbs faster: prices now rising {inflation} a year",
             "Families are paying more for the same basket of goods. The rise is above the {band} range the "
             "Central Bank accepts, and well past its target of {target}."),
            ("Households stretched as price rises reach {inflation}",
             "Traders and their customers are both feeling it. Prices rose {inflation} over the past year, "
             "against {previous} a quarter earlier, and the Central Bank's accepted range is {band}. The biggest "
             "push comes from {driver}."),
        ],
        "ogene": [
            ("Prices: up {inflation} in a year, above the accepted range",
             "Prices are rising faster than the Central Bank accepts. Its range is {band}."),
            ("Price rises hit {inflation}",
             "That is up from {previous} last quarter. The main cause is {driver}."),
            ("Too fast: prices climb {inflation} against a {target} target",
             "The figure breaks out of the Central Bank's {band} range. The bank's rule raises its interest rate "
             "when prices rise faster than target."),
        ],
        "ledger": [
            ("Prices rise {inflation} over the year, above the {band} range",
             "The yearly rise in prices reached {inflation}, from {previous} a quarter earlier. That is above the "
             "top of the range the Central Bank accepts. The main cause is {driver}."),
            ("Price rises at {inflation} against a target of {target}",
             "Prices are rising faster than the Central Bank allows for. Its rule raises the interest rate when "
             "prices run ahead of target, which makes loans dearer for companies and households."),
            ("{inflation} price rise puts pressure on costs and savings",
             "Companies face higher costs and savers find their cash buys less. The figure was {previous} last "
             "quarter and the accepted range is {band}. The largest push comes from {driver}."),
        ],
    },
    "inflation_low": {
        "herald": [
            ("Prices barely moving: up only {inflation} in a year",
             "Shoppers are seeing few price increases at the market. Prices rose {inflation} over the past year, "
             "down from {previous} a quarter ago. The main cause is {driver}."),
            ("Slow price rises of {inflation} go easy on the family purse",
             "Prices rising this slowly are kind to the family purse. But the figure is below the {band} range the "
             "Central Bank accepts, and under its target of {target}."),
            ("Price rises drop to {inflation}, under the Central Bank's range",
             "Goods cost little more than they did a year ago. The rise was {previous} last quarter, and the "
             "Central Bank aims for {target}. Behind the fall is {driver}."),
        ],
        "ogene": [
            ("Prices: up just {inflation} in a year, below the accepted range",
             "Prices are rising slower than the Central Bank accepts. Its range is {band}."),
            ("Price rises fall to {inflation}",
             "That is down from {previous} last quarter. The main cause is {driver}."),
            ("Too slow: prices rise {inflation} against a {target} target",
             "The figure drops out of the Central Bank's {band} range. The bank's rule cuts its interest rate "
             "when prices rise slower than target."),
        ],
        "ledger": [
            ("Prices rise {inflation} over the year, below the {band} range",
             "The yearly rise in prices fell to {inflation}, from {previous} a quarter earlier. That is below the "
             "bottom of the range the Central Bank accepts. The main cause is {driver}."),
            ("Price rises of {inflation} fall short of the {target} target",
             "Prices are rising slower than the Central Bank aims for. Its rule cuts the interest rate when "
             "prices fall behind target, which makes loans cheaper for companies and households."),
            ("{inflation} price rise sits below the Central Bank's range",
             "Prices across the economy are going up very slowly, for sellers as well as buyers. The figure "
             "was {previous} last quarter and the accepted range is {band}. The largest pull comes from {driver}."),
        ],
    },
    "inflation_rising": {
        "herald": [
            ("Prices creeping up: now rising {inflation} a year",
             "Shoppers may notice the market getting a little dearer. Prices rose {inflation} over the past year, "
             "up from {previous} a quarter ago. The main cause is {driver}."),
            ("Cost of living edges higher, with prices up {inflation}",
             "The rise is quicker than last quarter's {previous}, though still inside the {band} range the "
             "Central Bank accepts. Families will feel it most in everyday buying."),
            ("Price rises pick up to {inflation} from {previous}",
             "Traders are charging more than they did three months ago, and {driver} is the main reason. The "
             "Central Bank aims for {target} and accepts anything from {band}."),
        ],
        "ogene": [
            ("Prices: rising faster, now {inflation} a year",
             "The figure is up from {previous} last quarter. It stays inside the Central Bank's {band} range."),
            ("Price rises pick up to {inflation}",
             "The main cause is {driver}. The Central Bank's target is {target}."),
            ("Up from {previous}: prices now climb {inflation} a year",
             "Still within the accepted range of {band}. But the direction is up."),
        ],
        "ledger": [
            ("Price rises quicken to {inflation} from {previous}",
             "Prices rose {inflation} over the past year, clearly faster than a quarter earlier. The figure "
             "remains inside the Central Bank's accepted range of {band}. The main cause is {driver}."),
            ("Prices up {inflation} over the year, inside the {band} range",
             "The yearly rise was {previous} last quarter. The Central Bank's target is {target}, and its rule "
             "raises the interest rate when prices rise faster than that."),
            ("{inflation} price rise adds to costs for companies and households",
             "Costs are rising faster than they were three months ago, when the figure stood at {previous}. The "
             "largest push comes from {driver}. The rise is still within the range of {band}."),
        ],
    },
    "inflation_easing": {
        "herald": [
            ("Some relief at the market as price rises slow to {inflation}",
             "Prices are still going up, but more gently. They rose {inflation} over the past year, down from "
             "{previous} a quarter ago. The main cause is {driver}."),
            ("Cost of living climbs more slowly, with prices up {inflation}",
             "The rise is gentler than last quarter's {previous} and sits inside the {band} range the Central "
             "Bank accepts. Families should find their money stretching a little further than they feared."),
            ("Price rises cool to {inflation} from {previous}",
             "Shoppers are seeing smaller increases than three months ago, and {driver} is the main reason. The "
             "Central Bank aims for {target} and accepts anything from {band}."),
        ],
        "ogene": [
            ("Prices: rising slower, now {inflation} a year",
             "The figure is down from {previous} last quarter. It stays inside the Central Bank's {band} range."),
            ("Price rises ease to {inflation}",
             "Behind the slowdown: {driver}. The Central Bank aims for {target}."),
            ("Down from {previous}: prices now climb {inflation} a year",
             "Still within the accepted range of {band}. The direction is down."),
        ],
        "ledger": [
            ("Price rises slow to {inflation} from {previous}",
             "Prices rose {inflation} over the past year, clearly slower than a quarter earlier. The figure "
             "remains inside the Central Bank's accepted range of {band}. The main cause is {driver}."),
            ("Prices up {inflation} over the year, a slower pace inside the {band} range",
             "The yearly rise was {previous} last quarter. The Central Bank's target is {target}, and its rule "
             "cuts the interest rate when prices rise slower than that."),
            ("{inflation} price rise eases the pressure on costs",
             "Costs are rising more slowly than they were three months ago, when the figure stood at {previous}. "
             "The largest pull comes from {driver}. The rise is still within the range of {band}."),
        ],
    },
    "inflation_steady": {
        "herald": [
            ("Prices keep a steady pace, up {inflation} in a year",
             "There are no surprises for shoppers this quarter. Prices rose {inflation} over the past year, "
             "little changed from {previous} three months ago."),
            ("Little change at the market as price rises hold near {inflation}",
             "Families and traders can plan with some confidence. The rise sits inside the {band} range the "
             "Central Bank accepts, and the main influence is {driver}."),
            ("Price rises stay close to last quarter's at {inflation}",
             "Goods are getting dearer at about the same pace as before, when the figure was {previous}. The "
             "Central Bank aims for {target}."),
        ],
        "ogene": [
            ("Prices: steady, up {inflation} in a year",
             "Little change from {previous} last quarter. The figure sits inside the Central Bank's {band} range."),
            ("Price rises hold at {inflation}",
             "The main influence is {driver}. The Central Bank's target is {target}."),
            ("No big move: prices rise {inflation} a year",
             "Last quarter it was {previous}. The accepted range is {band}."),
        ],
        "ledger": [
            ("Price rises little changed at {inflation}, from {previous}",
             "Prices rose {inflation} over the past year, close to the figure a quarter earlier. That is inside "
             "the Central Bank's accepted range of {band}. The main influence is {driver}."),
            ("Prices up {inflation} over the year against a target of {target}",
             "The pace is close to last quarter's {previous}. A steady figure lets companies and lenders plan "
             "their costs with fewer surprises."),
            ("{inflation} price rise keeps costs on a steady path",
             "The yearly rise in prices has barely moved in three months. It stood at {previous} last quarter, "
             "and the accepted range is {band}. The main influence is {driver}."),
        ],
    },
    # ------------------------------------------------------------------ The Money Watch
    "money_watch_amber": {
        "herald": [
            ("Money Watch turns amber: a first warning on money",
             "The public check on how much money there is has raised a warning. {reason} Amber is the first of its two "
             "warning levels."),
            ("Warning light on money: amber on the Money Watch",
             "The Money Watch has moved to amber, the lower of its two warning levels. {reason} {action}"),
            ("Amber on the Money Watch: what it means for families",
             "Amber is a caution, not an alarm. {reason} {action}"),
        ],
        "ogene": [
            ("Money Watch: amber",
             "The Money Watch moves to amber, the lower of its two warning levels. {reason}"),
            ("Amber warning from the Money Watch",
             "The Money Watch raises a warning. {reason}"),
            ("Money Watch flashes amber",
             "{reason} {action}"),
        ],
        "ledger": [
            ("Money Watch at amber: money {money_growth}, sales {output_growth} over the year",
             "The Money Watch, the standing public check on how much money exists, moved to amber. {reason} "
             "{action}"),
            ("Money Watch moves to amber",
             "The yearly change in money was {money_growth}, against {output_growth} for the economy's sales. "
             "Amber is the first of two warning levels. {reason} {action}"),
            ("Amber reading on the Money Watch puts lenders on notice",
             "{reason} Borrowers and lenders should take note of what follows. {action}"),
        ],
    },
    "money_watch_red": {
        "herald": [
            ("Money Watch goes red: its strongest warning on money",
             "The public check on how much money there is has sounded its strongest warning. {reason} {action}"),
            ("Red alert on money: the Money Watch sounds its top warning",
             "{reason} Too much money chasing the same goods pushes prices up, and every family feels it at "
             "the market. {action}"),
            ("Red on the Money Watch: borrowers should brace",
             "This is the highest warning the Money Watch gives. {reason} {action}"),
        ],
        "ogene": [
            ("Money Watch: red",
             "The Money Watch goes to red, its highest warning. {reason}"),
            ("Red alert from the Money Watch",
             "The Money Watch sounds its top alarm. {reason}"),
            ("Money Watch hits red",
             "The warning is the strongest there is. {reason} {action}"),
        ],
        "ledger": [
            ("Money Watch at red: money {money_growth}, sales {output_growth} over the year",
             "The Money Watch, the standing public check on how much money exists, moved to red. {reason} "
             "{action}"),
            ("Money Watch moves to red, its highest level",
             "The yearly change in money was {money_growth}, against {output_growth} for the economy's sales. Red "
             "is the higher of two warning levels. {reason} {action}"),
            ("Red reading on the Money Watch brings a firm response",
             "{reason} This is the higher of the two warning levels. {action}"),
        ],
    },
    "money_watch_green": {
        "herald": [
            ("All clear on money: the Money Watch is back to green",
             "The warning on how much money there is has been lifted. {reason} That is welcome news for anyone "
             "worried about prices running away."),
            ("Money Watch returns to green after its warning",
             "The warning has been withdrawn. Over the year the change in money was {money_growth} and the change "
             "in the economy's sales was {output_growth}. {action}"),
            ("Green again on the Money Watch: the warning is over",
             "Families and traders can breathe a little easier. {reason} {action}"),
        ],
        "ogene": [
            ("Money Watch: green again",
             "The Money Watch returns to green. {reason}"),
            ("All clear from the Money Watch",
             "The Money Watch lifts its warning. {action}"),
            ("Money Watch back to green",
             "The warning is over. {reason} {action}"),
        ],
        "ledger": [
            ("Money Watch back at green: money {money_growth}, sales {output_growth} over the year",
             "The Money Watch, the standing public check on how much money exists, returned to green after its "
             "warning. {reason} {action}"),
            ("Money Watch returns to green",
             "The yearly change in money was {money_growth}, against {output_growth} for the economy's sales, and "
             "the earlier warning has been lifted. {action}"),
            ("Green reading on the Money Watch ends the warning for lenders",
             "{reason} The earlier warning no longer stands. {action}"),
        ],
    },
    # ------------------------------------------------------------------ The whole economy
    "household_borrowing_up": {
        "herald": [
            ("Families borrow more: household debt up {change} to {amount}",
             "More households turned to the banks this quarter. Together they now owe {amount}, up {change} in "
             "three months, and pay about {rate} a year in interest on their loans."),
            ("Households now owe the banks {amount}",
             "From school fees to shop stock, more is being paid for with borrowed money. What families owe rose "
             "{change} in the quarter. At {rate} a year, the interest is a real weight on a household budget."),
            ("More loans in more homes as household borrowing rises {change}",
             "Families across the country owe the banks {amount} between them. The yearly interest on those loans "
             "now stands at {rate}."),
        ],
        "ogene": [
            ("Household borrowing: up {change} to {amount}",
             "Households owe the banks more this quarter. They pay {rate} a year in interest."),
            ("Families owe more: {amount}",
             "Household borrowing rises {change} in the quarter. Loans cost {rate} a year."),
            ("Up {change}: households take more bank loans",
             "The total owed reaches {amount}. The interest rate on household loans is {rate} a year."),
        ],
        "ledger": [
            ("Household borrowing rises {change} to {amount}",
             "What households owe the banks grew {change} in the quarter to {amount}. Households now pay {rate} a "
             "year in interest on loans."),
            ("{amount} owed by households, up {change} in the quarter",
             "Lenders are earning interest on a larger pile of household loans, at {rate} a year. More borrowing "
             "puts more money in shoppers' hands now and leaves more to repay later."),
            ("Households take on more bank loans at {rate} a year",
             "Total household borrowing stands at {amount}, up {change} on the previous quarter. Repayments will "
             "take a larger share of household income."),
        ],
    },
    "household_borrowing_down": {
        "herald": [
            ("Families pull back: household debt down {change} to {amount}",
             "Fewer households leaned on the banks this quarter. Together they now owe {amount}, down {change} in "
             "three months. Loans cost them about {rate} a year in interest."),
            ("Households pay down loans as borrowing costs {rate} a year",
             "With interest at {rate} a year, families are paying off loans faster than they take new ones. What "
             "they owe the banks fell {change} in the quarter to {amount}."),
            ("Fewer loans in fewer homes as household borrowing falls {change}",
             "Families across the country now owe the banks {amount} between them. The yearly interest on those "
             "loans is {rate}."),
        ],
        "ogene": [
            ("Household borrowing: down {change} to {amount}",
             "Households owe the banks less this quarter. They pay {rate} a year in interest."),
            ("Families owe less: {amount}",
             "Household borrowing falls {change} in the quarter. Loans cost {rate} a year."),
            ("Down {change}: households cut back on bank loans",
             "The total owed drops to {amount}. The interest rate on household loans is {rate} a year."),
        ],
        "ledger": [
            ("Household borrowing falls {change} to {amount}",
             "What households owe the banks shrank {change} in the quarter to {amount}. Households now pay {rate} "
             "a year in interest on loans."),
            ("{amount} owed by households, down {change} in the quarter",
             "Lenders are earning interest on a smaller pile of household loans, at {rate} a year. Less borrowing "
             "means less borrowed money for shoppers to spend now and less to repay later."),
            ("Households repay more than they borrow at {rate} a year",
             "Total household borrowing stands at {amount}, down {change} on the previous quarter. Repayments "
             "will take a smaller share of household income."),
        ],
    },
    "jobs_report_up": {
        "herald": [
            ("More people at work as stock market companies add {change} jobs",
             "There are more pay packets going home this quarter. The companies whose shares trade on the stock "
             "market now employ {jobs} people between them. The biggest gain was in {location}."),
            ("{location} leads the way as companies take on more workers",
             "Job seekers had better luck this quarter, most of all in {location}. The stock market's companies "
             "together employ {jobs} people, {change} more than three months ago."),
            ("Hiring picks up: {jobs} now work for stock market companies",
             "That is {change} more than a quarter ago. For the families of the new workers it means a steady "
             "wage, and for traders in {location}, where hiring was strongest, more customers with money to spend."),
        ],
        "ogene": [
            ("{location}: hiring strongest as jobs rise",
             "Stock market companies now employ {jobs} people. That is {change} more than last quarter."),
            ("Jobs up: companies add {change} workers",
             "Total staff at stock market companies reaches {jobs}. {location} gains the most."),
            ("More jobs: {jobs} now on company payrolls",
             "The count is up {change} in a quarter. The biggest rise is in {location}."),
        ],
        "ledger": [
            ("Company payrolls rise to {jobs}, up {change} in the quarter",
             "The companies whose shares trade on the stock market together employ {jobs} people, {change} more "
             "than a quarter before. The largest increase was in {location}."),
            ("Jobs at stock market companies up {change}, led by {location}",
             "Total staff now stands at {jobs}. More workers mean a larger wage bill for companies and more "
             "wages for households to spend."),
            ("{location} records the biggest rise as companies hire",
             "Employment at companies on the stock market reached {jobs}. That is a rise of {change} on the "
             "previous quarter."),
        ],
    },
    "jobs_report_down": {
        "herald": [
            ("Fewer people at work as stock market companies shed {change} jobs",
             "There are fewer pay packets going home this quarter. The companies whose shares trade on the stock "
             "market now employ {jobs} people between them. The biggest loss was in {location}."),
            ("{location} hit hardest as companies let workers go",
             "It was a hard quarter for workers, most of all in {location}. The stock market's companies together "
             "employ {jobs} people, {change} fewer than three months ago."),
            ("Jobs shrink: {jobs} now work for stock market companies",
             "That is {change} fewer than a quarter ago. For the families of those workers it means a lost wage, "
             "and for traders in {location}, where the fall was sharpest, fewer customers with money to spend."),
        ],
        "ogene": [
            ("{location}: job losses heaviest as work shrinks",
             "Stock market companies now employ {jobs} people. That is {change} fewer than last quarter."),
            ("Jobs down: companies shed {change} workers",
             "Total staff at stock market companies falls to {jobs}. {location} loses the most."),
            ("Fewer jobs: {jobs} left on company payrolls",
             "The count is down {change} in a quarter. The biggest fall is in {location}."),
        ],
        "ledger": [
            ("Company payrolls fall to {jobs}, down {change} in the quarter",
             "The companies whose shares trade on the stock market together employ {jobs} people, {change} fewer "
             "than a quarter before. The largest decrease was in {location}."),
            ("Jobs at stock market companies down {change}, most of all in {location}",
             "Total staff now stands at {jobs}. Fewer workers mean a smaller wage bill for companies and fewer "
             "wages for households to spend."),
            ("{location} records the biggest fall as companies cut staff",
             "Employment at companies on the stock market dropped to {jobs}. That is a fall of {change} on the "
             "previous quarter."),
        ],
    },
    "economy_growing": {
        "herald": [
            ("Busy tills: the economy's sales grow {growth} in a year",
             "Businesses across the country are selling more. Total company sales came to {sales} in the latest "
             "quarter, and are {growth} higher than a year ago."),
            ("Economy on the up, with company sales reaching {sales}",
             "More goods are leaving the shelves and more services are being paid for. Sales across all companies "
             "grew {growth} over the past year, which is good news for workers and the traders who serve them."),
            ("Trade is good: sales up {growth} across the economy",
             "From factories to shops, companies took in {sales} between them in the latest quarter. Growing sales "
             "give businesses more reason to hire and to expand."),
        ],
        "ogene": [
            ("Economy: sales up {growth} in a year",
             "The economy is growing. Companies sell {sales} in the latest quarter."),
            ("Growth: company sales reach {sales}",
             "Total sales are {growth} higher than a year ago."),
            ("Up {growth}: the economy keeps growing",
             "All companies together take in {sales} this quarter."),
        ],
        "ledger": [
            ("Economy's sales grow {growth} over the year to {sales} a quarter",
             "Total sales by all companies reached {sales} in the latest quarter. That is {growth} more than a "
             "year earlier."),
            ("{growth} yearly growth in company sales",
             "The economy is measured here by what all companies sell. The latest quarter's total was {sales}. "
             "Higher sales bring companies more cash to pay staff, lenders and owners."),
            ("Company sales total {sales} as the economy expands",
             "Sales across the economy grew {growth} over the past year. Investors and lenders watch this figure "
             "because it shows how much business there is to go round."),
        ],
    },
    "economy_slowing": {
        "herald": [
            ("Quieter tills: the economy's growth slows to {growth}",
             "Businesses are still selling more than a year ago, but the pace has dropped. Total company sales came to "
             "{sales} in the latest quarter, {growth} higher than a year before and a clearly slower pace."),
            ("Economy loses pace, with sales growth down to {growth}",
             "Traders and shop owners may already feel it in thinner crowds. Sales across all companies grew "
             "{growth} over the past year, slower than before. The latest quarter's total was {sales}."),
            ("Trade cools: sales up only {growth} across the economy",
             "From factories to shops, companies took in {sales} between them in the latest quarter. Slower "
             "growth gives businesses less reason to hire and to expand."),
        ],
        "ogene": [
            ("Economy: growth slows to {growth}",
             "The economy is losing pace. Companies sell {sales} in the latest quarter."),
            ("Slowdown: sales growth drops to {growth}",
             "Total company sales stand at {sales} for the quarter. The pace is clearly slower than before."),
            ("Only {growth}: the economy cools",
             "All companies together take in {sales} this quarter. Growth is weaker than it was."),
        ],
        "ledger": [
            ("Economy's sales growth slows to {growth}, with {sales} sold in the quarter",
             "Total sales by all companies reached {sales} in the latest quarter. That is {growth} more than a "
             "year earlier, a clearly slower rate than before."),
            ("{growth} yearly growth in company sales marks a slowdown",
             "The economy is measured here by what all companies sell. The latest quarter's total was {sales}. "
             "Slower sales growth leaves companies less new cash to pay staff, lenders and owners."),
            ("Company sales total {sales} as the economy's growth weakens",
             "Sales across the economy grew {growth} over the past year, down on the earlier pace. Investors and "
             "lenders watch this figure because it shows how much business there is to go round."),
        ],
    },
    "bank_central_borrowing": {
        "herald": [
            ("Banks short of cash borrow {new} more from the Central Bank",
             "When banks run short of money to lend to families and businesses, they turn to the Central Bank. "
             "This quarter they borrowed another {new}, and now owe it {amount} in all."),
            ("Banks now owe the Central Bank {amount}",
             "The banks that lend to traders and households have themselves been borrowing. They took {new} from "
             "the Central Bank this quarter. The Central Bank creates new money to make these loans."),
            ("Where loan money comes from: banks draw {new} from the Central Bank",
             "Banks did not have enough cash of their own to meet the demand for loans. The extra they borrowed "
             "brings what they owe the Central Bank to {amount}."),
        ],
        "ogene": [
            ("Banks: {new} more borrowed from the Central Bank",
             "Banks are short of cash to lend. They now owe the Central Bank {amount}."),
            ("Banks owe the Central Bank {amount}",
             "{new} of that is new this quarter. The Central Bank creates new money to lend it."),
            ("Cash call: banks draw {new} from the Central Bank",
             "The total they owe rises to {amount}. The money is newly created."),
        ],
        "ledger": [
            ("Banks' borrowing from the Central Bank reaches {amount}",
             "Banks borrowed a further {new} from the Central Bank this quarter, taking the total they owe it to "
             "{amount}. They borrow there when they lack the cash to make loans."),
            ("{new} of new Central Bank lending to banks this quarter",
             "Each naira the Central Bank lends to a bank is newly created money. The banks' total debt to the "
             "Central Bank now stands at {amount}."),
            ("Lenders lean on the Central Bank for {new} more",
             "Banks short of cash to lend owe the Central Bank {amount} in all. Because this lending adds to the "
             "amount of money in the economy, it is one of the figures to watch for future price rises."),
        ],
    },
}
