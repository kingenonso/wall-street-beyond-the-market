"""News wordings for live events (16 November 2026): the bell, and how the evening ended."""

KINDS = ("live_event_open", "live_event_result")

WORDINGS = {
    "live_event_open": {
        "herald": [
            ("{happening}", "Tonight's live event is {show}. {detail_line} Traders across Lagos are reaching for their screens."),
            ("Breaking tonight: {show}", "{happening}. {detail_line} The next half hour will tell who saw it coming."),
            ("{show} on Broad Street", "{detail_line} Every empire has thirty minutes to make the most of it, or the least of the damage."),
        ],
        "ogene": [
            ("Breaking: {happening}", "{show} is live. {detail_line}"),
            ("Live now: {show}", "{detail_line} Thirty minutes on the clock."),
            ("{show}, right now", "{happening}. Watch the screens."),
        ],
        "ledger": [
            ("{show}: {happening}", "{detail_line} Investors who read the news at once are repricing the shares it touches."),
            ("Evening shock: {happening}", "{detail_line} The institutions will follow tomorrow, as they usually do."),
            ("Markets react to {show}", "{happening}. {detail_line} Prices are moving within the day's limit of a tenth."),
        ],
    },
    "live_event_result": {
        "herald": [
            ("{winner} wins the evening's {show}", "When the half hour ended, {company} had moved {move} from the bell. {winner} came out on top with {points} league points."),
            ("{show}: {winner} reads it best", "{company} finished the evening {move}. {winner} took {points} points for the league."),
            ("How the {show} ended", "{company} moved {move}. The best of the evening was {winner}, with {points} points."),
        ],
        "ogene": [
            ("{show} over. {winner} on top", "{company}: {move} since the bell. {points} points for {winner}."),
            ("Final whistle on {show}", "{winner} wins, {points} points. {company} {move}."),
            ("{winner} takes {show}", "{points} league points. {company} closed the window {move}."),
        ],
        "ledger": [
            ("{show}: {company} {move} over the window", "{winner} earned {points} league points, the most of any empire, from its prediction and its trading."),
            ("Scores from {show}", "{company} moved {move} between the bell and the end. Top of the table: {winner}, {points} points."),
            ("{winner} leads after {show}", "The featured share, {company}, moved {move}. {winner} collects {points} points toward the league."),
        ],
    },
}
