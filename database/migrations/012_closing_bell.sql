-- Stage 4, slice 4: the Closing Rush, the Closing Bell broadcast, the index kept day by
-- day, and each player's net worth day by day (design document, sections 5 and 11).

-- During the Closing Rush (the last ten minutes of the trading day) fees are reduced.
-- What an order was let off is kept beside what it paid, so the two always add up to the
-- full fee.
ALTER TABLE market_orders ADD COLUMN fee_rebate bigint NOT NULL DEFAULT 0 CHECK (fee_rebate >= 0);

-- Large orders placed during the Closing Rush, shown to everybody as they arrive:
-- the share, the side and the size. Never who placed them.
CREATE TABLE market_large_orders (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id    uuid NOT NULL REFERENCES market_instruments (company_id),
    session_date  date NOT NULL,
    side          text NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity      bigint NOT NULL CHECK (quantity > 0),
    value         bigint NOT NULL CHECK (value > 0),          -- kobo
    shown_at      timestamptz NOT NULL
);
CREATE INDEX market_large_orders_by_day ON market_large_orders (session_date, id DESC);
CREATE TRIGGER market_large_orders_permanent BEFORE UPDATE OR DELETE ON market_large_orders
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER market_large_orders_no_truncate BEFORE TRUNCATE ON market_large_orders
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- The Closing Bell: one broadcast for each trading day, put together from that day's records.
CREATE TABLE closing_bells (
    session_date  date PRIMARY KEY,
    rung_at       timestamptz NOT NULL,
    content       jsonb NOT NULL
);
CREATE TRIGGER closing_bells_permanent BEFORE UPDATE OR DELETE ON closing_bells
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER closing_bells_no_truncate BEFORE TRUNCATE ON closing_bells
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- The BSX 50 at the end of each trading day, in hundredths of a point.
CREATE TABLE index_days (
    session_date  date PRIMARY KEY,
    level         bigint NOT NULL CHECK (level > 0)
);
CREATE TRIGGER index_days_permanent BEFORE UPDATE OR DELETE ON index_days
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER index_days_no_truncate BEFORE TRUNCATE ON index_days
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- The figure the index is measured against. It starts as every company at its listing
-- price. When a company issues new shares it is raised in step, so that new shares
-- alone never move the index (only prices do).
ALTER TABLE market_status ADD COLUMN index_base numeric(40, 0) CHECK (index_base > 0);

-- What each player was worth at the end of each trading day: for their own chart only.
CREATE TABLE net_worth_days (
    account_id    uuid NOT NULL REFERENCES ledger_accounts (id),
    session_date  date NOT NULL,
    cash          bigint NOT NULL,        -- kobo, including cash held for orders and offers
    investments   bigint NOT NULL,        -- kobo, at that day's closing prices
    PRIMARY KEY (account_id, session_date)
);
CREATE TRIGGER net_worth_days_permanent BEFORE UPDATE OR DELETE ON net_worth_days
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER net_worth_days_no_truncate BEFORE TRUNCATE ON net_worth_days
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- Share splits (the rules for them come with the next change). Recorded here because
-- price history must allow for them: after a 2-for-1 split, yesterday's ₦40 is today's ₦20.
CREATE TABLE share_splits (
    company_id      uuid NOT NULL REFERENCES companies (id),
    period          integer NOT NULL,           -- it took effect as this quarter closed
    ratio           integer NOT NULL CHECK (ratio BETWEEN 2 AND 100),   -- new shares for each old one
    after_trade_id  bigint NOT NULL,            -- every trade up to this one was in old shares
    session_date    date NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, period)
);
CREATE TRIGGER share_splits_permanent BEFORE UPDATE OR DELETE ON share_splits
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER share_splits_no_truncate BEFORE TRUNCATE ON share_splits
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- How many of today's shares one share was at the time of a given trade.
CREATE FUNCTION split_factor(company uuid, trade_id bigint) RETURNS bigint LANGUAGE sql STABLE AS $$
    SELECT coalesce(round(exp(sum(ln(ratio::numeric))))::bigint, 1) FROM share_splits
     WHERE company_id = company AND after_trade_id >= trade_id
$$;

-- Shares that reached or left an account other than by a trade on the exchange: bought in
-- a share offer, received for a bond, or sold to a bidder in a takeover. Kept so that a
-- portfolio can show what its shares really cost.
CREATE TABLE holding_events (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id      uuid NOT NULL REFERENCES ledger_accounts (id),
    company_id      uuid NOT NULL REFERENCES companies (id),
    kind            text NOT NULL CHECK (kind IN ('offer', 'conversion', 'takeover')),
    shares          bigint NOT NULL CHECK (shares <> 0),      -- above zero: received; below: given up
    amount          bigint NOT NULL CHECK (amount >= 0),      -- kobo paid for them, or received for them
    after_trade_id  bigint NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX holding_events_by_account ON holding_events (account_id, id);
CREATE TRIGGER holding_events_permanent BEFORE UPDATE OR DELETE ON holding_events
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER holding_events_no_truncate BEFORE TRUNCATE ON holding_events
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();
