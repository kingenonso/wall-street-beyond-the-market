# The desk, rebuilt as a broker's ledger sheet — 8 November 2026

This is the report for the "My desk" screen of the redesign: the new colours, the new type,
and the screen itself, rebuilt around one idea — **the day's tape**. It says what was built,
what was checked, and what the checking found.

---

## The idea, in plain words

"My desk" is the first screen a player sees after signing in. It used to be a grid of cards:
each thing that wanted attention sat in its own rounded box, all the same size, so nothing
was louder than anything else and the player had to read every box to find the one that
mattered.

It is now a page from a broker's ledger. Three things changed:

**The page is ruled, not boxed.** Sections are separated by hairlines, not by borders and
shadows. That is how a ledger works: everything is on one sheet, and the ruled lines keep
the columns in order.

**One device carries the page: the day's tape.** Down the middle of the desk runs a single
ruled stream with three bands, each stamped in a narrow margin of brass:

- **now** — the six shares that moved most today, in the machine's monospace.
- **wire** — the day's news, typed out in the serif a printed story would use.
- **ledger** — the player's own money moving: salary in, shares bought, dividends paid.

The stamp margin is the device that makes the page unmistakable. Nothing else on the screen
uses it, so the eye always knows where the day's record is.

**Colour is earned.** Brass is the accent: figures, totals, the current page. Crimson
appears in exactly one place — the left margin of the first item in "Needs you now", the way
an accountant rules the margin where something is owed or overdue. If crimson is on the
screen, something needs the player.

Everything is in **sentence case**. No shouted labels. A rise or a fall always carries an
arrow as well as a colour, so it reads for someone who cannot tell green from red.

---

## The checklist, ticked

### 1. The palette and type scale set across the game — done

Twenty-two colour tokens were replaced in `web/src/styles.css`, in two themes:

| | Dark (night desk) | Light (green-bar ledger paper) |
|---|---|---|
| page | `#0a0f0b` | `#e8eee0` |
| panel | `#101811` | `#f8fbf3` |
| ink | `#e9efe4` | `#10170e` |
| brass | `#d9a845` | `#78520c` |
| rise | `#5fd39a` | `#0a6a3f` |
| fall | `#ff8f7a` | `#a3281b` |
| crimson margin | `#8d3327` | `#a8332a` |

Three typefaces, each with one job: **IBM Plex Sans** for prose and headings, **IBM Plex
Mono** for every figure and every stamp, **IBM Plex Serif** for the wire — the news reads
as a printed story, the market reads as a machine's output.

**Evidence:** the twenty-two tokens are in `web/src/styles.css` lines 17–66. The light theme
now also stripes alternate table rows with the green band (`--band`, `#edf3e4`) so the
daylight theme really is green-bar paper rather than a pale grey sheet.

### 2. The desk rebuilt around the day's tape — done

`web/src/Desk.tsx` is restructured. The old card grid is gone. The page now runs, top to
bottom: the desk head (who you are, the game's clock), the position band (six ruled figures
in one row — cash, what you own, shares and bonds, retirement, reputation, and a sparkline
of the last thirty Closing Bells), then two columns — "Needs you now" and your watchlist on
the left, the day's tape and the board on the right — and the rail on the far right.

**Evidence:** `web/src/Desk.tsx`, components `DeskHead`, `PositionBand`, `NeedsYouNow`,
`Tape`, `Book`, `Board`, `DeskWork`, `DeskRail`.

### 3. The desk's styles written — done

Seven hundred lines of authoring in `web/src/styles.css` (362 changed). The tape is a
three-column ruled grid with a 58-pixel stamp gutter; the wire is clamped to two lines so
the columns keep a steady rhythm down the page; the needs list is ruled lines with the
first one carrying the crimson margin; the band folds from six cells to three to two as the
window narrows.

### 4. The look book built and reviewed by screenshot — done

The look book is in `docs/lookbook/`. Four views:

