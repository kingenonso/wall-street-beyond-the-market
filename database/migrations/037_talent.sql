-- Proven Talent (the talent and funds stage, Part 1): a record of what each player has done, worked out from the game's
-- own books and nothing else; badges earned from it; a page the player may share; challenges set by real firms; a board
-- of players who choose to be found; and the checks that keep the record honest.
--
-- The record itself is never typed in by anybody. `talent_records` only keeps the latest working-out, made afresh from
-- the ledger, the closing prices and the game's own registers each trading day.

-- ---------------------------------------------------------------------------
-- The player's own settings: whether the record is shared, what is shown, whether firms may find them.
-- ---------------------------------------------------------------------------
CREATE TABLE talent_settings (
    player_id   uuid PRIMARY KEY REFERENCES players (id),
    shared      boolean NOT NULL DEFAULT false,
    slug        text UNIQUE CHECK (slug ~ '^[A-Za-z0-9_-]{20,40}$'),
    show        text[] NOT NULL DEFAULT ARRAY['investing', 'work', 'calls', 'audits', 'journalism', 'leadership', 'crisis', 'challenges'],
    on_board    boolean NOT NULL DEFAULT false,
    headline    text NOT NULL DEFAULT '' CHECK (length(headline) <= 140),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE talent_records (
    player_id    uuid PRIMARY KEY REFERENCES players (id),
    worked_on    date,                                   -- the last trading day it covers
    worked_at    timestamptz NOT NULL,
    record       jsonb NOT NULL,
    summary      jsonb NOT NULL                          -- the few figures the board filters on
);

-- A badge is earned once and kept; the few that depend on keeping a clean record can be lost again.
CREATE TABLE talent_badges (
    player_id  uuid NOT NULL REFERENCES players (id),
    code       text NOT NULL CHECK (code ~ '^[a-z0-9_:-]{2,60}$'),
    label      text NOT NULL,
    words      text NOT NULL,
    earned_at  timestamptz NOT NULL,
    lost_at    timestamptz,
    PRIMARY KEY (player_id, code)
);

-- ---------------------------------------------------------------------------
-- Keeping the record honest. Never shown to players.
-- ---------------------------------------------------------------------------
-- A one-way mark of the device a player logs in from (a keyed fingerprint of the address and browser, never the
-- address itself), kept for a day, so accounts run from one device can be noticed.
CREATE TABLE visitor_marks (
    player_id  uuid NOT NULL REFERENCES players (id),
    mark       text NOT NULL,
    day        date NOT NULL,
    PRIMARY KEY (player_id, mark, day)
);
CREATE INDEX visitor_marks_mark ON visitor_marks (mark, day);

CREATE TABLE talent_flags (
    id          bigserial PRIMARY KEY,
    player_id   uuid NOT NULL REFERENCES players (id),
    kind        text NOT NULL CHECK (kind IN ('off_market_trade', 'shared_device', 'linked')),
    other_id    uuid REFERENCES players (id),
    reference   text NOT NULL,
    amount      bigint NOT NULL DEFAULT 0,               -- for a trade at an odd price: the value handed to this player
    session_date date,
    detail      jsonb NOT NULL DEFAULT '{}',
    at          timestamptz NOT NULL,
    cleared_at  timestamptz,
    cleared_why text,
    UNIQUE (player_id, kind, reference)
);
CREATE INDEX talent_flags_player ON talent_flags (player_id) WHERE cleared_at IS NULL;

CREATE TABLE talent_progress (
    id              boolean PRIMARY KEY DEFAULT true CHECK (id),
    checked_through date                                   -- the last trading day whose trades have been looked at
);
INSERT INTO talent_progress (id) VALUES (true);

-- ---------------------------------------------------------------------------
-- Firms: real organisations that sponsor challenges and look for talent. They log in separately and have no player
-- powers at all. An administrator approves each one.
-- ---------------------------------------------------------------------------
CREATE TABLE talent_firms (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name             text NOT NULL CHECK (length(name) BETWEEN 2 AND 80),
    name_key         text NOT NULL UNIQUE,
    email            text NOT NULL,
    email_key        text NOT NULL UNIQUE,
    password_hash    text NOT NULL,
    contact_name     text NOT NULL CHECK (length(contact_name) BETWEEN 2 AND 80),
    website          text NOT NULL DEFAULT '' CHECK (length(website) <= 200),
    tagline          text NOT NULL DEFAULT '' CHECK (length(tagline) <= 140),
    colour           text NOT NULL DEFAULT '#2f6f9f' CHECK (colour ~ '^#[0-9a-f]{6}$'),
    status           text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'suspended')),
    session_version  integer NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    approved_at      timestamptz
);

