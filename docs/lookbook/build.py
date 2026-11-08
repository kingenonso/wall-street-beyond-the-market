"""Build the look book: the real stylesheet, the desk's real markup, one file per view.

Run:  python3 lookbook.py /path/to/web/src/styles.css /path/to/out-dir
"""
import sys, pathlib

CSS = pathlib.Path(sys.argv[1]).read_text()
OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
(OUT / "lbs").mkdir(exist_ok=True)


def spark_svg(values, w=110, h=22):
    lo, hi = min(values), max(values); span = hi - lo or 1
    pts = " ".join(f"{i * w / (len(values) - 1):.1f},{h - 2 - ((v - lo) / span) * (h - 4):.1f}" for i, v in enumerate(values))
    way = "up" if values[-1] >= values[0] else "down"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="var(--{way})" stroke-width="1.5"/></svg>')


NW = [3.10, 3.42, 3.31, 3.88, 3.75, 4.02, 3.91, 4.36, 4.18, 4.28]
# ticker, company, price, way, change, volume
SHARES = [
    ("OPP", "Opobo Petroleum", "1,284.50", "up", "3.1%", "412,900"),
    ("GGM", "Gangan Mobile", "2,916.00", "down", "2.4%", "188,400"),
    ("DFL", "Danfo Logistics", "196.40", "up", "4.6%", "1,240,500"),
    ("IDC", "Idanre Cement", "742.25", "down", "1.2%", "96,300"),
    ("IKB", "Ikenga Bank", "418.75", "up", "0.8%", "764,100"),
    ("AMP", "Amadioha Power", "288.10", "down", "0.9%", "133,800"),
]
WIRE = [
    ("d47", "The Central Bank holds the policy rate, and warns lenders of a tighter year", "The Lagoon Herald"),
    ("d47", "Opobo Petroleum strikes gas at Itshekiri North and lifts its own forecast", "The Naira Ledger"),
    ("d46", "A hostile bid for Garki Flour Mills at ₦1,910 a share", "Ogene News Network"),
    ("d46", "Harmattan Bank’s overdue loans rise for a second filing", "The Lagoon Herald"),
    ("d45", "Delta Creek Gas suspends its dividend to pay down debt", "Ogene News Network"),
]
LEDGER = [
    ("16:12", "Salary for Year 1 Q2", "paid by Gidan Construction", "+₦612,400", "up"),
    ("15:40", "400 Gangan Mobile", "paid to the exchange", "−₦1,166,400", "down"),
    ("15:40", "Broker’s fee on 400 Gangan Mobile", "paid to Harbour House 3", "−₦3,499", "down"),
    ("12:00", "Dividend on 1,000 Ikenga Bank shares", "paid by Ikenga Bank", "+₦42,000", "up"),
]
BOARD = [
    ("GGM", "Gangan Mobile", "2,916.00", "down", "2.4", "₦2.19tn", "AA"),
    ("OPP", "Opobo Petroleum", "1,284.50", "up", "3.1", "₦1.54tn", "A"),
    ("IDC", "Idanre Cement", "742.25", "down", "1.2", "₦1.02tn", "A"),
    ("DFL", "Danfo Logistics", "196.40", "up", "4.6", "₦356.4bn", "BBB"),
    ("IKB", "Ikenga Bank", "418.75", "up", "0.8", "₦712.6bn", "A"),
    ("HMB", "Harmattan Bank", "204.10", "down", "1.7", "₦483.9bn", "BB"),
    ("AMP", "Amadioha Power", "288.10", "down", "0.9", "₦341.2bn", "BBB"),
    ("BTS", "Bonny Tide Shipping", "41.20", "down", "6.3", "₦18.7bn", "D"),
]


def change(way, pct):
    arrow = "▲" if way == "up" else "▼"
    return f'<span class="mono change-{way}">{arrow} {pct}</span>'


