"""The market sitting's look book: the real stylesheet, the market's real markup.

Run:  python3 marketbook.py /path/to/web/src/styles.css /path/to/out-dir
"""
import sys, pathlib

CSS = pathlib.Path(sys.argv[1]).read_text()
OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
(OUT / "mbs").mkdir(exist_ok=True)

# code, name, sector, price, way, pct, volume, worth, rating, closes
SHARES = [
    ("GGM", "Gangan Mobile", "Telecoms", "2,916.00", "down", "2.4", "188,400", "₦2.19tn", "AA", [62, 64, 63, 66, 65, 64, 62, 60]),
    ("OPP", "Opobo Petroleum", "Oil and gas", "1,284.50", "up", "3.1", "412,900", "₦1.54tn", "A", [40, 42, 41, 44, 45, 47, 46, 49]),
    ("IDC", "Idanre Cement", "Building", "742.25", "down", "1.2", "96,300", "₦1.02tn", "A", [51, 50, 52, 51, 49, 48, 49, 47]),
    ("DFL", "Danfo Logistics", "Transport", "196.40", "up", "4.6", "1,240,500", "₦356.4bn", "BBB", [30, 31, 33, 32, 34, 36, 38, 41]),
    ("IKB", "Ikenga Bank", "Banking", "418.75", "up", "0.8", "764,100", "₦712.6bn", "A", [58, 58, 59, 60, 59, 60, 61, 62]),
    ("HMB", "Harmattan Bank", "Banking", "204.10", "down", "1.7", "522,700", "₦483.9bn", "BB", [44, 43, 43, 41, 42, 40, 39, 38]),
    ("AMP", "Amadioha Power", "Power", "288.10", "down", "0.9", "133,800", "₦341.2bn", "BBB", [37, 38, 37, 36, 37, 36, 35, 35]),
    ("BTS", "Bonny Tide Shipping", "Shipping", "41.20", "down", "6.3", "2,880,400", "₦18.7bn", "D", [22, 21, 19, 18, 16, 14, 12, 11]),
    ("GDC", "Gidan Construction", "Building", "612.00", "up", "1.4", "88,100", "₦402.8bn", "BBB", [48, 49, 48, 50, 51, 50, 52, 53]),
    ("KCB", "Kainji Commercial Bank", "Banking", "96.80", "up", "0.5", "334,200", "₦214.5bn", "A", [25, 25, 26, 26, 27, 26, 27, 27]),
    ("GFM", "Garki Flour Mills", "Food", "1,842.00", "up", "2.8", "41,600", "₦128.9bn", "BB", [70, 71, 72, 74, 73, 75, 77, 79]),
    ("TLH", "The Lagoon Herald", "Media", "38.40", "down", "0.4", "61,300", "₦9.2bn", "B", [15, 15, 14, 15, 14, 14, 13, 13]),
]
HEAT = {
    "Banking": [("IKB", "0.8", 1), ("HMB", "1.7", -1), ("KCB", "0.5", 1)],
    "Oil and gas": [("OPP", "3.1", 1)],
    "Telecoms": [("GGM", "2.4", -1)],
    "Building": [("IDC", "1.2", -1), ("GDC", "1.4", 1)],
    "Transport": [("DFL", "4.6", 1)],
    "Power": [("AMP", "0.9", -1)],
    "Shipping": [("BTS", "6.3", -1)],
    "Food": [("GFM", "2.8", 1)],
    "Media": [("TLH", "0.4", -1)],
}


def spark(values, w=90, h=20):
    lo, hi = min(values), max(values); span = hi - lo or 1
    pts = " ".join(f"{i * w / (len(values) - 1):.1f},{h - 2 - ((v - lo) / span) * (h - 4):.1f}" for i, v in enumerate(values))
    way = "up" if values[-1] >= values[0] else "down"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="var(--{way})" stroke-width="1.5"/></svg>')


def change(way, pct):
    return f'<span class="mono change-{way}">{"▲" if way == "up" else "▼"} {pct}%</span>'


def topbar():
    tick = "".join(
        f'<a class="ticker-item" href="#"><span class="mono strong">{t}</span><span class="mono">₦{p}</span>'
        f'<span class="mono change-{w}">{"▲" if w == "up" else "▼"} {d}%</span></a>'
        for t, _, _, p, w, d, _, _, _, _ in SHARES[:7])
    return f'''
  <header class="topbar">
    <a href="#" class="plain-link topbar-mark"><div class="wordmark"><span class="wordmark-main">WALL STREET</span><span class="wordmark-sub">BEYOND THE MARKET</span></div></a>
    <div class="command"><span class="command-icon" aria-hidden="true">⌕</span><input placeholder="Search a company, a page or an action" aria-label="Search"><span class="command-key">ctrl K</span></div>
    <div class="topbar-clock"><span class="mono topbar-date">Y1 · Q2 · D47<span class="muted topbar-time"> · 17:46 Lagos</span></span><span class="pill pill-open"><span class="pill-dot"></span><span class="pill-label">Market open</span></span></div>
    <div class="topbar-player"><span class="cash mono">₦4,280,500</span><span class="avatar" style="width:30px;height:30px;font-size:12px">AO</span></div>
  </header>
  <div class="ticker-bar"><a href="#" class="ticker-index"><span class="strong">BSX 50</span><span class="mono">1,284.72</span><span class="mono change-up">▲ 0.4%</span></a><div class="ticker-window"><div class="ticker-track">{tick}</div></div></div>'''


