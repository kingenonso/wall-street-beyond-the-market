"""Stage 10, Part 1: work about the news, with "How to do this".

Seven pieces for the Financial Journalist, from the editors of the three media houses (named clients who remember how
the work went), and one for each of the other five builds tied to the news: the Accountant checks a story's figures,
the Risk Manager rates a reputational risk, Legal Counsel reviews a story before it runs, the Asset Manager trades on
verified news, and the Investment Banker times a deal's announcement. Each comes in the three settings.
"""

from __future__ import annotations

from simulation import objectives as o
from simulation.objectives_gap import YES_NO, Q, choice, m, pc, piece, yn

NEWS: list = []


# ---------------------------------------------------------------------------
# The Financial Journalist
# ---------------------------------------------------------------------------

def _jn_check(ctx, r):
    profit_before = r.int(400, 2400, 20)
    profit_now = profit_before + r.int(-300, 600, 20)
    sales = r.int(5000, 30000, 100)
    rating_now = r.pick(["A", "BBB", "BB"])
    claim_change = (profit_now - profit_before) / profit_before * 100
    told = {"a": round(claim_change + r.pick([0, 0, 2.5, -3.0]), 1), "b": sales + r.pick([0, 0, 500, -400]), "c": r.pick([rating_now, "AA"])}
    return {"situation": "A reporter's draft makes three claims about Kainji Textiles. Before it runs, each must match the filed record.",
            "task": ["For each claim, say whether the record supports it."],
            "given": [("The record: profit a year ago", m(profit_before)), ("The record: profit this quarter", m(profit_now)),
                      ("The record: sales this quarter", m(sales)), ("The record: credit rating", rating_now),
                      ("Claim A", f"Profit changed {told['a']:+.1f}% on the year"), ("Claim B", f"Sales were {m(told['b'])}"),
                      ("Claim C", f"The company is rated {told['c']}")],
            "f": {"pb": profit_before, "pn": profit_now, "s": sales, "rt": rating_now, "ta": told["a"], "tb": told["b"], "tc": told["c"]}}


piece("jn_check_story", "journalist", "Checking stories", "Does the story match the record?", 21,
      "No figure goes to print until it has been checked against where it is kept.", _jn_check,
      [choice("a", "Claim A", lambda f: yn(abs((f["pn"] - f["pb"]) / f["pb"] * 100 - f["ta"]) < 0.15), *YES_NO),
       choice("b", "Claim B", lambda f: yn(f["tb"] == f["s"]), *YES_NO),
       choice("c", "Claim C", lambda f: yn(f["tc"] == f["rt"]), *YES_NO)],
      plain=lambda f, t: f"A: {t['a']}, B: {t['b']}, C: {t['c']}.",
      method="Find each claim's figure in the record. Work any change out yourself from the two filed figures (now minus before, divided by "
             "before) rather than trusting the draft. A claim stands only if it matches the record.",
      maths=lambda f, t: f"({f['pn']} − {f['pb']}) ÷ {f['pb']} = {(f['pn'] - f['pb']) / f['pb'] * 100:.1f}%; sales {f['s']}; rating {f['rt']}.",
      into=NEWS, client="herald_editor", need=3)


def _jn_readers(ctx, r):
    staff = r.int(8000, 32000, 1000)
    importance = r.int(45, 90, 5)
    fresh = r.pick(["scoop", "new", "old"])
    credibility = r.int(20, 90, 5)
    following = r.int(0, 40000, 1000)
    return {"situation": "Your editor wants to know how many people your next story will reach before giving it the front page.",
            "task": ["Work out the readers: the paper's audience (ten readers for each person it employs) × the story's importance (as a share of "
                     "100) × how fresh it is (1.5 for a scoop, 1 for news, 0.4 for what the wire already carried) × your credibility ÷ 50 (counted "
                     "between 0.5 and 1.5), plus a third of your following."],
            "given": [("The paper's staff", f"{staff:,}"), ("The story's importance", str(importance)),
                      ("How fresh", {"scoop": "a scoop", "new": "news, not a scoop", "old": "the wire already carried it"}[fresh]),
                      ("Your credibility", str(credibility)), ("Your following", f"{following:,}")],
            "f": {"st": staff, "im": importance, "sc": {"scoop": 1.5, "new": 1.0, "old": 0.4}[fresh], "cr": credibility, "fo": following}}


