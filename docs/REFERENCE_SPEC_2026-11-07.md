# The reference, screen by screen

*Your screenshots read back to you, so that nothing in them is lost between now and the day it is built. Written for the owner, who does not work in code.*

## How this document works

This is a growing document, not a finished one. You are sending screenshots; each one gets a section here that does three things. It says **what is on the screen**, in the order your eye crosses it. It says **what each control must do** when clicked — not what it looks like, what it does. And it says **what this build already has** behind that control, so you can see the size of the job before it starts rather than after.

Four screens are written up so far: the company's Overview page, the strip across the top with a message box over it, the three command menus, and your own page. When you tell me the set is complete, this document becomes the build order and I bring you a checklist to approve before any code is written, as the working rules require.

Later screenshots sometimes correct earlier ones. Where that happens I say so plainly and mark the correction, rather than quietly rewriting the earlier section and leaving you to spot the difference.

One rule I have applied throughout: your game is set in Nigeria and counts in naira. Your screenshots count in dollars. I am reading the *shape* of each thing — a price axis, a per-share figure, a percentage — and keeping the naira. If you would rather the game counted in dollars, say so and I will change the whole game instead of one screen.

---

## Screen one: a company's Overview page

The page is a wall of boxes, not a page of prose. Reading left to right, the price history takes the wide left column and four smaller panels stack down the right: Leadership, Analyst Summary, Company Information, Advisory Summary. (I am reading the stacking order from your screenshot and may have the last two swapped; it will be obvious once I build one screen to compare against.)

### The stock price history panel

A **candlestick chart** — each period drawn as a body between its opening and closing price with a thin wick above and below for the high and the low, green where the period closed up and red where it closed down. That is the single biggest difference from what the game has now, which draws one continuous line joining closing prices. A line answers "where has this been"; candles also answer "how violently did it get there", which is the question a trader actually asks.

Around the chart: a labelled price scale down the left with the word PRICE turned sideways beneath it, period labels along the foot (your screenshot reads `Q4-26` through `Q1-27` — quarters, so each candle is a quarter), and a box that follows the pointer giving that period's open, high, low, close and change.

### The Leadership panel

Two columns, each a small grey label above a large white answer. The left is **CEO** and a name. The right is **REPUTATION** and a word — your screenshot reads "V.Good", so reputation is shown as a band, not a number.

### The Analyst Summary panel

A single action in the panel's top right, **View Research Report**, and beneath it six judgements laid out three across and two down. Each is a small coloured dot, a label in small capitals, and the figure:

- P/E ratio — the price divided by a year's profit per share, which is how many years of today's earnings the market is paying
- Dividend yield — the cash paid out each year as a percentage of the share price
- Book value per share — what each share's slice of the company's own money comes to
- Credit rating — the letter grade for how safely it could repay a debt
- Analyst rating — a thumbs-up or thumbs-down verdict on the share
- Cash flow — the money actually moving through the business

The dot is the whole point. Green means this reading is a good sign, amber means it is unremarkable, red means it is a warning. A player should be able to read the six dots and know whether this company is healthy without reading a single number.

Clicking **View Research Report** opens a written report on the company. That report does not exist in the game today.

### The Company Information panel

Twelve facts in a two-column grid, each a small grey label above its answer: type, industry, headquarters, state, year founded, website, ticker code, country, sales, employees, market value, number of shareholders. The game has all twelve facts already; they are scattered across three tabs instead of gathered in one box.

### The Advisory Summary panel

Plain prose, three or four lines, being the game's own judgement of the company — what it does, how it is doing, what to watch. The game has nothing like this. It is written copy about a company that changes as the company changes, and it is the cheapest of the new pieces to build and possibly the most useful.

---

## Screen two: the strip across the top, and a box that interrupts you

### The strip

Left to right: **About**, **Change Law Firm**, **Toggle Global Autopilot**, **Cheats**, then the word **INSURANCE**, then **Player** which opens a menu. On the right-hand end, a way back through what you have open, reading `← Viewing: AZA GROUP (AZA)` — the company you are inside, in small capitals, with an arrow that takes you out.

