-- Stage 12: commodities — the goods themselves, the space they are kept in, and the desk
-- that deals in them.
--
-- The exchange already lists futures on gold (the metals index), oil, farm produce and
-- building materials, and settles them in cash. What has never existed is the goods: no
-- player has ever owned a gram of gold or a barrel of oil. This change adds them.
--
-- The goods are NOT a ledger asset. Money stays kobo in the ledger; goods are counted in
-- their own unit (a gram, a barrel, a bag, a tonne) and belong to a ledger account. Every
-- trade moves naira through the ledger and units through these tables, in one transaction,
-- so a player can never be paid and not delivered, or delivered and not charged.
--
-- The spot price of a good is never stored as a decision: it is fixed to the contract the
-- exchange already lists (one contract is so many units), so the price of the goods and the
-- price of a future cannot drift apart. What is stored is a reading each quarter, for the
-- record and for the screen.

-- ---------------------------------------------------------------------------
-- The goods, and what a space holds. Seeded once, then read.
-- ---------------------------------------------------------------------------
CREATE TABLE commodity_goods (
    code               text PRIMARY KEY,
    name               text NOT NULL,                        -- "gold", in the middle of a sentence
    unit               text NOT NULL,                        -- "a gram"
    unit_plural        text NOT NULL,                        -- "grams"
    unit_word          text NOT NULL,                        -- "g", on a tight line
    underlying         text NOT NULL,                        -- the exchange's code for its future: METALS, OIL, FARM, MATERIALS
    units_per_contract bigint NOT NULL CHECK (units_per_contract > 0),
    space              text NOT NULL CHECK (space IN ('vault', 'tank', 'silo', 'yard')),
    space_name         text NOT NULL,                        -- "a vault", in a sentence
    units_per_space    bigint NOT NULL CHECK (units_per_space > 0),
    spread_bps         integer NOT NULL CHECK (spread_bps >= 0),   -- a side, round the true price
    rent_bps           integer NOT NULL CHECK (rent_bps >= 0),     -- a quarter, of the value the space holds
    insurance_bps      integer NOT NULL CHECK (insurance_bps >= 0),-- a quarter, of the value of the goods insured
    loss_bps           integer NOT NULL CHECK (loss_bps >= 0),     -- the chance a quarter that a space is damaged
    lost_share_bps     integer NOT NULL CHECK (lost_share_bps >= 0),-- and how much of what it holds goes with it
    least_units        bigint NOT NULL CHECK (least_units > 0)     -- the smallest purchase a player may make
);

INSERT INTO commodity_goods (code, name, unit, unit_plural, unit_word, underlying, units_per_contract, space, space_name,
                             units_per_space, spread_bps, rent_bps, insurance_bps, loss_bps, lost_share_bps, least_units)
VALUES ('GOLD', 'gold', 'a gram', 'grams', 'g', 'METALS', 10, 'vault', 'a vault', 100, 25, 50, 20, 200, 5000, 1),
       ('OIL', 'oil', 'a barrel', 'barrels', 'bbl', 'OIL', 10, 'tank', 'a tank farm', 100, 50, 200, 20, 200, 5000, 1),
       ('FARM', 'farm produce', 'a 50 kg bag', 'bags', 'bag', 'FARM', 20, 'silo', 'a silo', 200, 100, 300, 20, 400, 7500, 1),
       ('MATERIALS', 'building materials', 'a tonne', 'tonnes', 't', 'MATERIALS', 10, 'yard', 'a yard', 100, 100, 200, 20, 200, 5000, 1);

