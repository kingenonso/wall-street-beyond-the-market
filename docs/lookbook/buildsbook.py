"""The six build screens' look book: the real stylesheet, the shapes each screen now opens with.

Run:  python3 buildsbook.py /path/to/web/src/styles.css /path/to/out-dir

Three screens are drawn, chosen to show every variant of the opening: the asset manager's band of four in
the night theme, the financial journalist's band of six in the daytime theme, and the legal counsel on a
phone, where a band of four folds into twos.
"""
import sys, pathlib

CSS = pathlib.Path(sys.argv[1]).read_text()
OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
(OUT / "bbs").mkdir(exist_ok=True)


def topbar():
    return '''
  <header class="topbar">
    <a href="#" class="plain-link topbar-mark"><div class="wordmark"><span class="wordmark-main">WALL STREET</span><span class="wordmark-sub">BEYOND THE MARKET</span></div></a>
    <div class="command"><span class="command-icon" aria-hidden="true">⌕</span><input placeholder="Search a company, a page or an action" aria-label="Search"><span class="command-key">ctrl K</span></div>
    <div class="topbar-clock"><span class="mono topbar-date">Y1 · Q2 · D47<span class="muted topbar-time"> · 17:46 Lagos</span></span><span class="pill pill-open"><span class="pill-dot"></span><span class="pill-label">Market open</span></span></div>
    <div class="topbar-player"><span class="cash mono">₦4,280,500</span><span class="avatar" style="width:30px;height:30px;font-size:12px">AO</span></div>
  </header>
  <div class="ticker-bar"><a href="#" class="ticker-index"><span class="strong">BSX 50</span><span class="mono">1,284.72</span><span class="mono change-up">▲ 0.4%</span></a><div class="ticker-window"><div class="ticker-track"></div></div></div>'''


def sections(current):
    names = ["My desk", "Work", "Empire", "Markets", "Money", "News", "Economy", "Court"]
    out = "".join(f'<a class="section{" current" if n == current else ""}" href="#"><span>{n}</span></a>' for n in names)
    return f'<nav class="sections" aria-label="Sections">{out}<a class="section section-button" href="#">Every screen</a></nav>'


def head(title, sub, aside):
    right = f'<span class="muted small">{aside}</span>' if aside else ""
    return f'''
      <div class="work-head">
        <div><h1>{title}</h1><div class="work-sub">{sub}</div></div>
        {right}
      </div>'''


def band(cells, four):
    body = "".join(
        f'<div class="band-cell"><div class="band-label">{label}</div>'
        f'<div class="band-value">{value}</div>'
        f'<div class="band-note">{note}</div></div>'
        for label, value, note in cells)
    return f'\n      <section class="band{" band-4" if four else ""}" aria-label="The figures this page opens with">{body}</section>'


def allocation():
    rows = [("Shares", 68, "₦6,672,395"), ("Cash", 26, "₦2,551,204"), ("Government bills", 6, "₦588,746")]
    inner = "".join(
        f'<div class="bar-row"><div class="row"><span>{name}</span><span class="mono">{worth}</span></div>'
        f'<div class="meter"><div class="meter-fill" style="width:{pct}%"></div></div>'
        f'<div class="muted small">{pct}% of everything you own</div></div>'
        for name, pct, worth in rows)
    return f'''
      <section class="panel">
        <div class="panel-head"><h2>How your money is divided</h2><span class="muted small">Everything you own, by kind</span></div>
        {inner}
      </section>'''


def ranking():
    rows = [
        (1, "Staff, for pay owed", "₦84,000,000", "Wages come first."),
        (2, "The tax office", "₦212,400,000", "Tax owed ranks ahead of ordinary lenders."),
        (3, "Banks, for their loans", "₦610,000,000", "A bank loan is secured on what the company owns."),
        (4, "Holders of its bonds", "₦250,000,000", "Bondholders rank after secured lenders."),
        (5, "Suppliers, for unpaid bills", "₦127,600,000", "Ordinary creditors share what is left."),
        (6, "Shareholders", "₦1,840,000,000", "Owners are paid last, and only if anything remains."),
    ]
    body = "".join(
        f'<tr><td class="num mono">{rank}</td><th scope="row">{who}</th>'
        f'<td class="num mono">{owed}</td><td class="muted small">{why}</td></tr>'
        for rank, who, owed, why in rows)
    return f'''
      <section class="panel">
        <div class="panel-head"><h2>Case workspace</h2><span class="muted small">Manufacturing</span></div>
        <div class="why-title">Risks: who is paid first if it fails (Y1 · Q2, as filed)</div>
        <div class="scroll" tabindex="0">
          <table class="dense">
            <thead><tr><th scope="col" class="num">Rank</th><th scope="col">Who</th><th scope="col" class="num">Owed</th><th scope="col">Why there</th></tr></thead>
            <tbody>{body}</tbody>
          </table>
        </div>
      </section>'''


ASSET_MANAGER = f'''
<div class="app">
{topbar()}
  <div class="shell">
{sections("Work")}
    <main class="work">
{head("Asset manager", "What you are looking after, how it is divided, and the console to trade it", "6 companies · 4 industries")}
{band([("Total value", "₦9,812,345", '<span class="mono change-up">▲ ₦58,700</span> against yesterday’s close'),
        ("Over the last game year", '<span class="change-up">▲ 8.4%</span>', "BSX 50: ▲ 6.1%"),
        ("Against the BSX 50", '<span class="change-up">▲ 2.3%</span>', "includes money paid in"),
        ("Largest single share", "34%", "of everything you own")], four=True)}
{allocation()}
    </main>
    <aside class="rail" aria-label="Context"></aside>
  </div>
</div>'''


