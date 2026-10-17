-- Stage 10, Part 2 (10B), first part: information as a thing in the world.
--
-- The Intelligence Market (design M29): every piece of information has a record: where it came from and how reliable
-- that source is, who found it and when, whether it is a rumour, a lead or verified, which companies or empires it
-- concerns, and when it stops being useful. Who held it, and since when, is kept, so "who knew what, when" can be
-- rebuilt. Whether it is TRUE, and what it was drawn from, is known only to the server.
-- The Sealed Tip (M31): one sealed piece of information each real day for every player.
-- Sources: a Financial Journalist's contacts inside companies and the ministries.
-- Rumours move prices (M32): what was believed is kept against what was true.

CREATE TABLE sources (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    journalist_id  uuid NOT NULL REFERENCES players (id),
    kind           text NOT NULL CHECK (kind IN ('company', 'ministry')),
    company_id     uuid REFERENCES companies (id),
    started_period integer NOT NULL,
    ready_period   integer NOT NULL,                    -- a source takes two quarters to build
    reliability_bps integer NOT NULL CHECK (reliability_bps BETWEEN 0 AND 10000),
    status         text NOT NULL DEFAULT 'cultivating' CHECK (status IN ('cultivating', 'active', 'burned', 'dropped')),
    last_asked     date,                                -- the real (Lagos) day it was last asked
    burned_at      timestamptz,
    at             timestamptz NOT NULL,
    CHECK ((kind = 'company') = (company_id IS NOT NULL))
);
CREATE UNIQUE INDEX sources_one_each ON sources (journalist_id, coalesce(company_id::text, 'ministry')) WHERE status IN ('cultivating', 'active');
CREATE INDEX sources_by_journalist ON sources (journalist_id);

CREATE TABLE intel_items (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ref            text NOT NULL UNIQUE,                -- the public reference (random); the id is never sent
    kind           text NOT NULL CHECK (kind IN ('tip', 'source_hint', 'rumour', 'finding', 'leak')),
    topic          text NOT NULL CHECK (topic IN ('company', 'pact', 'theft', 'rate', 'infrastructure', 'charity', 'empire')),
    company_id     uuid REFERENCES companies (id),
    empire_id      bigint REFERENCES empires (id),
    other_empire_id bigint REFERENCES empires (id),
    city           text,
    tone           integer NOT NULL DEFAULT 0 CHECK (tone BETWEEN -1 AND 1),
    words          text NOT NULL CHECK (length(words) BETWEEN 5 AND 400),
    status         text NOT NULL DEFAULT 'rumour' CHECK (status IN ('rumour', 'lead', 'verified', 'disproved')),
    -- SECRET: never sent. What it really is, and what it was drawn from.
    truth          text NOT NULL CHECK (truth IN ('true', 'false', 'worthless', 'unknown')),   -- unknown: a forecast, settled at the close
    basis          text,
    planted_by     uuid REFERENCES players (id),
    resolves_period integer,
    resolves_day   integer,
    -- Public.
    confidential   boolean NOT NULL DEFAULT false,      -- from someone inside: trading on it is dealing on confidential information
    source_id      bigint REFERENCES sources (id),
    reliability_bps integer,                            -- how reliable its source was known to be, if it came from one
    found_by       uuid REFERENCES players (id),
    period         integer NOT NULL,
    day            integer NOT NULL,
    found_at       timestamptz NOT NULL,
    useful_until   timestamptz,                         -- set when it is first opened
    resolved_at    timestamptz,
    ripple         text
);
CREATE INDEX intel_items_open ON intel_items (resolves_period, resolves_day) WHERE resolved_at IS NULL;
CREATE INDEX intel_items_by_company ON intel_items (company_id);

-- Who held each piece, how they came by it, and when: the record of who knew what, when. Permanent.
CREATE TABLE intel_holders (
    item_id    bigint NOT NULL REFERENCES intel_items (id),
    player_id  uuid NOT NULL REFERENCES players (id),
    how        text NOT NULL CHECK (how IN ('found', 'tip', 'bought', 'given', 'leaked', 'shared')),
    from_player uuid REFERENCES players (id),
    at         timestamptz NOT NULL,
    PRIMARY KEY (item_id, player_id)
);
CREATE INDEX intel_holders_by_player ON intel_holders (player_id, at DESC);
CREATE TRIGGER intel_holders_no_delete BEFORE DELETE ON intel_holders FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- The Sealed Tip: one each real day for every player. It cannot be bought, and only the day's one is given.
CREATE TABLE sealed_tips (
    player_id  uuid NOT NULL REFERENCES players (id),
    tip_day    date NOT NULL,                           -- the real (Lagos) day
    item_id    bigint NOT NULL REFERENCES intel_items (id),
    opened_at  timestamptz,
    PRIMARY KEY (player_id, tip_day)
);

-- A holder's own check of a piece: what they were told.
CREATE TABLE intel_checks (
    item_id    bigint NOT NULL REFERENCES intel_items (id),
    player_id  uuid NOT NULL REFERENCES players (id),
    verdict    text NOT NULL CHECK (verdict IN ('holds', 'fails', 'nothing_new')),
    by_player  uuid REFERENCES players (id),            -- who did the checking (an empire's fact-checking desk), if not the holder
    at         timestamptz NOT NULL,
    PRIMARY KEY (item_id, player_id)
);

-- The Intelligence Market: a piece offered for sale. The words are seen only by those who buy.
CREATE TABLE intel_listings (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id    bigint NOT NULL REFERENCES intel_items (id),
    seller     uuid NOT NULL REFERENCES players (id),
    price      bigint NOT NULL CHECK (price > 0),
    status     text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'withdrawn', 'ended')),
    sold       integer NOT NULL DEFAULT 0,
    at         timestamptz NOT NULL
);
CREATE UNIQUE INDEX intel_listings_one_open ON intel_listings (item_id, seller) WHERE status = 'open';

CREATE TABLE intel_sales (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_id bigint NOT NULL REFERENCES intel_listings (id),
    buyer      uuid NOT NULL REFERENCES players (id),
    price      bigint NOT NULL,
    at         timestamptz NOT NULL,
    UNIQUE (listing_id, buyer)
);

-- Trading on information from someone inside, while it was still useful. Kept for the courts (Stage 11). Permanent.
CREATE TABLE confidential_dealings (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id  uuid NOT NULL REFERENCES players (id),
    account_id uuid NOT NULL REFERENCES ledger_accounts (id),
    item_id    bigint NOT NULL REFERENCES intel_items (id),
    company_id uuid NOT NULL REFERENCES companies (id),
    at         timestamptz NOT NULL
);
CREATE TRIGGER confidential_dealings_permanent BEFORE UPDATE OR DELETE ON confidential_dealings FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- A story may carry one unconfirmed lead (M32): what was believed, against what turned out to be true.
ALTER TABLE stories ADD COLUMN lead jsonb;                 -- {item_id, ref, words, tickers, empire_id, tone, status}
ALTER TABLE stories ADD COLUMN lead_outcome text CHECK (lead_outcome IN ('confirmed', 'disproved'));
CREATE TABLE rumour_beliefs (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id    bigint NOT NULL REFERENCES intel_items (id),
    story_id   bigint NOT NULL REFERENCES stories (id),
    company_id uuid REFERENCES companies (id),
    bps        integer NOT NULL DEFAULT 0,             -- how far investors marked the company on it
    readers    bigint NOT NULL DEFAULT 0,
    outcome    text CHECK (outcome IN ('true', 'false')),
    at         timestamptz NOT NULL,
    settled_at timestamptz
);
