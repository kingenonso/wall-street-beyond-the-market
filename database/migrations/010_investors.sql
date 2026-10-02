-- Stage 4, Part A, slice 2: computer-run investors, what each company is worth, and
-- the "Why?" behind a price move (design document, section 11).

-- What a company is worth, worked out from its filed accounts each time it files.
-- It is the value today of the profits it is expected to make in future years (its
-- "net present value"): a naira expected in five years counts for less than a naira
-- today, because money today can earn interest in the meantime.
CREATE TABLE company_valuations (
    company_id       uuid NOT NULL REFERENCES companies (id),
    period           integer NOT NULL CHECK (period >= 0),
    value_per_share  bigint NOT NULL CHECK (value_per_share > 0),     -- kobo
    method           text NOT NULL CHECK (method IN ('profits', 'assets')),
    yearly_profit    bigint NOT NULL,              -- profit after tax over the past year, as filed
    growth_bps       integer NOT NULL,             -- how fast profit is expected to grow for five years
    discount_bps     integer NOT NULL,             -- the yearly return investors want for the risk
    long_run_bps     integer NOT NULL,             -- growth assumed after the fifth year
    book_per_share   bigint NOT NULL,              -- the owners' funds behind each share, kobo
    shares_in_issue  bigint NOT NULL CHECK (shares_in_issue > 0),
    reasons          jsonb NOT NULL DEFAULT '[]',  -- why it changed since the last filing, in plain words
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, period)
);
CREATE TRIGGER company_valuations_permanent BEFORE UPDATE OR DELETE ON company_valuations
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER company_valuations_no_truncate BEFORE TRUNCATE ON company_valuations
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- Which side was in a hurry: the buyer who took a waiting offer, or the seller who
-- hit a waiting bid. Empty for the opening auction, where nobody is.
ALTER TABLE market_trades ADD COLUMN taker_side text CHECK (taker_side IN ('buy', 'sell'));

-- Each computer-run investor's present view of each share.
CREATE TABLE investor_books (
    account_id    uuid NOT NULL REFERENCES ledger_accounts (id),
    company_id    uuid NOT NULL REFERENCES market_instruments (company_id),
    session_date  date NOT NULL,
    -- How far past buying or selling has moved the prices this investor asks, in hundredths
    -- of a percent. Half of it fades each trading day.
    carried_bps   integer NOT NULL DEFAULT 0,
    centre        bigint NOT NULL CHECK (centre > 0),      -- the price it is quoting around, kobo
    period        integer NOT NULL,                        -- the filing its view was last built on
    PRIMARY KEY (account_id, company_id)
);

-- One row: when the investors last acted, and whether trading is paused.
CREATE TABLE market_status (
    only_row         boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    investors_acted  timestamptz,
    acted_session    date,
    paused_until     timestamptz,           -- after a sharp fall across the whole market
    paused_session   date                   -- at most one pause in a trading day
);
INSERT INTO market_status DEFAULT VALUES;

-- The reasons behind price moves, as they happen. Shown to players under "Why?".
CREATE TABLE market_reasons (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id    uuid REFERENCES market_instruments (company_id),   -- empty for the whole market
    session_date  date NOT NULL,
    happened_at   timestamptz NOT NULL,
    reason        text NOT NULL CHECK (reason <> '')
);
CREATE INDEX market_reasons_by_company ON market_reasons (company_id, id DESC);
CREATE TRIGGER market_reasons_permanent BEFORE UPDATE OR DELETE ON market_reasons
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER market_reasons_no_truncate BEFORE TRUNCATE ON market_reasons
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();