-- ---------------------------------------------------------------------------
-- The market's own book: what the dealers hold of each good, and what they started with.
-- (Their cash is a ledger account like any other; stock is the other side of it.)
-- ---------------------------------------------------------------------------
CREATE TABLE commodity_market (
    good        text PRIMARY KEY REFERENCES commodity_goods (code),
    stock       bigint NOT NULL DEFAULT 0,        -- what the dealers hold now
    opening     bigint NOT NULL CHECK (opening >= 0),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO commodity_market (good, stock, opening)
VALUES ('GOLD', 20000, 20000),            -- 20 kg of gold: about ₦2 billion at par
       ('OIL', 100000, 100000),           -- a hundred thousand barrels
       ('FARM', 100000, 100000),          -- a hundred thousand bags: 5,000 tonnes
       ('MATERIALS', 50000, 50000);       -- fifty thousand tonnes

-- ---------------------------------------------------------------------------
-- A reading of the spot price each quarter. Permanent: a price once read is history.
-- ---------------------------------------------------------------------------
CREATE TABLE commodity_prices (
    period      integer NOT NULL,
    good        text NOT NULL REFERENCES commodity_goods (code),
    spot        bigint NOT NULL CHECK (spot > 0),      -- kobo for one unit
    bid         bigint NOT NULL CHECK (bid >= 0),
    ask         bigint NOT NULL CHECK (ask > 0),
    previous    bigint,                                -- the quarter before, so a screen can draw a move
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (period, good)
);
CREATE TRIGGER commodity_prices_permanent BEFORE UPDATE OR DELETE ON commodity_prices
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- Space: leased from the market's warehouse operator, by the unit, paid for by the quarter.
-- A lease is a thing with a life: opened, and either still open, given up, or lost for
-- non-payment. It is never deleted.
-- ---------------------------------------------------------------------------
CREATE TABLE commodity_storage (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account       uuid NOT NULL REFERENCES ledger_accounts (id),
    good          text NOT NULL REFERENCES commodity_goods (code),
    capacity      bigint NOT NULL CHECK (capacity > 0),      -- in goods units
    insured       boolean NOT NULL DEFAULT false,
    lease_paid    bigint NOT NULL CHECK (lease_paid > 0),    -- what the lease itself cost, once (kobo)
    opened_period integer NOT NULL,
    opened_at     timestamptz NOT NULL,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'lost', 'closed')),
    close_reason  text,
    closed_at     timestamptz
);
CREATE INDEX commodity_storage_owner ON commodity_storage (account, good, status);

-- ---------------------------------------------------------------------------
-- What is held, lot by lot, in a lease. A lot keeps what it cost, so a holder can be shown
-- what they made or lost on it rather than only what it is worth today.
-- ---------------------------------------------------------------------------
CREATE TABLE commodity_holdings (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account       uuid NOT NULL REFERENCES ledger_accounts (id),
    good          text NOT NULL REFERENCES commodity_goods (code),
    storage_id    bigint NOT NULL REFERENCES commodity_storage (id),
    units         bigint NOT NULL CHECK (units > 0),
    cost          bigint NOT NULL CHECK (cost >= 0),          -- kobo paid for the units still in the lot
    bought_period integer NOT NULL,
    bought_at     timestamptz NOT NULL
);
CREATE INDEX commodity_holdings_owner ON commodity_holdings (account, good);
CREATE INDEX commodity_holdings_space ON commodity_holdings (storage_id);

-- ---------------------------------------------------------------------------
-- Every trade with the market. Permanent.
-- ---------------------------------------------------------------------------
CREATE TABLE commodity_trades (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account      uuid NOT NULL REFERENCES ledger_accounts (id),
    good         text NOT NULL REFERENCES commodity_goods (code),
    side         text NOT NULL CHECK (side IN ('buy', 'sell')),
    units        bigint NOT NULL CHECK (units > 0),
    price        bigint NOT NULL CHECK (price > 0),           -- kobo a unit, what was actually paid
    storage_id   bigint REFERENCES commodity_storage (id),
    period       integer NOT NULL,
    at           timestamptz NOT NULL
);
CREATE INDEX commodity_trades_owner ON commodity_trades (account, id DESC);
CREATE TRIGGER commodity_trades_permanent BEFORE UPDATE OR DELETE ON commodity_trades
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- What happened to goods that nobody chose: rent taken from the cash, a space damaged, a
-- lease lost, a delivery that arrived and one that had to be settled in cash instead.
-- ---------------------------------------------------------------------------
CREATE TABLE commodity_events (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account  uuid NOT NULL REFERENCES ledger_accounts (id),
    good     text REFERENCES commodity_goods (code),
    kind     text NOT NULL CHECK (kind IN ('rent', 'insurance', 'loss', 'seized', 'delivery', 'delivery_refused')),
    amount   bigint NOT NULL DEFAULT 0,          -- kobo, where money moved
    units    bigint NOT NULL DEFAULT 0,          -- goods, where goods moved
    words    text NOT NULL,
    period   integer NOT NULL,
    at       timestamptz NOT NULL
);
CREATE INDEX commodity_events_account ON commodity_events (account, id DESC);

-- ---------------------------------------------------------------------------
-- Delivery: a long futures contract that asks for the goods instead of the cash.
-- It is a request, made before the quarter's close, and the goods only arrive if there is
-- room and cash for them.
-- ---------------------------------------------------------------------------
ALTER TABLE derivative_positions ADD COLUMN take_delivery boolean NOT NULL DEFAULT false;
ALTER TABLE derivative_positions ADD COLUMN delivered_units bigint NOT NULL DEFAULT 0;

