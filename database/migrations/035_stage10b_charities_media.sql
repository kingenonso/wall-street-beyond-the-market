-- Stage 10, Part 2 (10B), third part: charity foundations (owner's suggestion 10) and media titles sold at the Auction House
-- (owner's suggestion 1, confirmed for Stage 10 on 16 October 2026).

ALTER TABLE ledger_accounts DROP CONSTRAINT ledger_accounts_kind_check;
ALTER TABLE ledger_accounts ADD CONSTRAINT ledger_accounts_kind_check CHECK (kind IN (
    'central_bank', 'government', 'prize_pool', 'npc_public', 'npc_investors', 'company', 'player', 'exchange', 'empire', 'fund',
    'escrow', 'firm', 'rest_of_world', 'charity', 'media'));

-- ---------------------------------------------------------------------------
-- Charities
-- ---------------------------------------------------------------------------
CREATE TABLE charities (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          text NOT NULL,
    cause         text NOT NULL CHECK (cause IN ('education', 'health', 'water', 'arts', 'relief')),
    city          text NOT NULL,
    founder_player uuid REFERENCES players (id),
    founder_empire bigint REFERENCES empires (id),
    trustee_id    uuid NOT NULL REFERENCES players (id),       -- who decides its grants: the founder, or the founding empire's head
    account_id    uuid NOT NULL REFERENCES ledger_accounts (id),
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    exposed       boolean NOT NULL DEFAULT false,              -- an investigation showed it was used to move money to insiders
    period        integer NOT NULL,
    at            timestamptz NOT NULL,
    CHECK ((founder_player IS NULL) <> (founder_empire IS NULL))
);
CREATE UNIQUE INDEX charities_name ON charities (lower(name));
CREATE UNIQUE INDEX charities_one_each_player ON charities (founder_player) WHERE founder_player IS NOT NULL AND status = 'open';
CREATE UNIQUE INDEX charities_one_each_empire ON charities (founder_empire) WHERE founder_empire IS NOT NULL AND status = 'open';

CREATE TABLE charity_gifts (                   -- Permanent.
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    charity_id    bigint NOT NULL REFERENCES charities (id),
    from_player   uuid REFERENCES players (id),
    from_empire   bigint REFERENCES empires (id),
    amount        bigint NOT NULL CHECK (amount > 0),
    period        integer NOT NULL,
    at            timestamptz NOT NULL
);
CREATE TRIGGER charity_gifts_permanent BEFORE UPDATE OR DELETE ON charity_gifts FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE charity_grants (                  -- Permanent.
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    charity_id    bigint NOT NULL REFERENCES charities (id),
    to_player     uuid REFERENCES players (id),                -- a grant to a person (a scholarship, an award); empty = to the cause
    amount        bigint NOT NULL CHECK (amount > 0),
    words         text NOT NULL,
    connected     boolean NOT NULL DEFAULT false,              -- SECRET: the person is connected to the charity's founder or donors
    period        integer NOT NULL,
    at            timestamptz NOT NULL
);
CREATE TRIGGER charity_grants_permanent BEFORE UPDATE OR DELETE ON charity_grants FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

ALTER TABLE investigations ADD CONSTRAINT investigations_charity FOREIGN KEY (charity_id) REFERENCES charities (id);
CREATE UNIQUE INDEX investigations_one_each_charity ON investigations (journalist_id, charity_id) WHERE status = 'open' AND charity_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Media titles: small papers and stations, sold at the Auction House. An owner earns from readers.
-- ---------------------------------------------------------------------------
CREATE TABLE media_titles (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          text NOT NULL UNIQUE,
    kind          text NOT NULL CHECK (kind IN ('paper', 'radio')),
    city          text NOT NULL,
    audience      integer NOT NULL CHECK (audience >= 0),       -- regular readers or listeners
    base_audience integer NOT NULL,
    account_id    uuid NOT NULL REFERENCES ledger_accounts (id),
    owner_account uuid NOT NULL REFERENCES ledger_accounts (id),
    owner_player  uuid REFERENCES players (id),
    owner_empire  bigint REFERENCES empires (id),
    since_period  integer NOT NULL,
    paid          bigint NOT NULL DEFAULT 0,                   -- what its owner paid for it
    last_profit   bigint NOT NULL DEFAULT 0,
    at            timestamptz NOT NULL
);

CREATE TABLE media_results (                   -- each title's quarter. Permanent.
    title_id      bigint NOT NULL REFERENCES media_titles (id),
    period        integer NOT NULL,
    audience      integer NOT NULL,
    story_readers bigint NOT NULL,
    revenue       bigint NOT NULL,
    costs         bigint NOT NULL,
    profit        bigint NOT NULL,
    to_owner      bigint NOT NULL,
    PRIMARY KEY (title_id, period)
);
CREATE TRIGGER media_results_permanent BEFORE UPDATE OR DELETE ON media_results FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- An auction can sell a media title as well as a property.
ALTER TABLE auctions ALTER COLUMN property_id DROP NOT NULL;
ALTER TABLE auctions ADD COLUMN title_id bigint REFERENCES media_titles (id);
ALTER TABLE auctions ADD CONSTRAINT auctions_one_lot CHECK ((property_id IS NULL) <> (title_id IS NULL));
CREATE UNIQUE INDEX auctions_one_open_title ON auctions (title_id) WHERE status = 'open' AND title_id IS NOT NULL;

-- A story printed in a title its author's empire (or the author) owns.
ALTER TABLE stories ADD COLUMN title_id bigint REFERENCES media_titles (id);
