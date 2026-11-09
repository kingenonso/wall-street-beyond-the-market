"""The strip look book: the real stylesheet and the strip's own class names, three widths and two themes.

Run:  python3 stripbook.py /path/to/web/src/styles.css /path/to/out-dir

Nothing here is the reference's markup. It is the markup Shell.tsx and Ticker.tsx now produce, so what is
reviewed is what the game will do.
"""
import sys, pathlib

CSS = pathlib.Path(sys.argv[1]).read_text()
OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)


SECTIONS = [("My desk", ""), ("Work", "3"), ("Empire", ""), ("Markets", ""), ("Money", ""), ("News", ""), ("Economy", ""), ("Court", "")]


def strip():
    parts = []
    for label, count in SECTIONS:
        cls = " current" if label == "Markets" else ""
        badge = f'<span class="count">{count}</span>' if count else ""
        parts.append('<a href="#" class="%s">%s%s</a>' % (cls.strip(), label, badge))
    links = "".join(parts)
    return f'''
  <header class="topbar">
    <div class="strip-left">
      <div class="strip-menu">
        <button type="button" class="strip-item" aria-expanded="true" aria-haspopup="menu">☰ Menu <span class="strip-caret">▾</span></button>
        <div class="strip-sheet" role="menu">
          <nav class="strip-links" aria-label="Sections">{links}</nav>
        </div>
      </div>
      <button type="button" class="strip-item">Fullscreen</button>
      <a class="strip-item" href="#">Help</a>
      <a class="strip-item" href="#">About</a>
    </div>

    <nav class="strip-world" aria-label="Settings for the whole world">
      <button type="button" class="strip-item strip-world-item" disabled aria-disabled="true">Change Law Firm</button>
      <button type="button" class="strip-item strip-world-item" disabled aria-disabled="true">Toggle Global Autopilot</button>
      <button type="button" class="strip-item strip-world-item" disabled aria-disabled="true">Cheats</button>
      <button type="button" class="strip-item strip-world-item" disabled aria-disabled="true">Insurance</button>
    </nav>

    <div class="strip-right">
      <div class="strip-menu">
        <button type="button" class="strip-item" aria-expanded="false" aria-haspopup="menu"><span class="muted">Viewing:</span> Markets <span class="strip-caret">▾</span></button>
      </div>
      <div class="mono cash" title="Your cash">₦4,280,500</div>
      <div class="profile-menu">
        <button type="button" class="profile-button" aria-expanded="false"><span class="avatar" style="width:28px;height:28px;font-size:11px">AO</span></button>
      </div>
    </div>
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
  <div class="ticker-bar" role="region" aria-label="The game's date and today's share prices">
    <div class="tape-date">
      <span class="mono strong" title="The game's date">Y1 · Q2 · Day 47</span>
      <span class="pill pill-open"><span class="pill-dot"></span><span class="pill-label">Market open</span></span>
    </div>
    <a href="#" class="ticker-index"><span class="strong">BSX 50</span><span class="mono">1,284.72</span><span class="mono change-up">▲ 0.4%</span></a>
    <div class="ticker-window"><div class="ticker-track">{rows}</div></div>
  </div>'''


def body():
    return f'''
<div class="app">
{strip()}
{tape()}
  <div class="shell">
    <nav class="sections" aria-label="Sections">
      <a class="section current" href="#"><span>Markets</span></a>
      <a class="section" href="#"><span>Money</span></a>
    </nav>
    <main class="work">
      <div class="work-bar">
        <div class="command"><span class="command-icon" aria-hidden="true">⌕</span><input placeholder="Search: a company, a page, an action…" aria-label="Search"><kbd class="command-key">Ctrl K</kbd></div>
      </div>
      <div class="section-tabs">
        <a class="section-tab current" href="#">Trade shares</a>
        <a class="section-tab" href="#">Companies</a>
        <a class="section-tab" href="#">Property</a>
      </div>
      <section class="panel">
        <div class="panel-head"><h2>The work area</h2><span>below the tape</span></div>
        <p class="small">The strip sits above the tape; the tape carries the game's date and the market's state on its left; then the page's own tabs, with the search line above them.</p>
      </section>
    </main>
  </div>
</div>'''


def page(theme, title):
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); }}
  .app {{ min-height: 0; }}</style></head>
<body>{body()}</body></html>'''


(OUT / "strip-dark.html").write_text(page("dark", "the strip, dark"))
(OUT / "strip-light.html").write_text(page("light", "the strip, light"))


def framed(name, inner, width=1440, height=520, scale=0.3333):
    (OUT / name).write_text(f'''<!doctype html><html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; background: #000; overflow: hidden; }}
  .win {{ width: {int(width * scale)}px; height: {int(height * scale)}px; overflow: hidden; }}
  iframe {{ display: block; border: 0; width: {width}px; height: {height}px; transform: scale({scale}); transform-origin: top left; }}
</style></head><body><div class="win"><iframe src="{inner}"></iframe></div></body></html>''')


# The same page at a desk's width, shrunk to fit the preview panel.
framed("strip-wide.html", "strip-dark.html")
framed("strip-wide-light.html", "strip-light.html")

print("written to", OUT)
