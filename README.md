# Wall Street: Beyond the Market

A 2D online game where players work as finance, law and media professionals
inside one shared, living economy. The trial world is Nigeria, in naira.

The full design is the **Master Game Design v23**. See `docs/GAME_DESIGN.md`.

## Where the build stands

The game is built in 16 stages. Each stage is finished only when its test passes.

| Stage | Status |
| --- | --- |
| 1. Foundation: sign-up, login, world clock | **Done** |
| 2. Ledger and companies | Next |
| 3 to 16 | Not started |

Stage 1 test, from the design: *a player can sign up, log in and see Lagos
time and whether the market is open.* It passes.

## What is in each folder

| Folder | Holds | Language |
| --- | --- | --- |
| `web` | The website: every screen the player sees | TypeScript with React |
| `server` | Checks every request and decides every outcome | Python with FastAPI |
| `simulation` | The game's rules and calculations. So far: the world clock | Python |
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

The game date shows "Not started" until the moment set as `WORLD_START` in `.env`.
To see the calendar running now, set it to a date in the past.

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
