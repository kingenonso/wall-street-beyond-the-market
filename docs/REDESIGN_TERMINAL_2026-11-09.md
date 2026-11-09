# Back to the terminal: the reference you gave me, and what I had built instead

*A plain-language account of what went wrong, what has changed, and what is still to do. Written for the owner, who does not work in code.*

## What went wrong

You asked for a market terminal. The October design report describes exactly that: a command bar, a live tape, sortable tables with trend lines, charts, and a dense, dark, paneled feel. Then in November four sittings rebuilt the game as a light broker's ledger sheet instead — brass rules, serif headings, panels with no boxes, sentence case everywhere. Each of those sittings wrote a report that described the new direction as progress, and each report was accurate about what it had done. None of them held the result against your reference. That is how a game ends up looking nothing like what was asked for while every individual step looks sensible.

This sitting puts the look back on the reference.

## What the reference actually is

Reading your screenshot closely, the terminal has six things that the ledger sheet had none of:

A dark, near-black ground with every section boxed and a tinted bar across the top of each box. Monospace for every figure and nearly every word, small and tight. A strip across the very top with the game's date, a stop button, a speed clock and a play button, then a tape whose every name has a coloured bar under it — green for a rise, red for a fall. A left column of panels that never go away: the net worth history, the market indicators grouped under commodities, crypto and macroeconomic, the order-entry buttons. A company screen that opens with its code before its name, then a row of boxed tabs. And inside a panel, plain monospace lines separated by dashed rules rather than a table of well-behaved columns.

## What has changed

**The ground and the lettering.** The whole game now sits on the terminal's near-black navy, with panels a shade lighter and a defined edge. The body is monospace at 13 pixels, so figures line up down a page whether or not they are in a table. Headings are monospace too, and small. The daylight theme keeps the same boxes and the same indigo bars; only the ground and the ink change, so nothing has to be learned twice.

**Every panel is a box with a bar.** A panel is now a bordered box with an indigo bar across its top carrying its name, exactly as the reference's are. The bar takes back the panel's own padding so it runs the full width of the box, which means every panel's contents sit at the same inset without each screen having to be told. A panel that must stand out — yours, urgent, a warning — gets a coloured edge down its left rather than being unboxed.

**The tape has its bars.** Each name in the tape across the top now carries a two-pixel bar underneath in the colour of its move, green or red, grey where nothing has traded. That is the reference's most recognisable detail and it costs nothing to read.

**Tabs are boxes.** The tabs across the company page — Overview, Accounts, For investors, About it — are boxes along the bottom edge of the screen, with the open one lit in the same indigo as a panel bar. The tabs inside panels are boxes too.

**The company page leads with its code.** It now reads `IKB — Ikenga Bank`, as the reference reads `AZA — AZA Group`, because the code is what a player says when they mean a company.

**The sections menu is a panel.** The list of sections down the left is now a bordered box, with the open page lit in indigo.

## The guards, which had to be rewritten rather than deleted

The old tests enforced the ledger sheet: a panel must have no box and no fill, and nothing in the stylesheet may set text in capitals. Both are now wrong, and deleting them would have thrown away the only thing that has ever kept a design decision from quietly rotting. So they were rewritten to the terminal's rules instead.

The panel test now demands the opposite of what it used to: a box, a ground, a three-pixel radius, the bar across the top, and the bar's negative margin that makes it run the full width. The capitals test is more interesting. A terminal sets a panel's name and a table's headings in capitals, but the game's words stay in sentence case — the copy guard, which reads every screen's words, is untouched and still passing. So capitals are allowed to come from the stylesheet, and only from the handful of rules that are labels: a panel's bar, a table's headings, a group title. Any other rule that starts shouting fails the run.

## What was checked

The type check passes with nothing to report. The front-end run is 149 tests across six files, all passing. The contrast of every colour used for text against every background it sits on still passes the standard minimum readability, in both themes — that check reads the new palette and passed it unchanged. The bundle builds in under three seconds: 72 kilobytes of stylesheet, which is one and a half more than the ledger sheet took, because the terminal has more chrome.

## What is not done yet

This sitting changes how the game looks, not yet how it is laid out screen by screen. Three things from the reference are still missing, and they are the next sitting's work rather than this one's:

The **left column of always-on panels** — net worth history, market indicators, and the order buttons — currently only appears on the pages that happen to fill the context rail. In the reference it is there on every screen and never moves. That needs a real rail, fed with real figures, rather than a mock-up.

The **strip** — the game's date, a stop dot, a speed clock and a play button — is not built. The tape under it is.

The **per-company command line**, the wide input under the company's name, is not built. The game's command bar sits in the top bar instead.

And the screens themselves still use the shapes the ledger sittings gave them — heads, bands, ruled tables. They now wear the terminal's clothes, but their bones are still the ledger sheet's. Rewriting those bones, screen by screen, is the work that follows.

## To the owner

To see this, rebuild the web image: `docker compose build web` and then `docker compose up -d web`. The browser will need a hard refresh, because the stylesheet is cached.

I could not look at it myself: the file preview panel would not open in this session, so the four panels in `docs/lookbook` — `tb-1-company.html`, `tb-2-desk.html`, `tb-3-light.html` and `tb-4-phone.html` — have been seen by nobody. They are drawn with the game's own class names and the real stylesheet, so what they show is what the game will do, but they are not the game.

Tell me which of the three missing pieces matters most — the always-on left column, the date-and-speed strip, or the company command line — and I will do that next rather than guessing.
