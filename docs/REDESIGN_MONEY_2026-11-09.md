# Markets and money, second sitting: the portfolio, borrowing, currencies, property, bonds, and no screen shouts

*A plain-language account of what changed, what was checked, and what is still open. Written for the owner, who does not work in code.*

## The idea, in one paragraph

The first sitting put the market on the same ruled sheet as the desk. This one carries it into the money screens: the portfolio, borrowing, currencies, property, and the bonds and offers tabs of the capital markets. Each now opens the way the desk and the market do, with a page head and a band of four figures, and each table is the same table as the shares page, with the brass rule down its first column and its headings held still. Nothing about the money moved. What moved is where you find it: the figures that used to sit in a row of small boxes are now the band at the top of the page, and the numbers that used to be scattered through panels are in the order you would ask for them. The sitting also adds a guard on the words: no screen may shout.

## What changed, screen by screen

**The portfolio** (`web/src/Portfolio.tsx`). The head now reads "Portfolio", with a line under it saying how many companies you own and how many shares in all, and, when you have any, a link that takes you down the page to the orders waiting. Under it is the band of four: everything you own, with the change since the last Closing Bell under it; what your shares are worth at today's prices; the cash you can use now, saying separately what is held back for your buy orders; and the dividends you have been paid, saying by whom. The four figures are written out in full, not shortened to millions: this is the page about what you own, so it says what you own to the naira. The "what you own, by kind" bar keeps its place below. The share table is now the tape table: the share code has its own first column in the brass margin, the company's name no longer carries the code inside it, and the share of your shares is set with the other figures rather than off on its own. Under the table, one line says what you have made or lost on shares you have already sold — a figure the first draft of this page lost, and the review put back. The note under the table says plainly that during trading hours a figure can change while you are reading it.

**Borrowing** (`web/src/Borrow.tsx`). The three small boxes became a band of four: your worth after every debt is paid, everything owed, what is borrowed against shares, and the loan measured against what is held, which turns a colour and takes an arrow of its own as it nears the call. The thresholds sit under it in words: call at so much, sale at so much. The empire's version of the same page says "the empire's worth" rather than "yours". A short whose price has not moved shows a plain naira figure with no arrow, rather than a green rise of nothing.

**Currencies** (`web/src/Currencies.tsx`). The head says whether the naira is managed or floating, so the state of the currency is read before any figure. The naira's four figures, official rate, street rate, the gap between them, and the Central Bank's reserves, are the band. Every table here that scrolls sideways can now be reached with the keyboard, so a reader without a mouse can still get at the right-hand columns.

**Property** (`web/src/Property.tsx`). The same band for the market's own numbers: the yield investors ask, the mortgage rate, and the property and land tax, each with a line under it saying what it means. The auction tags that were typed in capitals now read "Listing", "Owner's sale" and "■ Forced sale", so the warning square is what marks a forced sale, not the shouting.

**Bonds and offers** (`web/src/Capital.tsx`). Both tabs have their own page head now: bonds and bills, with the difference between the two stated in the line under the title and whether the desk is open; and offers, votes and bids. The group titles inside them, government bills, government bonds, company bonds, credit spreads, takeover offers, are sentence case like everything else.

**The court** (`web/src/Court.tsx`, and a route in `App.tsx`). A page of its own, with the same head as every other screen, a rail, and a lead. It asks the server for the docket, the claims it can bring, and your own record. This is display only: the page reads what the server already knows. Until the server side of the court is committed, the page says that the courts open with the next stage rather than showing a fault; see the last section.

**Across every screen.** The money batch is what the first sitting's report called the second sitting, and it is now done for the screens above. Two rules changed in `styles.css` on the way: the sideways-scrolling table now keeps its air at the cells rather than on the box around them, so the brass rule on its first column is not broken by a gap, and the notes under the figures of a band wrap on to a second line on a phone rather than being cut off mid-sentence.

## The words guard, which is new

`web/src/copy.test.ts` walks every `.tsx` file in `web/src` and fails the run if any label is written in capitals. This is the design's own promise, checked rather than trusted, so it cannot quietly slip back.

Reading words out of code is harder than it sounds. A word can be written three ways: in a quoted string, in the bare text of a template, or in the bare text of a JSX element. A regex cannot tell prose from code, because an apostrophe in "the company's page", a quote in a comment, or a quote inside a `${…}` would each open a string that never closes. So the file is walked a character at a time, in three states, and a tag is read whole, so that `</Panel>` returns to code rather than opening a text of its own.

