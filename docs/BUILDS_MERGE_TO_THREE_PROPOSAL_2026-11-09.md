# Merging the six builds into three — what it costs and what has to be decided first

Written 9 November 2026, after the Empire page began showing "Something went wrong."

## Why the page is broken

`simulation/careers.py` now describes **three** builds: Asset Manager, Risk Manager and
Investment Banker. Accountant, Legal Counsel and Financial Journalist were removed, and a
comment says their work is folded into Asset Manager and Investment Banker.

But those three are still named in **their own seats** across the game, and the Empire page is
one of the places that looks a build up by name. `leagues.build_table()` reads
`careers.BUILDS[build]["name"]`, and `careers.career()` reads `BUILDS[mine["build"]]` and every
other career the player holds. When the name is one that no longer exists, Python raises
`KeyError`, the request fails, and the website can only say "Something went wrong." The same
crash is waiting on every other screen that names a build: the career page, the ranks page, the
firm's resolutions, the War Room, and the roster of any empire whose seats the game filled.

So the removal is real but half-finished: the list was cut, and nothing that depended on the cut
was told.

## How much depends on the three

| Where | Count | What breaks if it is left as it is |
| --- | --- | --- |
| Work templates tagged to a retired build | 211 (accountant 60, lawyer 58, journalist 93) of about 435 | Nobody can be offered 211 pieces of work: they belong to a track that no longer exists |
| Ministry of seats — empire seats | 13 per empire (a head, two for each of six) | Seats exist for builds nobody can hold; the War Room and firm lists name them |
| Empire duties gated on a seat's build | Audits (accountant), legal approval and pacts (lawyer), leaks and press (journalist) | The duties have no seat to sit in, so the empire loses them |
| Firm resolutions gated on a seat's build | Proposing bonuses, dividends, client intake, hiring, seeing all the papers, signing contracts | A firm can no longer be run, or one build runs everything |
| References in the server and simulation | about 347 | Each is a lookup or a gate that has to be re-pointed by hand |
| References in the tests | 862 across 103 files | The suite describes a game with six builds; it would fail almost everywhere |
| References in the website | 60 | Three of the six build screens, and every label naming a build |
| Database | four `CHECK` constraints and five columns hold the old names | Old rows survive, new names are refused only if a new constraint is written |

This is a stage-sized change, not a repair. It touches the syllabus, the rank cases, every
empire and firm duty, the newsroom, and two-thirds of the test suite. Your working rules say a
stage is not started without a checklist and your go-ahead; this document is that checklist, and
I have changed no code.

## Step 0: the crash stays until the merge lands (owner's decision, 9 November)

The game could be made to work again at once by giving each retired build a home to be read
as — Accountant as Asset Manager, Legal Counsel and Financial Journalist as Investment Banker.
The owner chose not to: the reading rule would be a second description of the game living beside
the real one. Instead the migration below renames the old names in the database, and the code is
left with one description of three builds.

The cost is accepted: no screen that names a build works until Steps 2 to 6 are in.

## The order the merge would go in

| # | Step | Why in this order |
| --- | --- | --- |
| 1 | The reading rule above: old build names resolve to their new home | Unbreaks the game and gives everything else one place to ask |
| 2 | A migration that renames the old names in every table that holds one, then tightens the four constraints to three | The database stops contradicting the code |
| 3 | `EMPIRE_BUILDS` down to three, and the seats rebuilt around it | The empire and the firm stop offering seats nobody can hold |
| 4 | Each duty that was gated on a retired seat given to a surviving seat | Audits, legal approvals, press: the empire keeps its work |
| 5 | The 211 pieces of work re-tagged, module by module, and the syllabus maps regenerated | The mastery gates and rank cases then describe three tracks |
| 6 | The website: three build screens, and the labels that name a build | What a player sees |
| 7 | The tests rewritten from the syllabus downwards, then the loophole check | The suite has to describe the new game, not the old |
| 8 | A stage report and a push | Your rule 7 |

