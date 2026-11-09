"""The column look book: the real stylesheet and the column's own class names, two themes and a desk's width.

Run:  python3 columnbook.py /path/to/web/src/styles.css /path/to/out-dir

Nothing here is the reference's markup. It is the markup LeftColumn.tsx now produces, beside the strip and the
work area it sits next to, so what is reviewed is what the game will draw.
"""
import math
import pathlib
import sys

CSS = pathlib.Path(sys.argv[1]).read_text()
OUT = pathlib.Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def money(value):
    for size, letter in ((1e9, "B"), (1e6, "M")):
        if value >= size:
            scaled = value / size
            return "₦%.1f%s" % (scaled, letter)
    return "₦%s" % format(int(value), ",")


# A year of closes: enough for the months along the foot to mean something.
CLOSES = [(f"2026-{3 + (i // 20):02d}-{1 + (i % 20) * 1:02d}", 2_400_000 + 900_000 * math.sin(i / 9) + 34_000 * i)
          for i in range(40)]


def plot():
    W, H, LEFT, RIGHT, TOP, BOTTOM = 260, 132, 4, 56, 20, 20
    values = [v for _, v in CLOSES]
    top = 8_000_000
    span = len(values) - 1
    x = lambda i: LEFT + (i * (W - LEFT - RIGHT)) / span
    y = lambda v: TOP + ((top - v) * (H - TOP - BOTTOM)) / top
    line = " ".join("%.1f,%.1f" % (x(i), y(v)) for i, v in enumerate(values))
    ticks = [top * n / 4 for n in range(5)]
    grid = "".join(
        '<line x1="%s" x2="%s" y1="%.1f" y2="%.1f" class="%s"/><text x="%s" y="%.1f" class="tick-label">%s</text>'
        % (LEFT, W - RIGHT, y(tick), y(tick), "axis-zero" if tick == 0 else "grid-line", W - RIGHT + 6, y(tick) + 3, money(tick))
        for tick in ticks)
    marks = [(0, "Mar"), (13, "Apr"), (26, "May"), (39, "Jun")]
    # The first and last months are anchored inward, as LeftColumn.tsx does it: a name centred on the plot's edge
    # loses its first letter to the edge of the drawing.
    foot = "".join('<text x="%.1f" y="%s" text-anchor="%s" class="tick-label">%s</text>'
                   % (x(i), H - 6, "start" if i == 0 else "end" if i == span else "middle", name) for i, name in marks)
    return f'''<figure class="networth">
      <svg viewBox="0 0 {W} {H}" role="img" aria-label="Ada Obi's money over 40 closes">
        <text x="{LEFT}" y="12" class="plot-title">Ada Obi, in naira</text>
        {grid}
        <polygon class="plot-fill" points="{LEFT},{y(0):.1f} {line} {x(span):.1f},{y(0):.1f}"/>
        <polyline class="plot-line" points="{line}"/>
        {foot}
        <line x1="{x(26):.1f}" x2="{x(26):.1f}" y1="{TOP}" y2="{H - BOTTOM}" class="crosshair"/>
        <circle cx="{x(26):.1f}" cy="{y(values[26]):.1f}" r="3" class="plot-dot"/>
        <text x="{x(26) + 6:.1f}" y="{y(values[26]) - 6:.1f}" class="plot-read">{money(values[26])}</text>
      </svg>
      <figcaption class="muted small">40 closes, to the last bell</figcaption>
    </figure>'''


def indicator(name, value, change, bps, biggest):
    way = "flat" if not bps else ("up" if bps > 0 else "down")
    arrow = "–" if not bps else ("▲" if bps > 0 else "▼")
    size = max(4, round(abs(bps) / biggest * 100)) if bps else 0
    bar = '<span class="bar-%s" style="width:%s%%"></span>' % (way, size) if size else ""
    return f'''<div class="indicator">
        <div class="indicator-name">{name}</div>
        <div class="indicator-figure"><span class="mono">{value}</span>
          <span class="mono change-{way}">{arrow} {change}</span></div>
        <div class="indicator-bar" aria-hidden="true">{bar}</div>
      </div>'''


