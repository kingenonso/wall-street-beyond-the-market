"""The terminal look book: the real stylesheet, the game's own class names, three screens.

Run:  python3 termbook.py /path/to/web/src/styles.css /path/to/out-dir

The markup is the game's, not the reference's: the same .panel, .panel-head, .band, .row, .underline-tabs
and .ticker-item the screens use, so what is reviewed here is what the stylesheet will do to them.
"""
import sys, pathlib

CSS = pathlib.Path(sys.argv[1]).read_text()
OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
(OUT / "tbs").mkdir(exist_ok=True)


def topbar():
    return '''
  <header class="topbar">
    <a href="#" class="plain-link topbar-mark"><div class="wordmark"><span class="wordmark-main">WALL STREET</span><span class="wordmark-sub">BEYOND THE MARKET</span></div></a>
    <div class="command"><span class="command-icon" aria-hidden="true">⌕</span><input placeholder="Search a company, a page or an action" aria-label="Search"><span class="command-key">ctrl K</span></div>
    <div class="topbar-clock"><span class="mono topbar-date">Y1 · Q2 · D47<span class="muted topbar-time"> · 17:46 Lagos</span></span><span class="pill pill-open"><span class="pill-dot"></span><span class="pill-label">Market open</span></span></div>
    <div class="topbar-player"><span class="cash mono">₦4,280,500</span><span class="avatar" style="width:28px;height:28px;font-size:11px">AO</span></div>
  </header>'''


def tape():
    items = [
        ("TRAN", "228.01", "up", "0.2"), ("RLTY", "164.24", "down", "5.3"), ("WNC", "159.98", "flat", "0.0"),
        ("ALLI", "67.45", "down", "16.8"), ("RETL", "150.10", "down", "1.8"), ("GGM", "2,916.00", "up", "2.4"),
        ("OPP", "1,284.50", "up", "3.1"), ("IKB", "418.75", "up", "0.8"),
    ]
    rows = "".join(
        f'<a href="#" class="ticker-item"><span class="mono strong">{code}</span>'
        f'<span class="mono">{price}</span>'
        f'<span class="mono change-{way}">{"▲" if way == "up" else "▼" if way == "down" else "–"} {pct}%</span></a>'
        for code, price, way, pct in items)
    return f'''
  <div class="ticker-bar"><a href="#" class="ticker-index"><span class="strong">BSX 50</span><span class="mono">1,284.72</span><span class="mono change-up">▲ 0.4%</span></a>
    <div class="ticker-window"><div class="ticker-track">{rows}</div></div></div>'''


def sections(current):
    names = ["My desk", "Work", "Empire", "Markets", "Money", "News", "Economy", "Court"]
    out = "".join(f'<a class="section{" current" if n == current else ""}" href="#"><span>{n}</span></a>' for n in names)
    return f'<nav class="sections" aria-label="Sections">{out}<a class="section section-button" href="#">Every screen</a></nav>'


def panel(title, aside, body):
    right = f"<span>{aside}</span>" if aside else ""
    return f'''
      <section class="panel">
        <div class="panel-head"><h2>{title}</h2>{right}</div>
        {body}
      </section>'''


def rows(pairs):
    return "".join(f'<div class="row"><span>{label}</span><span class="mono">{value}</span></div>' for label, value in pairs)


PARAGRAPH = ('<p class="small">It lends to households and companies in Lagos, Kano and Port Harcourt, and its '
             'profit follows the Central Bank\'s rate more closely than the shops it lends to. Its last quarter was '
             'better than the one before, mostly because fewer of its loans went bad.</p>')