def topbar():
    tick = "".join(
        f'<a class="ticker-item" href="#"><span class="mono strong">{t}</span><span class="mono">₦{p}</span>'
        f'<span class="mono change-{w}">{"▲" if w == "up" else "▼"} {d}</span></a>'
        for t, _, p, w, d, _ in SHARES)
    return f'''
  <header class="topbar">
    <a href="#" class="plain-link topbar-mark"><div class="wordmark"><span class="wordmark-main">WALL STREET</span><span class="wordmark-sub">BEYOND THE MARKET</span></div></a>
    <div class="command"><span class="command-icon" aria-hidden="true">⌕</span><input placeholder="Search a company, a page or an action" aria-label="Search"><span class="command-key">ctrl K</span></div>
    <div class="topbar-clock"><span class="mono topbar-date">Y1 · Q2 · D47<span class="muted topbar-time"> · 17:46 Lagos</span></span><span class="pill pill-open"><span class="pill-dot"></span><span class="pill-label">Market open</span></span></div>
    <div class="topbar-player"><span class="cash mono">₦4,280,500</span><span class="avatar" style="width:30px;height:30px;font-size:12px">AO</span></div>
  </header>
  <div class="ticker-bar"><a href="#" class="ticker-index"><span class="strong">BSX 50</span><span class="mono">1,284.72</span><span class="mono change-up">▲ 0.4%</span></a><div class="ticker-window"><div class="ticker-track">{tick}</div></div></div>'''


def sections():
    names = ["My desk", "Work", "Empire", "Market", "Portfolio", "News", "Companies", "Economy", "Career"]
    out = "".join(f'<a class="section{" current" if i == 0 else ""}" href="#"><span>{n}</span></a>' for i, n in enumerate(names))
    return f'<nav class="sections" aria-label="Sections">{out}<a class="section section-button" href="#">Every screen</a></nav>'


def band():
    return f'''
  <section class="band" aria-label="What you stand on">
    <div class="band-cell"><div class="band-label">Cash</div><div class="band-value">₦4.28m</div><div class="band-note">money you can spend now</div></div>
    <div class="band-cell"><div class="band-label">What you own</div><div class="band-value">₦18.94m</div><div class="band-note"><span class="mono change-up">▲ ₦214.7k</span> since the last bell</div></div>
    <div class="band-cell"><div class="band-label">Shares and bonds</div><div class="band-value">₦14.11m</div><div class="band-note">at today’s prices · <a href="#">portfolio</a></div></div>
    <div class="band-cell"><div class="band-label">Retirement savings</div><div class="band-value">₦550k</div><div class="band-note">locked until retirement</div></div>
    <div class="band-cell"><div class="band-label">Reputation</div><div class="band-value">62<span class="muted"> / 100</span></div><div class="band-note">everyone starts at 50</div></div>
    <div class="band-cell"><div class="band-label">The last 30 bells</div><div class="band-spark">{spark_svg(NW)}</div><div class="band-note">what you own, day by day</div></div>
  </section>'''


def needs():
    lines = [
        ("Press", "Within a day", "A journalist has asked your empire a question"),
        ("Takeover offer", "₦1,910", "Garki Flour Mills: an offer for the shares you hold"),
        ("Results", "Y1 Q1", "The Year 1 Q1 results are out"),
        ("Price alert", "₦196.40", "Danfo Logistics has reached ₦200"),
        ("Messages", "2 unread", "2 messages waiting"),
        ("Work", "This quarter", "Take on a piece of work"),
    ]
    body = "".join(f'<li><span class="needs-tag">{t}</span><a href="#">{title}</a><span class="needs-when">{when}</span></li>'
                   for t, when, title in lines)
    return f'''
    <section class="needs" aria-labelledby="needs-h">
      <div class="needs-head"><h2 id="needs-h">Needs you now</h2><span class="needs-count">7 waiting</span></div>
      <article class="needs-lead">
        <div class="card-top"><span class="card-tag">■ Margin call</span><span class="mono muted small">By the next Closing Bell</span></div>
        <h3 class="h3-look">A margin call is waiting</h3>
        <p class="muted small">Your loan against Gangan Mobile needs ₦310,000 more cash by the next Closing Bell (22:00), or the shares are sold at the market’s price.</p>
        <a class="button-primary" href="#">See what you owe</a>
      </article>
      <ul class="needs-lines">{body}</ul>
    </section>'''


