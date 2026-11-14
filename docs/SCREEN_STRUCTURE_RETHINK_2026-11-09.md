# Screen Structure Rethink: One Screen at a Time (November 2026)

This document rethinks how screens are structured across the game, moving from the current fragmented approach to a unified, consistent screen architecture. The goal is: one consistent screen pattern that every screen follows, so players learn one interface and apply it everywhere.

---

## The Core Problem

The game currently has **multiple screen architectures operating simultaneously**:

- **Company pages**: Left column + right-side panels (Overview)
- **Player page**: Left column + work area with verbs + tabs + four panels
- **Top strip**: Different implementations across screens
- **Command menus**: Three verbs (Trade/Corporate/Finance) but with inconsistent coloring and structure
- **No consistent "frame"**: Each screen builds its own surrounding UI

This means every new screen requires custom UI work, and players must re-learn the interface on each new page.

---

## The Unified Screen Architecture

Every screen in the game should follow this single pattern, from the simplest dialog to the most complex company page:

### Layer 1: The Top Strip (Always present)

A consistent bar across the top of every screen, reading left-to-right:

```
[Menu Button] [Fullscreen] [Lightbulb/Help] [About]
              |
        [Change Law Firm] [Toggle Global Autopilot] [Cheats]
              |
        [My Corps] [Viewing: <name> chooser]
```

**What this strip always does:**

| Element | Function | Consistent Behavior |
|---------|----------|---------------------|
| **Menu button** | Opens the three verb menu (Trade/Corporate/Finance) | Always opens the same menu, context-sensitive to what's being viewed |
| **Fullscreen** | Toggles fullscreen mode | Standard toggle |
| **Lightbulb/Help** | Shows tips or context-sensitive help | Always help, never varies |
| **About** | Game credits/rules or company-specific info | About sits at the right edge of navigation; company About is separate |
| **Change Law Firm** | Switches the defending law firm | World-switch, always present |
| **Toggle Global Autopilot** | Enables/disables autopilot for all companies | World-switch, always present |
| **Cheats** | Enables/disables cheat modes | World-switch, always present |
| **My Corps** | Dropdown of all companies the player owns | Always at the right end |
| **Viewing:** chooser | Changes what the player is looking at (company, own page, etc.) | Always present, always a dropdown |

**Critical design rule**: The three world-switches (Law Firm, Autopilot, Cheats) sit **away from the navigation** on purpose. Their separation from the menu button/About/My Corps group tells the player: "These are not pages, these are world settings." This visual grouping is doing informational work.

---

### Layer 2: The Left Column (Always present, takes ~30% width)

A vertical column running the full screen height, containing **three stacked panels**. This column **never moves** — it stays visible no matter which screen the player is on. Each panel presents the current context:

**Panel 1: Net Worth History**
- Filled chart of money over time
- Titled inside the plot area with player name and unit (naira)
- Value scale down the right edge
- Faint gridlines
- Months along the foot
- **Convention**: fill under the line (unless deliberately inverted)

**Panel 2: Market Indicators**
- Three groups, arranged in two items across:
  - COMMODITIES & INDEXES
  - CRYPTO  
  - MACROECONOMIC
- Each group: label, value, arrow (up/down), percentage, horizontal bar in green/red showing move size
- **Critical**: labels must have room to be readable — not truncated to "St…", "O.", etc.
- **Option A**: One item per row (more space, taller column)
- **Option B**: Shorter true names with room to read

**Panel 3: Quotes and News**
- Two tabs at the foot: **Overview** and **News**
- **News tab**: search field (comma-separated terms), "My News" filter, scrolling list of headlines
- Headline coloring: the player's company name and the action it took are picked out in colour
- **Search**: takes several terms separated by commas

**Why three panels?**
- Panels 1 and 2 are always present (net worth + market readout)
- Panel 3 switches between Overview/News based on what the player needs
- Three panels give a natural width: ~30% of screen, leaving ~70% for the work area
- Stacking them vertically means the column height always matches the work area