The important thing here is not the words but what they say about the game's shape. Four of those six are company-wide switches that sit above every page — the law firm defending you, the autopilot running things for you, the cheats, the insurance. That means they are not pages at all. They are settings that belong to the world and follow you everywhere, and the game has no such place for them today.

Two things I could not read from this screenshot: whether **INSURANCE** is a menu like the others or a heading over the Player menu, and whether **About** means the game's own credits and rules or something about the company you are looking at. The fourth screenshot settles About — it sits beside Help and Fullscreen, so it is the game's own — and leaves INSURANCE open. It also corrects my reading of **Viewing:**, which is a chooser rather than a trail; see screen four.

### The tape

Under the strip, a single line of names. Each reads symbol, last price, percentage moved today, and carries a small block in the colour of the move. At the far right a wider block for the market as a whole. The game already builds this; the tape is one of the few things in your screenshots that is already there.

### The message box

A rounded dark card floating over a dimmed page, with a thin edge and a soft shadow. The heading **Congratulations.** sits top left in sentence case, not capitals. Below it, two or three paragraphs of prose. One button, **OK**, in green, at the bottom right inside the card, and nothing else — no cross in the corner, no second choice. It is a box that tells you something happened and asks you to acknowledge it, which is a different job from a box that asks you to decide.

The game has dialogs, but they are built to take decisions. It needs this second kind: the announcement that stops you, tells you what just happened, and lets you carry on.

---

## Screen three: the command menus

### The three buttons

**Trade**, **Corporate**, **Finance** across the top of the work area, the open one lit. They are the three kinds of thing you can do *to a company*, as against the pages that tell you about it. The game today has six build screens reached from a menu down the left side. This is a different idea: the verbs live above the company and the pages live down the side.

### The menu itself

A panel hung under the lit button, in five groups. Each group is a small grey heading in capitals, and every item under it is coloured by what it will do to you.

**LEADERSHIP** — Elect as CEO (green), Fire Management (red)

**STRATEGY** — Set Productivity (amber), Set Growth Rate (amber), Rebrand (green), Restructure (dimmed)

**M&A** — Merger (green), Startup (green), Capital Contribution (green)

**ASSETS** — Buy Corporate Assets (green), Sell Corporate Assets (red), Offer to Sell Subsidiary Stock, Browse For Sale Items

**AUTOPILOT** — Toggle Company Autopilot, Toggle Global Autopilot

### The colour grammar

This is the part worth building into the game's rules rather than one screen's stylesheet, because it teaches a player to read a menu before they have read a single word:

**Green adds.** It buys, builds, hires, contributes. After it, you own more than you did.

**Red removes.** It fires, sells, liquidates. After it, you own less, and the game usually charges you for the privilege.

**Amber sets a number.** It changes a dial and nothing else — no money moves, no asset appears. Productivity and growth rate are both this.

**Dimmed means not now.** Restructure is greyed in your screenshot because something about that company forbids it at that moment. The menu still shows it, so the player learns it exists and learns why it is barred.

**Neutral, in the ordinary text colour, browses or toggles.** Opening a list, or flipping a switch back and forth. Nothing is spent and nothing is gained.

The rule I would write into the tests: a menu item's colour must follow from what the action does, not from what somebody typed next to it. If an action can both add and remove, it is neutral and says so.

---

## Screen four: your own page, and the frame around everything

This is the page you land on, and it is the player's own rather than a company's. It is the most useful screenshot of the four, because it shows the frame that every other screen will sit inside — and it corrects two readings I had taken from the earlier ones.

### What it corrects

**The panel bars are real, and they stay.** Every panel here carries a bar across its top, shading from purple on the left to indigo on the right, with the title in white. My question about whether to keep the bars is answered: keep them. The company page in the first screenshot reads plainer than this, and I am treating it as the same thing seen smaller, not as a different design.

**"Viewing:" is a chooser, not a trail.** In the company screenshot I read it as a breadcrumb with an arrow back out. Here it is a dropdown reading your own name. So it is the control that says *what you are looking at* and lets you change it. It is not a history of where you have been.

**The date and the transport sit on the tape's own row, not above it.** `Aug 22, 2027 (Q3)`, a play button, a speed, and a step-forward, and then the tape runs away to the right. The earlier design report described a separate strip. It is one row.

### The strip at the top

