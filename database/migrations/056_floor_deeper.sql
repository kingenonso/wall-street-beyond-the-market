-- The Floor, slice 3 (owner, 16 November 2026, "go on"): the deeper game on the Floor.
--   * Haggling: a client may counter a bank's price; the bank accepts or declines while its price holds.
--   * Firm or indicative: a firm price can be taken at once; an indicative one only guides, and taking it asks the bank to
--     confirm ("last look"). A bank that keeps backing away from prices it showed is marked for it, publicly.
--   * The second-best price ("the cover") is shown to the banks that lost, and to the winner.
--   * Baskets (several shares at once, priced as one margin over the market), blocks (very large deals, reported to the
--     market afterwards without names) and bonds (priced on yield).
--   * Chat between client and bank, where an agreed line becomes a deal ticket both sides confirm.
--   * The best-execution scorecard (each deal against the exchange and the other prices), client history for the banks,
--     and banks advertising what they want to buy or sell ("axes").
--   * Trading for an empire on the Floor, inside every limit an empire's order meets.

ALTER TABLE floor_requests ALTER COLUMN company_id DROP NOT NULL;
ALTER TABLE floor_requests ADD COLUMN kind text NOT NULL DEFAULT 'share' CHECK (kind IN ('share', 'basket', 'bond'));
ALTER TABLE floor_requests ADD COLUMN bond_id uuid REFERENCES bonds (id);
ALTER TABLE floor_requests ADD COLUMN block boolean NOT NULL DEFAULT false;
ALTER TABLE floor_requests ADD COLUMN for_empire bigint REFERENCES empires (id);
-- The exchange's best price on the client's side when it asked: what each deal is scored against.
ALTER TABLE floor_requests ADD COLUMN exchange_bid bigint;
ALTER TABLE floor_requests ADD COLUMN exchange_offer bigint;
ALTER TABLE floor_requests ADD CONSTRAINT floor_requests_what CHECK (
    (kind = 'share' AND company_id IS NOT NULL AND bond_id IS NULL) OR
    (kind = 'bond' AND bond_id IS NOT NULL AND company_id IS NULL) OR
    (kind = 'basket' AND company_id IS NULL AND bond_id IS NULL));

-- A basket's shares, each with the market's middle price when it was asked for.
CREATE TABLE floor_request_legs (
    request_id  bigint NOT NULL REFERENCES floor_requests (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    quantity    bigint NOT NULL CHECK (quantity > 0),
    mid         bigint NOT NULL CHECK (mid > 0),
    PRIMARY KEY (request_id, company_id)
);

ALTER TABLE floor_quotes ADD COLUMN firm boolean NOT NULL DEFAULT true;
-- A basket is priced as one margin, in hundredths of a percent, over (the bank sells) or under (it buys) each middle price.
ALTER TABLE floor_quotes ADD COLUMN margin_bps integer CHECK (margin_bps BETWEEN -500 AND 500);
ALTER TABLE floor_quotes DROP CONSTRAINT floor_quotes_check;
ALTER TABLE floor_quotes ADD CONSTRAINT floor_quotes_priced CHECK (bid IS NOT NULL OR offer IS NOT NULL OR margin_bps IS NOT NULL);

-- A counter from the client ("can you do 226?"), or a client taking an indicative price, which the bank must confirm.
CREATE TABLE floor_counters (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id   bigint NOT NULL REFERENCES floor_requests (id),
    quote_id     bigint NOT NULL REFERENCES floor_quotes (id),
    kind         text NOT NULL CHECK (kind IN ('counter', 'confirm')),
    side         text NOT NULL CHECK (side IN ('buy', 'sell')),       -- the client's side
    price        bigint CHECK (price > 0),
    margin_bps   integer CHECK (margin_bps BETWEEN -500 AND 500),
    created_at   timestamptz NOT NULL,
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'declined', 'expired')),
    answered_at  timestamptz,
    CHECK (price IS NOT NULL OR margin_bps IS NOT NULL)
);
CREATE INDEX floor_counters_by_request ON floor_counters (request_id, id);

ALTER TABLE floor_desks ADD COLUMN backed_away integer NOT NULL DEFAULT 0 CHECK (backed_away >= 0);

-- A deal may now be a basket (one row for each share) or a bond.
ALTER TABLE floor_trades DROP CONSTRAINT floor_trades_request_id_key;
ALTER TABLE floor_trades ALTER COLUMN company_id DROP NOT NULL;
ALTER TABLE floor_trades ADD COLUMN bond_id uuid REFERENCES bonds (id);
ALTER TABLE floor_trades ADD COLUMN cover bigint;                         -- the second-best price on the same side
ALTER TABLE floor_trades ADD COLUMN exchange_price bigint;                -- the exchange's best on the client's side, when asked
ALTER TABLE floor_trades ADD COLUMN client_bought boolean;
ALTER TABLE floor_trades ADD COLUMN block boolean NOT NULL DEFAULT false;
ALTER TABLE floor_trades ADD CONSTRAINT floor_trades_what CHECK ((company_id IS NULL) <> (bond_id IS NULL));
ALTER TABLE floor_trades ALTER COLUMN request_id DROP NOT NULL;           -- a deal ticket from the chat has no request...
ALTER TABLE floor_trades ALTER COLUMN quote_id DROP NOT NULL;             -- ...and no quote
CREATE INDEX floor_trades_blocks ON floor_trades (at DESC) WHERE block;

-- What a bank wants to buy or sell, advertised to clients.
CREATE TABLE floor_axes (
    player_id   uuid NOT NULL REFERENCES players (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    side        text NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity    bigint NOT NULL CHECK (quantity > 0),
    created_at  timestamptz NOT NULL,
    until       timestamptz NOT NULL,
    PRIMARY KEY (player_id, company_id)
);

-- Chat between two players on the Floor, kept for good: the Money Watch may read it.
CREATE TABLE floor_chat (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_player uuid NOT NULL REFERENCES players (id),
    to_player   uuid NOT NULL REFERENCES players (id),
    body        text NOT NULL CHECK (length(body) BETWEEN 1 AND 300),
    at          timestamptz NOT NULL,
    CHECK (from_player <> to_player)
);
CREATE INDEX floor_chat_pair ON floor_chat (least(from_player, to_player), greatest(from_player, to_player), id DESC);
CREATE TRIGGER floor_chat_permanent BEFORE UPDATE OR DELETE ON floor_chat FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- A deal ticket: an agreed chat line, proposed by one side, done when the other confirms.
CREATE TABLE floor_tickets (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_player  uuid NOT NULL REFERENCES players (id),
    to_player    uuid NOT NULL REFERENCES players (id),
    company_id   uuid NOT NULL REFERENCES companies (id),
    side         text NOT NULL CHECK (side IN ('buy', 'sell')),       -- the proposer's side
    quantity     bigint NOT NULL CHECK (quantity > 0),
    price        bigint NOT NULL CHECK (price > 0),
    created_at   timestamptz NOT NULL,
    valid_until  timestamptz NOT NULL,
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'declined', 'withdrawn', 'expired')),
    done_at      timestamptz,
    CHECK (from_player <> to_player)
);
CREATE INDEX floor_tickets_by_player ON floor_tickets (to_player, status);
ALTER TABLE floor_trades ADD COLUMN ticket_id bigint REFERENCES floor_tickets (id);
ALTER TABLE floor_trades ADD CONSTRAINT floor_trades_from CHECK ((request_id IS NULL) <> (ticket_id IS NULL));
