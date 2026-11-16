-- The Archegos moment (owner, 16 November 2026: "ok build"). Computer hedge funds ask the players' bank desks to hold
-- shares for them on a swap: the bank buys the shares with its own cash and holds them; the fund posts margin with the
-- bank (20% of the value) and pays interest when the swap closes. Each bank sees only its own swap, never how much the
-- fund has asked of the others. Most funds close quietly and the banks earn their interest. Now and then one blows up:
-- it misses a margin call, the banks keep its margin and are left holding its shares, the share falls hard in two
-- steps ten minutes apart, and the banks race to sell. The last out takes the big loss. Modelled on Archegos, March 2021.

CREATE TABLE floor_funds (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL,
    company_id  uuid NOT NULL REFERENCES companies (id),
    status      text NOT NULL DEFAULT 'building' CHECK (status IN ('building', 'blown', 'closed')),
    created_at  timestamptz NOT NULL,
    ends_at     timestamptz NOT NULL,              -- it closes, or blows up, then
    blows_up    boolean NOT NULL,                  -- SECRET until it happens: decided from the world's secret
    stage       integer NOT NULL DEFAULT 0,        -- after a blow-up: 1 the first fall, 2 the second, 3 the dust settles
    blown_at    timestamptz,
    entry_price bigint NOT NULL CHECK (entry_price > 0)
);
CREATE INDEX floor_funds_open ON floor_funds (status);

CREATE TABLE floor_swaps (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fund_id      bigint NOT NULL REFERENCES floor_funds (id),
    player_id    uuid NOT NULL REFERENCES players (id),
    shares       bigint NOT NULL CHECK (shares > 0),
    price        bigint,                            -- what the bank paid for them
    margin       bigint,                            -- what the fund posted with the bank
    rate_bps     integer NOT NULL,                  -- the fund's interest for the swap's life
    status       text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'declined', 'lapsed', 'open', 'closed', 'defaulted')),
    offered_at   timestamptz NOT NULL,
    answer_by    timestamptz NOT NULL,
    opened_at    timestamptz,
    closed_at    timestamptz,
    interest     bigint NOT NULL DEFAULT 0,
    out_before   integer,                           -- after a blow-up: the fall the bank had got out before (1 or 2), or none
    UNIQUE (fund_id, player_id)
);
CREATE INDEX floor_swaps_by_player ON floor_swaps (player_id, id DESC);