def _cred(f) -> float:
    return min(max(f["cr"] / 50, 0.5), 1.5)


piece("jn_readers", "journalist", "Readers and reach", "How many will read it?", 23,
      "Reach comes from the size of the news, how early it is, where it is printed and the name on it.", _jn_readers,
      [Q("readers", "Readers", "number", lambda f: f["st"] * 10 * f["im"] / 100 * f["sc"] * _cred(f) + f["fo"] * 0.3, 50)],
      plain=lambda f, t: f"About {t['readers']:,.0f} readers.", need=1,
      method="Start from the audience (staff × 10). Scale it by importance out of 100, by how fresh it is, and by credibility out of 50 "
             "(never below half or above one and a half). Then add the third of your followers who read everything you write.",
      maths=lambda f, t: f"{f['st']} × 10 × {f['im']}/100 × {f['sc']} × {_cred(f):.2f} + {f['fo']} × 0.3 = {t['readers']:,.0f}.",
      into=NEWS, client="ogene_editor")


def _jn_scoop(ctx, r):
    rows = []
    for name in ("Rate decision", "Danfo results", "Port closure"):
        wire_day = r.int(1, 20)
        mine = r.int(1, 20)
        rows.append((name, wire_day, mine))
    return {"situation": "Three of your stories went out this quarter. A scoop is a confirmed fact you printed before the wire carried it.",
            "task": ["For each, say whether it was a scoop."],
            "given": [(n, f"the wire carried it on day {w}; you published on day {mine}") for n, w, mine in rows],
            "f": {"w": [w for _, w, _ in rows], "y": [mine for _, _, mine in rows]}}


piece("jn_scoop", "journalist", "Scoops", "Which were scoops?", 25,
      "Being first with a confirmed fact is what a scoop is: not first with a guess.", _jn_scoop,
      [choice(k, f"Story {i + 1}", (lambda i: lambda f: yn(f["y"][i] < f["w"][i]))(i), *YES_NO) for i, k in enumerate(("a", "b", "c"))],
      plain=lambda f, t: f"{t['a']}, {t['b']}, {t['c']}.", need=3,
      method="Compare the day you published with the day the wire carried the same fact. Strictly earlier is a scoop; the same day is not.",
      maths=lambda f, t: "; ".join(f"you {y} vs wire {w}" for y, w in zip(f["y"], f["w"])),
      into=NEWS, client="ogene_editor")


def _jn_nudge(ctx, r):
    readers = r.int(10, 400) * 1000
    good = r.pick([True, False])
    day = r.int(1, 5)
    return {"situation": "A widely read, true story moves how the computer-run investors value a company: a hundredth of a percent for each "
                         "thousand readers, at most 2%, fading evenly to nothing over five trading days.",
            "task": ["Work out the push on its first day (in %).", "Work out what is left of it on the given day (in %)."],
            "given": [("Readers", f"{readers:,}"), ("The news", "good" if good else "bad"), ("Trading day", f"day {day} of 5")],
            "f": {"rd": readers, "s": 1 if good else -1, "d": day}}


piece("jn_nudge", "journalist", "Stories and prices", "How far will it push the price?", 27,
      "A story moves a price only a little, and only for a while; facts, not opinions, do the moving.", _jn_nudge,
      [Q("first", "Push on day 1 (%)", "percent", lambda f: f["s"] * min(f["rd"] / 1000 * 0.01, 2.0), 0.01),
       Q("left", "Push left on that day (%)", "percent", lambda f: f["s"] * min(f["rd"] / 1000 * 0.01, 2.0) * (5 - (f["d"] - 1)) / 5, 0.01)],
      plain=lambda f, t: f"{t['first']:+.2f}% at first; {t['left']:+.2f}% on that day.", need=2,
      method="Readers ÷ 1,000 × 0.01%, capped at 2%, with the sign of the news. Each trading day a fifth of the first day's push fades.",
      maths=lambda f, t: f"min({f['rd']}/1000 × 0.01, 2) = {abs(t['first']):.2f}; × (5 − {f['d'] - 1})/5.",
      into=NEWS, client="ledger_editor")