def book():
    rows = "".join(
        f'<tr><td class="mono strong"><a href="#">{t}</a></td><th scope="row">{n}</th>'
        f'<td class="num mono">₦{p}</td><td class="num">{change(w, d)}</td>'
        f'<td class="book-spark">{spark_svg([40, 42, 39, 44, 43, 47, 45, 48], 90, 24)}</td></tr>'
        for t, n, p, w, d in [("OPP", "Opobo Petroleum", "1,284.50", "up", "3.1%"),
                              ("GGM", "Gangan Mobile", "2,916.00", "down", "2.4%"),
                              ("DFL", "Danfo Logistics", "196.40", "up", "4.6%"),
                              ("IKB", "Ikenga Bank", "418.75", "up", "0.8%")])
    return f'''
    <section class="panel"><div class="panel-head"><h2>What you are watching</h2><aside><a href="#">Open the market</a></aside></div>
      <div class="scroll" tabindex="0"><table class="dense">
        <thead><tr><th scope="col">Code</th><th scope="col">Company</th><th scope="col" class="num">Price</th><th scope="col" class="num">Today</th><th scope="col">Last 5 days</th></tr></thead>
        <tbody>{rows}</tbody></table></div>
    </section>'''


def tape():
    now = "".join(
        f'<div class="tape-row"><a class="tape-stamp" href="#">{t}</a>'
        f'<span class="tape-text"><span class="tape-name">{n} · </span>{v} shares</span>'
        f'<span class="tape-figure">₦{p} {change(w, d)}</span></div>'
        for t, n, p, w, d, v in SHARES)
    wire = "".join(
        f'<div class="tape-row wire"><a class="tape-stamp" href="#">{day}</a><span class="tape-text">{h}</span><span class="tape-figure wire">{o}</span></div>'
        for day, h, o in WIRE)
    ledger = "".join(
        f'<div class="tape-row"><span class="tape-stamp">{at}</span>'
        f'<span class="tape-text">{memo} <span class="tape-name">· {cp}</span></span>'
        f'<span class="tape-figure change-{w}">{amt}</span></div>'
        for at, memo, cp, amt, w in LEDGER)
    return f'''
    <section class="tape" aria-labelledby="tape-h">
      <div class="tape-head"><h2 id="tape-h">The day’s tape</h2>
        <div class="tape-quote"><span>BSX 50 <b>1,284.72</b></span>{change("up", "0.4%")}
          <span><span class="mono">3,412,800</span> shares traded</span><span><span class="mono">1,284</span> trades</span></div>
      </div>
      <div class="tape-band"><p class="tape-gutter">now</p><div class="tape-lines">{now}</div></div>
      <div class="tape-band"><p class="tape-gutter">wire</p><div class="tape-lines">{wire}</div></div>
      <div class="tape-band"><p class="tape-gutter">ledger</p><div class="tape-lines">{ledger}</div></div>
      <div class="tape-foot"><a href="#">The whole market</a><a href="#">Read the wire</a></div>
    </section>'''


def board():
    rows = "".join(
        f'<tr><td class="mono strong"><a href="#">{t}</a></td><th scope="row" class="company-cell">{n}</th>'
        f'<td class="num mono">₦{p}</td><td class="num">{change(w, d + "%")}</td>'
        f'<td class="num mono">{v}</td>'
        f'<td><span class="rating rating-{"strong" if r in ("AAA", "AA", "A") else "middle" if r in ("BBB", "BB") else "weak"}">{r}</span></td></tr>'
        for t, n, p, w, d, v, r in BOARD)
    return f'''
    <section class="panel"><div class="panel-head"><h2>The board · 42 shares</h2><aside><a href="#">Sort it every way</a></aside></div>
      <div class="scroll" tabindex="0"><table class="dense">
        <thead><tr><th scope="col">Code</th><th scope="col">Company</th>
          <th scope="col" class="num"><button class="sort-head">Price</button></th>
          <th scope="col" class="num" aria-sort="descending"><button class="sort-head">Today ▼</button></th>
          <th scope="col" class="num"><button class="sort-head">Worth</button></th><th scope="col">Rating</th></tr></thead>
        <tbody>{rows}</tbody></table></div>
    </section>'''