COMPANY = f'''
<div class="app">
{topbar()}
{tape()}
  <div class="shell">
{sections("Markets")}
    <main class="work">
      <div class="company-head">
        <nav aria-label="Breadcrumb" class="small muted"><a href="#">Companies</a> › Banking › Ikenga Bank</nav>
        <div class="company-title">
          <h1><span class="company-code">IKB</span> — Ikenga Bank</h1>
          <span class="rating">BBB</span>
          <span class="muted small">Banking · head office in Lagos</span>
        </div>
        <div class="company-price">
          <span class="mono figure">₦418.75</span>
          <span class="mono change-up">▲ 0.8%</span>
          <span class="muted small">Can trade between ₦410.00 and ₦427.50 today</span>
          <span class="company-actions">
            <button class="button-quiet">★ Watching</button>
            <button class="button-quiet">Trade ↓</button>
          </span>
        </div>
        <span class="muted small">Latest filing: Y1 · Q2</span>
      </div>

      <div class="underline-tabs" role="tablist" aria-label="About this company">
        <button role="tab" aria-selected="true" class="active">Overview</button>
        <button role="tab" aria-selected="false">Accounts</button>
        <button role="tab" aria-selected="false">For investors</button>
        <button role="tab" aria-selected="false">About it</button>
      </div>

{panel("Sales and profit", "As filed, by quarter", rows([("Sales", "₦8,420,000,000"), ("EBITDA", "₦2,910,000,000"), ("Net profit", "₦1,180,000,000"), ("Cash", "₦3,240,000,000")]))}

{panel("The company in one paragraph", "", PARAGRAPH)}

{panel("What it owes", "As filed", rows([("Bank loans", "₦24,000,000,000"), ("Bonds in issue", "₦12,500,000,000"), ("Deposits", "₦96,400,000,000")]))}

      <section class="panel">
        <div class="panel-head"><h2>Its shares, this quarter</h2><span>Five closing prices</span></div>
        <div class="scroll" tabindex="0">
          <table class="dense">
            <thead><tr><th scope="col">Day</th><th scope="col" class="num">Close</th><th scope="col" class="num">Traded</th><th scope="col" class="num">Change</th></tr></thead>
            <tbody>
              <tr><th scope="row">Y1 · Q2 · D43</th><td class="num mono">₦411.00</td><td class="num mono">184,000</td><td class="num mono change-up">▲ 1.2%</td></tr>
              <tr><th scope="row">Y1 · Q2 · D44</th><td class="num mono">₦414.50</td><td class="num mono">96,500</td><td class="num mono change-up">▲ 0.9%</td></tr>
              <tr><th scope="row">Y1 · Q2 · D45</th><td class="num mono">₦409.25</td><td class="num mono">121,000</td><td class="num mono change-down">▼ 1.3%</td></tr>
              <tr><th scope="row">Y1 · Q2 · D46</th><td class="num mono">₦415.50</td><td class="num mono">74,000</td><td class="num mono change-up">▲ 1.5%</td></tr>
              <tr><th scope="row">Y1 · Q2 · D47</th><td class="num mono">₦418.75</td><td class="num mono">52,300</td><td class="num mono change-up">▲ 0.8%</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
    <aside class="rail" aria-label="Context">
{panel("Trade Ikenga Bank", "Fees 0.4%", rows([("You hold", "5,000 shares"), ("Worth", "₦2,093,750"), ("Cash you can use", "₦4,280,500")]))}
{panel("In the news", "", '<div class="news-line"><div class="small muted">Y1 · Q2 · D46 · The Lagos Ledger</div><div class="strong">Ikenga Bank lifts its dividend</div></div>')}
    </aside>
  </div>
</div>'''