Left to right: a menu button, **Fullscreen**, a lightbulb, **Help**, **About** — then, set away from the rest in the middle, **Change Law Firm**, **Toggle Global Autopilot**, **Cheats** — then at the right **My Corps**, the word **Viewing:**, and the chooser with your name on it.

The three world-switches sit apart from the navigation on purpose. That placement is doing work: it tells the player these are not pages, they are how the world is set up. The lightbulb next to Help is presumably tips or hints.

### The left column that never moves

Three panels, stacked, present whatever page you are on. This is the thing the earlier design report called for and never built.

**Net worth history** — your own money over time as a filled chart, titled inside the plot area with your name and the unit, the value scale down the right-hand edge, faint gridlines, and months along the foot. In your screenshot the fill is bright green and sits *above* the line rather than under it. I will draw it the conventional way, under, unless you tell me the inversion is deliberate.

**Market indicators** — three groups: COMMODITIES & INDEXES, CRYPTO, MACROECONOMIC. Two items across, each a label, a value, an arrow and a percentage, with a horizontal bar beneath in green or red showing the size of the move. This is the market readout that never leaves the screen.

**Quotes and News** — two tabs at the foot of the column. News carries a search field that takes several terms separated by commas, a "My News" filter, and a scrolling list of headlines in which the company's name and the action it took are picked out in colour.

### The work area

One line above the panels: your name, then the three big verbs, then a wide field reading **Enter command…** with a **?** button at its left. The verbs are coloured and carry icons — **Trade** green with a checklist, **Corporate** blue with a building, **Finance** orange with a banker. The command field is the game's command line, sitting on the page in plain sight rather than hidden behind a keyboard shortcut.

Then the tabs, built as boxes with rounded tops: **Overview, Financials, Advances, Holdings, My Corporations, Market, Search**, with the open one lit.

Then four panels. **Net worth** gives three figures side by side, each with a coloured dot: total assets, total debt, net worth. **Borrowing** gives the borrowing rate, the unused line of credit, the debt-to-equity ratio, and the capital gains realised so far this year. **Personal profile** gives name, country, employment status, lending bank as a blue link, credit rating, and net worth trend. **Advisory summary** is the prose one, in two paragraphs with bold capitals lead-ins — *Your financial situation:* and *Your tax situation:* — the second computing a projected tax bill for the whole year from what you hold today.

That last panel is the same idea as the company's Advisory Summary: the game saying, in words, what it thinks of you.

### One thing worth arguing with

The market indicators cut their labels down to a letter and a dot — "St…", "O.", "S.", "C…", "W…" — because two items across is too narrow to hold a name. Nobody can read that, and in a game whose whole point is reading figures quickly, it is the one place your reference works against itself. I would keep everything else exactly as it is and give those labels room, either one item per row or shorter true names. Tell me if the truncation is deliberate and I will match it.

---

## Screen five: the three menus, opened

Three screenshots, one per verb, which between them give me every action in the game's three families.

### Trade

One wide panel in three columns, each headed in grey capitals, and everything in it is a purchase:

**STOCKS** — Buy Stock
**CORPORATE BONDS** — Buy Corp Bond
**GOVERNMENT BONDS** — Buy Long Govt Bonds, Buy Short Govt Bonds
**COMMODITIES** — Buy Futures, Buy Physical
**OPTIONS** — Buy Calls, Sell Calls, Buy Puts, Sell Puts, Advanced Options…

Two things worth noticing. There is no Sell Stock and no Short Stock anywhere in this menu: selling lives on the Holdings tab, beside the position you are selling, which is the right place for it. And **Sell Calls** and **Sell Puts** are green, like the buys. That is not an inconsistency — selling an option does not dispose of something you own, it opens a new position and pays you a premium. So green means *this adds a position to your book*, not *this makes you money*.

Long and short government bonds are listed separately, which is a real distinction and not decoration: a short bill barely moves when interest rates change, a long bond swings hard.

### Corporate

The panel from the earlier screenshot, unchanged: LEADERSHIP, STRATEGY, M&A, ASSETS, AUTOPILOT.

### Finance

Three columns, four groups:

**DEBT** — Borrow Money, Repay Loan, Trade T-Bills
**BANKING** — Change Bank, Advance Funds
**SWAPS** — Interest Rate Swaps
**TAXES** — Prepay Taxes

**Change Bank** is the second chooser in this design hunt, sitting in the same family as Change Law Firm and the two Autopilot toggles. And **Advances**, the tab, is dimmed in these screenshots — correctly, because the player is Independent and has no employer to advance against. That is the dimmed rule working as designed: the control stays visible so you learn it exists, and stays dimmed so you learn why it does not apply to you yet.

### The colour grammar, revised

My first reading was too simple, and these three screenshots correct it. The rule that holds across all thirty-odd items is:

**Green** — adds a position, or moves money into something you now hold. Buy stock, buy a bond, borrow money, contribute capital, prepay tax.

**Red** — gives something up. Fire management, sell corporate assets, and by the same logic a short sale, which creates a liability rather than acquiring an asset. (No short sale appears in these screenshots, so that last one is my inference rather than something I have seen.)

**Amber** — sets a value. A dial, not a transaction. Set Productivity, Set Growth Rate.

**Cyan** — opens a chooser, a further list, or flips a switch. Change Bank, Change Law Firm, Advanced Options, Toggle Autopilot. Nothing is spent and nothing is gained.

**Dimmed** — cannot be done now, for a reason about your situation rather than a fault. Advances without an employer, Restructure on a company that forbids it.

**Plain grey capitals** — group headings, never actions.

The rule I would enforce in a test: an item's colour must follow from what the action does, not from what somebody typed beside it. Two items in the same list that do the same kind of thing must wear the same colour, or the grammar teaches the player something false.

---

## What belongs inside each of the seven tabs

This is the part you asked me to decide rather than show you. Each tab is a different question about the same player, and I have kept them from overlapping: money over time, money this quarter, money not yet earned, what you hold, what you control, what the world is doing, and finding a thing.

**Overview** — the page in your fourth screenshot, as drawn. Net worth in three figures with verdict dots, the net worth history chart, borrowing, personal profile, advisory summary. Nothing added.

**Financials** — your own accounts, laid out the way an accountant would. Income first: salary, dividends, interest received, gains you actually realised. Then outgoings: interest paid, tax, upkeep, living costs. Then the balance sheet — assets by class, liabilities by class, net worth at the foot. Every line against the last four quarters so the trend is visible rather than inferred, and a tax block at the bottom showing what has been assessed, what has been prepaid, and what is still due.

**Advances** — money drawn against income you have not earned yet. Dimmed when there is no employer, open when there is. It shows the ceiling as a multiple of salary, the rate, what comes out of each pay packet, what it does to your credit rating, and one button to take it or pay it back.

**Holdings** — everything you own, one row to a position: name, type, quantity, what it cost, the price now, the market value, the gain or loss, today's move, and its share of the whole. Grouped by stocks, corporate bonds, government bonds, commodities, options and property. Sortable on every column, with a bar showing how the money splits between the classes. The sell and short actions live here, beside the thing being sold, rather than in the Trade menu.

**My Corporations** — every company you control, one row each: name and code, the share you own, its price, what your stake is worth, its profit, its credit rating, whether its autopilot is on, and whether anything is waiting on your decision. A row opens that company's page.

**Market** — the world's state in one place: every share with price, move, volume and sector; the index; each sector's performance; the biggest risers and fallers; government yields; commodities. Plus the offers, votes and takeover bids that need an answer from you.

**Search** — free text across everything at once: a company, a person, a news story, a page, an order you placed last year. The same engine as the command line, given a page of its own.

---

## Prepay Taxes, and why a player would ever

This is the one item in your menus that cannot be left as a single green line. As drawn, it takes money out of your account early and returns nothing — no rational player would click it, and a game that offers an option nobody should take has taught the player something true but useless.

You have told me the benefit should be real, and to think like a treasury desk rather than a tax office. Here is what a bank would say about it, and what I intend to build.

**A discount for paying early.** The revenue service would rather have the money now than at the year end. Prepaying the whole assessed bill in the first quarter earns a settlement discount — call it three per cent. On its own that makes prepayment profitable whenever you have cash spare.