def indicators():
    biggest = 420
    commodities = [("Oil and gas", "128.44", "2.1%", 210), ("Farm produce", "141.02", "4.2%", 420),
                   ("Metals", "119.60", "0.6%", 60), ("Building materials", "133.18", "1.4%", 140)]
    macro = [("Jobs", "1,204,912", "0.4%", 40), ("Policy rate", "18.50%", "0.25 pt", 25),
             ("Inflation", "12.40%", "0.30 pt", 30), ("Confidence", "98.20", "1.80 pt", 180)]
    block = "".join(f'''<div class="indicator-group">
        <div class="group-label">{title}</div>
        <div class="indicators">{''.join(indicator(*row, biggest) for row in rows)}</div>
      </div>''' for title, rows in (("Commodities", commodities), ("Macroeconomic", macro)))
    return block + '<p class="muted small indicator-foot">Every move is since the close of Year 2 Q3.</p>'


def news():
    rows = [
        ("Ikenga Bank raises its dividend after a strong quarter", "The Lagos Ledger", "Year 2 Q3, day 64",
         [("IKB", "up", "2.4")]),
        ("Arewa Air grounds four aircraft and its shares fall", "Business Day Wire", "Year 2 Q3, day 63",
         [("ARW", "down", "5.3")]),
        ("Cement makers agree a price rise across the south", "The Market Post", "Year 2 Q3, day 62",
         [("CEM", "up", "1.1"), ("BUI", "up", "0.8")]),
        ("The Central Bank holds the rate for a third quarter", "The Lagos Ledger", "Year 2 Q3, day 61", []),
    ]
    items = "".join(f'''<li class="news-line">
          <a href="#" class="news-line-head">{head}</a>
          <div class="news-line-foot"><span class="muted small">{outlet} · {when}</span>{codes}</div>
        </li>''' for head, outlet, when, tickers in rows
        for codes in ["".join('<a href="#" class="mono">%s <span class="mono change-%s">%s %s%%</span></a>'
                              % (code, way, "▲" if way == "up" else "▼", size) for code, way, size in tickers)])
    return f'''<div class="column-list">
        <div class="news-search">
          <input type="search" aria-label="Search the news" placeholder="Search the wire">
          <button type="button" class="filter-chip" aria-pressed="false">My news</button>
        </div>
        <ul>{items}</ul>
        <a class="news-more" href="#">The whole wire</a>
      </div>'''


def column():
    return f'''<aside class="column" aria-label="Your money, the market and the news">
      <section class="panel">
        <div class="panel-head"><h2>Net worth history</h2><span class="muted small">{money(CLOSES[-1][1])}</span></div>
        {plot()}
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Market indicators</h2><span class="muted small">Year 2 Q3</span></div>
        {indicators()}
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Quotes and news</h2></div>
        <div class="column-tabs" role="tablist" aria-label="Quotes or news">
          <button type="button" role="tab" aria-selected="true" class="current">News</button>
          <button type="button" role="tab" aria-selected="false">Quotes</button>
        </div>
        {news()}
      </section>
    </aside>'''


def strip():
    links = "".join('<a href="#" class="%s">%s%s</a>' % ("current" if label == "Markets" else "", label,
                                                         '<span class="count">3</span>' if label == "Work" else "")
                    for label in ["My desk", "Work", "Empire", "Markets", "Money", "News", "Economy", "Court"])
    return f'''<header class="topbar">
    <div class="strip-left">
      <div class="strip-menu">
        <button type="button" class="strip-item" aria-expanded="false" aria-haspopup="menu">☰ Menu <span class="waiting-dot" aria-hidden="true"></span></button>
      </div>
      <button type="button" class="strip-item">Fullscreen</button>
      <a class="strip-item" href="#">Help</a>
      <a class="strip-item" href="#">About</a>
    </div>
    <nav class="strip-world" aria-label="Settings for the whole world">
      <button type="button" class="strip-item strip-world-item" disabled>Change Law Firm</button>
      <button type="button" class="strip-item strip-world-item" disabled>Toggle Global Autopilot</button>
      <button type="button" class="strip-item strip-world-item" disabled>Cheats</button>
      <button type="button" class="strip-item strip-world-item" disabled>Insurance</button>
    </nav>
    <div class="strip-right">
      <div class="strip-menu"><button type="button" class="strip-item"><span class="muted">Viewing:</span> Markets ▾</button></div>
      <div class="mono cash" title="Your cash">₦4,280,500</div>
      <div class="profile-menu"><button type="button" class="profile-button"><span class="avatar" style="width:28px;height:28px;font-size:11px">AO</span></button></div>
    </div>
  </header>'''