def rail():
    return f'''
    <aside class="rail" aria-label="Context">
      <section class="panel"><div class="panel-head"><h2>Broad Street Exchange</h2></div>
        <div class="headline"><span class="figure-small">Market open</span></div>
        <p class="muted small">Closed in <span class="mono">2h 14m</span>, at <span class="mono">22:00</span> Lagos time.</p>
        <div class="row"><span>Opening auction</span><span class="mono">11:30 to 12:00</span></div>
        <div class="row row-current"><span>Open</span><span class="mono">12:00 to 22:00</span></div>
        <div class="row"><span>Closed</span><span class="mono">22:00 to 11:30</span></div>
      </section>
      <section class="panel"><div class="panel-head"><h2>Game calendar</h2></div>
        <div class="headline"><span class="figure-small">Year 1 · Q2</span></div>
        <div class="meter" role="img" aria-label="Day 47 of 90"><div class="meter-fill" style="width:52%"></div></div>
        <p class="muted small">Day 47 of 90. Companies file their results when the quarter ends.</p>
        <div class="row"><span>One real week</span><span class="mono">one game quarter</span></div>
        <div class="row"><span>Four real weeks</span><span class="mono">one game year</span></div>
      </section>
      <section class="panel"><div class="panel-head"><h2>Your standing</h2></div>
        <div class="row"><span>Reputation</span><span class="mono">62 / 100</span></div>
        <div class="row"><span>Level</span><span class="mono">3 · Senior clerk</span></div>
        <div class="row"><span>Employer</span><span>Gidan Construction</span></div>
        <div class="row"><span>Bank</span><span>Kainji Commercial Bank</span></div>
      </section>
    </aside>'''


def desk_head():
    return '''
  <header class="desk-head">
    <div><h1>My desk</h1>
      <div class="desk-who"><span class="mono strong">Accountant · L3</span><span class="dot-sep">·</span><span>Senior clerk</span><span class="dot-sep">·</span><span>Gidan Construction</span><span class="desk-who-bank"><span class="dot-sep">·</span> banking at Kainji Commercial Bank</span></div>
    </div>
    <div class="desk-clock">
      <div><span class="mono">Year 1 · Q2 · Day 47</span><span class="dot-sep"> · </span><span>Market open</span></div>
      <div>Closed in <span class="mono">2h 14m</span><span class="muted"> · at 22:00 Lagos</span></div>
    </div>
  </header>'''


APP = f'''
<div class="app">
{topbar()}
  <div class="shell">
{sections()}
    <main class="work">
      <div class="desk">
{desk_head()}
{band()}
      <div class="desk-grid">
        <div class="desk-col">
{needs()}
{book()}
        </div>
        <div class="desk-col">
{tape()}
{board()}
        </div>
      </div>
      </div>
    </main>
{rail()}
  </div>
</div>'''


def frame(theme, width, height):
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<title>desk {theme} {width}</title><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); }}
  .app {{ min-height: 0; }}</style></head>
<body><div id="frame" style="width:{width}px;height:{height}px;overflow:hidden">{APP}</div></body></html>'''


(OUT / "lbs" / "desk-dark.html").write_text(frame("dark", 1440, 1080))
(OUT / "lbs" / "desk-light.html").write_text(frame("light", 1440, 1080))
(OUT / "lbs" / "desk-phone.html").write_text(frame("dark", 390, 844))


def panel(name, inner):
    (OUT / name).write_text(f'''<!doctype html><html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; background: #000; overflow: hidden; }}
  .win {{ width: 484px; height: 652px; overflow: hidden; }}
  iframe {{ display: block; border: 0; }}
</style></head><body><div class="win">{inner}</div></body></html>''')


panel("lb-1-desk.html",
      '<iframe src="lbs/desk-dark.html" width="1440" height="1080" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel("lb-2-tape.html",
      '<iframe src="lbs/desk-dark.html" width="1440" height="1080" style="margin-left:-540px;margin-top:-300px"></iframe>')
panel("lb-3-phone.html", '<iframe src="lbs/desk-phone.html" width="390" height="844"></iframe>')
panel("lb-4-light.html",
      '<iframe src="lbs/desk-light.html" width="1440" height="1080" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
print("written to", OUT)