**No year-end shock.** The commonest way to die in a game like this is a large bill landing in a quarter when you are illiquid. Prepayment trades one big uncertain outflow for a series of small ones you chose yourself. That is the whole of treasury management and it is worth more than the discount.

**Interest on the credit balance.** Overpay and the balance sits with the tax authority earning a modest, safe rate, refundable on request. It becomes a place to park cash that cannot fall in value — which matters a great deal in a world where the share price of the company you work for can halve.

**A better credit rating, and therefore cheaper borrowing.** Compliance history is one of the inputs to your rating, and your rating sets the rate on every loan you take for the rest of the game. This is the benefit that compounds and the reason a sophisticated player prepays even with cash they could otherwise invest.

**A hedge against a tax rise.** The economy can raise rates mid-year. A prepayment made at the old rate is honoured, so prepaying is a one-way bet on fiscal policy.

**Less chance of an audit.** An audit costs fees, a quarter of your time, and often penalties. Prepayment buys a lower chance of being looked at.

**And the credit balance can be pledged.** A tax credit is an asset the revenue service owes you, and a bank will lend against it. This is the sharpest of the seven: it lets a player who has prepaid borrow more than one who has not, on the same income. It is exactly the kind of thing a treasury desk does with a receivable, and it is the reason to prepay even in a year you expect to be short of cash.

The cost, so that it stays a decision rather than free money: the cash is locked, a refund takes a quarter to come back, and prepaying more than you owe strands capital that would have earned more in the market. It should be obviously right when you are liquid and obviously wrong when you are not — and if it is ever obviously right all the time, I have built it wrong.

---

## What this build already has

This is the register that matters most to you. Every control in your three screenshots, what it must do, and whether the game can already do it. "Partial" means something like it exists in a different place, or exists for the player but not for a company.

| Control | What it must do | Today |
| --- | --- | --- |
| About | Explains the game | No game-level About page |
| Change Law Firm | Chooses the firm that defends the company | No law firm in the game at all |
| Toggle Global Autopilot | Lets every company you control run itself | No autopilot anywhere |
| Cheats | Alters the world by hand | Only a test-world fast-forward, shown as a pill on the top bar |
| INSURANCE | Unknown — see the question above | No insurance as a player action |
| Player | Profile, look, sound, sign out | Built: the menu behind your picture |
| Viewing: AZA GROUP | A trail back through what is open | No breadcrumb anywhere |
| Candlestick price history | Open, high, low, close per period | Line chart only |
| Leadership: CEO | Names the person running it | Not on the page; the game has CEOs elsewhere |
| Leadership: Reputation | A banded verdict on them | No reputation shown anywhere |
| View Research Report | Opens a written report | No research report exists |
| Analyst Summary, six dotted readings | Six judgements, each with a good/neutral/bad dot | Credit rating exists; the multiples exist on the banker's desk; no combined panel and no dots |
| Company Information grid | Twelve facts in one box | All twelve exist, spread over three tabs |
| Advisory Summary | Written judgement of the company | Nothing |
| Elect as CEO | Puts your person in charge | No |
| Fire Management | Removes the team, costs money and standing | No |
| Set Productivity | Dials how hard the company works | The idea exists in the CEO objectives; no control |
| Set Growth Rate | Dials the company's target growth | No control |
| Rebrand | Renames and restyles for a fee | Built for your own firm only |
| Restructure | Reorganises once, for a fee | Exists inside the dealmaking screens |
| Merger | Joins two companies | Built |
| Startup | Founds a new company | Built |
| Capital Contribution | Puts your own money in | No |
| Buy Corporate Assets | Buys property a company uses | Property exists for you, not for companies |
| Sell Corporate Assets | Sells it, at a discount | No |
| Offer to Sell Subsidiary Stock | Floats part of a subsidiary | Named in one objectives file and nowhere else |
| Browse For Sale Items | What is on offer | Auctions exist, for property |
| Toggle Company Autopilot | This company runs itself | No |
| Toggle Global Autopilot | All of them do | No |
| Fullscreen | Fills the screen | No |
| Help | Explains how the game works | No help screen |
| The lightbulb | Tips and hints | No |
| About | The game's credits and rules | No game-level About page |
| The menu button | Opens the section list | A list of build screens exists; a rail menu does not |
| My Corps | A shortcut to the companies you control | The empire pages cover this; nothing in the strip |
| Viewing: chooser | Says what you are looking at, and switches it | No such control |
| Command line on the page | Typing a page, a code or an action | Built, but only behind Ctrl-K in the top bar |
| Date, play, speed, step | Drives time forward | The date is built and sits on the tape row (9 November); the transport has no server endpoint, so it is not built |
| Player net worth history chart | Your money over time | An empire's history is charted; the player's is not |
| Net worth: assets, debt, worth, with dots | Three figures and a verdict | The desk shows cash and standing, not these three |
| Borrowing: rate, unused credit, debt/equity, gains | Your borrowing state in four figures | A loans page exists; not these four in one box |
| Personal profile: name, country, status, bank, rating, trend | Your identity and standing | A profile page exists; a credit rating *for you* is not built |
| Advisory summary: your finances and your tax | Prose judgement of you | Nothing; a tax bill for the player is not a thing |
| Market indicators with bars | An always-on market readout | The economy page has indicators; not always-on, and no bars |
| Quotes and News tabs in the rail | Watchlist and headlines always visible | A news page exists; not in a rail |
| Buy Stock | Buys a share | Built |
| Buy Corp Bond | Buys a company's bond | Partial — company bonds sit in the book, but there is no market to buy them on |
| Buy Long Govt Bonds | Buys long-dated government debt | Built |
| Buy Short Govt Bonds | Buys short-dated | Built |
| Buy Futures | Buys a forward contract | Built |
| Buy Physical | Buys the commodity itself | No |
| Buy and Sell Calls and Puts | Options, bought and written | Built |
| Advanced Options… | The further strategies | Partial |
| Borrow Money | Takes a loan | Built |
| Repay Loan | Pays it back | Built |
| Trade T-Bills | Trades short government paper | Partial — government bonds yes, bills no |
| Change Bank | Chooses your lending bank | Yes — six banks, one move a quarter, at `PUT /api/career/bank`. This row said "No" until 9 November and was wrong |
| Advance Funds | Draws against income not yet earned | No |
| Interest Rate Swaps | Swaps a fixed rate for a floating one | Built |
| Prepay Taxes | Pays early, and gains by it | No — the player has no tax bill to prepay |
| The seven tabs | Overview, Financials, Advances, Holdings, My Corporations, Market, Search | Overview exists in some form; the middle four do not; Market and Search are pages, not tabs |