---

### Layer 3: The Work Area ( Takes ~70% width)

The right side of the screen, containing everything that varies by screen context:

#### 3a: The Command Line (Always at the top of work area)

One line reading:
```
<player name>  [Trade ▼] [Corporate ▼] [Finance ▼]  Enter command…
```

With a **?** button at the left of the command field.

**The three verbs are always present** and always carry:
- **Trade** — green with a checklist icon
- **Corporate** — blue with a building icon
- **Finance** — orange with a banker icon

**Color grammar (consistent across all screens)**:
- **Green** — adds a position, or moves money into something you now hold. Buy stock, buy a bond, borrow money, contribute capital, prepay tax.
- **Red** — gives something up. Fire management, sell corporate assets.
- **Amber** — sets a number. Changes a dial, no money moves.
- **Dimmed** — not now. Control stays visible so you learn it exists; stays dimmed so you learn why it doesn't apply.
- **Neutral** (default text color) — browses or toggles. Opens a list, or flips a switch back and forth. Nothing is spent and nothing is gained.

**The command field** is the game's command line, sitting in plain sight rather than hidden behind keyboard shortcuts.

#### 3b: The Tabs (Below the command line)

Built as boxes with rounded tops. Always the same set of tabs, though different screens show different tabs as active:

```
Overview  Financials  Advances  Holdings  My Corporations  Market  Search
```

**Tab semantics (consistent across all screens)**:
- **Overview**: The default "about this page" view
- **Financials**: Financial statements, ratios, performance
- **Advances**: borrowing, loans, credit lines
- **Holdings**: What you own, positions, quantities
- **My Corporations**: Your empire's companies
- **Market**: Broad market data, indices, commodities
- **Search**: Find companies, deals, players

**The open tab is always lit**; inactive tabs are in ordinary text color.

#### 3c: The Panels (Fill the remaining work area)

Below the tabs, four panels stacked, presenting the screen's data. **Not all panels are always visible** — visibility depends on screen context, but when a panel is present, its structure is consistent:

**Panel 1: Net Worth** (always present when player page)
- Three figures side by side, each with a colored dot
- Total assets (green dot)
- Total debt (red dot)
- Net worth (amber/or dot)

**Panel 2: Borrowing** (present when relevant)
- Borrowing rate
- Unused line of credit
- Debt-to-equity ratio
- Capital gains realised so far this year

**Panel 3: Personal Profile** (always present on player page)
- Name, country, employment status
- Lending bank as a blue link
- Credit rating
- Net worth trend (sparkline or summary)

**Panel 4: Advisory Summary** (always present)
- Two paragraphs with bold capital lead-ins
- *"Your financial situation:"* and *"Your tax situation:"*
- Tax situation computes a projected tax bill for the whole year from what you hold today
- **Same idea as company Advisory Summary**: the game saying, in words, what it thinks of you

---

### Layer 4: Screen-Specific Content

Layers 1-3 provide the **frame** that never changes. Layer 4 is what varies per screen:

| Screen Type | Panel 1 Content | Panel 2 Content | Panel 3/4 Content |
|-------------|-----------------|-----------------|-------------------|
| **Company Overview** | Leadership panel (CEO + reputation) | Analyst Summary (6 dots: P/E, dividend yield, book value, credit rating, analyst rating, cash flow) | Company Information (12 facts in 2-column grid) + Advisory Summary (company judgement) |
| **Company Trade** | Trade sub-menu panel (Stocks, Bonds, Commodities, Options) | Corporate sub-menu panel (Leadership, Strategy, M&A, Assets, Autopilot) | Finance sub-menu panel (Debt, Banking, Swaps, Taxes) |
| **Player Own Page** | Net Worth History | Market Indicators | Quotes and News tabs |
| **Dialog/Message Box** | Dismiss button only | — | Colored prose message + OK button |