def _jn_declare(ctx, r):
    cases = [r.pick([True, False]) for _ in range(3)]
    sits = [r.pick([True, False]) for _ in range(3)]
    return {"situation": "A journalist who sits in an empire must declare the empire's interest in any company they write about.",
            "task": ["For each story, say whether a declaration is needed."],
            "given": [(f"Story {i + 1}", f"you {'sit' if s else 'do not sit'} in an empire; it {'holds' if c else 'does not hold'} shares, "
                                         f"options or a short in the company")
                      for i, (s, c) in enumerate(zip(sits, cases))],
            "f": {"s": sits, "c": cases}}


piece("jn_declare", "journalist", "Declaring an interest", "Must you declare it?", 29,
      "Readers trust a story more when they know who stands to gain from it.", _jn_declare,
      [choice(k, f"Story {i + 1}", (lambda i: lambda f: yn(f["s"][i] and f["c"][i]))(i), *YES_NO) for i, k in enumerate(("a", "b", "c"))],
      plain=lambda f, t: f"{t['a']}, {t['b']}, {t['c']}.", need=3,
      method="A declaration is needed when you sit in an empire and that empire has any position (shares, options, futures, a short, preferred "
             "shares or warrants) in a company you name. Without a seat, or without a position, there is nothing to declare.",
      maths=lambda f, t: "; ".join(f"seat {s}, position {c}" for s, c in zip(f["s"], f["c"])),
      into=NEWS, client="ledger_editor")


def _jn_ethics(ctx, r):
    offer = r.pick(["see your story before it runs", "choose which figures you print", "approve your headline"])
    return {"situation": f"A company offers you an exclusive interview if you let them {offer}.",
            "task": ["Do you accept?", "If you decline, may you still report the company's filed figures?"],
            "given": [("The offer", f"an exclusive, if they may {offer}"), ("Your paper's rule", "no subject sees or shapes a story before it runs")],
            "f": {"o": offer}}


piece("jn_exclusive", "journalist", "Press ethics", "An exclusive with strings", 31,
      "A story shaped by its subject is no longer the reader's story.", _jn_ethics,
      [choice("accept", "Accept the offer?", lambda f: "no", *YES_NO), choice("report", "Still report the filed figures?", lambda f: "yes", *YES_NO)],
      plain=lambda f, t: "Decline the strings; the record is yours to report anyway.", need=2,
      method="An interview is worth having only on the record and without conditions on what you print. Filed figures are public: nobody can stop "
             "you reporting them, with or without an interview.",
      maths=lambda f, t: "Accept: no. Report the record: yes.",
      into=NEWS, client="herald_editor")


def _jn_front(ctx, r):
    stories = [(name, r.int(40, 95, 5), r.pick([True, False])) for name in ("Bank results", "A strike", "The rate decision")]
    staff = r.int(10000, 30000, 1000)
    return {"situation": "The editor keeps the front page for the story that will reach the most readers, and trusts you to choose it.",
            "task": ["Which story leads?", "How many readers will it reach (staff × 10 × importance/100, × 1.5 if a scoop)?"],
            "given": [("The paper's staff", f"{staff:,}")] + [(n, f"importance {i}{', a scoop' if s else ''}") for n, i, s in stories],
            "f": {"st": staff, "n": [n for n, _, _ in stories], "i": [i for _, i, _ in stories], "s": [s for _, _, s in stories]}}


def _best(f):
    scores = [i * (1.5 if s else 1.0) for i, s in zip(f["i"], f["s"])]
    return scores.index(max(scores))


