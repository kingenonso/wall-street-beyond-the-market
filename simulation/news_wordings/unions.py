"""News wordings for unions and strikes (16 November 2026): a demand, a deal, a strike and its end."""

KINDS = ("union_demand", "union_deal", "union_strike", "union_strike_over")

WORDINGS = {
    "union_demand": {
        "herald": [
            ("{union} demands {demand} more at {company}",
             "{leader} has told {company} in {city} that its staff want a pay rise of {demand}. \"{grievance}\" The board has "
             "{days} days to answer, or the workers may walk out."),
            ("Pay row brews at {company}",
             "Workers at {company} want {demand} more, says {leader} of the {union}. {grievance} The company must reply within "
             "{days} days."),
            ("{company} staff want {demand}: answer in {days} days",
             "The {union} has lodged a pay demand at {company} in {city}. {grievance} {leader} warns that a refusal will not "
             "be taken quietly."),
        ],
        "ogene": [
            ("Pay or we stop: {union} to {company}",
             "{leader} wants {demand} for {company} staff. {days} days to decide."),
            ("{company}: {demand} pay demand",
             "{union} gives the board {days} days. {grievance}"),
            ("Strike threat at {company}",
             "Staff in {city} ask {demand} more. {leader}: answer in {days} days."),
        ],
        "ledger": [
            ("{company} ({ticker}) faces a {demand} pay claim",
             "The {union} has lodged a claim for a {demand} rise at {company}. {grievance} The board has {days} days to "
             "respond. A strike would cut the quarter's sales."),
            ("Labour risk at {ticker}: {demand} claim lodged",
             "{company} must answer a {demand} pay claim from the {union} within {days} days. {grievance}"),
            ("{union} presses {company} for {demand}",
             "A pay claim of {demand} has been lodged at {company} ({ticker}). Investors will weigh a higher wage bill "
             "against the cost of a stoppage. {grievance}"),
        ],
    },
    "union_deal": {
        "herald": [
            ("Deal done: {company} staff get {settled}",
             "{company} and the {union} have agreed a pay rise of {settled}, against the {demand} first asked. {leader} "
             "called it a fair day's work. The staff in {city} stay at their posts."),
            ("No strike at {company}",
             "The board of {company} offered {offer} and the {union} took it. {leader} says the workers will be watching to "
             "see the deal kept."),
            ("{company} settles its pay row",
             "A pay rise of {settled} ends the dispute at {company} in {city}. The union had asked {demand}."),
        ],
        "ogene": [
            ("{company} pays up: {settled}",
             "{union} accepts. No strike in {city}."),
            ("Deal at {company}",
             "{leader} takes {settled}. Work goes on."),
            ("{settled} rise ends {company} row",
             "Staff asked {demand}, settled for {settled}."),
        ],
        "ledger": [
            ("{company} ({ticker}) agrees {settled} pay rise",
             "{company} has settled with the {union} at {settled}, against a claim of {demand}. The wage bill rises, and the "
             "risk of a stoppage this quarter falls away."),
            ("{ticker}: pay claim settled at {settled}",
             "The {union}'s claim at {company} is settled at {settled}. Running costs will be higher in the coming quarters."),
            ("Labour deal at {company}",
             "{company} accepted a pay rise of {settled}. The {union} had asked {demand}, and the board offered {offer}."),
        ],
    },
    "union_strike": {
        "herald": [
            ("Strike! {company} staff walk out",
             "Workers at {company} in {city} downed tools after the board offered {offer} against the {demand} they asked. "
             "{leader} of the {union} says they will be out for about {days} days. Customers are already going elsewhere."),
            ("{union} shuts {company}",
             "Picket lines went up at {company} this morning. \"{offer} is an insult,\" said {leader}. The strike is "
             "expected to last about {days} days."),
            ("No deal, no work at {company}",
             "Talks at {company} broke down: the union wanted {demand}, the board would go to {offer}. Staff in {city} have "
             "walked out, for about {days} days, {leader} says."),
        ],
        "ogene": [
            ("{company} on strike",
             "{union} walks out. About {days} days, says {leader}."),
            ("Picket lines at {company}",
             "Board offered {offer}. Staff wanted {demand}. Strike."),
            ("Strike hits {company} in {city}",
             "{leader}: we stay out until the pay is right."),
        ],
        "ledger": [
            ("{company} ({ticker}) hit by strike",
             "Staff at {company} walked out after the {union} rejected an offer of {offer} against a claim of {demand}. "
             "The stoppage is expected to last about {days} days, and its lost sales will show in the quarter's results."),
            ("Strike at {ticker}: about {days} days of lost output",
             "The {union} has called its members out at {company}. Analysts expect the quarter's sales to suffer, and the "
             "eventual settlement will raise the wage bill."),
            ("{ticker}: talks fail, staff strike",
             "{company} offered {offer}, but the {union} wanted {demand}. A strike of about {days} days has begun in {city}."),
        ],
    },
    "union_strike_over": {
        "herald": [
            ("Strike over at {company}",
             "After {days} days, the {union} and {company} have agreed a rise of {settled}. Staff in {city} go back to work "
             "tomorrow. {leader} says the union won something worth having."),
            ("Back to work at {company}",
             "The strike at {company} has ended with a {settled} pay rise. It lasted {days} days."),
            ("{company} and union settle at {settled}",
             "Picket lines come down in {city} after {days} days. {leader} accepted {settled}."),
        ],
        "ogene": [
            ("{company} strike ends",
             "{settled} rise. {days} days out."),
            ("Workers return to {company}",
             "{union} settles at {settled}."),
            ("Peace at {company}",
             "After {days} days, a {settled} deal."),
        ],
        "ledger": [
            ("{company} ({ticker}) strike settled at {settled}",
             "The {days}-day strike at {company} ended with a pay rise of {settled}. The quarter's sales will show the days "
             "lost, and the wage bill will show the deal."),
            ("{ticker}: stoppage ends",
             "{company} and the {union} have settled at {settled} after {days} days."),
            ("Settlement at {company}",
             "Work resumes at {company} in {city} after a {days}-day strike. Agreed rise: {settled}."),
        ],
    },
}