Counting the register: about a third of the controls work, a third exist in some other shape, and the rest have nothing behind them at all — the law firm, both autopilots, cheats, insurance, capital contribution, corporate assets, subsidiary stock, the research report, the transport controls, the always-on rail, physical commodities, T-bills, advances, and everything about the player's own finances that your fourth screenshot shows. (Changing your bank was in this list until 9 November; it is built, and that was my error, not the game's.)

Those last eight are not menus to style. Each is a set of rules about money and consequence, and each needs its own proposal before it is built. You have told me to make them fully simulated, so I will write each one up, tell you what it will cost a player and what it will cost you in work, and wait for your yes — the working rules do not let me start without it.

## Decisions

**Settled by your fourth screenshot:** the **panel bars stay** — purple to indigo, title in white, running the full width. I had asked whether the company page's plainer headings meant the bars should go. They do not. **About** is the game's own credits and rules, sitting as it does beside Help and Fullscreen rather than beside the company's name.

**Settled by you, 7 November:**

- **The game counts in naira, at naira scale.** Your screenshots' half-billion figures are the reference's, not the target. The look carries over; the magnitudes do not. The game's existing habit of compacting large sums with a suffix stays, because a naira balance with eleven digits on it is unreadable at 13 pixels.
- **My Corps is dropped.** Nothing in the strip on that account.
- **INSURANCE becomes a menu of its own**, in the middle group with the law firm and the two autopilots. What it sells is worked out below.

**Two judgement calls you left to me:**

**Market indicator labels are never truncated.** A label cut to "St…" or "O." is a label the player cannot read, and a panel of unreadable labels is worse than a panel with fewer items on it. The fix is not to widen the column but to give each figure a true short name — Gold, Brent, Cocoa, Sesame for the commodities; Policy rate, Inflation, Confidence, Jobs for the macro lines — all of which fit two across at 13 pixels without being cut. Where a name still will not fit, the value wraps beneath it rather than the name losing letters. Nothing in the panel is ever abbreviated to a letter.