piece("jn_front_page", "journalist", "The front page", "Choose the lead", 36,
      "The front page goes to the story that reaches the most people, not the one you like best.", _jn_front,
      [choice("lead", "The lead story", lambda f: ("a", "b", "c")[_best(f)], ("a", "Bank results"), ("b", "A strike"), ("c", "The rate decision")),
       Q("readers", "Its readers", "number", lambda f: f["st"] * 10 * f["i"][_best(f)] / 100 * (1.5 if f["s"][_best(f)] else 1.0), 50)],
      plain=lambda f, t: f"Lead with {f['n'][_best(f)]}: about {t['readers']:,.0f} readers.", need=2,
      method="Score each story by importance, half as much again for a scoop. The highest score leads; its readers are the audience × its "
             "importance out of 100 (× 1.5 if a scoop).",
      maths=lambda f, t: f"scores {[i * (1.5 if s else 1) for i, s in zip(f['i'], f['s'])]}; {f['st']} × 10 × … = {t['readers']:,.0f}.",
      into=NEWS, client="herald_editor")


# ---------------------------------------------------------------------------
# One piece for each of the other builds
# ---------------------------------------------------------------------------

def _ac_press(ctx, r):
    before, now = r.int(500, 3000, 10), 0
    now = before + r.int(-400, 900, 10)
    printed = round((now - before) / before * 100 + r.pick([0, 0, 2.5, -3.0]), 1)
    return {"situation": "A newspaper says your client's profit rose by a figure you must check before the board replies to it.",
            "task": ["Work out the real change in profit (%).", "Was the paper right?"],
            "given": [("Profit a year ago (filed)", m(before)), ("Profit this quarter (filed)", m(now)), ("The paper printed", f"{printed:+.1f}%")],
            "f": {"b": before, "n": now, "p": printed}}


piece("ac_press_check", "accountant", "Checking the press", "Is the paper's figure right?", 26,
      "When a figure about your company is printed, check it against the books before anyone replies to it.", _ac_press,
      [Q("change", "Real change (%)", "percent", lambda f: (f["n"] - f["b"]) / f["b"] * 100, 0.1),
       choice("right", "Was the paper right?", lambda f: yn(abs((f["n"] - f["b"]) / f["b"] * 100 - f["p"]) < 0.15), *YES_NO)],
      plain=lambda f, t: f"The real change is {t['change']:.1f}%: the paper was {'right' if t['right'] == 'yes' else 'wrong'}.", need=2,
      method="Change = (now − before) ÷ before. Compare it with the printed figure to one decimal place.",
      maths=lambda f, t: f"({f['n']} − {f['b']}) ÷ {f['b']} = {t['change']:.2f}%.", into=NEWS)


def _rm_reputation(ctx, r):
    chance = r.int(5, 40)
    points = r.int(2, 15)
    worth = r.int(5000, 40000, 500)
    per_point = r.int(1, 5) / 10
    return {"situation": "An investigation into your empire may be published. Rate the reputational risk for the board.",
            "task": ["Expected loss of reputation (points).", "Expected cost (₦m): each point lost costs the given share of the empire's worth."],
            "given": [("Chance it runs", pc(chance)), ("Reputation lost if it runs", f"{points} points"), ("Empire's worth", m(worth)),
                      ("Each point costs", pc(per_point))],
            "f": {"c": chance, "p": points, "w": worth, "k": per_point}}


piece("rm_reputation", "risk_manager", "Reputational risk", "What could the story cost?", 28,
      "A risk is its chance times its damage, whether it is a loan going bad or a headline.", _rm_reputation,
      [Q("points", "Expected points lost", "number", lambda f: f["c"] / 100 * f["p"], 0.05),
       Q("cost", "Expected cost (₦m)", "millions", lambda f: f["c"] / 100 * f["p"] * f["k"] / 100 * f["w"])],
      plain=lambda f, t: f"About {t['points']:.2f} points, or {m(t['cost'])}.", need=2,
      method="Multiply the chance by the points lost. Turn points into naira with the cost of a point (a share of the empire's worth).",
      maths=lambda f, t: f"{f['c']}% × {f['p']} = {t['points']:.2f}; × {f['k']}% × {f['w']} = {t['cost']:.2f}.", into=NEWS)


