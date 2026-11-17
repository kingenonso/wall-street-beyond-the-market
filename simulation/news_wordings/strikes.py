"""News wordings for strike waves and the general strike (unions and strikes, part 4, 17 November 2026)."""

KINDS = ("union_wave_demand", "union_wave_deal", "union_wave_strike", "union_wave_over",
         "general_strike_notice", "general_strike_called_off", "general_strike", "general_strike_over")

WORDINGS = {
    "union_wave_demand": {
        "herald": [
            ("{union} demands {demand} across {industry}",
             "{leader} has served one pay demand on {companies} employers in {industry} at once: {demand} more for every worker. "
             "The employers have {days} days to answer together, or the whole industry may stop."),
            ("Industry-wide pay claim in {industry}",
             "The {union} wants {demand} from every employer in {industry}. {leader} says staff across the industry are out of "
             "patience. The answer is due in {days} days."),
            ("{industry} faces an all-out pay fight",
             "{companies} employers, one demand: {demand}. {leader} of the {union} has given them {days} days."),
        ],
        "ogene": [
            ("{union}: {demand} for all of {industry}",
             "{leader} gives {companies} employers {days} days."),
            ("Whole of {industry} told to pay {demand}",
             "Answer in {days} days or face a stoppage, says {leader}."),
            ("Pay war across {industry}",
             "{union} serves {companies} employers at once."),
        ],
        "ledger": [
            ("Sector risk: {industry} faces a {demand} claim",
             "The {union} has lodged an industry-wide claim of {demand} on {companies} employers in {industry}. A refusal "
             "would stop output across the sector. Employers must answer within {days} days."),
            ("{union} lodges industry-wide {demand} claim",
             "Investors in {industry} should weigh a higher wage bill across the sector against the risk of a stoppage at "
             "{companies} companies at once."),
            ("{industry}: one claim, {companies} employers",
             "{leader} of the {union} wants {demand}. The employers have {days} days to respond."),
        ],
    },
    "union_wave_deal": {
        "herald": [
            ("{industry} settles: {settled} for all",
             "Employers across {industry} have agreed a pay rise of {settled} with the {union}, against the {demand} asked. "
             "No stoppage. {leader} says the industry's workers stood together and it paid."),
            ("No strike in {industry}",
             "The {union} took the employers' offer of {offer}. Work goes on at {companies} companies."),
            ("Peace across {industry} at {settled}",
             "An industry-wide deal ends the pay fight in {industry}. The union had asked {demand}."),
        ],
        "ogene": [
            ("{industry} pays {settled}",
             "{union} accepts. No strike."),
            ("Deal across {industry}",
             "{leader} takes {settled} for everybody."),
            ("{settled} ends {industry} row",
             "Asked {demand}, settled {settled}."),
        ],
        "ledger": [
            ("{industry} agrees {settled} sector-wide",
             "Employers in {industry} have settled with the {union} at {settled}, against a claim of {demand}. Wage bills rise "
             "across the sector, and the risk of a stoppage falls away."),
            ("Sector pay deal in {industry}",
             "The {union}'s industry-wide claim is settled at {settled} at {companies} companies."),
            ("{union} accepts {offer} across {industry}",
             "Running costs in {industry} will be higher in the coming quarters. The claim was {demand}."),
        ],
    },
    "union_wave_strike": {
        "herald": [
            ("{industry} stops: the {union} walks out",
             "Workers at {companies} employers across {industry} downed tools after the employers offered {offer} against the "
             "{demand} asked. {leader} says the stoppage will last about {days} days."),
            ("Industry-wide strike hits {industry}",
             "From today, {industry} is idle. The {union} turned down {offer}. {leader}: we stay out about {days} days."),
            ("No work across {industry}",
             "Talks failed: {demand} asked, {offer} offered. The {union} has called out every member in the industry."),
        ],
        "ogene": [
            ("{industry} on strike",
             "{union} shuts {companies} companies. About {days} days."),
            ("All out in {industry}",
             "Offer of {offer} rejected. {leader} calls the strike."),
            ("Sector stoppage: {industry}",
             "No deal, no work, says {leader}."),
        ],
        "ledger": [
            ("Sector-wide strike in {industry}",
             "The {union} has called out its members at {companies} employers after rejecting an offer of {offer} against a "
             "claim of {demand}. About {days} days of output are at risk across the sector."),
            ("{industry}: output halts at {companies} companies",
             "An industry-wide stoppage has begun. Analysts expect lower sales across {industry} this quarter."),
            ("{union} strikes across {industry}",
             "Employers offered {offer}. The union wanted {demand}. The strike is expected to last about {days} days."),
        ],
    },
    "union_wave_over": {
        "herald": [
            ("{industry} goes back to work",
             "After {days} days, the {union} and the employers of {industry} have settled at {settled}. {leader} says the "
             "industry's workers won what they came for."),
            ("Strike over across {industry}",
             "The industry-wide stoppage ends with a {settled} rise. It lasted {days} days."),
            ("{industry} settles at {settled}",
             "Picket lines come down across {industry} after {days} days."),
        ],
        "ogene": [
            ("{industry} strike ends",
             "{settled} rise after {days} days out."),
            ("Back to work in {industry}",
             "{union} settles the whole industry at {settled}."),
            ("Peace returns to {industry}",
             "A {settled} deal after {days} days."),
        ],
        "ledger": [
            ("{industry} stoppage settled at {settled}",
             "The sector-wide strike ended after {days} days with a rise of {settled}. Sales lost will show in the quarter's "
             "results, and the higher wage bill in the quarters after."),
            ("Sector strike ends: {industry}",
             "The {union} and employers settled at {settled} after {days} days."),
            ("{industry} output resumes",
             "Work restarts across {industry}. Agreed rise: {settled}."),
        ],
    },
    "general_strike_notice": {
        "herald": [
            ("General strike threat: {federation} gives notice",
             "With prices {squeeze} ahead of pay over the year and {industries} industries already in dispute, the {federation} "
             "has warned that the whole country will stop unless the Government pays households a cost-of-living award of "
             "{award}. {leader} says the Government has {days} days."),
            ("{federation}: pay {award} or the nation stops",
             "{leader} has served notice of a general strike. The exchange would close and work would stop everywhere. The "
             "Government has {days} days to answer."),
            ("Countdown to a general strike",
             "The {federation} wants a {award} cost-of-living award. Prices have outrun pay by {squeeze} in a year."),
        ],
        "ogene": [
            ("General strike in {days} days?",
             "{federation} wants {award} for households."),
            ("{leader}: pay {award} or we stop",
             "Prices up {squeeze} on pay. {industries} industries already out."),
            ("Nationwide strike notice",
             "Government must answer the {federation} in {days} days."),
        ],
        "ledger": [
            ("Notice of general strike served",
             "The {federation} has given the Government {days} days to pay a cost-of-living award of {award} to households, "
             "or face a general strike that would close the exchange. Prices have outrun pay by {squeeze} over the year."),
            ("Markets brace for a general strike",
             "A refusal by the Government would shut the exchange and cut sales in every industry with a union. The award "
             "asked is {award}."),
            ("{federation} threatens a national stoppage",
             "{industries} industries are already in dispute. {leader} wants {award} within {days} days."),
        ],
    },
    "general_strike_called_off": {
        "herald": [
            ("General strike called off",
             "The Government has agreed to pay households a cost-of-living award of {award}, and the {federation} has called "
             "off its strike. {leader} thanked workers for standing firm."),
            ("Government pays {award}: no general strike",
             "Families will receive {award} from the Treasury. The {federation} stands down."),
            ("Strike averted at the last moment",
             "{leader} accepts the Government's {award} award. Work goes on."),
        ],
        "ogene": [
            ("No general strike",
             "Government pays {award}. {federation} stands down."),
            ("{award} for households",
             "{leader} calls off the strike."),
            ("Strike off",
             "The {federation} takes the award."),
        ],
        "ledger": [
            ("General strike averted with {award} award",
             "The Treasury will pay households a cost-of-living award of {award}. The {federation} has withdrawn its notice, "
             "and the exchange stays open."),
            ("Treasury pays {award} to avert strike",
             "The award lifts household income and spending, at a cost to the Treasury."),
            ("{federation} withdraws strike notice",
             "{leader} accepted the Government's award of {award}."),
        ],
    },
    "general_strike": {
        "herald": [
            ("General strike: the country stops",
             "The Government refused the {federation}'s demand, and from today work has stopped across every industry with a "
             "union. The exchange is shut for {hours} hours. {leader} says workers will not be ignored."),
            ("Nation idle as general strike begins",
             "Factories, ports and offices are empty. The {federation}'s strike will cost about {days} days of work. The "
             "exchange is closed for {hours} hours."),
            ("{leader} leads the country out",
             "The general strike has begun. Orders on the exchange wait in the queue until it reopens in {hours} hours."),
        ],
        "ogene": [
            ("General strike!",
             "Everything stops. Exchange shut {hours} hours."),
            ("Country on strike",
             "{federation} walks out after the Government says no."),
            ("All out, everywhere",
             "{leader}: the Government chose this."),
        ],
        "ledger": [
            ("Exchange shut as general strike begins",
             "The {federation} has called a general strike after the Government refused its award. The exchange is closed for "
             "{hours} hours, and orders wait for the reopening auction. Sales across the economy will show about {days} days lost."),
            ("General strike: markets closed for {hours} hours",
             "Every industry with a union is out. Expect weaker results across the board this quarter."),
            ("{federation} strike halts trading",
             "The exchange reopens in {hours} hours. {leader} called the strike after talks with the Government failed."),
        ],
    },
    "general_strike_over": {
        "herald": [
            ("General strike ends",
             "Work resumes across the country after the {federation}'s strike. It cost about {days} days of work. {leader} "
             "says the Government has been warned."),
            ("Back to work after the general strike",
             "The exchange reopens and workers return. The strike lasted about {days} days of work."),
            ("The country restarts",
             "The {federation} has ended its general strike."),
        ],
        "ogene": [
            ("General strike over",
             "Work restarts after {days} days. Exchange open."),
            ("Back to work",
             "{federation} ends the strike."),
            ("It's over",
             "{leader} calls workers back."),
        ],
        "ledger": [
            ("General strike over: exchange reopens",
             "Trading resumes with the reopening auction. The strike cost about {days} days of output, which will show in the "
             "quarter's results."),
            ("Markets reopen after general strike",
             "Orders that waited in the queue meet at the reopening auction, after about {days} days of work lost."),
            ("{federation} ends national stoppage",
             "Work resumes across every industry with a union."),
        ],
    },
}