## What has to be decided before step 3

I have a recommendation for each, but these are yours: they change what the game is, not just
what the code says.

| # | Decision | Settled |
| --- | --- | --- |
| A | **Who signs the accounts now.** The accountant's seat holds the audit and the sign-off on the empire's books | The Asset Manager's seat |
| B | **Who gives legal approval now.** The lawyer's seat approves pacts, mergers and the firm's papers | The Investment Banker's seat |
| C | **Who is a journalist now.** The newsroom, leaks and the press office are open only to the journalist build | Open to every build. The 93 journalism pieces stay available to anyone |
| D | **Size of an empire.** Thirteen seats today | Seven: a head, and two for each of the three builds. Existing empires shrink and their human members move to the nearest seat |
| E | **The 211 pieces of work** | Re-tagged by subject into the merged build, keeping the wording |
| F | **Players already part-way through a retired career** | Keep their level, experience and any rank case passed; move them to the new build, with a line in their history saying why |

Only the empire's seven seats change what an existing player sees; E and F decide what survives.

## What exists so far

Nothing has been applied. Two files exist:

* this plan;
* `database/migrations/045_builds_merge.sql`, which moves the retired names in the database:
  players, careers (folding two careers into one without losing the further of them), jobs, work,
  open rank cases, seats, and every live table that names a build, then tightens the five checks
  to three builds. Records of the past are left as they were written — payslips, career events,
  desk scores, judged ranks, memberships that have ended — and each player whose career moves
  gets one line of history saying why.

The migration carries a warning at its head that it must not be run on its own, and that warning
is not caution for its own sake. `simulation/world_data.py` still lists six builds in
`EMPIRE_BUILDS`, so the moment the new check is in place, founding an empire would be refused.
The migration and the code that writes build names are one change, and have to land together.

## What is left, in the order it has to be done

The line count is not the difficulty. The difficulty is that 201 places in the code and 862 in
the tests name a build, and each has to be read to know which of three things it is: a desk whose
duty moves to a surviving build, a piece of work whose tag moves, or the newsroom's own nouns,
which stay exactly as they are.

| # | Where | What happens |
| --- | --- | --- |
| 1 | `simulation/world_data.py` | `EMPIRE_BUILDS` to three. Must land with the migration |
| 2 | `simulation/empires.py` | 19 places: the audit moves to the Asset Manager's seat, the pact and legal approval to the Investment Banker's, and the three company documents (results, ratios, control) are filed by the desk that now owns them. The journalist gate on leaks becomes open to all |
| 3 | `simulation/firm.py`, `firm_money.py`, `firm_people.py`, `firm_clients.py`, `firm_deals.py`, `firm_duties.py`, `firm_owned.py`, `firm_practice.py`, `firm_tasks.py` | about 80 places, the same three moves, one resolution at a time |
| 4 | `simulation/press.py`, `newsroom.py`, `chronicle.py`, `intel.py`, `careers.py` | the newsroom opens to every build: the gate is removed, not re-pointed, so journalism work and pay follow the player's own build |
| 5 | `simulation/objectives*.py` | the 211 pieces of work re-tagged by subject, and the syllabus maps regenerated for three tracks |
| 6 | `web/src/*` | three build screens, and every label that names a build. The panel that says "a team of thirteen" now says seven |
| 7 | `docs/` | the stage reports that describe six builds say what changed and why |
| 8 | `tests/` | the 862 references, rewritten against runs of the suite |

## What I need to finish it

A run of the suite. This sandbox has Python 3.10 while the project's packages are built for 3.12,
and the package index is blocked, so not one test can be collected here — I cannot prove a single
line of the above. The way to work is: I write a step, you run `python -m pytest` (or
`docker compose exec server python -m pytest`) and paste the failures, and we work through them.
Steps 1 to 4 can be written and read through without the suite; step 5 changes what the game
offers and should not be judged by eye.
