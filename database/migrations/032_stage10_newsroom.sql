-- Stage 10, Part 1: the newsroom. Players' stories built from confirmed facts, readers and reach, scoops,
-- interviews, corrections, stories that move the market, declared interests, the empire's public reputation,
-- full articles for the wire, the Ripple (what caused what) and the Chronicle (the world's memory).

-- A wire item or a player's story. Players' stories are news items too, with an author.
ALTER TABLE news_items ADD COLUMN author_id uuid REFERENCES players (id);
ALTER TABLE news_items ADD COLUMN follows bigint REFERENCES news_items (id);      -- a follow-up points at the first item
CREATE INDEX news_items_by_author ON news_items (author_id, id DESC) WHERE author_id IS NOT NULL;
CREATE INDEX news_items_by_story ON news_items (story, id);

-- The full article written for a wire item from its recorded facts. Kept for good.
CREATE TABLE news_articles (
    news_item_id  bigint PRIMARY KEY REFERENCES news_items (id),
    writer        text NOT NULL CHECK (writer IN ('built_in', 'service')),
    body          text NOT NULL CHECK (body <> ''),
    figures       jsonb NOT NULL DEFAULT '[]',        -- every figure in the article, each found in the record
    period        integer NOT NULL,
    day           integer NOT NULL,
    at            timestamptz NOT NULL
);
CREATE INDEX news_articles_by_day ON news_articles (period, day);
CREATE TRIGGER news_articles_permanent BEFORE UPDATE OR DELETE ON news_articles
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- A journalist's public record.
CREATE TABLE journalist_profiles (
    player_id     uuid PRIMARY KEY REFERENCES players (id),
    following     bigint NOT NULL DEFAULT 0 CHECK (following >= 0),     -- readers who follow their name
    readers       bigint NOT NULL DEFAULT 0 CHECK (readers >= 0),       -- every reader of every story
    stories       integer NOT NULL DEFAULT 0,
    scoops        integer NOT NULL DEFAULT 0,
    corrections   integer NOT NULL DEFAULT 0,
    credibility   integer NOT NULL DEFAULT 50 CHECK (credibility BETWEEN 0 AND 100)
);

-- A player's story, from first draft to publication and after.
CREATE TABLE stories (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    author_id      uuid NOT NULL REFERENCES players (id),
    empire_id      bigint REFERENCES empires (id),             -- the empire the author sat in when they began
    outlet_company uuid REFERENCES companies (id),             -- the media house they wrote for; empty = independent
    status         text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'withdrawn')),
    facts          jsonb NOT NULL DEFAULT '[]',                -- the confirmed facts chosen, as they stood when chosen
    checked        jsonb NOT NULL DEFAULT '[]',                -- which of them the author checked against the record
    angle          text NOT NULL DEFAULT 'straight',
    comment        text NOT NULL DEFAULT '',                   -- the author's own view, in words, no figures
    tickers        text[] NOT NULL DEFAULT '{}',
    tone           integer NOT NULL DEFAULT 0 CHECK (tone BETWEEN -1 AND 1),
    declared       boolean NOT NULL DEFAULT false,             -- the author declared their empire's interest
    headline       text NOT NULL DEFAULT '',
    body           text NOT NULL DEFAULT '',
    readers        bigint NOT NULL DEFAULT 0,
    scoop          boolean NOT NULL DEFAULT false,
    paid           bigint NOT NULL DEFAULT 0,
    news_item_id   bigint REFERENCES news_items (id),
    period         integer,                                    -- when it was published
    day            integer,
    started_at     timestamptz NOT NULL,
    published_at   timestamptz,
    -- A fact it used was later changed in the record: the author must correct it by `correct_by`.
    correction_due boolean NOT NULL DEFAULT false,
    correct_by     timestamptz,
    correction_id  bigint REFERENCES news_items (id),
    correction_late boolean NOT NULL DEFAULT false
);
CREATE INDEX stories_by_author ON stories (author_id, id DESC);
CREATE INDEX stories_by_status ON stories (status, published_at);
CREATE UNIQUE INDEX stories_one_draft ON stories (author_id) WHERE status = 'draft';

-- Interviews: a journalist asks a company or the head of an empire for comment.
CREATE TABLE interviews (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    story_id      bigint NOT NULL REFERENCES stories (id),
    journalist_id uuid NOT NULL REFERENCES players (id),
    company_id    uuid REFERENCES companies (id),
    empire_id     bigint REFERENCES empires (id),
    question      text NOT NULL CHECK (length(question) BETWEEN 10 AND 300),
    answer        text,
    status        text NOT NULL DEFAULT 'asked' CHECK (status IN ('asked', 'answered', 'declined', 'lapsed')),
    asked_at      timestamptz NOT NULL,
    due_at        timestamptz NOT NULL,
    answered_at   timestamptz,
    CHECK ((company_id IS NULL) <> (empire_id IS NULL))
);
CREATE INDEX interviews_by_empire ON interviews (empire_id, status);
CREATE UNIQUE INDEX interviews_one_each ON interviews (story_id, coalesce(company_id::text, ''), coalesce(empire_id, 0));

-- No trading a company around one's own story: from the first draft until two trading days after publication.
CREATE TABLE story_blocks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    story_id    bigint NOT NULL REFERENCES stories (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    since       timestamptz NOT NULL,
    until       timestamptz,                    -- empty while the story is still being written
    UNIQUE (story_id, account_id, company_id)
);
CREATE INDEX story_blocks_by_account ON story_blocks (account_id, company_id);

