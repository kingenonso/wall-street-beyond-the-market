# Stage 1: Foundation

**Test from the design:** a player can sign up, log in and see Lagos time and
whether the market is open. **Status: passes.**

## What was built

| Piece | Where | What it does |
| --- | --- | --- |
| World clock | `simulation/clock.py` | Works out Lagos time, whether the exchange is open, and the game-calendar date |
| Players table | `database/migrations/001_players.sql` | Stores each player |
| Accounts | `server/main.py`, `server/security.py` | Sign-up, login, logout, "who am I" |
| Website | `web/src` | Sign-up and login page; home page with the top bar and clock |

## Rules it enforces

- **Market hours** (design section 5): opening auction 11:30 to 12:00, open 12:00
  to 22:00, closed otherwise. Lagos time, every day, the same for every player.
- **Game calendar** (section 5): one real week is one game quarter; four real
  weeks are one game year. A quarter has 90 game days.
- **Adults only** (section 2): sign-up asks for a date of birth, refuses anyone
  under 18, and keeps only the fact that the check passed, not the birthday.
- **Starting position** (section 10): ₦500,000 cash and a reputation of 50.
- **The server decides** (section 19): the time on screen comes from the server,
  never from the player's device.

## Security choices

- Passwords are stored scrambled (Argon2), never as written.
- The login pass is kept in a cookie that page scripts cannot read.
- A wrong email and a wrong password give the same answer, so the login form
  cannot be used to discover who has an account.
- Secrets come from the `.env` file, never from the code.

## Known stand-ins, to be replaced

| Stand-in | Replaced in | Why |
| --- | --- | --- |
| Starting cash is a single number on the player's row | Stage 2 | The ledger will own all money, and every naira will have a recorded payer |
| No limit on repeated login attempts | Stage 16 | Part of the security review |
| Email addresses are not verified by sending a message | Stage 16 | Needs an email service, which the owner must approve |

## Tests

37 server tests (`tests/`) and 4 website tests (`web/src/format.test.ts`).
