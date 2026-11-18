-- Alerts (owner, 18 November 2026: "one more good feature in the floor that makes it Bloomberg like" → "Alerts").
--
-- As on a Bloomberg terminal, a player sets alerts and is told the moment one is hit: a share above or below a price, a
-- share moving so much in a day, a story naming a company, a flash storm on the Floor, a new wealth client.

CREATE TABLE alerts (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id    uuid NOT NULL REFERENCES players (id),
    kind         text NOT NULL CHECK (kind IN ('above', 'below', 'move', 'news', 'storm', 'wealth')),
    ticker       text,
    level        bigint,                       -- a price in kobo (above, below) or a day's move in hundredths of a percent
    note         text,                         -- the player's own words, shown when it is hit
    created_at   timestamptz NOT NULL,
    active       boolean NOT NULL DEFAULT true,
    last_day     date,                         -- the trading day a move alert last fired (once a day)
    seen_up_to   bigint NOT NULL DEFAULT 0,    -- the last story, storm or client already looked at
    hits         integer NOT NULL DEFAULT 0,
    CHECK ((kind IN ('above', 'below', 'move', 'news')) = (ticker IS NOT NULL)),
    CHECK ((kind IN ('above', 'below', 'move')) = (level IS NOT NULL))
);
CREATE INDEX alerts_active ON alerts (active, kind);
CREATE INDEX alerts_player ON alerts (player_id);

CREATE TABLE alert_hits (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_id  integer NOT NULL REFERENCES alerts (id),
    player_id uuid NOT NULL REFERENCES players (id),
    at        timestamptz NOT NULL,
    ticker    text,
    words     text NOT NULL,
    seen      boolean NOT NULL DEFAULT false
);
CREATE INDEX alert_hits_player ON alert_hits (player_id, seen, id DESC);