**The net worth chart is filled under the line, conventionally.** Your screenshot fills above it. Every other chart in the game — the empire's net worth, the share price history, the results — fills downward from the line, and one chart in the whole game filling the other way reads as a fault rather than a choice. It also makes the chart lie: filling above the line visually puts the colour where the money *is not*.

---

## INSURANCE: what it should be

You asked me to suggest, so here is the proposal. It follows the same logic as prepaying tax — insurance is not a purchase, it is the price of certainty — and it is built so it cannot be used to cheat.

**Where it lives.** A menu in the middle group of the strip, beside Change Law Firm and the two Autopilot switches, because it is a setting about your whole position rather than a page about one company. Its items wear the grammar: **Buy a policy** green, **Cancel a policy** red, **Review your cover** and **Claim** cyan.

**What it sells.** Four policies, each aimed at a loss the game can already inflict:

*Property and premises.* Fire, flood, riot and forced closure on the buildings you own. Premium by district and by building type; a claim pays the repair less an excess. This is the policy most players will want first, because property is where the game's largest single losses sit.

*Directors' and officers'.* Covers you when a company whose board you sit on is sued — the court module already does this. Premium rises with the number of boards you sit on and with how litigious the sector is. It is the policy that makes running companies survivable.

*Income protection.* Pays a share of your salary for a set number of quarters after you lose your job, and covers the gap while you look for the next. Cheap while employed, unavailable once you are not.

*Personal umbrella.* Covers claims against you personally that fall outside the other three. Priced as a top-up above a limit you choose.

**How it is priced.** Premium is the expected loss plus a loading — not a random number. That means a player can work out that insurance is a losing bet in the long run and still buy it, because it is the difference between a loss that hurts and a loss that ends the game. That is exactly how insurance works in life and it is the only honest way to price it.

**The no-claims record.** Every year without a claim cuts the premium. A claim resets it. This turns four static policies into a relationship you carry, and it gives the player a reason to hold cover through a quiet stretch rather than cancelling it the month after a false alarm.

**Why you would buy it even though it loses money.** The same reason a treasury desk prepays tax: an insured balance sheet is a cheaper balance sheet. Insured assets improve your credit rating, and your credit rating sets the rate on every loan in the game for the rest of it. So cover that never pays out still earns its premium back through cheaper borrowing. That is the compounding benefit, and it is the one that makes insurance a decision rather than a tax on the timid.

**The loophole, stated plainly.** The obvious cheat is to insure something and then arrange for it to be lost — burn the building, sink the ship, provoke the lawsuit. So the game must assume players will try exactly that. A claim is investigated; where the loss was caused by the player, the claim is refused, the premium is kept, the incident becomes a court matter, and the reputation takes the damage. A second attempt ends the policy permanently and no insurer will write another. Under working rule 3 this needs an automated test per attack and a second AI told to break it, before the feature is called done.

## What happens next

Five screenshots are catalogued and the open questions are closed. The document is now a specification rather than a wish list: every screen you have shown me is written down, every control is registered against what the build can already do, and the things that have no engine behind them are named.

What remains is the build order. It is not one job — it is roughly these, in an order I would argue for:

1. **The frame.** The strip, the tape row with its date and transport, the always-on left column, the three verb buttons with their menus and the colour grammar, the command line on the page. Almost everything else sits inside this, so it goes first or it gets built twice.
2. **The player's page.** Seven tabs, the five panels on Overview, the Accounts and Advances tabs built from scratch, the advisory copy.
3. **The company page.** Candles, the Leadership column, the analyst summary with its dots, the information grid, the research report.
4. **The four subsystems, each with its own proposal:** law firm, autopilot, cheats, insurance. Autopilot and cheats get a loophole check before they are called done.
5. **The three missing markets:** corporate bonds, T-bills, physical commodities.

Keep any further screenshots coming and I will add them as they arrive; anything sent before the build starts costs nothing to fold in. Say the word when the set is complete and I will bring the checklist for step one.