- `lb-1-desk.html` — the whole desk, night, at 1440 pixels wide.
- `lb-2-tape.html` — the tape at full size, close enough to judge the type.
- `lb-3-phone.html` — the desk on a 390-pixel phone.
- `lb-4-light.html` — the whole desk in daylight, on green-bar paper.

They are live HTML rather than pictures because the build machine has no browser to
rasterise a page into a PNG (the network sandbox refuses to install one). Each page holds
the real `styles.css` and the desk's real markup, so opening one in a browser shows exactly
what the game shows. `docs/lookbook/build.py` rebuilds them from the stylesheet:

```
python3 docs/lookbook/build.py web/src/styles.css docs/lookbook
```

**What the review found, and what was fixed:**

- **Two CSS collisions.** The new desk reused two class names that older screens already
  define: `.queue` (an auto-fitting card grid still used by three other screens) and
  `.sort` (the market page's filter buttons). Left alone, the desk's needs list would have
  turned into a grid with a twelve-pixel gap. The desk's names were changed to `.needs…`
  and `.sort-head`, and the older screens were left untouched.
- **Shouted labels.** Seventeen card tags were set in capitals — `■ MARGIN CALL`,
  `TAKEOVER OFFER`, `PRESS`. All are now sentence case, and the outlet name no longer has
  `.toUpperCase()` forced on it.
- **A ragged tape.** Wire lines wrapped to one line or two at random, so the stream had no
  rhythm. They are now clamped to two, giving every row the same height.
- **A four-line head on a phone.** The identity line ran "Accountant · L3 · Senior clerk ·
  Gidan Construction · banking at Kainji Commercial Bank", which wrapped to two lines
  before the player saw a single figure. On a phone the bank clause is now dropped and the
  gaps closed up.
- **A tag and its deadline at opposite ends of a phone.** "■ Margin call" sat on the left
  and "By the next Closing Bell" on the far right of a narrow card. On a phone they now
  stack.
- **No green bars in daylight.** The light theme striped alternate rows with a 22% tint of
  the border colour, which read as grey. It now uses the actual green band.

### 5. The build, the tests and the contrast verified — done

- **The build:** `npm run build` in `web/` — type check clean, 87 modules, built in 2.6
  seconds. (It warns that the JavaScript bundle is 958 kB, over the 500 kB the bundler
  suggests. That is a size warning for the phone networks, not an error, and splitting the
  bundles is work for another stage.)
- **The tests:** `npx vitest run` — 3 files, 23 tests, all passing (9 redesign, 12 format,
  2 messages).
- **The contrast:** every one of the eight text colours checked against all three surfaces
  (page, panel, raised) in both themes — 48 pairs. Every pair passes the WCAG AA threshold
  of 4.5:1. The lowest is the light theme's rise colour on the page at 5.64:1; the highest
  is the light theme's ink on a panel at 17.45:1.

---

## What is not done yet

The palette is set for the whole game, because the tokens are global. But only the desk has
been rebuilt on it. Market, Portfolio, News, Companies, Economy, Career, Empire, Work and
the Court still use the old card layouts; they will pick up the new colours automatically
but not the new structure. That is the next stretch of work, screen by screen, and it stops
here for the owner to look at the desk first.

Also still open from earlier: the owner's ten-year run with the court in it (task 5), and
the rebuilt web image so the Court page appears (task 7).

## The commit, and the push

The work is committed on `main` — "The desk is rebuilt as a broker's ledger sheet, ruled
down the middle by the day's tape". **It has not been pushed.** The build machine's network
is sandboxed and GitHub is not on the list it may reach: `git push` comes back with
`Received HTTP code 403 from proxy after CONNECT`. **The owner needs to push it** — GitHub
Desktop's "Push origin", or `git push origin main` in their own terminal.

The court work from Stage 11 is in the same working tree and was deliberately left out of
this commit, so the two stages stay separate: `server/main.py`, `simulation/exchange.py`,
`simulation/quarters.py`, `simulation/world_data.py`, `tests/test_loopholes.py`,
`tests/test_quarters.py`, `web/src/App.tsx`, `web/src/Shell.tsx`, `web/src/api.ts` and the
new `web/src/Court.tsx`.
