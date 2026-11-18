-- Floor extras, slice 2 (owner, 17 November 2026: "go on"): the bank desk.
--
-- A client asks the Floor for money: how much, for how many days, and which banks. Each bank prices the loan as a yearly
-- interest rate, having looked at the client's credit file; the client takes the cheapest it likes. The lender pays the
-- money over at once, and on the due day the borrower pays it back with the interest. A player who cannot pay owes the
-- rest as a debt in default; a computer client who fails pays back only part, and the lender bears the loss.

CREATE TABLE floor_loan_asks (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_account uuid NOT NULL REFERENCES ledger_accounts (id),
    client_player  uuid REFERENCES players (id),             -- empty for a computer client
    client_name    text NOT NULL,
    purpose        text NOT NULL,
    grade          text NOT NULL CHECK (grade IN ('A', 'B', 'C', 'D')),
    amount         bigint NOT NULL CHECK (amount > 0),
    days           integer NOT NULL CHECK (days BETWEEN 1 AND 30),
    created_at     timestamptz NOT NULL,
    quotes_until   timestamptz NOT NULL,
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'taken', 'passed', 'expired')),
    done_at        timestamptz
);
CREATE INDEX floor_loan_asks_open ON floor_loan_asks (status, quotes_until);

CREATE TABLE floor_loan_ask_desks (
    ask_id      integer NOT NULL REFERENCES floor_loan_asks (id),
    desk        text NOT NULL,
    desk_player uuid REFERENCES players (id),
    PRIMARY KEY (ask_id, desk)
);
CREATE INDEX floor_loan_ask_desks_player ON floor_loan_ask_desks (desk_player);

CREATE TABLE floor_loan_quotes (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ask_id     integer NOT NULL REFERENCES floor_loan_asks (id),
    desk       text NOT NULL,
    rate_bps   integer NOT NULL CHECK (rate_bps > 0),          -- a yearly rate
    created_at timestamptz NOT NULL,
    status     text NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'won', 'lost', 'withdrawn'))
);
CREATE UNIQUE INDEX floor_loan_quotes_one_live ON floor_loan_quotes (ask_id, desk) WHERE status = 'live';

CREATE TABLE floor_loans (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ask_id           integer NOT NULL UNIQUE REFERENCES floor_loan_asks (id),
    quote_id         integer NOT NULL REFERENCES floor_loan_quotes (id),
    lender_desk      text NOT NULL,
    lender_account   uuid NOT NULL REFERENCES ledger_accounts (id),
    lender_player    uuid REFERENCES players (id),
    borrower_account uuid NOT NULL REFERENCES ledger_accounts (id),
    borrower_player  uuid REFERENCES players (id),
    borrower_name    text NOT NULL,
    grade            text NOT NULL,
    principal        bigint NOT NULL CHECK (principal > 0),
    rate_bps         integer NOT NULL CHECK (rate_bps > 0),
    days             integer NOT NULL,
    starts_at        timestamptz NOT NULL,
    due_at           timestamptz NOT NULL,
    status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'repaid', 'shortfall', 'defaulted')),
    interest         bigint NOT NULL DEFAULT 0,              -- the interest due when it closed
    paid             bigint NOT NULL DEFAULT 0,              -- what the lender was paid back
    lost             bigint NOT NULL DEFAULT 0,              -- what the lender lost (a computer client that failed)
    closed_at        timestamptz,
    CHECK (lender_account <> borrower_account)
);
CREATE INDEX floor_loans_open ON floor_loans (status, due_at);
CREATE INDEX floor_loans_lender ON floor_loans (lender_player);
CREATE INDEX floor_loans_borrower ON floor_loans (borrower_account);

ALTER TABLE floor_notes DROP CONSTRAINT floor_notes_kind_check;
ALTER TABLE floor_notes ADD CONSTRAINT floor_notes_kind_check CHECK (kind IN ('nudge', 'drop', 'hour', 'storm', 'risk', 'loan'));
