"""Stage 10, Part 2: the Financial Journalist's work on sources, investigations and intelligence, with "How to do this".

Two pieces on the craft (how far to trust a source and a check; when an exposé may run) and four for the Economic
Intelligence Officer (owner's suggestion 11): reading the Central Bank, foreign money, oil and the naira, and company risk.
Each comes in the three settings.
"""

from __future__ import annotations

from simulation import objectives as o
from simulation import world_data as data
from simulation.objectives_gap import YES_NO, Q, choice, m, piece, yn

INTEL: list = []


def _odds(f) -> float:
    r, c = f["r"] / 100, f["c"] / 100
    if f["said"] == "holds":
        return r * c / (r * c + (1 - r) * (1 - c)) * 100
    return r * (1 - c) / (r * (1 - c) + (1 - r) * c) * 100


def _jn_source_odds(ctx, r):
    reliability = r.int(60, 90, 5)
    right = r.int(70, 95, 5)
    said = r.pick(["holds", "fails"])
    return {"situation": "A source has given you a hint, and you paid to have it checked before you print it.",
            "task": ["How likely is the hint to be true now (%)?", "Is it more likely true than not?"],
            "given": [("Your source is right", f"{reliability}% of the time"), ("The check is right", f"{right}% of the time"),
                      ("The check said", "it checks out" if said == "holds" else "it does not check out")],
            "f": {"r": reliability, "c": right, "said": said}}


piece("jn_source_odds", "journalist", "Sources", "How far can you trust it?", 33,
      "A hint is only as good as its source, and a check is only as good as its checker: weigh both before you print.", _jn_source_odds,
      [Q("odds", "Chance it is true (%)", "percent", _odds, 0.5),
       choice("likely", "More likely true than not?", lambda f: yn(_odds(f) > 50), *YES_NO)],
      plain=lambda f, t: f"About {t['odds']:.1f}%.", need=2,
      method="Of every hundred hints, the source gets its share right. The check then says 'checks out' to most true ones and to a few "
             "false ones. Count both ways the check could have said what it said: true-and-checked-right, or false-and-checked-wrong. "
             "The chance it is true is the first count out of the two together.",
      maths=lambda f, t: (f"{f['r']}% × {f['c']}% ÷ ({f['r']}% × {f['c']}% + {100 - f['r']}% × {100 - f['c']}%) = {t['odds']:.1f}%"
                          if f["said"] == "holds" else
                          f"{f['r']}% × {100 - f['c']}% ÷ ({f['r']}% × {100 - f['c']}% + {100 - f['r']}% × {f['c']}%) = {t['odds']:.1f}%"),
      into=INTEL)


def _jn_expose(ctx, r):
    docs = r.int(1, 4)
    second = r.pick([True, False])
    out = r.pick([False, False, True])
    return {"situation": f"Your investigation file is on your desk. An exposé needs {data.DOCUMENTS_NEEDED} documents and a second source, "
                         "about something that is still hidden.",
            "task": ["May the exposé run today?", "How many more documents do you need?"],
            "given": [("Documents found", str(docs)), ("A second source has confirmed it", "yes" if second else "no"),
                      ("What it points at has already come out some other way", "yes" if out else "no")],
            "f": {"d": docs, "s": second, "o": out}}


piece("jn_expose_ready", "journalist", "Investigations", "Is the exposé ready?", 38,
      "Nothing goes to print without the documents and a second source: that is what makes an exposé stand.", _jn_expose,
      [choice("run", "May it run?", lambda f: yn(f["d"] >= data.DOCUMENTS_NEEDED and f["s"] and not f["o"]), *YES_NO),
       Q("more", "More documents needed", "number", lambda f: max(data.DOCUMENTS_NEEDED - f["d"], 0), 0)],
      plain=lambda f, t: f"{'It can run.' if t['run'] == 'yes' else 'Not yet.'} {t['more']:.0f} more document(s).", need=2,
      method=f"It runs only with {data.DOCUMENTS_NEEDED} documents, a second source, and while what it shows is still hidden (if it has come "
             "out some other way, it is no longer your story). Documents still needed: the target minus what you have, never below nothing.",
      maths=lambda f, t: f"{data.DOCUMENTS_NEEDED} − {f['d']} = {t['more']:.0f}; second source {'yes' if f['s'] else 'no'}; "
                         f"already out {'yes' if f['o'] else 'no'}.", into=INTEL)


