# Wall Street: Beyond the Market

A 2D online game where players work as finance, law and media professionals
inside one shared, living economy. The trial world is Nigeria, in naira.

The full design is the **Master Game Design v23**. See `docs/GAME_DESIGN.md`.

## Where the build stands

The game is built in 16 stages. Each stage is finished only when its test passes.

| Stage | Status |
| --- | --- |
| 1. Foundation: sign-up, login, world clock | **Done** |
| 2. Ledger and companies | **Done** |
| 3. The economy and its people, Part A: households, wages, spending | **Done** |
| 3. Part B: banks, the Central Bank, inflation, the Money Watch, the news wire | Next (not started) |
| 4 to 16 | Not started |

Stage 1 test, from the design: *a player can sign up, log in and see Lagos
time and whether the market is open.* It passes.

Stage 2 test, from the design: *eight game quarters run, every balance sheet
balances, and no naira appears without a recorded payer.* It passes.
See `docs/STAGE_02_LEDGER_AND_COMPANIES.md` for the full report.

Stage 3 Part A report: `docs/STAGE_03A_HOUSEHOLDS_AND_SPENDING.md`.

## What is in each folder

| Folder | Holds | Language |
| --- | --- | --- |
| `web` | The website: every screen the player sees | TypeScript with React |
| `server` | Checks every request and decides every outcome | Python with FastAPI |
| `simulation` | The game's rules and calculations: the clock, the ledger, the companies and their accounts | Python |
| `database` | The database tables, as numbered change files | SQL |
| `tests` | Automated checks that the rules work | Python |
| `docs` | The design and a note on each finished stage | |

## Run it on your computer

You need one program installed: **Docker Desktop** (https://www.docker.com/products/docker-desktop).
Docker runs the database, the server and the website together, the same way on any computer.

```
cp .env.example .env
docker compose up --build
```

Then open http://localhost:5173 in your browser.

The first command makes your private settings file. The second builds and starts
everything; the first run takes a few minutes. Press Ctrl+C to stop.

Before the second command, open `.env` and replace the `SECRET_KEY` line with
your own long random text. The server refuses to start with the example value.

Creating an account takes two steps: fill in the form, then type in a 6-digit
code. On a real website the code is emailed to you. On your own computer no
email service is connected, so the code is shown on the screen instead.

On the first run the game world is created: the Central Bank, the Government,
the 50 companies and their opening accounts. It is created **once**. The
`WORLD_START` date in `.env` is read only at that moment; the example value is
eight weeks in the past, so every company already has eight quarters of
accounts to browse. After that, a new quarter closes by itself every real week.

To wipe the world and start again (this deletes every player and all history):

```
docker compose down -v
docker compose up --build
```

## Run the tests

With a PostgreSQL database available:

```
pip install -r server/requirements.txt -r tests/requirements.txt
TEST_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/wsbm_test python -m pytest
cd web && npm install && npm test && npm run build
```

## Rules for anyone changing this code

These come from section 19 of the design.

1. The server decides everything. The browser only asks.
2. Each important value is calculated in exactly one place.
3. Records are added, never edited or deleted.
4. Every rule has an automated test. New code must not break old tests.
5. Build one stage at a time, in order. Do not start a stage before the previous one passes.
6. Never put a password or key in the code. They live in `.env`, which is never shared.
7. Money and shares move only through `simulation/ledger.py`. Nothing else writes a balance.
8. Players see only what companies have filed (`company_reports`). The true record
   (`company_results`) never leaves the server.
9. Every feature gets the loophole check (design section 19): an automated test for
   each question that applies, and a review by a second AI that did not write the code.
   Players may cheat each other inside the game. Nobody may cheat the game.