**Key invariant**: Screens 1-3 (the frame) are **always present**. Screen 4 (content) varies. This means players always know where to look: the left column shows net worth/market, the work area has the command line and tabs, and the panels show context-specific data.

---

### Layer 5: Dialogs and Message Boxes

When a screen needs to present a decision or announcement, a modal dialog appears **on top of** the regular screen structure.

**Dialog types** (all consistent):

| Type | Appearance | Buttons | Purpose |
|------|-----------|---------|---------|
| **Announcement** | Rounded dark card over dimmed page | **OK** (green, bottom right) | Tells something happened; player acknowledges and carries on |
| **Decision** | Rounded dark card over dimmed page | Multiple choices (green/red/amber) | Player makes a choice that affects game state |
| **Yes/No** | Rounded dark card over dimmed page | **Yes**, **No** | Binary choice |
| **Input** | Rounded dark card with form fields | **OK**, **Cancel** | Player enters data |

**Critical rule**: Dialogs built to **take decisions** are different from dialogs that **announce things**. The game has dialogs built for decisions (e.g., "Fire management? Yes/No"). It needs a second kind: the announcement that stops you, tells you what just happened, and lets you carry on. The announcement dialog has only an **OK** button.

---

## Integration with Existing Code

The server already has route handlers and schemas for many of these elements. The screen structure rethink doesn't require rewriting existing code — it provides a **design framework** that new code should follow.

**Existing elements that fit the new structure**:

- **Top strip**: Already present in main.py routes and schemas; just needs consistent ordering
- **Left column panels**: The server already renders net worth, market indicators; just needs consistent panel ordering
- **Command menu (Trade/Corporate/Finance)**: Already in server code; color grammar needs to be enforced in tests
- **Tabs (Overview/Financials/Advances/Holdings/My Corporations/Market/Search)**: Already in schemas; just needs consistent active-inactive styling
- **Four panels (Net Worth/Borrowing/Personal Profile/Advisory Summary)**: Server has some of these; standardize what's always present
- **Color grammar**: Already partially in server code (route handlers set colors); formalize in a design doc

**What needs to change in code**:

1. **Consistent panel ordering** in all screen renderers — always Net Worth, Borrowing, Personal Profile, Advisory Summary (in that order when present)
2. **Consistent tab styling** — active tab lit, inactive in default text color
3. **Color grammar enforcement** in route handlers and test expectations
4. **Dialog type distinction** — announcements vs. decisions get different button sets
5. **Left column panel stacking** — always three panels in consistent order

---

## Migration Plan

**Phase 1**: Document the screen structure (this doc). No code changes yet.

**Phase 2**: Update the reference spec (REFERENCE_SPEC_2026-11-07.md) to include this screen structure as the "build order" checkpoint. Mark which existing screens conform and which need updating.

**Phase 3**: Update the server's screen renderers to follow the new consistent structure. Start with the player page (most complex), then company pages, then dialogs.

**Phase 4**: Update all test expectations to match the new consistent screen structure. This is the critical step — without updated tests, code changes will break things.

**Phase 5**: Refactor any screen-specific code that violates the new structure. This includes removing duplicate UI code, consolidating panel renderers, etc.

---

## Why This Works

1. **One screen to learn**: Players learn the frame once and apply it everywhere. The only thing that changes is the content in panels 4.

2. **Design changes are localized**: If you want to move the net worth history to the right column, you change one renderer, not every screen.

3. **New screens are cheaper**: A new screen just needs its Layer 4 content; Layers 1-3 are reused from the framework.

4. **The frame does instructional work**: The consistent placement of world-switches, the color grammar of menus, the panel ordering — all of these teach the player how the game works without them having to read a manual.

5. **Backward compatible**: Existing screens can be updated incrementally. You don't have to rebuild everything at once.

---

*This document was generated as part of task #34: Rethink the screen structures to the terminal, one screen at a time. It redefines the unified screen architecture that all future screens should follow, with consistent layers (top strip, left column, work area, dialogs) and consistent behaviors (color grammar, panel ordering, tab styling).*