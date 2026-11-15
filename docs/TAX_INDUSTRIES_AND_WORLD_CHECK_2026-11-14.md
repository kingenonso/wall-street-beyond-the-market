# Taxes, industry work and a world check, 14 November 2026

Three changes the owner chose after the ten-year run (see `TEN_YEAR_RUN_2026-11-14.md`). Branch `tax-and-industries`.

## 1. The stand-in government cuts taxes only on a real surplus

The ten-year run found that, with nobody elected, taxes only ever fell: a "dove" stand-in cut every rate whenever the
Treasury grew at all, and since the Treasury spends its taxes back into the economy it grows a little most years.

Now (the owner's choice, option 2):

- **a dove** cuts every rate a point only when the Treasury grew by **more than a tenth** over the year;
- **a hawk** raises every rate a point when the Treasury **fell at all** (as before);
- **steady** keeps the rates (as before).

The rule is one setting, `STAND_IN_DOVE_SURPLUS_BPS` in `simulation/world_data.py`, and the Government page shows it in the
stand-in's description.

A ten-year run on a fresh world, with the same three shocks, drew a dove five times, steady four times and a hawk twice.
The dove cut once, in the second year, when the Treasury had grown by more than a tenth, and never again. Income tax ended
at 11% and company tax at 29% (the run before this change ended at 8% and 26%). The books passed all forty quarters.

## 2. Retail, film and medicines have work again

The trim to 106 kinds of work had retired three of the six industry pieces. They are back, so every industry has work of
its own:

| Industry | Piece | Build |
| --- | --- | --- |
| Retail | How far can the shops' sales fall? (`ac_retail_margin`) | Asset Manager |
| Film | A studio's quarter, with and without the hit (`jn_film_quarter`) | the newsroom (open to every build) |
| Medicines | Who carries the currency risk? (`lw_currency_clause`) | Investment Banker |

There are now **109 kinds of work** on the board: the Asset Manager 33, the Investment Banker 31, the Risk Manager 20, the
newsroom 11 and the head's 14. Thirty-five stay retired.

## 3. A health check for a running world

A new command reads a world and says, in plain words, whether all is well. It changes nothing.

```bash
docker compose exec server python -m simulation.check_world
```

It checks:

- the books, exactly as at each quarter's close (the ledger re-added, and every part's own books);
- that every database change is applied;
- every player-run empire: the head in the head's chair, and no build with more members than seats;
- who governs this year, and the tax rates in force.

It ends with "All is well." or a list of what it found.

## Tests

- `tests/test_government.py`: a new test for the stand-in's rule (a small surplus: no cut; a real one: a cut; any fall:
  the hawk raises; steady never moves).
- `tests/test_check_world.py`: a sound world passes; a head left in an ordinary seat is found, and the books still pass.
- Updated counts in `test_tasks_trim.py`, `test_mastery.py` and `test_part4c_more.py`.
