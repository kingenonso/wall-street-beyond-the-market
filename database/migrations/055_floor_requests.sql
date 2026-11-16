-- The Floor, slice 2 (owner, 16 November 2026): price requests. A player asks one to five banks for a price on a share,
-- with a countdown; each bank answers with its prices and how long they hold; the player takes the best, and the shares
-- and the money change hands at once, away from the exchange (as the owner played it in the investing challenge).
--
-- The banks are the investment bankers who open a desk, and six computer banks so there is always competition. Computer
-- clients send requests to the players' desks, so a banker always has work.

-- A banker's desk: open when they are there to answer, so nobody is sent requests they cannot see.
CREATE TABLE floor_desks (
    player_id   uuid PRIMARY KEY REFERENCES players (id),
    open        boolean NOT NULL DEFAULT false,
    changed_at  timestamptz NOT NULL,
    failed      integer NOT NULL DEFAULT 0 CHECK (failed >= 0)     -- deals it could not deliver: shown to its clients
);

CREATE TABLE floor_requests (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_account  uuid NOT NULL REFERENCES ledger_accounts (id),
    client_player   uuid REFERENCES players (id),                  -- none for a computer client
    client_name     text,                                          -- a computer client's name
    company_id      uuid NOT NULL REFERENCES companies (id),
    side            text NOT NULL CHECK (side IN ('buy', 'sell', 'two_way')),   -- two_way: the client does not say which
    quantity        bigint NOT NULL CHECK (quantity > 0),
    created_at      timestamptz NOT NULL,
    quotes_until    timestamptz NOT NULL,                          -- the banks' countdown
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'passed', 'expired')),
    done_at         timestamptz,
    CHECK (quotes_until > created_at AND (client_player IS NOT NULL OR client_name IS NOT NULL))
);
CREATE INDEX floor_requests_open ON floor_requests (status, quotes_until) WHERE status = 'open';
CREATE INDEX floor_requests_by_client ON floor_requests (client_account, id DESC);

-- The banks a request went to: a player's desk, or a computer bank by its code.
CREATE TABLE floor_request_desks (
    request_id   bigint NOT NULL REFERENCES floor_requests (id),
    desk         text NOT NULL,                                    -- 'player:<uuid>' or 'computer:<code>'
    desk_player  uuid REFERENCES players (id),
    PRIMARY KEY (request_id, desk)
);
CREATE INDEX floor_request_desks_by_player ON floor_request_desks (desk_player, request_id DESC) WHERE desk_player IS NOT NULL;

CREATE TABLE floor_quotes (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id   bigint NOT NULL REFERENCES floor_requests (id),
    desk         text NOT NULL,
    bid          bigint CHECK (bid > 0),                           -- the bank buys at this
    offer        bigint CHECK (offer > 0),                         -- the bank sells at this
    created_at   timestamptz NOT NULL,
    shown_at     timestamptz NOT NULL,                             -- a computer bank takes a few seconds to answer
    valid_until  timestamptz NOT NULL,
    status       text NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'replaced', 'taken', 'failed', 'lost')),
    CHECK (bid IS NOT NULL OR offer IS NOT NULL),
    CHECK (bid IS NULL OR offer IS NULL OR bid < offer),
    CHECK (valid_until > shown_at AND shown_at >= created_at),
    FOREIGN KEY (request_id, desk) REFERENCES floor_request_desks (request_id, desk)
);
CREATE INDEX floor_quotes_by_request ON floor_quotes (request_id, id);

-- Every deal done on the Floor. Permanent.
CREATE TABLE floor_trades (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id      bigint NOT NULL UNIQUE REFERENCES floor_requests (id),
    quote_id        bigint NOT NULL REFERENCES floor_quotes (id),
    company_id      uuid NOT NULL REFERENCES companies (id),
    buyer_account   uuid NOT NULL REFERENCES ledger_accounts (id),
    seller_account  uuid NOT NULL REFERENCES ledger_accounts (id),
    price           bigint NOT NULL CHECK (price > 0),
    quantity        bigint NOT NULL CHECK (quantity > 0),
    desk            text NOT NULL,
    at              timestamptz NOT NULL,
    CHECK (buyer_account <> seller_account)
);
CREATE INDEX floor_trades_by_buyer ON floor_trades (buyer_account, id DESC);
CREATE INDEX floor_trades_by_seller ON floor_trades (seller_account, id DESC);
CREATE TRIGGER floor_trades_permanent BEFORE UPDATE OR DELETE ON floor_trades FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- A deal on the Floor is a trade away from the exchange: its shares are recorded for each side's cost, as a block is.
ALTER TABLE holding_events DROP CONSTRAINT holding_events_kind_check;
ALTER TABLE holding_events ADD CONSTRAINT holding_events_kind_check CHECK (kind IN ('offer', 'conversion', 'takeover', 'block', 'floor'));