-- ---------------------------------------------------------------------------
-- Challenges. "Sealed" kinds never touch the live world: a paper portfolio dealt at the live prices, a valuation, the
-- weakest bank, a profit forecast. The "live" kind scores the entrants' real record over the challenge's weeks.
-- ---------------------------------------------------------------------------
CREATE TABLE talent_challenges (
    id             bigserial PRIMARY KEY,
    firm_id        uuid NOT NULL REFERENCES talent_firms (id),
    kind           text NOT NULL CHECK (kind IN ('paper', 'valuation', 'weak_bank', 'forecast', 'live')),
    title          text NOT NULL CHECK (length(title) BETWEEN 4 AND 90),
    brief          text NOT NULL DEFAULT '' CHECK (length(brief) <= 1200),
    company_id     uuid REFERENCES companies (id),
    target_period  integer,
    starting_cash  bigint NOT NULL DEFAULT 0 CHECK (starting_cash >= 0),
    opens_at       timestamptz NOT NULL,
    locks_at       timestamptz NOT NULL,
    ends_at        timestamptz NOT NULL,
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'scored', 'cancelled')),
    top_shown      integer NOT NULL DEFAULT 10 CHECK (top_shown BETWEEN 1 AND 50),
    created_at     timestamptz NOT NULL,
    scored_at      timestamptz,
    results        jsonb,
    CHECK (opens_at <= locks_at AND locks_at <= ends_at)
);

CREATE TABLE challenge_entries (
    id                 bigserial PRIMARY KEY,
    challenge_id       bigint NOT NULL REFERENCES talent_challenges (id),
    player_id          uuid NOT NULL REFERENCES players (id),
    joined_at          timestamptz NOT NULL,
    seen_by_sponsor    boolean NOT NULL DEFAULT false,
    cash               bigint NOT NULL DEFAULT 0 CHECK (cash >= 0),
    answer             bigint,
    answer_company     uuid REFERENCES companies (id),
    answer_text        text NOT NULL DEFAULT '' CHECK (length(answer_text) <= 1000),
    answered_at        timestamptz,
    start_worth        bigint,                            -- the live kind: where the entrant's record stood at the start
    score              bigint,                            -- higher is better; worked out once, at the end
    score_words        text,
    place              integer,
    UNIQUE (challenge_id, player_id)
);

CREATE TABLE challenge_positions (
    entry_id    bigint NOT NULL REFERENCES challenge_entries (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    quantity    bigint NOT NULL CHECK (quantity >= 0),
    cost        bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (entry_id, company_id)
);

CREATE TABLE challenge_trades (
    id          bigserial PRIMARY KEY,
    entry_id    bigint NOT NULL REFERENCES challenge_entries (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    side        text NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity    bigint NOT NULL CHECK (quantity > 0),
    price       bigint NOT NULL CHECK (price > 0),
    fee         bigint NOT NULL CHECK (fee >= 0),
    at          timestamptz NOT NULL
);

CREATE TABLE challenge_days (
    entry_id      bigint NOT NULL REFERENCES challenge_entries (id),
    session_date  date NOT NULL,
    value         bigint NOT NULL,
    PRIMARY KEY (entry_id, session_date)
);

-- ---------------------------------------------------------------------------
-- Invitations from a firm to a player who chose to be on the board. The player's contact details reach the firm only
-- if the player accepts and types them in.
-- ---------------------------------------------------------------------------
CREATE TABLE talent_invitations (
    id           bigserial PRIMARY KEY,
    firm_id      uuid NOT NULL REFERENCES talent_firms (id),
    player_id    uuid NOT NULL REFERENCES players (id),
    challenge_id bigint REFERENCES talent_challenges (id),
    message      text NOT NULL CHECK (length(message) BETWEEN 10 AND 800),
    status       text NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'accepted', 'declined')),
    contact      text CHECK (length(contact) <= 300),
    sent_at      timestamptz NOT NULL,
    answered_at  timestamptz
);
CREATE INDEX talent_invitations_player ON talent_invitations (player_id, status);
CREATE UNIQUE INDEX talent_invitations_open ON talent_invitations (firm_id, player_id) WHERE status = 'sent';

CREATE TABLE talent_firm_blocks (
    player_id  uuid NOT NULL REFERENCES players (id),
    firm_id    uuid NOT NULL REFERENCES talent_firms (id),
    at         timestamptz NOT NULL,
    PRIMARY KEY (player_id, firm_id)
);
