-- Quick fixes after the private equity stage (owner, 8 and 9 October 2026).
--
--   early retirement   after 20 quarters of work or at Level 35, with a smaller pension (1.5% of savings a quarter);
--                      full retirement stays at 40 quarters or Level 50 (2.5%). The rate is fixed when the pension begins.
--   messages           players write to each other; either may block the other
--   news alerts        each player's choice to have quiet pop-ups for every story (on by default)

ALTER TABLE retirement_accounts ADD COLUMN pension_bps integer CHECK (pension_bps BETWEEN 1 AND 10000);
UPDATE retirement_accounts SET pension_bps = 250 WHERE retired_period IS NOT NULL;

CREATE TABLE player_messages (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sender_id   uuid NOT NULL REFERENCES players (id),
    receiver_id uuid NOT NULL REFERENCES players (id),
    body        text NOT NULL CHECK (length(body) BETWEEN 1 AND 1000),
    sent_at     timestamptz NOT NULL,
    read_at     timestamptz,
    hidden_for_sender boolean NOT NULL DEFAULT false,
    hidden_for_receiver boolean NOT NULL DEFAULT false,
    CHECK (sender_id <> receiver_id)
);
CREATE INDEX player_messages_between ON player_messages (least(sender_id, receiver_id), greatest(sender_id, receiver_id), id);
CREATE INDEX player_messages_sent ON player_messages (sender_id, sent_at);
CREATE INDEX player_messages_unread ON player_messages (receiver_id) WHERE read_at IS NULL;

CREATE TABLE player_blocks (
    blocker_id  uuid NOT NULL REFERENCES players (id),
    blocked_id  uuid NOT NULL REFERENCES players (id),
    at          timestamptz NOT NULL,
    PRIMARY KEY (blocker_id, blocked_id),
    CHECK (blocker_id <> blocked_id)
);

CREATE TABLE message_reports (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_id  bigint NOT NULL REFERENCES player_messages (id),
    reporter_id uuid NOT NULL REFERENCES players (id),
    reason      text CHECK (length(reason) <= 300),
    at          timestamptz NOT NULL,
    UNIQUE (message_id, reporter_id)
);

ALTER TABLE players ADD COLUMN news_alerts boolean NOT NULL DEFAULT true;