def _next_rate(f) -> float:
    wanted = f["n"] + (f["i"] - f["t"]) * f["k"]
    wanted = min(max(wanted, f["lo"]), f["hi"])
    gap = wanted - f["r"]
    step = 0 if abs(gap) < f["hold"] else max(min(gap, f["step"]), -f["step"])
    step = round(step / 0.25) * 0.25
    return f["r"] + step


def _jn_rate(ctx, r):
    rate = r.int(1000, 1600, 25) / 100
    inflation = r.int(300, 1100, 10) / 100
    f = {"r": rate, "i": inflation, "t": data.INFLATION_TARGET_BPS / 100, "n": data.NEUTRAL_RATE_BPS / 100,
         "k": data.RATE_RESPONSE_BPS / 10_000, "lo": data.RATE_FLOOR_BPS / 100, "hi": data.RATE_CEILING_BPS / 100,
         "hold": data.RATE_HOLD_WITHIN_BPS / 100, "step": data.RATE_STEP_BPS / 100}
    return {"situation": "Your editor wants the paper's call on the Central Bank's decision at this quarter's close, from its published rule.",
            "task": ["The rate it will set (%)."],
            "given": [("The rate now", f"{rate:.2f}%"), ("Prices rose over the year", f"{inflation:.1f}%"),
                      ("Its target", f"{f['t']:.1f}%"), ("Its neutral rate", f"{f['n']:.1f}%"),
                      ("How far it leans for each point of inflation above or below target", f"{f['k']:.2f} of a point"),
                      ("It holds within", f"{f['hold']:.2f} of a point of where its rule points"),
                      ("It moves at most", f"{f['step']:.2f} of a point a quarter, in quarter points")],
            "f": f}


piece("jn_rate_read", "journalist", "Reading the Central Bank", "Reading the Central Bank", 40,
      "The Central Bank publishes its rule: read the numbers it reads, and you can call the decision before it comes.", _jn_rate,
      [Q("rate", "Its rate (%)", "percent", _next_rate, 0.01)],
      plain=lambda f, t: f"{t['rate']:.2f}%.", need=1,
      method="Where the rule points: the neutral rate, plus the lean for each point inflation is above target (minus if below). If that is "
             "within the holding band of today's rate, it holds. Otherwise it moves towards it, at most one step, rounded to a quarter point.",
      maths=lambda f, t: (f"{f['n']} + ({f['i']} − {f['t']}) × {f['k']} = {f['n'] + (f['i'] - f['t']) * f['k']:.2f}%; "
                          f"from {f['r']:.2f}% → {t['rate']:.2f}%."), into=INTEL)


def _jn_foreign(ctx, r):
    start = r.int(2000, 20000, 50)
    move = r.int(-15, 20)
    end = round(start * (1 + move / 100) + r.int(-3000, 3000, 50), 0)
    return {"situation": "Foreign investors' holdings of shares here are published each quarter. Your readers want to know whether foreign "
                         "money came in or went out, not just whether prices moved.",
            "task": ["What foreign investors bought (+) or sold (−), net (₦m)."],
            "given": [("Their holdings at the start of the quarter", m(start)), ("Share prices over the quarter", f"{move:+d}%"),
                      ("Their holdings at the end", m(end))],
            "f": {"s": start, "mv": move, "e": end}}


