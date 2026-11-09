"""The money screens' look book: the real stylesheet, the portfolio's real shapes.

Run:  python3 moneybook.py /path/to/web/src/styles.css /path/to/out-dir
"""
import sys, pathlib

CSS = pathlib.Path(sys.argv[1]).read_text()
OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
(OUT / "mbs").mkdir(exist_ok=True)


def topbar():
    return '''
  <header class="topbar">
    <a href="#" class="plain-link topbar-mark"><div class="wordmark"><span class="wordmark-main">WALL STREET</span><span class="wordmark-sub">BEYOND THE MARKET</span></div></a>
    <div class="command"><span class="command-icon" aria-hidden="true">⌕</span><input placeholder="Search a company, a page or an action" aria-label="Search"><span class="command-key">ctrl K</span></div>
    <div class="topbar-clock"><span class="mono topbar-date">Y1 · Q2 · D47<span class="muted topbar-time"> · 17:46 Lagos</span></span><span class="pill pill-open"><span class="pill-dot"></span><span class="pill-label">Market open</span></span></div>
    <div class="topbar-player"><span class="cash mono">₦4,280,500</span><span class="avatar" style="width:30px;height:30px;font-size:12px">AO</span></div>
  </header>
  <div class="ticker-bar"><a href="#" class="ticker-index"><span class="strong">BSX 50</span><span class="mono">1,284.72</span><span class="mono change-up">▲ 0.4%</span></a><div class="ticker-window"><div class="ticker-track"></div></div></div>'''


def sections():
    names = ["My desk", "Work", "Empire", "Markets", "Money", "News", "Economy", "Court"]
    out = "".join(f'<a class="section{" current" if n == "Money" else ""}" href="#"><span>{n}</span></a>' for n in names)
    return f'<nav class="sections" aria-label="Sections">{out}<a class="section section-button" href="#">Every screen</a></nav>'


HOLDINGS = [
    ("GGM", "Gangan Mobile", "2,400", "₦2,916.00", "▼ 2.4%", "₦6,998,400", "₦6,120,000", "▲ ₦878,400", "₦96,000", 34),
    ("OPP", "Opobo Petroleum", "3,100", "₦1,284.50", "▲ 3.1%", "₦3,981,950", "₦3,720,000", "▲ ₦261,950", "₦62,000", 19),
    ("IKB", "Ikenga Bank", "5,000", "₦418.75", "▲ 0.8%", "₦2,093,750", "₦1,975,000", "▲ ₦118,750", "₦25,000", 10),
    ("DFL", "Danfo Logistics", "4,200", "₦196.40", "▲ 4.6%", "₦824,880", "₦861,000", "▼ ₦36,120", "—", 4),
    ("GGM2", "Garki Flour Mills", "800", "₦1,842.00", "▲ 2.8%", "₦1,473,600", "₦1,440,000", "▲ ₦33,600", "—", 7),
]


def band():
    return '''
      <section class="band band-4" aria-label="What you own">
        <div class="band-cell"><div class="band-label">Everything you own</div><div class="band-value">₦9,812,345</div><div class="band-note"><span class="mono change-up">▲ ₦58,700</span> since the last Closing Bell</div></div>
        <div class="band-cell"><div class="band-label">Shares</div><div class="band-value">₦6,420,880</div><div class="band-note">at today’s prices</div></div>
        <div class="band-cell"><div class="band-label">Cash you can use now</div><div class="band-value">₦2,104,300</div><div class="band-note">plus ₦180,400 held for your buy orders</div></div>
        <div class="band-cell"><div class="band-label">Dividends received</div><div class="band-value">₦1,287,165</div><div class="band-note">cash paid to you by the companies you own</div></div>
      </section>'''


def shares_table():
    rows = "".join(
        f'<tr><td class="mono strong"><a href="#">{t}</a></td><th scope="row">{name}</th>'
        f'<td class="num mono">{q}</td><td class="num mono">{p}</td><td class="num">{ch}</td>'
        f'<td class="num mono">{worth}</td><td class="num mono">{cost}</td><td class="num">{gain}</td>'
        f'<td class="num mono">{div}</td>'
        f'<td class="num"><span class="share-of"><span class="share-of-track"><span style="width:{pct}%"></span></span><span class="mono small">{pct}%</span></span></td></tr>'
        for t, name, q, p, ch, worth, cost, gain, div, pct in HOLDINGS)
    return f'''
      <section class="panel">
        <div class="panel-head"><h2>Your shares</h2><span class="muted small">Share of your shares shown beside each company</span></div>
        <div class="scroll scroll-sticky" tabindex="0">
          <table class="dense tape-table">
            <thead><tr><th scope="col" class="sr-only">Code</th><th scope="col">Company</th><th scope="col" class="num">Shares</th>
              <th scope="col" class="num">Price</th><th scope="col" class="num">Today</th><th scope="col" class="num">Worth</th>
              <th scope="col" class="num">They cost you</th><th scope="col" class="num">Gain or loss</th><th scope="col" class="num">Dividends</th>
              <th scope="col" class="num">Share of your shares</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        <p class="muted small">“They cost you” is what you paid for the shares you still hold, fees included. When you sell some, the average cost of those shares comes off. Inside the market’s trading hours, a figure can change before you finish reading it.</p>
        <p class="muted small">On shares sold: <span class="mono change-up">▲ ₦243,000</span>. This is money already made or lost, so it is not in the gain or loss on what you still hold.</p>
      </section>'''


APP = f'''
<div class="app">
{topbar()}
  <div class="shell">
{sections()}
    <main class="work">
      <div class="work-head">
        <div><h1>Portfolio</h1><div class="work-sub">What you own, what it cost and what it is worth now<span class="dot-sep"> · </span>5 companies · 15,500 shares</div></div>
      </div>
{band()}
{shares_table()}
    </main>
    <aside class="rail" aria-label="Context"></aside>
  </div>
</div>'''


def frame(theme, width, height, body):
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<title>portfolio {theme}</title><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); }}
  .app {{ min-height: 0; }}</style></head>
<body><div id="frame" style="width:{width}px;height:{height}px;overflow:hidden">{body}</div></body></html>'''


(OUT / "mbs" / "portfolio-dark.html").write_text(frame("dark", 1440, 900, APP))
(OUT / "mbs" / "portfolio-light.html").write_text(frame("light", 1440, 900, APP))
(OUT / "mbs" / "portfolio-phone.html").write_text(frame("dark", 390, 844, APP))


def panel(name, inner):
    (OUT / name).write_text(f'''<!doctype html><html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; background: #000; overflow: hidden; }}
  .win {{ width: 484px; height: 652px; overflow: hidden; }}
  iframe {{ display: block; border: 0; }}
</style></head><body><div class="win">{inner}</div></body></html>''')


panel("mp-1-portfolio.html",
      '<iframe src="mbs/portfolio-dark.html" width="1440" height="900" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel("mp-2-light.html",
      '<iframe src="mbs/portfolio-light.html" width="1440" height="900" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel("mp-3-phone.html", '<iframe src="mbs/portfolio-phone.html" width="390" height="844"></iframe>')
print("written to", OUT)