def tape():
    shares = [("TRAN", "228.01", "up", "0.2"), ("RLTY", "164.24", "down", "5.3"), ("WNC", "159.98", "flat", "0.0"),
              ("ALLI", "67.45", "down", "16.8"), ("RETL", "150.10", "down", "1.8"), ("GGM", "2,916.00", "up", "2.4"),
              ("IKB", "385.00", "up", "1.6"), ("ARW", "221.00", "down", "4.2")]
    items = "".join('<a href="#" class="ticker-item"><span class="mono strong">%s</span><span class="mono">%s</span>'
                    '<span class="mono change-%s">%s %s%%</span></a>'
                    % (code, price, way, "▲" if way == "up" else "▼" if way == "down" else "–", size)
                    for code, price, way, size in shares)
    return f'''<div class="ticker-bar">
    <div class="tape-date"><span class="mono strong">Y2 · Q3 · Day 67</span>
      <span class="pill pill-open"><span class="pill-dot"></span><span class="pill-label">Open</span></span></div>
    <a href="#" class="ticker-index"><span class="strong">BSX 50</span><span class="mono">4,118.20</span>
      <span class="mono change-up">▲ 0.9%</span></a>
    <div class="ticker-window"><div class="ticker-track">{items}</div></div>
  </div>'''


def work():
    return '''<main class="work">
    <div class="work-bar"><div class="command"><input class="command-input" placeholder="Enter command…"></div></div>
    <div class="work-head"><div><h1>Markets</h1><div class="work-sub">Trade shares, look at the book, and read the tape</div></div>
      <span class="muted small">Year 2 Q3, day 67</span></div>
    <section class="panel">
      <div class="panel-head"><h2>The day's tape</h2><span class="muted small">Every share, one line each</span></div>
      <p class="small muted">The work area keeps the width the column leaves it. On this page the tape's table
      sits here, with the same rules and the same boxes every other page has.</p>
      <div class="band band-4">
        <div class="band-cell"><div class="band-label">Cash</div><div class="band-value">₦4.28M</div><div class="band-note">money you can spend now</div></div>
        <div class="band-cell"><div class="band-label">Net worth</div><div class="band-value">₦6.44M</div><div class="band-note">since the last bell</div></div>
        <div class="band-cell"><div class="band-label">Shares and bonds</div><div class="band-value">₦2.16M</div><div class="band-note">at today's prices</div></div>
        <div class="band-cell"><div class="band-label">Reputation</div><div class="band-value">54</div><div class="band-note">everyone starts at 50</div></div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2>What you hold</h2></div>
      <table class="tape-table"><thead><tr><th>Code</th><th>Shares</th><th class="num">Price</th><th class="num">Value</th></tr></thead>
        <tbody>
          <tr><td class="mono strong">IKB</td><td>2,400</td><td class="num mono">₦385.00</td><td class="num mono">₦924,000</td></tr>
          <tr><td class="mono strong">ARW</td><td>1,000</td><td class="num mono">₦221.00</td><td class="num mono">₦221,000</td></tr>
          <tr><td class="mono strong">GGM</td><td>120</td><td class="num mono">₦2,916.00</td><td class="num mono">₦349,920</td></tr>
        </tbody></table>
    </section>
  </main>'''


def rail():
    return '''<aside class="rail" aria-label="Context">
    <section class="panel"><div class="panel-head"><h2>Needs you now</h2></div>
      <p class="small">One margin call, and a bid waiting on your company's shares.</p></section>
    <section class="panel"><div class="panel-head"><h2>Your account</h2></div>
      <p class="small muted">The right-hand rail keeps the page's own context.</p></section>
  </aside>'''


def page(theme, title):
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); }}
  .app {{ min-height: 0; }}</style></head>
<body><div class="app">{strip()}{tape()}<div class="shell">{column()}{work()}{rail()}</div></div></body></html>'''


for theme in ("dark", "light"):
    (OUT / f"column-{theme}.html").write_text(page(theme, f"the column, {theme}"))


def framed(name, theme, width=1440, height=900, scale=0.42):
    """The desk's width, shrunk to fit the preview panel: the same markup, scaled, and no iframe to be refused."""
    (OUT / name).write_text(f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<title>{name}</title><style>{CSS}
  html, body {{ margin: 0; background: #05080d; }}
  .win {{ width: {int(width * scale)}px; height: {int(height * scale)}px; overflow: hidden; }}
  .page {{ width: {width}px; transform: scale({scale}); transform-origin: top left; }}</style></head>
<body><div class="win"><div class="page"><div class="app">{strip()}{tape()}<div class="shell">{column()}{work()}{rail()}</div></div></div></div></body></html>''')


framed("column-wide.html", "dark")
framed("column-wide-light.html", "light")
print("written to", OUT)