DESK = f'''
<div class="app">
{topbar()}
{tape()}
  <div class="shell">
{sections("My desk")}
    <main class="work">
      <div class="work-head"><div><h1>My desk</h1><div class="work-sub">What needs you, what the market is doing, and what you hold</div></div><span class="muted small">Y1 · Q2 · D47</span></div>
      <section class="band band-4" aria-label="What you own">
        <div class="band-cell"><div class="band-label">Everything you own</div><div class="band-value">₦9,812,345</div><div class="band-note"><span class="mono change-up">▲ ₦58,700</span> since the last Closing Bell</div></div>
        <div class="band-cell"><div class="band-label">Shares</div><div class="band-value">₦6,420,880</div><div class="band-note">at today’s prices</div></div>
        <div class="band-cell"><div class="band-label">Cash you can use now</div><div class="band-value">₦2,104,300</div><div class="band-note">plus ₦180,400 held for your buy orders</div></div>
        <div class="band-cell"><div class="band-label">Dividends received</div><div class="band-value">₦1,287,165</div><div class="band-note">paid to you by the companies you own</div></div>
      </section>
{panel("Needs you now", "Three things", '<div class="queue"><div class="card"><div class="card-top"><span class="card-tag">Order</span><span class="muted small">Today</span></div><p class="small">Your buy order for 2,000 GGM is waiting for a seller.</p><button class="button-primary">See the order</button></div></div>')}
      <section class="panel">
        <div class="panel-head"><h2>The tape</h2><span>Today</span></div>
        <div class="scroll" tabindex="0">
          <table class="dense tape-table">
            <thead><tr><th scope="col">Code</th><th scope="col">Company</th><th scope="col" class="num">Price</th><th scope="col" class="num">Today</th><th scope="col" class="num">Traded</th></tr></thead>
            <tbody>
              <tr><td class="mono strong"><a href="#">GGM</a></td><th scope="row">Gangan Mobile</th><td class="num mono">₦2,916.00</td><td class="num mono change-down">▼ 2.4%</td><td class="num mono">18,400</td></tr>
              <tr><td class="mono strong"><a href="#">OPP</a></td><th scope="row">Opobo Petroleum</th><td class="num mono">₦1,284.50</td><td class="num mono change-up">▲ 3.1%</td><td class="num mono">9,120</td></tr>
              <tr><td class="mono strong"><a href="#">IKB</a></td><th scope="row">Ikenga Bank</th><td class="num mono">₦418.75</td><td class="num mono change-up">▲ 0.8%</td><td class="num mono">52,300</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
    <aside class="rail" aria-label="Context">
{panel("Net worth history", "Twelve quarters", '<div class="spark" style="height:90px;background:var(--bg);border:1px solid var(--border)"></div>')}
{panel("Market indicators", "", '<div class="why-title">Commodities and indexes</div>' + rows([("BSX 50", "1,284.72 ▲ 0.4%"), ("Oil", "₦103.30 ▼ 1.8%"), ("Gold", "₦5,175.56 ▼ 1.2%")]) + '<div class="why-title">Macroeconomic</div>' + rows([("GDP", "0.90%"), ("Inflation", "12.4%"), ("Policy rate", "18.50%")]))}
    </aside>
  </div>
</div>'''


def page(body, theme, title):
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); }}
  .app {{ min-height: 0; }}</style></head>
<body>{body}</body></html>'''


def framed(body, theme, title, width, height):
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8"><title>{title}</title><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); overflow: hidden; }}
  .app {{ min-height: 0; }}
  #frame {{ width: {width}px; height: {height}px; overflow: hidden; }}
  .topbar, .sections {{ position: static; }}</style></head>
<body><div id="frame">{body}</div></body></html>'''


def panel_file(name, inner, width=484, height=652):
    (OUT / name).write_text(f'''<!doctype html><html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; background: #000; overflow: hidden; }}
  .win {{ width: {width}px; height: {height}px; overflow: hidden; }}
  iframe {{ display: block; border: 0; }}
</style></head><body><div class="win">{inner}</div></body></html>''')


(OUT / "tbs" / "company-dark.html").write_text(page(COMPANY, "dark", "company"))
(OUT / "tbs" / "company-light.html").write_text(page(COMPANY, "light", "company light"))
(OUT / "tbs" / "desk-dark.html").write_text(page(DESK, "dark", "desk"))
(OUT / "tbs" / "company-phone.html").write_text(framed(COMPANY, "dark", "company phone", 390, 844))

panel_file("tb-1-company.html", '<iframe src="tbs/company-dark.html" width="1440" height="900" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel_file("tb-2-desk.html", '<iframe src="tbs/desk-dark.html" width="1440" height="900" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel_file("tb-3-light.html", '<iframe src="tbs/company-light.html" width="1440" height="900" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel_file("tb-4-phone.html", '<iframe src="tbs/company-phone.html" width="390" height="844"></iframe>', 390, 844)

print("written to", OUT)
