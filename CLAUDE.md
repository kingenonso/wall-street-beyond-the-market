# Working rules for this project

The owner is not a developer. Explain everything in plain language and explain
any technical term the first time it is used.

1. **Never start a new stage without the owner's explicit go-ahead.** Present the
   stage's checklist first, wait for approval, then build.
2. **The Nigeria trial has every feature of the design** except multi-region
   items. Never drop, condense or defer a feature without asking.
3. **Loophole check after every feature** (design section 19, ten questions):
   an automated test per applicable question, then a second AI that did not write
   the code is told to break it. Fix what it finds, add a test for each attack,
   and list question / answer / test in the stage report. Players may commit
   crimes against each other in the game, never against the game.
4. **Front end:** the focus-first layout (top bar, sections menu, work area with
   "Needs you now", context rail). Rises and falls carry an arrow as well as a
   colour. Profile picture: male icon, female icon, or (later) an uploaded picture.
5. **Languages:** TypeScript, Python, SQL; Rust only for the order-matching engine
   (Stage 4).
6. The real exam bodies' names are never used in the game; only objectives
   drawn from their learning modules. No question papers.
7. Each stage ends with: all tests passing, a report in `docs/STAGE_NN_*.md` that
   ticks every checklist item against its tests with screenshots, and a push to GitHub.
8. Money is whole kobo, moved only through `simulation/ledger.py`. Records are
   added, never edited or deleted. The server decides everything.
