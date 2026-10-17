-- Stage 10, Part 2 (10B), second part: investigations and the empire's press desk.

-- An investigation, as a file: a tip or a hunch, documents found over time, a second source, publication (Journalist 7).
CREATE TABLE investigations (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    journalist_id uuid NOT NULL REFERENCES players (id),
    target_kind   text NOT NULL CHECK (target_kind IN ('empire', 'charity')),
    empire_id     bigint REFERENCES empires (id),
    charity_id    bigint,                                      -- (charities come with the next part)
    from_item     bigint REFERENCES intel_items (id),          -- the tip or lead it began from, if any
    opened_period integer NOT NULL,
    documents     integer NOT NULL DEFAULT 0,                  -- documents found so far
    confirmed     boolean NOT NULL DEFAULT false,              -- a second source has confirmed it
    -- SECRET: what the documents point at, once the first is found. Never sent.
    basis         text,
    last_dug      date,                                        -- the real (Lagos) day of the last search
    last_asked    date,                                        -- the real day a second source was last sought
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'published', 'dropped')),
    story_id      bigint REFERENCES stories (id),
    notes         jsonb NOT NULL DEFAULT '[]',                 -- what the journalist has found, in words
    at            timestamptz NOT NULL
);
CREATE INDEX investigations_by_journalist ON investigations (journalist_id, status);
CREATE UNIQUE INDEX investigations_one_each ON investigations (journalist_id, empire_id) WHERE status = 'open' AND empire_id IS NOT NULL;

-- A crisis an empire must answer within a deadline: a theft or a pact that came to light, a leak, a damaging report.
CREATE TABLE crises (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id     bigint NOT NULL REFERENCES empires (id),
    kind          text NOT NULL CHECK (kind IN ('theft', 'pact', 'leak', 'report', 'spin')),
    ref           text NOT NULL,                               -- what it is about (book:, pact:, story:, leak:)
    words         text NOT NULL,                               -- what happened, as the public knows it
    truth         text NOT NULL CHECK (truth IN ('true', 'false', 'worthless')),     -- SECRET: never sent
    opened_at     timestamptz NOT NULL,
    due_at        timestamptz NOT NULL,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered', 'silent')),
    stance        text CHECK (stance IN ('admit', 'deny', 'regret')),
    statement     text,
    answered_by   uuid REFERENCES players (id),
    answered_at   timestamptz,
    change        integer,
    UNIQUE (empire_id, ref)
);
CREATE INDEX crises_open ON crises (due_at) WHERE status = 'open';

-- A member passed something about their own empire to a journalist. The record of who, kept for the leak hunt.
CREATE TABLE leaks (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id     bigint NOT NULL REFERENCES empires (id),
    member_id     uuid REFERENCES players (id),                -- SECRET: never sent, except to a head whose hunt finds it
    journalist_id uuid REFERENCES players (id),
    item_id       bigint NOT NULL REFERENCES intel_items (id),
    kind          text NOT NULL CHECK (kind IN ('holding', 'pact', 'plan', 'random')),
    period        integer NOT NULL,
    printed       boolean NOT NULL DEFAULT false,
    at            timestamptz NOT NULL
);
CREATE TRIGGER leaks_no_delete BEFORE DELETE ON leaks FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE leak_hunts (
    leak_id       bigint PRIMARY KEY REFERENCES leaks (id),    -- one hunt for each leak
    hunter_id     uuid NOT NULL REFERENCES players (id),
    found         boolean NOT NULL,
    at            timestamptz NOT NULL
);

-- The head asks the empire's journalist to bury or twist a story. Refusing keeps a clean name; going along carries risk.
CREATE TABLE spin_requests (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id     bigint NOT NULL REFERENCES empires (id),
    head_id       uuid NOT NULL REFERENCES players (id),
    journalist_id uuid NOT NULL REFERENCES players (id),
    story_id      bigint NOT NULL REFERENCES stories (id),     -- the story the head wants answered
    status        text NOT NULL DEFAULT 'asked' CHECK (status IN ('asked', 'refused', 'complied', 'lapsed')),
    reply_item    bigint REFERENCES news_items (id),           -- the piece the journalist wrote, if they went along
    exposed       boolean NOT NULL DEFAULT false,
    period        integer NOT NULL,
    at            timestamptz NOT NULL,
    decided_at    timestamptz
);
CREATE UNIQUE INDEX spin_one_open ON spin_requests (empire_id, story_id);

CREATE TABLE spin_raises (                      -- a player says a reply was spin: once each
    item_id    bigint NOT NULL REFERENCES news_items (id),
    player_id  uuid NOT NULL REFERENCES players (id),
    at         timestamptz NOT NULL,
    PRIMARY KEY (item_id, player_id)
);
