-- Big client orders on the Floor (owner, 16 November 2026: "ok build"): a computer pension fund or insurer hands an
-- asset manager a large order to buy a share before a deadline. The manager buys it with their own cash, on the exchange
-- or from the banks on the Floor, as cheaply as they can without pushing the price up; at the deadline the fund takes the
-- shares at the market's average price over the window and pays a small commission. Buying below that average is the
-- manager's gain, above it their loss: execution skill, scored.

CREATE TABLE floor_mandates (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id     uuid NOT NULL REFERENCES players (id),
    client_name   text NOT NULL,
    company_id    uuid NOT NULL REFERENCES companies (id),
    quantity      bigint NOT NULL CHECK (quantity > 0),
    offered_at    timestamptz NOT NULL,
    answer_by     timestamptz NOT NULL,
    status        text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'working', 'declined', 'lapsed', 'done')),
    started_at    timestamptz,
    deadline      timestamptz,
    held_before   bigint,                                -- what the manager already held when they took it on
    event_id      bigint REFERENCES live_events (id),    -- handed out at a live event's bell
    delivered     bigint,
    benchmark     bigint,                                -- the market's average price over the window
    average_paid  bigint,
    commission    bigint,
    score_bps     integer,                               -- the average price against the benchmark: above nought is better
    done_at       timestamptz
);
CREATE INDEX floor_mandates_by_player ON floor_mandates (player_id, id DESC);
CREATE INDEX floor_mandates_working ON floor_mandates (status, deadline);
