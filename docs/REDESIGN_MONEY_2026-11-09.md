# Markets and money, second sitting: the portfolio, borrowing, currencies, property, bonds, and no screen shouts

*A plain-language account of what changed, what was checked, and what is still open. Written for the owner, who does not work in code.*

## The idea, in one paragraph

The first sitting put the market on the same ruled sheet as the desk. This one carries it into the money screens: the portfolio, borrowing, currencies, property, and the bonds and offers tabs of the capital markets. Each now opens the way the desk and the market do, with a page head and a band of four figures, and each table is the same table as the shares page, with the brass rule down its first column and its headings held still. Nothing about the money moved. What moved is where you find it: the figures that used to sit in a row of small boxes are now the band at the top of the page, and the numbers that used to be scattered through panels are in the order you would ask for them. The sitting also adds a guard on the words: no screen may shout.

## What changed, screen by screen

**The portfolio** (`web/src/Portfolio.tsx`). The head now reads "Portfolio", with a line under it saying how many companies you own and how many shares in all, and, when you have any, a link to the orders waiting on the right. Under it is the band of four: everything you own, with the change since the last Closing Bell under it; what your shares are worth at today's prices; the cash you can use now, saying separately what is held back for your buy orders; and the dividends you have been paid, saying by whom. The "what you own, by kind" bar keeps its place below. The share table is now the tape table: the share code has its own first column in the brass margin, the company's name no longer carries the code inside it, and the share of your shares is set with the other figures rather than off on its own. The note under the table says plainly that during trading hours a figure can change while you are reading it.

**Borrowing** (`web/src/Borrow.tsx`). The three small boxes became a band of four: your worth after every debt is paid, everything owed, what is borrowed against shares, and the loan measured against what is held, which turns a colour and takes an arrow of its own as it nears the call. The thresholds sit under it in words: call at so much, sale at so much. The empire's version of the same page says "the empire's worth" rather than "yours".

**Currencies** (`web/src/Currencies.tsx`). The head says whether the naira is managed or floating, so the state of the currency is read before any figure. The naira's four figures, official rate, street rate, the gap between them, and the Central Bank's reserves, are the band.

**Property** (`web/src/Property.tsx`). The same band for the market's own numbers: the yield investors ask, the mortgage rate, and the property and land tax, each with a line under it saying what it means. The auction tags that were typed in capitals now read "Listing", "Owner's sale" and "■ Forced sale", so the warning square is what marks a forced sale, not the shouting.

**Bonds and offers** (`web/src/Capital.tsx`). Both tabs have their own page head now: bonds and bills, with the difference between the two stated in the line under the title and whether the desk is open; and offers, votes and bids. The group titles inside them, government bills, government bonds, company bonds, credit spreads, takeover offers, are sentence case like everything else.

**The court** (`web/src/Court.tsx`, and a route in `App.tsx`). A page of its own, with a rail and a lead. It asks the server for the docket, the claims it can bring, and your own record. This is display only: the page reads what the server already knows. It will not answer until the server side of the court is committed and the image rebuilt; see the last section.

**Across every screen.** The money batch is what the first sitting's report called the second sitting, and it is now done for the screens above. Two rules changed in `styles.css` on the way: the sideways-scrolling table now keeps its air at the cells rather than on the box around them, so the brass rule on its first column is not broken by a gap, and a table that has a height of its own can opt out of holding its headings still.

## The words guard, which is new

`web/src/copy.test.ts` walks every `.tsx` file in `web/src` and fails the run if any label is written in capitals. This is the design's own promise, checked rather than trusted, so it cannot quietly slip back.

Reading words out of code is harder than it sounds. A word can be written three ways: in a quoted string, in the bare text of a template, or in the bare text of a JSX element. A regex cannot tell prose from code, because an apostrophe in "the company's page", a quote in a comment, or a quote inside a `${…}` would each open a string that never closes. So the file is walked a character at a time, in three states, and a tag is read whole, so that `</Panel>` returns to code rather than opening a text of its own.

What it found and what was done: it flagged 24 headings typed in capitals in 15 screens, among them "WHO IS WAITING", "THE PROFESSIONAL METHOD", "CASH OUTLOOK" and "● BREAKING ·". All 24 are sentence case now. A handful of abbreviations that a broker writes that way are allowed by name: US, AI, PDF, NPV, alongside the codes, markets and ratings already listed.

## What was checked

The type check passes with no complaints. The front-end test run is 139 tests across five files, all passing: the copy guard's 56, the design rules' 60, the redesign's structure tests, the figures' formatting tests and the messages' tests. The contrast of every colour used for text against every background it sits on still passes the standard minimum readability in both themes. The bundle builds in under three seconds; its one note, that the single bundle is large, was there before this sitting.

The look book is rebuilt from the current stylesheet, in `docs/lookbook/`. The market's panels are `mb-1-market.html` (the whole page at night), `mb-2-table.html` (the table close up), `mb-3-light.html` (daytime) and `mb-4-phone.html` (a phone); the money screens are `mp-1-portfolio.html`, `mp-2-light.html` and `mp-3-phone.html`. Open the phone panels rather than the inner pages they frame: the layout only takes its phone shape inside a narrow frame, and the inner page opened in a full window shows a cramped desktop instead.

Two things were seen by screenshot this time: the phone panel, and so much of the wide page as the viewer could show before it clipped at 1440 pixels. **The visual review of the money screens is therefore still the owner's to do**, as the desk's was. What the phone panel showed has been fixed once already: the share table's subtitle read "Share of your shares shown beside each", a sentence that stops before its object, and now says "shown beside each company".

## What this sitting did not do

No figure is calculated anywhere new. Every number in every band comes from what the server already sends, in kobo, and is only formatted for the page. Nothing here touches the ledger, the server, or the rules of any transaction. The Python side has no part in this sitting.

The sitting has also not had the second AI's review. The desk and the market each were given to an AI that had written none of the code and was told to break it, and that review found eleven problems in the market sitting. This one has not had that treatment yet, so it should be read as unchecked by fresh eyes.

## To the owner

Three things are needed.

First, open the seven look book panels and say what looks wrong. The money screens have not been seen at full width.

Second, the court page needs its server. The Python side of the court is in the working tree but uncommitted, waiting on your ten-year run, and the web image will not show the page until that side is committed and `docker compose build server` has been run. If the docket is empty or the page errors, that is the reason, not the page.

Third, say whether you want the independent review of this sitting before it is built on. I would recommend it: the market sitting's review found a broken build and a rule that clipped a figure off the edge of eleven screens, and neither was visible from reading the tests that passed.
