# The column that never moves

*A plain-language account of what changed in this sitting. Written for the owner, who does not work in code.*

## What you asked for

The second slice of the rebuild: the always-on left column of panels from your screenshots — your money over time, the market's indicators, and the quotes and news. It is the piece of the reference that was most obviously missing on every screen.

## What stands down the left edge now

Three panels, the same three on every page of the game: your net worth history at the top, the market indicators under it, and quotes and news at the foot. They are boxes with the indigo bar like everything else, they stay put while the page scrolls, and they scroll inside themselves when the whole column is taller than the screen — so they are still there when you are at the bottom of a company's page.

**Your money over time** is a filled chart of your own closes, titled with your name and the unit inside the plot, the scale down the right-hand edge, and the months along the foot. It reads your recorded closes to the last bell. A player who has never seen a bell yet gets a sentence saying so rather than an empty box or a made-up line — the first figure is written at their first Closing Bell.

**Market indicators** are two groups: commodities, and the macroeconomic lines (jobs, the policy rate, inflation, confidence). Two items across, each a name, a figure, its move with an arrow, and a bar whose length is the size of that move against the biggest move in the panel. No name is ever cut to a letter: where a name will not fit across, it takes a second line and its figure sits under it.

**Quotes and news** has the two tabs from your screenshot. News carries the search field that takes several terms separated by commas, the "My news" filter, and the headlines with the companies they name picked out in green or red by how the price has moved since. Quotes lists the shares you hold, priced — and it is only read the first time you open that tab, not on every screen in the game.

The column carries no navigation at all. That is the trade your reference makes: the left edge belongs to the market, and the sections live behind the strip's **Menu**, which is the next section of this report.

## One small server answer, not a dozen

Every screen in the game now draws this column, so it must be cheap. The server has a new read — `/api/readout` — that answers in one go with the last closed quarter's figures, the player's own recorded closes and the tickers they hold. It computes no share prices: the tape across the top already carries the index and every price, live, and a column that repriced the market on every page would be both slow and a second opinion about prices.

It also invents nothing. The numbers on the panel are read from the same records the economy page reads, and the moves are measured against the last close, which the panel says in words at its foot. Where the server writes a figure it writes it with its own unit — "2.4%" for a price index, "0.25 pt" for a rate — so no screen has to decide what a point is.

## The sections menu has moved into the strip

Your reference has no list of sections down the left of the page, and neither has the game now. The list is behind the strip's **Menu** button, and it says when something in it is waiting: a dot on the word Menu, because a count you can only find by opening a menu is a count nobody finds. That dot covers the same things the old column covered — unread messages, a rank case, a talent invitation, work in hand, a margin call, an empire waiting on you.

## What looking at it caught

The look book for this sitting is in `docs/lookbook` — the game's own stylesheet and the column's own class names, in both themes, at a desk's width and at a phone's. Reading it rather than assuming found four faults, and all four are fixed.

The chart's first month was cut: a label centred on the plot's left edge loses its first letter, so "Mar" was drawn as "lar". The first and last months are now anchored inward.

A headline was set beside its own outlet in half the column, four words to a line, instead of above it. The cause was a list rule that was more specific than the headline's own rule; the list now applies its inline layout only to the quote lines, and a headline keeps the whole width.

The figures in the indicators panel were falling onto a second line for some rows and not others, which left the bars at different heights across a row. A nine-character figure and its move are within a pixel of half a 260-pixel column at this type size, so the gap between them is now four pixels and the rows match. A wrap is still the fallback for a longer figure rather than a name losing a letter.

And the news list's scrollbar was sitting on the last character of each line; the list now leaves room for it.

## The phone, and a decision I want you to check

On a phone there is no left edge to stand in, and my first cut simply hid the column below 760 pixels. That is the kind of quiet dropping of a feature this project's rules forbid, and the comment I had written to justify it claimed the desk's band carried the same two figures — which it does not.

So the column now lies down at the foot of the page on a phone instead: the page's own work first, the readout after it, the context rail last. Nothing is dropped and nothing is a decoration; the cost is one scroll at the foot of every page. If you would rather a phone opened straight onto the page with no readout under it, say so and I will hide it — but I am not going to hide it on my own judgement.

## The one place this sitting is short of your screenshot

Your screenshot's middle group of indicators is **crypto**, and this game has no crypto market: nothing in the engine prices a coin, and adding one is a market, not a panel. So the column has two groups, commodities and the macroeconomic lines, and no third box pretending to have nothing in it. If you want a crypto market it can be built, and the panel will grow a third group the day it exists. I have marked this in the reference spec's register rather than leaving it to be discovered.

## The guard

Seven more tests in `design.test.ts`, all reading the stylesheet and the two screens as text, in a fraction of a second:

The column must be drawn once and outside the condition that drops the right-hand rail, so a focused screen cannot lose it. It must be the reference's three panels in the reference's order. It must not be hidden on a phone, and the page's own work must still come first there. The page-level sections menu must not come back, and the strip's Menu must carry the waiting dot. An indicator's name must never be given an ellipsis, a single line or a clipping box, and the list rule that squeezed a headline must keep its `:not()`. The chart must fill from the zero line upward, and the first month must stay anchored inward. And the panel's figures must be printed as the server wrote them, not rebuilt on the page.

## What was checked

The type check passes with nothing to report. The front-end run is 161 tests across six files, all passing — seven more than before this sitting. The look book was rebuilt against the final stylesheet and read again after every fix, which is how the four faults above were found and then confirmed gone.

The server's new read has no test of its own yet. This sandbox cannot run the Python suite — it needs the database, which only your machine has — so the endpoint is written, parsed and reviewed, but not yet exercised. When you run the suite, `tests/test_loopholes.py` and the quarter-close test cover it in passing; if you want a test aimed straight at it, say so and I will add one.

## What comes next

The three verb buttons — Trade, Corporate, Finance — with their menus and the colour grammar held by a test. Then the seven tabs on your own page, then the company page, then the four missing subsystems (law firm, autopilots, cheats, insurance), then the three missing markets.

The play, speed and step controls on the tape row are still waiting on the same thing as before: the server's clock can be read but not driven, so those three buttons would be a lie until there is an endpoint behind them.

One thing I noticed and did not change: between about 1150 and 1260 pixels of window width, the work area is narrower than it was, because the left column takes 60 more pixels than the sections menu did and the right rail has not yet dropped below. The fold point is a single number in the stylesheet if you want it moved.

## To the owner

To see it: `docker compose build web`, then `docker compose up -d web`, then a hard refresh, because the stylesheet is cached. I cannot push from here — the sandbox has no permission to write to your repository — so the commit is sitting locally and wants your push.
