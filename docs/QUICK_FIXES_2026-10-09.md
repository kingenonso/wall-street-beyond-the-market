# Quick fixes, 9 October 2026

Six changes the owner asked for after the private equity stage. You approved them on 8 October and said "build" on 9 October.

Tests at the end:
- **978 on the server.** 28 of them are new:
  - 13 in `tests/test_quick_fixes.py`
  - 10 in `tests/test_quick_fixes_loopholes.py`
  - 5 in `tests/test_quick_fixes_review.py`
- 13 on the order-matching engine.
- 14 on the website. 2 of these are new, in `web/src/messages.test.ts`.

All of them pass.

## Checklist

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| 1 | A "Trade for: Me / My empire" switch on every trading screen | Yes, on both trading screens: a company's share panel and the bond desk. You only see the switch if you can trade for your empire, meaning you are its Asset Manager or its head. With "My empire" picked, the panel shows the empire's cash, your limit for the quarter, and what the empire holds. Orders go through the empire's own routes. If the empire can't be traded for at that moment, nothing is sent, so your own money is never spent by mistake | `test_q9_...`; screenshots 01 and 02 |
| 2 | Legal Counsel's colour changes from red to silver | Yes | `tests/test_builds.py`; screenshot 03 |
| 3 | Quiet news pop-ups for every story | Yes. Each new story appears as a short headline in the bottom corner. It has no sound and fades after 7 seconds. It stays while your mouse or keyboard is on it. It shows at most three stories at a time, plus "and N more". Tapping it opens the News page. You can mute it from the pop-up itself or from the menu under your picture | `test_news_alerts_...` (2 tests), `test_q6_...`; screenshot 04 |
| 4 | Player-to-player messages, with blocking, report-abuse and rate limits | Yes. You write to a player by their display name. You can block, unblock, report a message (and block the sender at the same time), and clear a conversation from your own list. The limits are below | 6 tests in `test_quick_fixes.py`, loophole questions 1 to 5 and 10, review tests; screenshots 06 and 08 |
| 5 | Rank leaves the left menu and moves under the profile picture, with a dot when a rank case is waiting | Yes. Tapping your picture opens a small menu: Profile, Rank, Messages, the news pop-ups switch, and Log out. A dot on the picture means a rank case can be begun or is in hand, including the CEO case, or that a message is unread. Profile and Rank have left the left-hand menu | `test_the_dot_shows_...`, `test_r10_...`; screenshots 05 and 09 |
| 6 | Early retirement | Yes. It opens after 20 quarters of work or at Level 35, whichever comes first. It pays 1.5% of your savings each quarter, and that rate is fixed for good. Full retirement stays at 40 quarters or Level 50, paying 2.5%. Anyone who already qualifies for the full pension is pointed to it, because it pays more | 3 retirement tests, `test_q8_...`; screenshot 07 |

## The message limits

To keep things calm:
- **Messages an hour:** at most 30.
- **New people a day:** at most 10 players you have never written to before.
- **Unanswered messages:** at most 3 in a row to someone who hasn't answered yet.
- **Length:** a message can be up to 1,000 characters.
- **Hidden characters:** removed. These are invisible characters and ones that reverse the direction of text.

Reports have a consequence. If three different players report the same sender within a week, that sender can only answer people who wrote to them first, until the week is up.

## Decisions I made that you did not specify

- **A block is never revealed.** The blocked player can still write, and nothing tells them they are blocked. Their messages simply never arrive. This is how the large messaging apps handle it, and it stops a blocked player from working out who blocked them.
- **You can report a message only once, and only if it was sent to you.** The player you report is never told.
- **The first look at the news shows no pop-ups.** When you log in, you are not flooded with every past story. Pop-ups start with the next new one.
- **Clearing a conversation** removes it from your own list only. The other player keeps their copy.
- **The bond desk switch covers buying and selling.** Swapping a convertible bond for shares stays a personal action, because the empire has no route for it.
- **"Messages" went into the profile menu too**, with its unread count, since that is where the dot points.

## The loophole check

Ten questions, with one test each, in `tests/test_quick_fixes_loopholes.py`:

1. Can a player read a conversation they are not in? No.
2. Can a player find out who blocked or reported them? No.
3. Can a message be sent as somebody else, or with its own time, reader or state? No.
4. Can a message, a block or a report move money or anything else of value? No. The money in the world and the ledger don't change.
5. Can two sends at the same moment both slip under a limit? No. One goes through and the other is refused.
6. Can a pop-up show a story before its day? No, not even with a made-up marker of how far you have read.
7. Can a player change another player's settings, or begin someone else's pension? No.
8. Can a player take the early pension, then switch to the full one or choose their own rate? No. The database also refuses any rate outside the allowed range.
9. Can the "My empire" switch let a member who may not trade for the empire use its money? No. Only an Asset Manager or the head can.
10. Can a player put a dot or a count on someone's screen that can't be cleared, or slip hidden characters into a message? No.

## The independent review

A second reviewer, who did not write the code, found 11 problems. All of them are fixed.

The most serious was that a block could be worked out. A blocked player's message box was swapped for "messages cannot pass between you", which told them they had been blocked. Blocking is now silent, as described above.

The others:
- Opening a conversation could mark a message as read when it had arrived a moment after the page was shown.
- An empire order held for the Risk Manager's approval was reported as placed.
- If the empire briefly couldn't be read, the "My empire" switch could fall back to trading with your own money.
- A failed send wiped what you had typed.
- The unread count in the conversation list disagreed with the dot after a block.
- "At the best price now" stayed selected after switching to an empire the computer runs, where only a named price is allowed.
- A broken message link could blank the page.
- The menu and the pop-up needed better keyboard and screen-reader behaviour.
- The dot ignored the CEO case.
- Some loophole tests had weak checks.

The server-side fixes each have a test in `tests/test_quick_fixes_review.py`. The website-side fixes were checked in the browser run, and the broken-link fix also has a website test.

## Honest limits

- **Nobody acts on reports yet.** They are stored, and the automatic one-week limit applies. A moderator's screen to read them belongs with the moderation and safety work in Stage 16.
- **Some stories may never pop up.** If a story is filed for an earlier day after you have already looked past that day, it won't appear as a pop-up. This can happen at a late quarter close. It is still on the News page.
- **The news pop-ups and the dot are checked once a minute.** They are not instant.
- **On a phone, the left-hand menu row still leaves a gap.** This was there before these fixes. The front-end redesign stage will deal with the layout.

## Screenshots

These are in `docs/screenshots/quickfixes/`:
- 01: the share panel trading for the empire.
- 02: the bond desk trading for the empire.
- 03: Legal Counsel in silver.
- 04: a news pop-up.
- 05: the profile menu, with a rank case waiting and a message unread.
- 06: a conversation, with the report box open.
- 07: the full and early pensions on the career page.
- 08: messages on a phone.
- 09: the menu on a phone.

## Run it

```powershell
cd $HOME\wall-street-beyond-the-market
git pull
docker compose up --build
```

You don't need a fresh world. The new tables and settings are added to the world you already have.