-- A true, widely read story moves how the computer-run investors see a company, a little, fading over days.
CREATE TABLE story_nudges (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id    uuid NOT NULL REFERENCES companies (id),
    story_id      bigint NOT NULL REFERENCES stories (id),
    bps           integer NOT NULL CHECK (bps BETWEEN -200 AND 200),
    session_date  date NOT NULL,                -- the trading day it starts
    days          integer NOT NULL,
    at            timestamptz NOT NULL,
    UNIQUE (company_id, session_date)
);
CREATE TRIGGER story_nudges_permanent BEFORE UPDATE OR DELETE ON story_nudges
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Whether an author's empire held what they wrote about, as it stood when the story came out. Never shown,
-- except as the verdict when another player exposes an interest that was not declared.
CREATE TABLE story_interests (
    story_id   bigint PRIMARY KEY REFERENCES stories (id),
    empire_id  bigint NOT NULL REFERENCES empires (id),
    held       boolean NOT NULL,
    declared   boolean NOT NULL
);
CREATE TABLE interest_exposures (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    story_id   bigint NOT NULL REFERENCES stories (id),
    by_player  uuid NOT NULL REFERENCES players (id),
    upheld     boolean NOT NULL,
    at         timestamptz NOT NULL,
    UNIQUE (story_id, by_player)
);

-- The empire's public reputation, and every change to it with its reason.
ALTER TABLE empires ADD COLUMN reputation integer NOT NULL DEFAULT 50 CHECK (reputation BETWEEN 0 AND 100);
CREATE TABLE empire_reputation (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    change      integer NOT NULL,
    after       integer NOT NULL,
    why         text NOT NULL,
    period      integer NOT NULL,
    at          timestamptz NOT NULL,
    press       boolean NOT NULL DEFAULT false      -- moved by the press (answers, lapsed questions): capped each day
);
CREATE INDEX empire_reputation_by_empire ON empire_reputation (empire_id, id DESC);
CREATE TRIGGER empire_reputation_permanent BEFORE UPDATE OR DELETE ON empire_reputation
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- The Ripple: what caused what. Each link joins an effect to one of its causes. Kept for good.
CREATE TABLE ripple_links (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    effect      text NOT NULL,                  -- e.g. 'results:IDC:9', 'rate:9', 'story:12', 'nudge:IDC:2026-10-12'
    cause       text NOT NULL,
    words       text NOT NULL CHECK (words <> ''),     -- how the cause led to the effect, in one line
    numbers     jsonb NOT NULL DEFAULT '{}',    -- the figures behind it
    period      integer NOT NULL,
    at          timestamptz NOT NULL,
    UNIQUE (effect, cause)
);
CREATE INDEX ripple_links_by_effect ON ripple_links (effect);
CREATE INDEX ripple_links_by_cause ON ripple_links (cause);
CREATE TRIGGER ripple_links_permanent BEFORE UPDATE OR DELETE ON ripple_links
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- The Chronicle: the world's memory, in three layers. The game writes the record; journalists add signed accounts.
CREATE TABLE chronicle_entries (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    layer       text NOT NULL CHECK (layer IN ('personal', 'company', 'world')),
    player_id   uuid REFERENCES players (id),
    company_id  uuid REFERENCES companies (id),
    kind        text NOT NULL,
    ref         text NOT NULL,                  -- the record it comes from, and the Ripple's key for it
    title       text NOT NULL CHECK (title <> ''),
    words       text NOT NULL CHECK (words <> ''),
    period      integer NOT NULL,
    day         integer NOT NULL,
    at          timestamptz NOT NULL,
    UNIQUE NULLS NOT DISTINCT (layer, ref, player_id)
);
CREATE INDEX chronicle_by_layer ON chronicle_entries (layer, period DESC, day DESC, id DESC);
CREATE INDEX chronicle_by_player ON chronicle_entries (player_id, id DESC) WHERE player_id IS NOT NULL;
CREATE INDEX chronicle_by_company ON chronicle_entries (company_id, id DESC) WHERE company_id IS NOT NULL;
CREATE TRIGGER chronicle_entries_permanent BEFORE UPDATE OR DELETE ON chronicle_entries
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE chronicle_accounts (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id    bigint NOT NULL REFERENCES chronicle_entries (id),
    author_id   uuid NOT NULL REFERENCES players (id),
    words       text NOT NULL CHECK (length(words) BETWEEN 40 AND 1200),
    evidence    jsonb NOT NULL DEFAULT '[]',    -- the confirmed facts it cites
    credibility integer NOT NULL CHECK (credibility BETWEEN 0 AND 100),
    period      integer NOT NULL,
    at          timestamptz NOT NULL,
    UNIQUE (entry_id, author_id)
);
CREATE TRIGGER chronicle_accounts_permanent BEFORE UPDATE OR DELETE ON chronicle_accounts
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Named clients who come back, and remember how a player's work for them went (starting with the Journalist).
CREATE TABLE client_trust (
    player_id  uuid NOT NULL REFERENCES players (id),
    client     text NOT NULL,
    trust      integer NOT NULL DEFAULT 50 CHECK (trust BETWEEN 0 AND 100),
    pieces     integer NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, client)
);
