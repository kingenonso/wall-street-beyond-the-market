-- Prediction markets (owner, 16 November 2026: "build"). Players buy YES or NO on things the game itself decides: will
-- the Central Bank raise its rate at the quarter's close, will a company's profit beat last quarter's, will the next
-- live event be a run on a bank, will the live event's featured share fall more than 3%. A YES share pays ₦100 if it
-- happens, a NO share if it does not. The price of YES is the crowd's chance that it happens.
--
-- The computer makes the market by a rule (the logarithmic market scoring rule): there is always a price, a buyer moves
-- it, and the most the market maker can lose on a question is fixed. Every answer comes from the game's own books, so
-- nobody can rig it; the one who decides an answer (the Government Leader, on the rate) may not bet on it.

CREATE TABLE prediction_markets (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key          text NOT NULL UNIQUE,                 -- what it is about, so it is made once
    kind         text NOT NULL CHECK (kind IN ('rate_rise', 'profit_beat', 'live_kind', 'live_fall')),
    question     text NOT NULL,
    details      text NOT NULL,
    period       integer,                              -- the quarter it is about
    company_id   uuid REFERENCES companies (id),
    bell         timestamptz,                          -- the live event it is about
    baseline     bigint,                               -- what the answer is measured against (a rate, a profit)
    opened_at    timestamptz NOT NULL,
    closes_at    timestamptz NOT NULL,                 -- trading stops
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'resolved', 'void')),
    outcome      boolean,
    resolved_at  timestamptz,
    b            integer NOT NULL CHECK (b > 0),       -- the market maker's depth, in shares
    q_yes        bigint NOT NULL DEFAULT 0,            -- shares the market maker has sold of each side
    q_no         bigint NOT NULL DEFAULT 0
);
CREATE INDEX prediction_markets_open ON prediction_markets (status, closes_at);

CREATE TABLE prediction_positions (
    market_id   bigint NOT NULL REFERENCES prediction_markets (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    yes         bigint NOT NULL DEFAULT 0 CHECK (yes >= 0),
    no          bigint NOT NULL DEFAULT 0 CHECK (no >= 0),
    paid        bigint NOT NULL DEFAULT 0,             -- net money put in (bought less sold), for a refund if void
    paid_out    bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (market_id, account_id)
);

CREATE TABLE prediction_trades (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market_id   bigint NOT NULL REFERENCES prediction_markets (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    side        text NOT NULL CHECK (side IN ('yes', 'no')),
    shares      bigint NOT NULL CHECK (shares <> 0),   -- above nought bought, below sold back
    amount      bigint NOT NULL,                       -- kobo paid (or, below nought, received)
    price_after integer NOT NULL,                      -- the chance of YES after it, in hundredths of a percent
    at          timestamptz NOT NULL
);
CREATE INDEX prediction_trades_by_market ON prediction_trades (market_id, id);
CREATE TRIGGER prediction_trades_permanent BEFORE UPDATE OR DELETE ON prediction_trades FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