What it found and what was done: it first flagged 24 headings typed in capitals in 15 screens, among them "WHO IS WAITING", "THE PROFESSIONAL METHOD", "CASH OUTLOOK" and "● BREAKING ·". All 24 are sentence case. A handful of abbreviations that a broker writes that way are allowed by name: US, AI, PDF, NPV, alongside the codes, markets and ratings already listed.

The guard had a hole. It let through any word of up to six capitals, on the reasoning that a short all-capitals word is a share code — but six capitals is also the shape of nearly every shouted heading, so it was blind to the very thing it exists to catch. Reading the screen by hand afterwards turned up 44 more labels in 12 screens: "RANK", "YOUR ETFS", "THE SHADOW SIDE", "BONDS AND BILLS", "READ THIS FIRST", "LATEST TRADES", and the fourteen cards on the firm's list of things needing you, among them "RESCUE", "MERGER" and "CLIENT". All 44 are sentence case now, and the guard allows a bare word only at three capitals or fewer, or where it carries a digit (a share code, a quarter). Two tests now feed the guard labels it must catch and codes it must not, so it cannot go quietly blind again.

## What the second AI found, and what was done about each

A second AI that had written none of this code was given the change and told to break it. It found eleven problems. Every one has been dealt with.

1. **The guard could not see shouts** — the fault above. Fixed, and the 44 labels it had been missing are sentence case.

2. **The page about what you own had lost a figure.** "On shares sold" — what you have made or lost on shares you no longer hold — was on the old page and not on the new one, though the server still sends it. Restored, under the share table, with a line saying why it is not the same thing as the gain on what you still hold.

3. **The headline figures were rounded.** Everything you own, your shares, your cash and your dividends were shortened to millions ("₦9.81M"), so the exact net worth appeared nowhere on the page. They are now written out in full.

4. **A link that went nowhere.** "3 orders waiting" pointed at the portfolio page, which is the page it was on. It now carries you down to the orders on that same page, and it respects a reader who has asked their machine for less motion.

5. **Eight tables the keyboard could not reach.** The currency tables scroll sideways, and every other such table in the game can be focused with the keyboard — these eight could not, so the right-hand columns were out of reach without a mouse. Fixed.

6. **A rise of nothing.** A short position whose price had not moved showed a green up-arrow against ₦0. It now shows a plain figure, as the rest of the game does.

7. **A long table that had opted out of holding its headings still** — the very thing the headings were added for. Restored, and the opt-out rule, which nothing then used, is gone.

8. **The court page had no page head and no title heading**, unlike the five screens this sitting rebuilt. It has both now.

9. **One missing figure could have taken the whole game down.** The court page printed server figures without checking them; a null where a number should be would have thrown, and there is no error boundary on this website, so the page would have gone white rather than one line saying "—". Every figure on that page is now checked first.

10. **A server that does not have the court yet looked like a fault.** It would have shown "Not Found" with a "Try again" button. It now says the courts open with the next stage, which is the truth.

11. **The notes under the band figures were cut off on a phone**, the end of a 40- or 60-character sentence lost behind an ellipsis. They wrap now.

## What was checked

The type check passes with no complaints. The front-end test run is 141 tests across five files, all passing: the copy guard's 58, the design rules' 60, the redesign's structure tests, the figures' formatting tests and the messages' tests. The contrast of every colour used for text against every background it sits on still passes the standard minimum readability in both themes. The bundle builds in under three seconds; its one note, that the single bundle is large, was there before this sitting.

The look book is rebuilt from the current stylesheet, in `docs/lookbook/`. The market's panels are `mb-1-market.html` (the whole page at night), `mb-2-table.html` (the table close up), `mb-3-light.html` (daytime) and `mb-4-phone.html` (a phone); the money screens are `mp-1-portfolio.html`, `mp-2-light.html` and `mp-3-phone.html`. Open the phone panels rather than the inner pages they frame: the layout only takes its phone shape inside a narrow frame, and the inner page opened in a full window shows a cramped desktop instead.

The phone panel has now been looked at, and it is what showed the band notes cut off. The wide portfolio panel cannot be seen whole here — the viewer clips it — so **the full-width review of the money screens is still the owner's to do.**

## What this sitting did not do

No figure is calculated anywhere new. Every number in every band comes from what the server already sends, in kobo, and is only formatted for the page. Nothing here touches the ledger, the server, or the rules of any transaction. The Python side has no part in this sitting.

## To the owner

Two things are needed.

First, open the seven look book panels and say what looks wrong. The money screens have not been seen at full width by anybody.

Second, the court page needs its server. The Python side of the court — the docket, the regulator, the bonds and the judgments — is in the working tree but uncommitted, waiting on your ten-year run, and the image will not show a working court until that side is committed and `docker compose build server` has been run. The website now says so in plain words instead of failing, so nothing will look broken in the meantime.