piece("jn_foreign_money", "journalist", "Foreign money", "Did foreign money come or go?", 42,
      "Holdings change both because prices move and because investors buy or sell: take the price out to see the money.", _jn_foreign,
      [Q("flow", "Net bought (₦m)", "millions", lambda f: f["e"] - f["s"] * (1 + f["mv"] / 100), 0.5)],
      plain=lambda f, t: f"{'Bought' if t['flow'] >= 0 else 'Sold'} about {m(abs(t['flow']))} net.", need=1,
      method="What their start holdings would be worth at the end prices, had they done nothing: start × (1 + the price move). Whatever "
             "the end holdings are above that, they bought; below it, they sold.",
      maths=lambda f, t: f"{f['e']} − {f['s']} × (1 {f['mv']:+d}%) = {t['flow']:,.1f}", into=INTEL)


def _jn_oil(ctx, r):
    oil = r.int(-30, 40)
    naira = r.int(-15, 20)
    return {"situation": "Oil has moved, and so has the naira. Energy at home is priced from oil in dollars, turned into naira.",
            "task": ["How much energy at home changes (%).", "Does a weaker naira make energy dearer?"],
            "given": [("Oil, in dollars", f"{oil:+d}%"), ("Naira to the dollar (more naira for a dollar is weaker)", f"{naira:+d}%")],
            "f": {"o": oil, "n": naira}}


piece("jn_oil_naira", "journalist", "Oil and the naira", "Oil, the naira, and energy at home", 44,
      "Two moves together: what oil costs abroad, and how many naira a dollar costs.", _jn_oil,
      [Q("energy", "Energy at home (%)", "percent", lambda f: ((1 + f["o"] / 100) * (1 + f["n"] / 100) - 1) * 100, 0.1),
       choice("dearer", "A weaker naira makes it dearer?", lambda f: "yes", *YES_NO)],
      plain=lambda f, t: f"About {t['energy']:+.1f}%.", need=2,
      method="Multiply the two: (1 + the oil move) × (1 + the move in naira per dollar), then take away one. A weaker naira means more "
             "naira for the same dollar price, so energy at home costs more.",
      maths=lambda f, t: f"(1 {f['o']:+d}%) × (1 {f['n']:+d}%) − 1 = {t['energy']:+.1f}%", into=INTEL)


def _jn_risk(ctx, r):
    rows = []
    for name in ("Kogi Ridge Cement", "Oguta Airways", "Benue Harvest Foods"):
        ebit = r.int(200, 3000, 50)
        interest = r.int(50, 1500, 25)
        rows.append((name, ebit, interest))
    return {"situation": "Your editor wants to know which of three companies is closest to trouble paying its lenders.",
            "task": ["Which has the thinnest cover (operating profit ÷ interest)?", "Its cover (times)."],
            "given": [(n, f"operating profit {m(e)}, interest {m(i)}") for n, e, i in rows],
            "f": {"rows": rows}}


def _thinnest(f):
    return min(f["rows"], key=lambda x: x[1] / x[2])


piece("jn_company_risk", "journalist", "Company risk", "Who is closest to trouble?", 47,
      "Interest cover tells you how many times over a company's profit pays its lenders: the thinner it is, the nearer the edge.", _jn_risk,
      [choice("which", "Thinnest cover", lambda f: _thinnest(f)[0], *[(n, n) for n in ("Kogi Ridge Cement", "Oguta Airways", "Benue Harvest Foods")]),
       Q("cover", "Its cover (times)", "times", lambda f: _thinnest(f)[1] / _thinnest(f)[2], 0.05)],
      plain=lambda f, t: f"{t['which']}, at {t['cover']:.2f} times.", need=2,
      method="For each, divide operating profit by interest. The smallest answer is the thinnest cover: the company least able to pay if "
             "profit falls.",
      maths=lambda f, t: "; ".join(f"{n}: {e} ÷ {i} = {e / i:.2f}" for n, e, i in f["rows"]), into=INTEL)


o.TEMPLATES.update({t.code: t for t in INTEL})