def sections():
    names = ["My desk", "Work", "Empire", "Markets", "Money", "News", "Economy", "Court"]
    out = "".join(f'<a class="section{" current" if n == "Markets" else ""}" href="#"><span>{n}</span></a>' for n in names)
    return f'<nav class="sections" aria-label="Sections">{out}<a class="section section-button" href="#">Every screen</a></nav>'


def tabs():
    names = ["Shares", "Bonds and bills", "Funds", "Indexes & ETFs", "World markets", "Options and futures", "Risk", "Offers, votes and bids", "Industries", "Who owns what"]
    out = "".join(f'<a class="tab{" active" if i == 0 else ""}" href="#" role="tab" aria-selected="{"true" if i == 0 else "false"}">{n}</a>' for i, n in enumerate(names))
    return f'<div class="tabs tabs-inline" role="tablist" aria-label="The market, by kind of asset">{out}</div>'


def area():
    vals = [1240, 1252, 1247, 1261, 1258, 1270, 1266, 1279, 1274, 1284]
    w, h = 700, 150
    lo, hi = min(vals), max(vals); span = hi - lo or 1
    pts = [(i * w / (len(vals) - 1), h - 6 - ((v - lo) / span) * (h - 24)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    fill = f"0,{h} " + line + f" {w},{h}"
    return (f'<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polygon points="{fill}" fill="color-mix(in srgb, var(--up) 12%, transparent)"/>'
            f'<polyline points="{line}" fill="none" stroke="var(--up)" stroke-width="1.5"/></svg>')


def market_head():
    return '''
      <div class="work-head">
        <div>
          <h1>Market</h1>
          <div class="work-sub">Broad Street Exchange<span class="dot-sep"> · </span>market open<span class="dot-sep"> · </span>trading from 12:00 to 22:00 Lagos</div>
        </div>
        <span class="muted small">12 listed shares</span>
      </div>'''


def band():
    return '''
      <section class="band band-4" aria-label="The market today">
        <div class="band-cell"><div class="band-label">BSX 50</div><div class="band-value">1,284.72</div><div class="band-note"><span class="mono change-up">▲ 0.4%</span> today</div></div>
        <div class="band-cell"><div class="band-label">All companies are worth</div><div class="band-value">₦16.03tn</div><div class="band-note">at today’s prices</div></div>
        <div class="band-cell"><div class="band-label">Shares traded today</div><div class="band-value">3,412,800</div><div class="band-note">since the opening auction</div></div>
        <div class="band-cell"><div class="band-label">Trades today</div><div class="band-value">1,284</div><div class="band-note">orders filled</div></div>
      </section>'''


def index_panel():
    return f'''
      <section class="panel">
        <div class="panel-head"><h2>The index, over time</h2>
          <div class="range-buttons" role="group" aria-label="How far back">
            <button aria-pressed="true">A week (one quarter)</button><button aria-pressed="false">Four weeks (one year)</button><button aria-pressed="false">Everything</button>
          </div>
        </div>
        {area()}
        <p class="muted small" style="margin-top:6px">The BSX 50 went from 1,240.00 on 1 Nov to 1,284.72 today.</p>
      </section>'''


def heat_grid():
    cells = ""
    for sector, items in HEAT.items():
        inner = "".join(
            f'<a class="heat-cell" href="#" style="border-color: var(--{("up" if way > 0 else "down")}); color: var(--{("up" if way > 0 else "down")})">'
            f'<span class="mono strong">{t}</span><span class="mono">{"▲" if way > 0 else "▼"}{p}%</span></a>'
            for t, p, way in items)
        cells += f'<div class="heat-group"><div class="small" style="color: var(--text-2); margin-bottom: 6px">{sector}</div><div class="heat-cells">{inner}</div></div>'
    return f'''
      <section class="panel">
        <div class="panel-head"><h2>Today at a glance: every share, by industry</h2><span class="muted small">▲ up · ▼ down · stronger colour = bigger move</span></div>
        <div class="heat-grid">{cells}</div>
      </section>'''


def shares_table(n=12, sticky=True):
    rows = "".join(
        f'<tr><td class="mono strong"><a href="#">{t}</a></td>'
        f'<th scope="row">{name}<div class="muted small">{sector}</div></th>'
        f'<td class="num mono">₦{price}</td><td class="num">{change(way, pct)}</td>'
        f'<td>{spark(closes)}</td>'
        f'<td class="num mono">{vol}</td><td class="num mono">{worth}</td>'
        f'<td><span class="rating rating-{"strong" if r in ("AAA", "AA", "A") else "middle" if r in ("BBB", "BB") else "weak"}">{r}</span></td>'
        f'<td><button class="star-button" aria-pressed="false" aria-label="Watch {name}">☆</button></td></tr>'
        for t, name, sector, price, way, pct, vol, worth, r, closes in SHARES[:n])
    cls = "scroll scroll-sticky" if sticky else "scroll"
    return f'''
        <div class="{cls}" tabindex="0">
          <table class="dense tape-table">
            <thead><tr>
              <th scope="col"><button class="sort-button">Code</button></th>
              <th scope="col"><button class="sort-button">Company</button></th>
              <th scope="col" class="num"><button class="sort-button">Price</button></th>
              <th scope="col" class="num" aria-sort="descending"><button class="sort-button">Today ▼</button></th>
              <th scope="col">Last 5 days</th>
              <th scope="col" class="num"><button class="sort-button">Traded today</button></th>
              <th scope="col" class="num"><button class="sort-button">Whole company</button></th>
              <th scope="col">Rating</th>
              <th scope="col"><span class="sr-only">Watch</span></th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>'''


def all_shares_panel():
    return f'''
      <section class="panel">
        <div class="panel-head"><h2>All 12 shares</h2></div>
        <div class="filter-row" role="group" aria-label="Show">
          <button class="filter-chip" aria-pressed="true">All</button>
          <button class="filter-chip" aria-pressed="false">★ My watchlist</button>
          <label class="filter-select"><span class="sr-only">Industry</span><select><option>Industry…</option><option>Banking</option></select></label>
        </div>
        {shares_table()}
      </section>'''


def rail():
    movers = "".join(
        f'<a class="row plain-link" href="#"><span><span class="mono strong">{t}</span> {name}</span>{change(way, pct)}</a>'
        for t, name, _s, _p, way, pct, *_ in [SHARES[3], SHARES[10], SHARES[1], SHARES[7], SHARES[0], SHARES[5]])
    watch = "".join(
        f'<div class="row"><span><a href="#">{name}</a></span><span class="mono">₦{price} {change(way, pct)}</span></div>'
        for t, name, _s, price, way, pct, *_ in SHARES[:3])
    return f'''
    <aside class="rail" aria-label="Context">
      <section class="panel"><div class="panel-head"><h2>Biggest moves today</h2></div>{movers}</section>
      <section class="panel"><div class="panel-head"><h2>Your watchlist</h2><span class="muted small">3 of 30</span></div>{watch}</section>
      <section class="panel"><div class="panel-head"><h2>Closing Bell</h2></div>
        <p class="muted small">At 22:00 the Bell names the day’s winner, loser and boldest move.</p>
        <div class="row"><span>Closes in</span><span class="mono">2h 14m</span></div>
        <div class="row"><span>Last winner</span><span>Danfo Logistics ▲ 4.6%</span></div>
      </section>
    </aside>'''


APP = f'''
<div class="app">
{topbar()}
  <div class="shell">
{sections()}
    <main class="work">
{tabs()}
{market_head()}
{band()}
{index_panel()}
{heat_grid()}
{all_shares_panel()}
    </main>
{rail()}
  </div>
</div>'''


def frame(theme, width, height, body):
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<title>market {theme}</title><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); }}
  .app {{ min-height: 0; }}</style></head>
<body><div id="frame" style="width:{width}px;height:{height}px;overflow:hidden">{body}</div></body></html>'''


(OUT / "mbs" / "market-dark.html").write_text(frame("dark", 1440, 1180, APP))
(OUT / "mbs" / "market-light.html").write_text(frame("light", 1440, 1180, APP))
(OUT / "mbs" / "market-phone.html").write_text(frame("dark", 390, 844, APP))


def panel(name, inner):
    (OUT / name).write_text(f'''<!doctype html><html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; background: #000; overflow: hidden; }}
  .win {{ width: 484px; height: 652px; overflow: hidden; }}
  iframe {{ display: block; border: 0; }}
</style></head><body><div class="win">{inner}</div></body></html>''')


panel("mb-1-market.html",
      '<iframe src="mbs/market-dark.html" width="1440" height="1180" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel("mb-2-table.html",
      '<iframe src="mbs/market-dark.html" width="1440" height="1180" style="margin-left:-380px;margin-top:-810px"></iframe>')
panel("mb-3-light.html",
      '<iframe src="mbs/market-light.html" width="1440" height="1180" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel("mb-4-phone.html", '<iframe src="mbs/market-phone.html" width="390" height="844"></iframe>')
print("written to", OUT)
