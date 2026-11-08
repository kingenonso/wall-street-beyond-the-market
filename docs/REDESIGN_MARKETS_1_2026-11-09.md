# Markets and money, first sitting: the market, the companies, a company's page

*A plain-language account of what changed, what was checked, and what is still open. Written for the owner, who does not work in code.*

## The idea, in one paragraph

The desk was rebuilt first, as a broker's ledger sheet: no boxes, everything ruled, figures in a fixed-width type so they line up like a ledger, rises and falls carrying an arrow as well as a colour. This sitting carries that same sheet onto the market. The point is not that the market looks like the desk — it is that the whole game looks like one book, so a figure found on one page is found in the same place, in the same clothes, on the next. The page now opens with a head (who is reading, what the market is doing), then a band of four figures, then the market itself, its tape, a heat map of every share by industry, and the full table. The table is given a brass rule down its first column, like the margin of a ledger, and its headings stay still while you scroll.

## The checklist, item by item

The nine items below are the ones approved before this sitting began. Each is ticked against the evidence that it was done.

**1. One sheet — every screen on the same ruled sheet with a page head. Ticked, within this sitting.**

The trade shares page (`web/src/Market.tsx`), the companies list (`web/src/Companies.tsx`) and each company's page (`web/src/Company.tsx`) now open with the same head the desk uses: a title, a line of small text under it saying in plain words what the page is showing, and one figure or label set to the right. The shared parts of that head live in `styles.css` as `.work-head` and `.work-sub`. The other market screens — Portfolio, Borrow, Currencies, Property and the capital-markets tabs — have not been through this yet; they are the second sitting.

**2. The table restyled once — figures right-aligned in the fixed-width type, arrows beside rises and falls, green-bar banding, headings that stay still, "not yet traded" in plain words. Ticked.**

The rules live once, in `styles.css`, under `.tape-table` (the brass margin on the first column) and `.scroll-sticky` (the holding-still headings). The table on the shares page uses both; the companies list uses the same figures, the same arrows and the same banding. A share that has never changed hands reads "not yet traded" rather than a dash. Tests in `web/src/redesign.test.ts` and `web/src/design.test.ts` check the rules directly, so an edit to the stylesheet that quietly undoes one of them fails the test run.

**3. The tape where it earns its place — Trade shares, a company's page, the portfolio. Ticked for two of the three.**

The desk's tape is the ruled column with a brass gutter, a stamp in the margin, and each line saying what moved or what was written. On the shares page, the market's own numbers are read out in that form. On a company's page, a new section — "This share's tape" — shows the last four sessions, each stamped with its date, closing price, how many shares changed hands and how far it moved, newest at the bottom. A day with no trading says "nothing traded" rather than showing a zero. The portfolio's tape comes with the second sitting, because the portfolio screen is rebuilt there.

**4. Every feature kept — the heat map, all ten market tabs, the filter chips, the industry dropdown, the stars, the Closing Bell panel, the ratings, the explanation bubbles on technical words, the watchlist. Ticked, by reading the code.**

Nothing was removed. The heat map, the ten tabs, the "All / ★ My watchlist" chips, the industry dropdown, the star buttons, the Closing Bell panel, the credit ratings, the word-explanation bubbles and the watchlist are all still on the page. Two pieces were moved rather than dropped: the index figure and its change, which used to sit inside the index panel's title, now sit at the head of the page in the band of four, so you see the whole market's state before anything else. The index panel keeps its chart and its time-range buttons.

**5. Every money screen keeps its own logic. Ticked.**

No figure is calculated anywhere new. The band reads the index, the market's total value, the shares traded and the trades done, each straight from what the server sends. The company tape's percentage moves are worked out from the closing prices the server sends, day against the day before, and go blank rather than divide by an earlier price of nothing. No money moves in this sitting: it is all display.

**6. The loophole check — ten questions, automated tests, then a second AI asked to break it. Done; the findings are in the next section.**

**7. A look book, reviewed by screenshot. Built; the pictures could not be reviewed here.**