def _lw_review(ctx, r):
    lines = [("A", "fact", "The company's filed accounts show a loss."), ("B", "opinion", "In my view the board has lost its way."),
             ("C", "unsupported", "Insiders say the chief executive will resign.")]
    order = [lines[i] for i in (r.int(0, 2), r.int(0, 2), r.int(0, 2))]
    return {"situation": "Before a story runs, you check each sentence: a fact must be on the record; a view must be shown as the author's; "
                         "a claim with no record behind it cannot run as fact.",
            "task": ["For each sentence, may it run as written?"],
            "given": [(f"Sentence {i + 1}", text + (" (printed as the author's view)" if kind == "opinion" else "")) for i, (_, kind, text) in enumerate(order)],
            "f": {"k": [kind for _, kind, _ in order]}}


piece("lw_prepublication", "lawyer", "Pre-publication review", "May it run?", 24,
      "Print what the record shows, label opinion as opinion, and leave out what nobody can show.", _lw_review,
      [choice(k, f"Sentence {i + 1}", (lambda i: lambda f: yn(f["k"][i] != "unsupported"))(i), *YES_NO) for i, k in enumerate(("a", "b", "c"))],
      plain=lambda f, t: f"{t['a']}, {t['b']}, {t['c']}.", need=3,
      method="A fact on the record may run. An opinion may run when it is clearly the author's own. A claim nobody can show from the record "
             "may not run as fact.",
      maths=lambda f, t: ", ".join(f["k"]), into=NEWS)


def _am_news(ctx, r):
    price = r.int(1000, 9000, 50) / 100
    readers = r.int(20, 300) * 1000
    shares = r.int(10, 200) * 1000
    return {"situation": "A true, widely read story about a company you hold has just been published. The investors will mark it up a hundredth "
                         "of a percent for each thousand readers (at most 2%).",
            "task": ["The likely push on the price (%).", "What it adds to your holding (₦)."],
            "given": [("Share price", f"₦{price:,.2f}"), ("Readers", f"{readers:,}"), ("Shares you hold", f"{shares:,}")],
            "f": {"p": price, "rd": readers, "sh": shares}}


piece("am_news_trade", "asset_manager", "Trading on news", "What is the story worth to you?", 30,
      "Trade on verified news, and know how small and short-lived its effect usually is.", _am_news,
      [Q("push", "Push (%)", "percent", lambda f: min(f["rd"] / 1000 * 0.01, 2.0), 0.01),
       Q("gain", "Added to your holding (₦)", "naira", lambda f: f["p"] * f["sh"] * min(f["rd"] / 1000 * 0.01, 2.0) / 100, 5)],
      plain=lambda f, t: f"About {t['push']:.2f}%, worth ₦{t['gain']:,.0f}, and it fades over five days.", need=2,
      method="Readers ÷ 1,000 × 0.01%, capped at 2%. Multiply the price by the shares, then by the push.",
      maths=lambda f, t: f"{f['rd']}/1000 × 0.01 = {t['push']:.2f}%; {f['p']} × {f['sh']} × {t['push']:.2f}% = {t['gain']:,.0f}.", into=NEWS)


def _ib_announce(ctx, r):
    published = r.int(1, 25)
    return {"situation": "Your empire's journalist will publish the story of the deal. Neither the journalist nor the empire may trade the "
                         "company from the first draft until two trading days after it is published.",
            "task": ["The first trading day the empire may trade again.", "May the empire trade it on the day of publication?"],
            "given": [("Published on trading day", str(published))],
            "f": {"d": published}}


piece("ib_announcement", "investment_banker", "Announcing a deal", "When may we trade again?", 33,
      "Whoever writes the story of a deal does not trade around it: the market must hear it first.", _ib_announce,
      [Q("day", "First day the empire may trade", "number", lambda f: f["d"] + 3, 0), choice("same", "Trade on publication day?", lambda f: "no", *YES_NO)],
      plain=lambda f, t: f"From day {t['day']:.0f}.", need=2,
      method="The block lasts through the day of publication and the two trading days after it; trading opens again the day after that.",
      maths=lambda f, t: f"{f['d']} + 2 days blocked → day {f['d'] + 3}.", into=NEWS)


o.TEMPLATES.update({t.code: t for t in NEWS})
