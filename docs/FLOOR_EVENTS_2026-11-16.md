# The Floor's features and events, 16 November 2026

Built on the owner's "ok build" after The Floor, on the branch `floor-events`, in the order agreed with him: duels on the
Floor, then big client orders and the live deal tape, then the Archegos moment.

## Duels on the Floor

The owner chose a duel on the Floor in the real world over the October idea of a private copy of the world.

- **The challenge.** An empire's head challenges another empire for the next live event, until ten minutes before its
  bell. An empire the computer runs always accepts; a player-run empire's head accepts or declines. One duel for an
  empire at each bell.
- **The score.** For each side: what the event did to its money (its event result, which counts its trades and Floor
  deals in the touched shares), plus what its members earned as banks on the Floor during the event, both as a share of
  what the empire was worth at the bell, so a small empire can beat a big one. Both see the score live, split into
  the event's part and the Floor's.
- **Points.** The winner gets 8 league points; a draw gets 3 each. Once only.
- **Declines.** Free, but three in a season (not answering by the bell counts) are shown beside the empire's name, as
  the owner decided. No point penalty.
- **Where.** The Floor → Duels (a tab), and `DUEL` on the desk's command line.

Where: migration `058_floor_duels.sql`; `simulation/duels.py`; settings `DUEL_*`; routes `GET /api/floor/duels`,
`POST /api/floor/duels/challenge|answer|withdraw`; `web/src/Duels.tsx`. Tests: `tests/test_duels.py` (3).