The look book is in `docs/lookbook/`: `marketbook.py` builds from the real stylesheet, and the panels `mb-1-market.html` (the whole market page at night), `mb-2-table.html` (the table close up), `mb-3-light.html` (the ledger-paper daytime theme) and `mb-4-phone.html` (a phone). This machine's image viewer would not open them — it reported no open file each time it was asked. So **the visual review of this sitting is not done.** The layout is therefore checked by the reader's judgement and by the second AI's reading of the code, not by looking at it. The owner should open the four panels and say what is wrong; the next sitting should not begin until they have.

**8. Verification — the type check, the front-end tests, the contrast, the bundle. Ticked.**

The type check passes with no complaints. The front-end test run is 82 tests, all passing. The contrast of every colour used for text against every background it sits on passes the standard minimum readability in both themes — that is 48 pairings, checked by test. The bundle builds in under three seconds and the only note is the existing warning that the single bundle is large, which was already there. The Python side has no changes in this sitting, so the Python tests do not need to be run for it; the court work in the working tree still does, and that is the owner's task.

**9. The report and the commit. Ticked.**

This report, and a commit. As with the desk, this machine cannot reach GitHub, so the commit is made here and the owner pushes it.

## What the second AI found, and what was done about each

A second AI that did not write any of this code was given the whole change and told to break it. It found eleven problems. All eleven were dealt with; six were real faults, and the rest were things worth tidying while in there.

1. **The build was broken.** The new design tests read the stylesheet off the disk with a feature the project's type checker did not know about, so the type check failed — and the build runs the type check first. That would have stopped the website being rebuilt. **Fixed** by declaring, in `web/src/node-fs.d.ts`, the one disk-reading call those tests use. The proper fix is a small package of type descriptions the sandbox could not download (the registry refused it), so the file says plainly what it is and that it should be deleted if the package is ever installed.

2. **The row-of-figures rule was written twice, with different spacing, and the gap rule only recognised the very first figure.** Where the figures wrapped onto a second row, the leftmost one had a stray rule hanging off its left edge. **Fixed** by defining the spacing once, and by drawing the rule from the figure on the right rather than the left (`web/src/styles.css`, `.tile + .tile`), so a wrapped row can never begin with a line. This affected eleven screens, not only the ones in this sitting.

3. **On a narrow screen the trade panel lost the first figure's left edge.** The separating rule went missing when two of the three figures were hidden. **Fixed** by the same change as item 2.

4. **On screens narrower than about 1,180 pixels the market's band of four folded into three and an orphan.** **Fixed**: two blocks of two.

5. **A company's page asked the server for its price history twice**, once for the tape and once for the chart. **Fixed** by asking once, in the page, and handing the same answer to both. It also now only asks while the overview is the tab being read.

6. **The tape's percentage change treated an earlier price of zero as "show nothing"**, which is the right answer for the wrong reason. **Fixed** so that case says so plainly.

7. **The shares table's own scroll window would have trapped a phone user in about four rows.** **Fixed**: on a phone the page scrolls and the headings travel with it.

8. **The brass margin rule was written in a way that would apply to any table reusing the name.** Left as it is, because only one table uses the name, and added to the list of things to watch.

9. **Several panels lost their inside margin when the boxes came off**, leaving tables touching the page edge. **Fixed** for tables, which now keep a little air at both sides and show a focus ring when the keyboard reaches them.

10. **Letters had been spaced out for capitals.** When capitals went, the spacing stayed, which reads as though the words are still shouted. **Fixed** on the five labels where it mattered. The one label built from a staff member's job name is safe because those names are already written in title case.

11. **The table's row spacing changed for every table in the game at once, and nothing checked that the shares table stays readable.** The duplicate spacing rule was removed (one rule, not two), and four new tests now guard the fixes above so they cannot quietly come undone.

## What this sitting deliberately did not do

The portfolio, borrowing, currencies, property and the capital-markets tabs are the second sitting, on the owner's word. Nothing in this sitting touches money, the ledger, or the server.

## To the owner

Two things are needed from you. First, open the four look book panels and say what looks wrong — this sitting has not been seen. Second, push this commit and the one before it from GitHub Desktop or your own terminal; this machine's network refuses the connection to GitHub.
