"""News wordings for the talent and funds stage, Part 4b: foreign markets."""

KINDS = ("world_rates", "world_growth", "world_fall", "world_rise", "world_leaving", "world_sold", "world_trapped")

WORDINGS = {
    "world_rates": {
        "herald": [
            ("{bank} {side} its rate to {rate}",
             "The central bank of {country} moved its interest rate by {move} to {rate}, with inflation there at {inflation}. Money abroad now pays a different return, and Lagos will feel it."),
            ("Rates move in {country}",
             "{bank} {side} its rate by {move}. Its rate is now {rate}. Inflation stands at {inflation}."),
            ("A new interest rate abroad: {rate}",
             "{bank} changed course by {move} as inflation in {country} reached {inflation}."),
        ],
        "ogene": [
            ("{bank} moves", "Rate now {rate}, a {move} change."),
            ("Rates abroad: {rate}", "{bank} {side} by {move}."),
            ("Money abroad changes price", "{country}: rate {rate}, inflation {inflation}."),
        ],
        "ledger": [
            ("{bank} {side} by {move} to {rate}",
             "Inflation in {country} is {inflation}. Higher rates abroad tend to pull foreign money away from Nigerian shares and bonds."),
            ("Policy rate in {country}: {rate}",
             "{bank} moved by {move}. Share prices abroad are worth fewer years of profit when rates rise."),
            ("{country} sets its rate at {rate}",
             "A {move} move by {bank}, with inflation at {inflation}. Watch the pound, the euro and the dollar."),
        ],
    },
    "world_growth": {
        "herald": [
            ("The economies abroad in {quarter}",
             "Growth ran at {us} a year in the United States, {uk} in Britain and {ea} in the euro area."),
            ("How the world grew in {quarter}",
             "America grew at a pace of {us}, Britain {uk} and the euro area {ea}. Faster growth abroad means more demand for oil."),
            ("Growth abroad: America {us}",
             "Britain managed {uk} and the euro area {ea} in {quarter}."),
        ],
        "ogene": [
            ("World growth check", "America {us}, Britain {uk}, euro area {ea}."),
            ("Abroad in {quarter}", "Growth: {us}, {uk}, {ea}."),
            ("The big economies", "America grows {us} a year."),
        ],
        "ledger": [
            ("Growth abroad, {quarter}",
             "United States {us}, United Kingdom {uk}, euro area {ea}, at yearly rates. Oil demand follows the gap to trend."),
            ("America {us}, Britain {uk}, euro area {ea}",
             "The quarter's growth figures abroad. Companies listed in New York, London and Frankfurt report against them."),
            ("World economy: the figures",
             "In {quarter} the United States grew at {us}, Britain at {uk} and the euro area at {ea}."),
        ],
    },
    "world_fall": {
        "herald": [
            ("Shares tumble in {city}",
             "The {index} fell {move} in a day to close at {level}."),
            ("A bad day abroad: the {index} drops {move}",
             "Investors in {city} sold hard. The index closed at {level}."),
            ("Selling sweeps {city}",
             "The {index} lost {move} by the close, ending at {level}."),
        ],
        "ogene": [
            ("{city} crash!", "The {index} is down {move}."),
            ("Red day abroad", "{index} at {level}, down {move}."),
            ("Shares fall in {city}", "A drop of {move} in one day."),
        ],
        "ledger": [
            ("{index} down {move}",
             "A one-day fall to {level} in {city}. Holders of foreign shares and of ETFs that copy them lose too."),
            ("Heavy losses in {city}",
             "The {index} closed {move} lower at {level}."),
            ("The {index} slides to {level}",
             "A fall of {move} in a single session in {city}."),
        ],
    },
    "world_rise": {
        "herald": [
            ("Shares soar in {city}",
             "The {index} rose {move} in a day to close at {level}."),
            ("A rally abroad: the {index} jumps {move}",
             "Buyers returned in {city}. The index closed at {level}."),
            ("Buying sweeps {city}",
             "The {index} gained {move} by the close, ending at {level}."),
        ],
        "ogene": [
            ("{city} flies!", "The {index} is up {move}."),
            ("Green day abroad", "{index} at {level}, up {move}."),
            ("Shares jump in {city}", "A rise of {move} in one day."),
        ],
        "ledger": [
            ("{index} up {move}",
             "A one-day rise to {level} in {city}."),
            ("Strong gains in {city}",
             "The {index} closed {move} higher at {level}."),
            ("The {index} climbs to {level}",
             "A rise of {move} in a single session in {city}."),
        ],
    },
    "world_leaving": {
        "herald": [
            ("{parent} to leave Nigeria",
             "The foreign owner of {company} is selling its stake. It says {why}. Empires may buy pieces of the stake for two quarters."),
            ("{company}'s foreign parent heads for the door",
             "{parent} will sell its holding in {company} because {why}."),
            ("Another multinational quits",
             "{parent} has put its stake in {company} up for sale. The reason given: {why}."),
        ],
        "ogene": [
            ("{parent} is going!", "Its stake in {company} is for sale."),
            ("Bye bye, {parent}", "{company} loses its foreign owner."),
            ("Multinational exit", "{parent} sells out of {company}."),
        ],
        "ledger": [
            ("{parent} puts its {company} stake up for sale",
             "The parent cites that {why}. Empires may buy pieces for two quarters, and the pension funds take what is left at a discount."),
            ("Exit: {parent} to sell {company}",
             "Another foreign owner leaves as {why}. Any takeover offer for {company} will get its shares."),
            ("{company} ownership to change",
             "{parent} is leaving Nigeria. It says {why}."),
        ],
    },
    "world_sold": {
        "herald": [
            ("{parent} has left Nigeria",
             "Its stake in {company} went to {buyer}."),
            ("{company} has new owners",
             "{parent} completed its exit. The shares were bought by {buyer}."),
            ("The end of an era at {company}",
             "{parent} has sold out. The buyers were {buyer}."),
        ],
        "ogene": [
            ("{parent} gone", "{company} now belongs to {buyer}."),
            ("Exit done", "{buyer} bought {company} from {parent}."),
            ("Fresh owners at {company}", "Sold by {parent}."),
        ],
        "ledger": [
            ("{parent} completes its sale of {company}",
             "The stake went to {buyer}. Dividends still waiting for dollars will be sent home as they can."),
            ("{company}: foreign parent gone",
             "{buyer} took the shares {parent} held."),
            ("Exit completed at {company}",
             "{parent} has no stake left. Buyers: {buyer}."),
        ],
    },
    "world_trapped": {
        "herald": [
            ("{amount} of dividends stuck in Nigeria",
             "{parent} cannot send home what {company} has paid it. The Central Bank has too few dollars to spare."),
            ("Foreign owners wait for dollars",
             "{amount} of {company}'s dividends to {parent} are waiting in naira."),
            ("{parent}'s money is trapped",
             "Dividends from {company} worth {amount} cannot leave the country for now."),
        ],
        "ogene": [
            ("Trapped money", "{amount} for {parent} stuck here."),
            ("No dollars for {parent}", "{company}'s dividends wait."),
            ("Stuck!", "{amount} cannot leave."),
        ],
        "ledger": [
            ("{amount} of {company} dividends await dollars",
             "{parent} holds the naira here until reserves allow them out. Trapped money has driven foreign owners away before."),
            ("Repatriation backlog: {parent}",
             "Dividends from {company} worth {amount} are waiting for dollars."),
            ("{parent} cannot repatriate {amount}",
             "The dollar shortage holds {company}'s payments to its parent."),
        ],
    },
}