-- ---------------------------------------------------------------------------
-- The firm's door: a commodities desk at an empire (a bank or any firm), what the head
-- allows it to risk, what it quoted, what was taken up, and how it hedged on the exchange.
-- ---------------------------------------------------------------------------
CREATE TABLE commodity_desks (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id     bigint NOT NULL REFERENCES empires (id),
    limit_kobo    bigint NOT NULL CHECK (limit_kobo > 0),     -- the most the desk may owe on any one day
    opened_period integer NOT NULL,
    opened_at     timestamptz NOT NULL,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'shut')),
    closed_period integer,
    UNIQUE (empire_id)
);

CREATE TABLE commodity_quotes (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    desk_id       bigint NOT NULL REFERENCES commodity_desks (id),
    company_id    uuid NOT NULL REFERENCES companies (id),
    good          text NOT NULL REFERENCES commodity_goods (code),
    side          text NOT NULL CHECK (side IN ('buy', 'sell')),   -- what the client does: buys the good (a user) or sells it (a producer)
    units         bigint NOT NULL CHECK (units > 0),
    price         bigint NOT NULL CHECK (price > 0),          -- kobo a unit, fixed for the client
    fee           bigint NOT NULL CHECK (fee >= 0),           -- kobo, the desk's charge
    expiry_period integer NOT NULL,
    status        text NOT NULL DEFAULT 'quoted'
                  CHECK (status IN ('quoted', 'accepted', 'declined', 'expired', 'settled', 'failed')),
    quoted_period integer NOT NULL,
    quoted_at     timestamptz NOT NULL,
    decided_at    timestamptz,
    settled_at    timestamptz,
    client_paid   bigint NOT NULL DEFAULT 0,                  -- what has moved each way with the client
    desk_paid     bigint NOT NULL DEFAULT 0
);
CREATE INDEX commodity_quotes_desk ON commodity_quotes (desk_id, status);
CREATE INDEX commodity_quotes_company ON commodity_quotes (company_id, status);
-- A quote has a price and a size, and neither is rewritten once it is made: what changes is
-- whether the client took it. (Records are added, never edited: working rule 8.)
CREATE FUNCTION commodity_quotes_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.desk_id <> OLD.desk_id
       OR NEW.company_id <> OLD.company_id
       OR NEW.good <> OLD.good
       OR NEW.side <> OLD.side
       OR NEW.units <> OLD.units
       OR NEW.price <> OLD.price
       OR NEW.fee <> OLD.fee
       OR NEW.expiry_period <> OLD.expiry_period
       OR NEW.quoted_period <> OLD.quoted_period
       OR NEW.quoted_at <> OLD.quoted_at THEN
        RAISE EXCEPTION 'A quote''s terms are never changed once it is made';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER commodity_quotes_guard BEFORE UPDATE ON commodity_quotes
    FOR EACH ROW EXECUTE FUNCTION commodity_quotes_guard();

-- The desk's hedge on the exchange: the contracts it holds against an accepted quote.
CREATE TABLE commodity_hedges (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    desk_id     bigint NOT NULL REFERENCES commodity_desks (id),
    quote_id    bigint NOT NULL REFERENCES commodity_quotes (id),
    series_id   bigint NOT NULL REFERENCES derivative_series (id),
    contracts   bigint NOT NULL CHECK (contracts > 0),
    position_id bigint REFERENCES derivative_positions (id),
    placed_at   timestamptz NOT NULL,
    placed_period integer NOT NULL
);
CREATE INDEX commodity_hedges_desk ON commodity_hedges (desk_id);

-- What the desk did each quarter, closed and kept. Permanent.
CREATE TABLE commodity_desk_results (
    desk_id        bigint NOT NULL REFERENCES commodity_desks (id),
    period         integer NOT NULL,
    quoted         integer NOT NULL DEFAULT 0,
    accepted       integer NOT NULL DEFAULT 0,
    fees           bigint NOT NULL DEFAULT 0,
    hedged_units   bigint NOT NULL DEFAULT 0,
    client_paid    bigint NOT NULL DEFAULT 0,
    desk_paid      bigint NOT NULL DEFAULT 0,
    closed_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (desk_id, period)
);
CREATE TRIGGER commodity_desk_results_permanent BEFORE UPDATE OR DELETE ON commodity_desk_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