JOURNALIST = f'''
<div class="app">
{topbar()}
  <div class="shell">
{sections("News")}
    <main class="work">
{head("Financial journalist", 'The wire, the investigations open to you, and the economy the stories are written against. <a href="#">Macro research</a>', "Y1 · Q2")}
{band([("Growth, on the quarter", '<span class="change-up">▲ 2.1%</span>', "companies’ sales"),
        ("Inflation, over the year", "12.4%", "target 9.0%"),
        ("Jobs, on the quarter", '<span class="change-up">▲ 0.4%</span>', "4,182,000 in work"),
        ("The Central Bank’s rate", "18.50%", '<span class="change-up">▲ 0.50</span>'),
        ("Confidence", "104", "100 is normal"),
        ("Biggest move today", '<span class="change-up">▲ 4.6%</span>', "Danfo Logistics")], four=False)}
{allocation()}
    </main>
    <aside class="rail" aria-label="Context"></aside>
  </div>
</div>'''


LAWYER = f'''
<div class="app">
{topbar()}
  <div class="shell">
{sections("Work")}
    <main class="work">
{head("Legal counsel", "A company’s parties and the order they are paid in, and the companies the rules are closing in on", "Lagos")}
{band([("Owed in all", "₦1,284,000,000", "staff and the tax office first, owners last"),
        ("Credit rating", "BBB", "nothing it owes is past its date"),
        ("Takeover offer", "None open", "no bid in the market today"),
        ("Under watch", "3", "in default, behind on debt, or under offer")], four=True)}
{ranking()}
    </main>
    <aside class="rail" aria-label="Context"></aside>
  </div>
</div>'''


def page(theme, body, title):
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<title>{title} {theme}</title><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); }}
  .app {{ min-height: 0; }}</style></head>
<body><div id="frame" style="width:100%;height:100%;overflow:hidden">{body}</div></body></html>'''


def scaled(body, width, height, theme, scale):
    """A whole screen drawn at its true width and then reduced, so a narrow panel can show all of it."""
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8"><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); overflow: hidden; }}
  .app {{ min-height: 0; }}
  .screen {{ width: {width}px; height: {height}px; overflow: hidden; transform: scale({scale}); transform-origin: top left; }}
</style></head><body><div class="screen">{body}</div></body></html>'''


def phone(body, theme):
    """A phone: the page at 390 wide, in a frame that size, with no reduction."""
    return f'''<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8"><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); overflow: hidden; }}
  .app {{ min-height: 0; }}
  .screen {{ width: 390px; height: 844px; overflow: hidden; }}
</style></head><body><div class="screen">{body}</div></body></html>'''


(OUT / "bbs" / "asset-manager-dark.html").write_text(page("dark", ASSET_MANAGER, "asset manager"))
(OUT / "bbs" / "journalist-light.html").write_text(page("light", JOURNALIST, "financial journalist"))
(OUT / "bbs" / "lawyer-phone.html").write_text(phone(LAWYER, "dark"))


def panel(name, inner, width=484, height=652):
    (OUT / name).write_text(f'''<!doctype html><html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; background: #000; overflow: hidden; }}
  .win {{ width: {width}px; height: {height}px; overflow: hidden; }}
  iframe {{ display: block; border: 0; }}
</style></head><body><div class="win">{inner}</div></body></html>''')


panel("bb-1-asset-manager.html",
      '<iframe src="bbs/asset-manager-dark.html" width="1440" height="900" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel("bb-2-journalist.html",
      '<iframe src="bbs/journalist-light.html" width="1440" height="900" style="transform:scale(0.3361);transform-origin:top left"></iframe>')
panel("bb-3-phone.html", '<iframe src="bbs/lawyer-phone.html" width="390" height="844"></iframe>', 390, 844)

# The heads and bands alone, at true size: what this sitting actually changed, with nothing around them.
(OUT / "bb-4-heads.html").write_text(f'''<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8"><style>{CSS}
  html, body {{ margin: 0; background: var(--bg); }}
  .app, .shell {{ display: block; }}
  .strip {{ width: 1000px; padding: 18px 20px; }}
  .strip + .strip {{ border-top: 3px solid var(--border-strong); }}
  .where {{ font-size: 11px; color: var(--muted); margin-bottom: 6px; }}
</style></head><body>
  <div class="strip"><div class="where">Asset manager</div>{head("Asset manager", "What you are looking after, how it is divided, and the console to trade it", "6 companies · 4 industries")}
  {band([("Total value", "₦9,812,345", '<span class="mono change-up">▲ ₦58,700</span> against yesterday’s close'),
          ("Over the last game year", '<span class="change-up">▲ 8.4%</span>', "BSX 50: ▲ 6.1%"),
          ("Against the BSX 50", '<span class="change-up">▲ 2.3%</span>', "includes money paid in"),
          ("Largest single share", "34%", "of everything you own")], four=True)}</div>
  <div class="strip"><div class="where">Financial journalist</div>{head("Financial journalist", 'The wire, the investigations open to you, and the economy the stories are written against. <a href="#">Macro research</a>', "Y1 · Q2")}
  {band([("Growth, on the quarter", '<span class="change-up">▲ 2.1%</span>', "companies’ sales"),
          ("Inflation, over the year", "12.4%", "target 9.0%"),
          ("Jobs, on the quarter", '<span class="change-up">▲ 0.4%</span>', "4,182,000 in work"),
          ("The Central Bank’s rate", "18.50%", '<span class="change-up">▲ 0.50</span>'),
          ("Confidence", "104", "100 is normal"),
          ("Biggest move today", '<span class="change-up">▲ 4.6%</span>', "Danfo Logistics")], four=False)}</div>
</body></html>''')

print("written to", OUT)
