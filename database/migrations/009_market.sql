-- Stage 4, Part A: the Broad Street Exchange (design document, section 11).
--
-- Players and computer-run investors buy and sell companies' shares. The order
-- book lives here in the database. The order-matching engine (written in Rust)
-- only says who trades with whom; every trade is then settled through the ledger.
--
-- Words used here:
--   order        an instruction to buy or sell a number of shares
--   limit order  "at this price or better"; it waits in the order book until matched
--   market order "at the best price available now"; what cannot be matched is cancelled
--   reserve      when an order is placed, the cash (to buy) or the shares (to sell) are
--                moved to the exchange to hold, so the same cash or shares cannot be
--                promised twice

-- The exchange holds reserved cash and shares, and collects its fees.
ALTER TABLE ledger_accounts DROP CONSTRAINT ledger_accounts_kind_check;
ALTER TABLE ledger_accounts ADD CONSTRAINT ledger_accounts_kind_check CHECK (kind IN (
    'central_bank', 'government', 'prize_pool', 'npc_public', 'npc_investors', 'company', 'player', 'exchange'));

-- One row for each share that can be traded.
CREATE TABLE market_instruments (
    company_id       uuid PRIMARY KEY REFERENCES companies (id),
    asset            text NOT NULL UNIQUE REFERENCES assets (code),
    listing_price    bigint NOT NULL CHECK (listing_price > 0),     -- kobo per share, when the share was first listed
    -- The price the day's limits are measured from: the last price of the session before.
    reference_price  bigint NOT NULL CHECK (reference_price > 0),
    last_price       bigint CHECK (last_price > 0),                 -- the latest trade; empty until the first one
    session_date     date NOT NULL,                                 -- the trading day these figures belong to
    auction_done     boolean NOT NULL DEFAULT false,                -- whether that day's opening auction has been run
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE market_orders (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- also the order's place in the queue
    account_id     uuid NOT NULL REFERENCES ledger_accounts (id),
    company_id     uuid NOT NULL REFERENCES market_instruments (company_id),
    side           text NOT NULL CHECK (side IN ('buy', 'sell')),
    kind           text NOT NULL CHECK (kind IN ('limit', 'market')),
    limit_price    bigint CHECK (limit_price > 0),                   -- kobo per share; empty for a market order
    quantity       bigint NOT NULL CHECK (quantity > 0),
    remaining      bigint NOT NULL CHECK (remaining >= 0),           -- shares not yet traded
    reserved       bigint NOT NULL CHECK (reserved >= 0),            -- kobo the exchange holds for a buy order
    value_filled   bigint NOT NULL DEFAULT 0 CHECK (value_filled >= 0),
    fees_paid      bigint NOT NULL DEFAULT 0 CHECK (fees_paid >= 0),
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'filled', 'cancelled', 'expired')),
    closed_reason  text,
    placed_at      timestamptz NOT NULL,
    closed_at      timestamptz,
    CHECK (remaining <= quantity),
    CHECK ((kind = 'limit') = (limit_price IS NOT NULL)),
    CHECK ((status = 'open') = (closed_at IS NULL)),
    CHECK (status <> 'filled' OR remaining = 0),
    CHECK (status = 'open' OR reserved = 0),                         -- nothing stays reserved for a closed order
    CHECK (side = 'buy' OR reserved = 0)                             -- a sell order reserves shares, not cash
);
CREATE INDEX market_orders_book ON market_orders (company_id, side, limit_price, id) WHERE status = 'open';
CREATE INDEX market_orders_by_account ON market_orders (account_id, id DESC);
CREATE INDEX market_orders_open_by_account ON market_orders (account_id) WHERE status = 'open';

-- What an order IS can never change: who placed it, for which share, which way, how many,
-- at what price. Only its progress moves, and only forwards.
CREATE FUNCTION market_orders_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Orders are never deleted. A cancelled order stays on record.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'market_orders_permanent';
    END IF;
    IF (NEW.id, NEW.account_id, NEW.company_id, NEW.side, NEW.kind, NEW.quantity, NEW.placed_at)
           IS DISTINCT FROM (OLD.id, OLD.account_id, OLD.company_id, OLD.side, OLD.kind, OLD.quantity, OLD.placed_at)
       OR NEW.limit_price IS DISTINCT FROM OLD.limit_price THEN
        RAISE EXCEPTION 'An order cannot be changed once placed. Cancel it and place a new one.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'market_orders_fixed';
    END IF;
    IF OLD.status <> 'open' THEN
        RAISE EXCEPTION 'That order is closed. Nothing about it can change.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'market_orders_closed';
    END IF;
    IF NEW.remaining > OLD.remaining OR NEW.value_filled < OLD.value_filled OR NEW.fees_paid < OLD.fees_paid
       OR NEW.reserved > OLD.reserved THEN
        RAISE EXCEPTION 'An order only moves forwards: shares left and cash held can only go down.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'market_orders_forwards';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER market_orders_guard BEFORE UPDATE OR DELETE ON market_orders
    FOR EACH ROW EXECUTE FUNCTION market_orders_guard();
CREATE TRIGGER market_orders_no_truncate BEFORE TRUNCATE ON market_orders
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- Every trade, for ever.
CREATE TABLE market_trades (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id         uuid NOT NULL REFERENCES market_instruments (company_id),
    price              bigint NOT NULL CHECK (price > 0),             -- kobo per share
    quantity           bigint NOT NULL CHECK (quantity > 0),
    buy_order_id       bigint NOT NULL REFERENCES market_orders (id),
    sell_order_id      bigint NOT NULL REFERENCES market_orders (id),
    buyer_account_id   uuid NOT NULL REFERENCES ledger_accounts (id),
    seller_account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    buyer_fee          bigint NOT NULL CHECK (buyer_fee >= 0),
    seller_fee         bigint NOT NULL CHECK (seller_fee >= 0),
    in_auction         boolean NOT NULL,
    -- Buyer and seller are the same account. It is allowed (and costs fees twice), and it is
    -- recorded: making a price look busier than it is will matter when the law stages arrive.
    same_owner         boolean NOT NULL,
    session_date       date NOT NULL,
    ledger_transaction uuid NOT NULL REFERENCES ledger_transactions (id),
    traded_at          timestamptz NOT NULL
);
CREATE INDEX market_trades_by_company ON market_trades (company_id, id DESC);
CREATE TRIGGER market_trades_permanent BEFORE UPDATE OR DELETE ON market_trades
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER market_trades_no_truncate BEFORE TRUNCATE ON market_trades
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();
