# The strip across the top, and the date moving onto the tape

*A plain-language account of what changed in this sitting. Written for the owner, who does not work in code.*

## What you asked for

You said the build was still far behind, sent five batches of screenshots, and then told me to go ahead and build rather than keep writing the specification. This is the first slice of that build: the frame everything else sits inside — the strip across the very top.

## What the strip is now

Your screenshots show three groups along the top, and that is what the game now draws.

On the left, the things that take you somewhere: a **Menu** button that opens the list of the game's sections, **Fullscreen**, **Help** and **About**. The sections themselves still live down the left edge of the page as they did — the menu is a second door to the same rooms, which is what the reference's hamburger does.

In the middle, set away from the navigation by a thin rule, the four switches that change the whole world rather than opening a page: **Change Law Firm**, **Toggle Global Autopilot**, **Cheats** and **Insurance**.

On the right, **Viewing:** with the name of the page you are on, then your cash, then the picture that opens your own menu.

The **Viewing:** words are new and they are a correction to something I got wrong earlier. When I first read your second screenshot I took "Viewing:" for a trail of breadcrumbs and wrote it up that way. It is not a trail: it is one box that says what you are looking at and opens a list of the other places you could be looking. It now behaves that way — a click opens the list, Escape closes it, and a click anywhere else closes it too.

## The four switches are dark, on purpose

None of the four has anything behind it yet. There is no law firm, no autopilot, no cheats and no insurance in the engine. So each one is drawn dimmed and cannot be pressed, and its tooltip says plainly that it is not built yet.

That is deliberate rather than unfinished. A button that looks ready and does nothing is a lie to the player, and the colour grammar already has a word for it: dimmed means this does not apply to you yet. When each of those four is built, it lights up. Until then it tells the truth.

## The date has moved onto the tape

Your fourth screenshot showed the date on the tape's own row, not in a strip above it, and the earlier design report had that wrong. It is one row: **Y1 · Q2 · Day 47**, the market's state beside it as a coloured dot and a word, and then the prices running away to the right.

The date now appears even before the prices have arrived, which matters at the start of a session: the row is never blank.

**What is not there yet, and why.** Your screenshot also has a play button, a speed and a step-forward on that row. I have not built them. The server's clock can be read but not driven — there is no way to ask it to go faster, to stop, or to take a single step. Three buttons that do nothing would be the same lie as the four switches, only harder to spot, because a play button that does nothing looks like a market that has paused. They wait until the clock itself can be driven, which is a piece of server work, not a piece of screen work.

## The search line has moved, not gone

The search-and-command line used to sit in the top bar. The reference has no search box in its strip, so it has moved down into the page, in its own row above the tabs. It works exactly as before — Control K still puts the cursor in it from anywhere — and it no longer competes with the strip for width.

## Two new pages

**Help** and **About** now go somewhere. Help lists the handful of things that save real time: Control K, the arrow keys between tabs, Escape to close a menu, and the tape as a way into a company. About says what the game is in three sentences. Neither invents a feature that does not exist; if a key is listed there, it works.

## The guard

Every design decision in this project gets a test, because a decision that is only in somebody's head lasts until the next sitting. This one got four, in `design.test.ts`, which reads the stylesheet and the two screens as text and takes a fraction of a second:

The strip must be three groups with the middle one set apart by a rule — so a later change cannot quietly collapse it back into one grey row. The date must be on the tape row and must not creep back into the strip. The search line must still be reachable now that it is not in the top bar. And the four switches must stay disabled while nothing is behind them — that last one is the loophole check: it fails the day somebody builds one of the four and forgets to light it, and it fails the day somebody lights one before its engine exists.

## The error I found in my own work

The specification's register of every control listed **Change Bank** as having nothing behind it. That was wrong. The bank chooser is built: six banks, a player may move once a quarter, and the server refuses a move in the same quarter you joined. I have corrected the register and marked the correction, because a register that is quietly edited is a register nobody can trust.

## What was checked

The type check passes with nothing to report. The front-end run is now 153 tests across six files, all passing — four more than before this sitting, all four of them the guards above. The bundle builds. And I looked at the strip rather than assuming: the look book was rebuilt with the game's own stylesheet and its own class names, in dark and in light, at a desk's width and at a phone's, and the screenshots are in `docs/lookbook` as `strip-wide.html`, `strip-wide-light.html` and `strip-dark.html`.

One thing the screenshots settled. I thought the open-menu button and the current item in a list were wearing two different indigos in the light theme, which would have been a real fault — the grammar says two things doing the same job wear the same colour. So I asked the page itself what colours it was painting: a panel's bar, the open menu button and the current item all resolve to the same indigo, in both themes. There was no fault; the small screenshot had fooled my eye.

## What comes next, in the order I would do it

The always-on left column of panels — net worth over time, the market indicators grouped under commodities and macroeconomic, the order buttons — because it is the piece of the reference that is still most obviously missing on every screen, and it needs a figure the server does not yet keep: your net worth, quarter by quarter. That is a small piece of server work followed by a large piece of screen work.

Then the three verb buttons — Trade, Corporate, Finance — with their menus and the colour grammar enforced by a test.

Then the seven tabs on your own page, then the company page, then the four missing subsystems, then the three missing markets.

## To the owner

To see it: `docker compose build web`, then `docker compose up -d web`, then a hard refresh in the browser, because the stylesheet is cached. I cannot push from here — the sandbox has no permission to write to the repository — so the commit is sitting locally and wants your push.
