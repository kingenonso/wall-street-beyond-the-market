# The six build screens: a head, a band of figures, and the work under it

*A plain-language account of what changed, what was checked, and what is still open. Written for the owner, who does not work in code.*

## The idea, in one paragraph

The desk, the market and the money screens already open the same way: the page says its name, one line says what the page is for, and a band of figures sits under it before any of the work. The six build screens did not. Each was a stack of sections whose first section was a row of small boxes — the asset manager's portfolio, the accountant's books, the investment banker's company analysis, the risk manager's exposure, the journalist's six indicators — with the page beginning somewhere in the middle of itself. This sitting gives all six the same opening as the rest of the game, built from three shared pieces rather than written six times, so the next screen that needs a head and a band gets both by asking for them. Nothing about the six builds moved: same figures, same panels, same order of work underneath. What moved is where the page begins.

## What changed, screen by screen

**Asset manager** (`web/src/BuildDesk.tsx`). The head reads "Asset manager", with a line saying what you are looking after, how it is divided, and the console to trade it, and a count of the companies and industries you hold set right. The band of four is everything you own with the change since the last Closing Bell under it; what you made or lost over the last game year, beside the BSX 50 for comparison; the same figure against the BSX 50, saying plainly that it includes money you paid in; and your largest single share. The section that used to hold those four small boxes is now "How your money is divided" and keeps the allocation bar and the rest of its contents.

**Accountant** (`web/src/BuildDesk.tsx`). The head says "Accountant", with a line naming the three things the screen is for: the statements a company files, what they say quarter by quarter, and what waits on an audit. The band is the company's last filed quarter: sales, with the change on the quarter before; profit after tax, with its change; cash, with the staff count; and the credit rating, with a link to the company's own page. The band is labelled with the company's name and "as it filed", so the figures are never mistaken for another company's when the picker moves. The section called "The books" keeps the picker and the three statements.

**Investment banker** (`web/src/Desks2.tsx`). The head says "Investment banker"; the band labels itself with the company's name and "priced", and carries the share price today, the value of all its shares, the profit for the period with the sales it came from, and the credit rating. The panel called "Company analysis" keeps the picker, the valuation multiples and the companies like it.

**Risk manager** (`web/src/Desks2.tsx`). The head says "Risk manager", with a line saying what the book could lose on a bad day and the trades that would punch through its limits. The band is the four figures that were in boxes: total exposure, value-at-risk for one day, expected shortfall, and the largest fall on record. The empire's book and your own book still switch inside the section below, where the limits and the reasons are.

**Legal counsel** (`web/src/Desks2.tsx`). The head says "Legal counsel" with the company's headquarters set right, over a line about a company's parties, the order they are paid in, and the companies the rules are closing in on. The band is new work rather than a move: what the company owes in all, with a note that staff and the tax office come first and owners last; its credit rating, saying whether anything it owes is past its date; the takeover offer open on it, if any, and whether it is hostile and when it closes; and how many companies the rules are closing in on. The first of those figures — the total owed — the server was already sending and the website was not yet describing to itself, so it has been added to that description.

**Financial journalist** (`web/src/Desks2.tsx`). The head says "Financial journalist", with the game's period set right, and the link to macro research now in the line under the title. The band is six figures rather than four, because this is the screen whose whole subject is the economy: growth on the quarter, inflation over the year with its target, jobs on the quarter, the Central Bank's rate, confidence, and the day's biggest move. The section called "Economic indicators" is gone, because its six small boxes were exactly what the band now is.

**The head of an empire** is not one of the six. It is the CEO's screen, it already opened with its own head, and it was left alone in this sitting.

## The shared pieces

Three pieces in `web/src/Shell.tsx` now carry the opening: a page head (the title, the line under it, and a figure or label set right), a band (the ruled row of figures), and a cell (one figure of that band with its label and its note). The desk, the market and the money screens were written before them and have their own copies of the same shape; the six build screens are the first to use the shared ones.

## What was found on the way

Two faults, neither of them in the six screens, both of them real.

**A band of six on a phone drew a stray rule.** A band folds from six figures across to two on a phone, which means every other figure starts a row and must lose the rule on its left. That rule was written for the third figure only — which is right for a band of four, where the third figure is the first of the second row, and wrong for a band of six, where the fifth figure starts the third row and kept a vertical line down its left. The journalist's band is the first six-figure band on a page; the fix is on every odd figure, and it covers a band of four just as well.

**The old shapes were still available to fall back to.** Nothing stopped a later edit from putting a row of small boxes back at the top of a build screen and calling it done, because the small boxes are still used elsewhere in the game for good reason. There is now a test that fails if it happens.

## The guard, which is new

`web/src/screens.test.ts` reads the two files the six screens live in, takes each screen's own source from its declaration to the next, and checks three things about the six of them: that a page head comes first, that a band comes straight after it with nothing in between, and that the band holds more than two figures. It then checks that no build screen has a row of small boxes at the top again.

The guard was proved by breaking the screens on purpose rather than by seeing it pass. The legal counsel's page head was taken off and a row of small boxes was put back at the top of the journalist's screen: the run failed, on both counts, in exactly the places it should. Both were then put back. In the same way the new design rule was proved: the old phone rule was restored for one run and the design test failed, then the fix was restored.

## What was checked

The type check passes with nothing to report. The front-end test run is 149 tests across six files, all passing: the copy guard's 58, the design rules' 61 (one of them new), the redesign's 9 structure tests, the six screens' 7 (all new), the figures' 12 and the messages' 2. The contrast of every colour used for text still passes the standard minimum readability in both themes. The bundle builds in about six seconds. Its one note, that the single bundle is large, was there before this sitting.

The look book is rebuilt from the current stylesheet into `docs/lookbook/`: `bb-1-asset-manager.html` and `bb-2-journalist.html` are whole screens, one at night and one in daylight, reduced to fit a panel; `bb-3-phone.html` is the legal counsel at true phone width; and `bb-4-heads.html` is the four-figure and six-figure bands side by side at full size, with nothing else on the page, which is the closest thing to looking at the thing this sitting changed.

## What this sitting did not do

No figure is calculated anywhere new. Every number in every band comes from what the server already sends, and is only placed on the page. Nothing here touches the ledger, the server or the rules of any transaction; the Python side has no part in this sitting.

## To the owner

Two things are needed.

First, look at the look book. I could not see it: the file preview panel would not open in this sitting, so nobody has actually looked at these four panels. `bb-4-heads.html` is the one to open first, then the two whole screens, then the phone. Say what looks wrong, especially on the phone, where a band of six now wraps three times.

Second, the court's server side is still in the working tree, uncommitted and waiting on your ten-year run, exactly as the money sitting's report said. The website still shows the court page saying that the courts open with the next stage, which remains the truth until that side is committed and `docker compose build server` has been run.
