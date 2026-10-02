# Stage 2: The ledger and the 40 companies

**Test from the design:** eight game quarters run, every balance sheet balances,
and no naira appears without a recorded payer. **Status: passes.**

258 automated server tests and 12 website tests pass. The loophole check was run
on Stage 1 and Stage 2, including a review by a second AI that did not write the code.

Words used below:

- **Ledger**: the permanent book in which every movement of money or shares is written.
- **Kobo**: 1 naira = 100 kobo. All money is stored as whole kobo, so nothing is ever rounded.
- **Game quarter**: three months of game time, which is one real week.
- **Filing**: the set of accounts a company publishes at the end of a quarter.
- **Trigger**: a rule that lives inside the database and runs by itself every time a
  record is written, whatever program wrote it.

## The checklist, item by item

| # | Promised | Done | Proved by |
| --- | --- | --- | --- |
| 1 | Every movement recorded with payer, receiver, amount and reason | Yes | `test_ledger.py` (44 tests); `test_quarters.py::TestStageTwo::test_every_transaction_carries_a_reason` |
| 2 | Entries are added, never edited or deleted | Yes | `test_ledger.py` (edit, delete and wipe attempts all refused by the database) |
| 3 | Whole kobo, with the currency beside every amount | Yes | `test_ledger.py`, `test_formulas.py` (no fractions accepted; rounding rule tested) |
| 4 | Accounts for players, companies, the six banks, the Government and the prize pool | Yes | `test_world.py::test_accounts_exist_for_companies_banks_government_and_the_prize_pool` |
| 5 | A new player's ₦500,000 is paid from a named source | Yes | `test_accounts.py` (paid by the Federal Government Treasury; shown in the player's account history) |
| 6 | All 40 companies exist with names and sectors | Yes | `test_world.py::test_all_40_companies_exist_with_the_blueprint_names_and_sectors` |
| 7 | Income statement, balance sheet and cash-flow statement for each | Yes | `test_quarters.py`, `test_world.py::test_every_company_has_statements_shares_owners_debts_and_a_rating` |
| 8 | Shares in issue, owners, debts with rates and repayment dates, credit rating | Yes | `test_world.py::test_debts_have_a_lender_a_rate_and_a_repayment_date`, `test_formulas.py` (rating) |
| 9 | Accounts update each game quarter | Yes | `test_quarters.py` (closes on time, once only, in order, even with several servers) |
| 10 | The reported record is stored separately from the true record | Yes | `test_quarters.py`, `test_companies_api.py` (the website is only ever sent the filed version) |
| 11 | A list of all 40 companies by sector | Yes | `test_companies_api.py`; screenshot `screenshots/stage-02/04-companies.png` |
| 12 | A page per company with its accounts quarter by quarter | Yes | `test_companies_api.py`; screenshots `05-company-DCG.png`, `06-balance.png` |

**Stage test**: `test_quarters.py::TestStageTwo` runs eight quarters and checks four
things: eight quarters ran; every balance sheet balances, checked against the ledger
rather than against the company's own sums; every transaction carries a reason; and
no naira exists that the Central Bank did not issue on day one.

**Catch-up jobs**

| Job | Done |
| --- | --- |
| Stage 1 screens restyled to the focus-first layout | Yes. Top bar, sections menu, work area with "Needs you now", context rail. One column on phones. |
| Male and female profile icons | Yes. Chosen at sign-up, changeable on the Profile page. Uploading your own picture comes later, once pictures can be checked. |
| Loophole check on Stage 1 | Yes. See below. |

Screenshots are in `docs/screenshots/stage-02/`.

## How it works, in plain words

**The ledger.** Every payment is written as one transaction with at least two lines:
who paid (a minus amount) and who received (a plus amount). The lines must add up
to zero, so money can only move, never appear. These rules are enforced by triggers
inside the database, not just by the game's code:

1. A transaction that does not add up to zero is refused.
2. Records cannot be edited, deleted or wiped.
3. Nobody can pay out more than they hold.
4. A finished transaction is closed; nothing can be added to it later.
5. Running balances change only when a ledger line is added.
6. New money or shares can come into existence for two reasons only: the opening
   of the world, and a share issue.

**Where the money comes from.** When the world is created the Central Bank issues
₦14,710.2 billion, once. That is all the naira there is. The Federal Government
Treasury starts with ₦500 billion and pays each new player's ₦500,000 from it.

**Shares** live in the same ledger as money. Each company's shares are held by
three groups for now: founders and insiders, pension funds and institutions, and
small investors. Players can buy them when the exchange opens in Stage 4.

**The companies.** At the end of each game quarter the server closes each company's
books: sales come in from customers, costs, interest and tax are paid, debt is
repaid, a dividend is paid to owners. Each of these is a real ledger payment. The
company's accounts are then drawn up from what actually moved.

**Two records.** The true result is kept on the server. The company's *filing* is
stored separately and is the only thing players ever see. Today the two are equal.
The separation exists so that later stages can allow a dishonest company to file
false numbers and auditors, journalists and regulators to catch it.

**Credit ratings** (AAA down to D) are worked out from the filed figures: how much
the company has borrowed, how easily profit covers interest, how much cash it
holds. Each rating comes with its reasons in plain words. After eight quarters the
spread is: A 12, AAA 9, BBB 8, AA 6, BB 3, B 2.

## Decisions I made that you did not specify

| Decision | Why |
| --- | --- |
| Starting cash is paid by the Federal Government Treasury | It needed a named payer. The Treasury's reserve is finite; if it ever ran out, sign-up would be paused rather than money invented. |
| Money travels between server and website as text, e.g. `"50000000"` | Browsers lose exact kobo on very large numbers. Text never does. |
| The world remembers its own start date | So nobody can move the calendar by changing a setting later. |
| A re-count of the whole ledger runs before every quarter closes | If the books ever disagree, the quarter does not close and the fault is reported. |
| Display names: Latin letters (accents and under-dots welcome), digits, spaces, hyphens, underscores | Stops names written in look-alike letters from other alphabets. "Ada", "ada", "A da" and "Ádá" count as one name. |
| Logging out cancels the login pass on every device | A copied pass must stop working. |

## Stand-ins, to be replaced

These are simplified on purpose and flagged in the code as temporary.

| Stand-in | Replaced in | Honest note |
| --- | --- | --- |
| "Households and small businesses" is one account that buys from every company | Stage 3 | See the long-run limit below. |
| Demand is set per sector, so companies in one sector grow at the same rate | Stage 3 onwards | Rivals do not yet compete with each other. |
| The Government spends its tax straight back to the public | Stage 12 | |
| Investors spend their dividends straight back to the public | Stage 3 and 4 | |
| Banks' loans to the public and customers' deposits do not move | Stage 5 | |
| Attempt limits are counted in one server's memory | Stage 16 | Must be shared when the game runs on several servers. |

## The loophole check

The ten questions from section 19 of the design, applied to Stage 1 and Stage 2.
"Tests" are in `tests/test_loopholes.py` (74 tests) unless another file is named.

| # | Question | Answer | Tests |
| --- | --- | --- | --- |
| 1 | Forgery: can a browser send a made-up request and have it accepted? | No. Extra fields are refused. Login passes signed with the wrong key, unsigned, expired, without an expiry date, or naming a player who does not exist are refused. The website has no request that moves money. | Section 1 and "found by the reviewer" |
| 2 | Money from nothing? | No. The database refuses unbalanced transactions, overdrafts, new money for a made-up reason, look-alike currencies and an account paying itself. | `test_ledger.py`; `test_new_money_cannot_be_issued_for_a_made_up_reason` and four beside it |
| 3 | Farming: can a reward be collected again and again? | No. The starting grant is paid once per account, enforced by the database itself. | `test_the_database_itself_refuses_a_second_starting_grant` and three beside it |
| 4 | Timing: two requests at the same instant? | Safe. Ten identical sign-ups at once make one player and one grant. Several servers closing the same quarter close it once. | `test_the_same_sign_up_sent_many_times_at_once_makes_one_player`; `test_quarters.py` |
| 5 | Permissions: can a player do or change what is not theirs? | No. A player sees only their own account history and can change only their own profile picture. | Section 5 |
| 6 | Hidden information: can a player see what they should not? | No. No password, email, other player's id, account balance or true company result is ever sent. Rejected requests no longer repeat back what was typed. | Section 6; `test_companies_api.py` |
| 7 | Bad numbers: negative, enormous, fractional, nonsense? | Refused, with an ordinary "not found" or "not valid" answer rather than a crash. Oversized requests are refused before being read. | Section 7; `test_a_nonsense_ticker_is_simply_not_found` |
| 8 | Collusion: can players together drain the game? | Not applicable yet. Players have no way to pay each other; the reviewer confirmed this. It becomes a live question at Stage 4. | `test_the_website_has_no_way_to_move_money_or_change_records` |
| 9 | Many accounts and automation? | Closed as far as email allows. An account and its ₦500,000 only exist after the person types in a code sent to their email. Every spelling of one mailbox (capitals, `+tags`, Gmail dots) counts as the same address. Throwaway mailbox services are refused. One address can try 8 passwords per email and ask for 10 sign-ups per hour, then is cut off. **What remains:** a person who really owns several separate mailboxes can still open one account per mailbox. See "One email, one account" below. | "One real, confirmed email address per account" section (23 tests) |
| 10 | The clock: can time be faked, rewound or skipped? | No. Time comes from the server; quarters are closed by the database's own clock; the calendar can only move forward one quarter at a time; filings cannot be backdated or filed for a future quarter. | Section 10; `test_the_calendar_cannot_be_rewound_skipped_or_restarted` |

### What the independent reviewer found

A second AI, which had not seen the code being written, was told to break it. It
built its own copy of the world and attacked it. **It could not create, move or
destroy money or shares as a player, and could not see another player's data.** It
did find fourteen weaknesses. Each fixed one now has a test.

The four items left open are: the database login (Stage 16), the long-run limit
(Stage 3), attempt limits shared across servers (Stage 16), and people who own
several mailboxes (below).

| Finding | Severity | What was done |
| --- | --- | --- |
| 60 automated logins at once made the whole server stop answering | High | **Fixed.** Attempt limits, a cap on simultaneous password checks, more database connections, and a polite "busy, try again" instead of a crash. |
| The example secret key from `.env.example` was accepted; a copied login pass still worked after logout | High | **Fixed.** The server refuses to start with the example key. Logout cancels all passes. Passes without an expiry are refused. |
| Anyone with full control of the database could switch the ledger's rules off | High, but not reachable by a player | **Partly done.** A full re-count of the ledger now runs before every quarter closes and stops the calendar if anything disagrees. **Still open:** the game should connect to the database with a restricted login that cannot switch rules off. Planned for Stage 16. |
| Program code (not a player) could issue new money for any reason, backdate a filing, or rewind the calendar | Medium | **Fixed.** All refused by the database. |
| The starting grant could be paid twice if code spelled the player's id in capitals | Medium, not reachable by a player | **Fixed** in the code and in the database. |
| Left running for years, the economy runs down | Medium | **Not fixed. See below.** |
| Unlimited free accounts | Medium | **Fixed** as far as email allows: confirmed email, one account per mailbox. See below. |
| Sign-up says whether an email is already registered | Low | **Fixed.** The answer is the same either way; the owner of the address is told by email. |
| Look-alike and official-sounding display names | Low | **Fixed.** |
| A nonsense company code crashed the request | Low | **Fixed.** |
| No size limit on requests; error messages repeated what was typed | Low | **Fixed.** |
| An account could "pay itself" in code | Low | **Fixed.** |
| Quarter closing trusted each server's own clock | Low | **Fixed.** The database's clock decides. |
| Smaller items: the world was not created automatically in Docker; impossible dates of birth accepted | Info | **Fixed.** |

### One email, one account

Added after the first Stage 2 report, at the owner's instruction.

- **Sign-up has two steps.** Filling in the form opens nothing and pays nothing. A
  6-digit code is emailed. Only typing in the right code opens the account and pays
  the ₦500,000, once.
- **One account per mailbox.** `ada@gmail.com`, `Ada@Gmail.com`, `a.d.a@gmail.com`
  and `ada+second@gmail.com` all deliver to the same inbox, so they count as one
  address. The database itself refuses a second player on the same mailbox.
- **Codes cannot be guessed.** A code lasts 15 minutes, is thrown away after five
  wrong guesses, is cancelled when a new one is asked for, and is stored only in
  scrambled form.
- **Throwaway mailbox services are refused.** The list covers the well-known ones
  and cannot ever be complete.
- **The form does not reveal who plays.** The answer is identical whether or not
  the address already has an account.
- **On your own computer** no email service is connected, so the code is shown on
  the sign-up screen, clearly marked as test mode. A real website must be given an
  email service (the `SMTP_` lines in `.env`) or the server refuses to start.

**Not yet proved:** sending through a real email provider. The sending code is
written and the flow is tested with a stand-in for the provider, but no real
email has been sent, because no provider account exists yet.

**What email cannot stop:** a person who owns several real, separate mailboxes
can open one account on each. Stronger checks exist (a phone number confirmed by
text message; releasing the ₦500,000 in parts as the player actually plays) and
are a decision for the owner before Stage 4, when players can first trade.

### The long-run limit, stated plainly

The reviewer ran the world for 320 game quarters (over six real years). With the
Stage 2 stand-ins, money slowly piles up inside companies and banks and does not
flow back to customers. Customers start running short around **quarter 29, about
seven real months in**; companies begin defaulting from quarter 41.

This is a weakness of the stand-in "public" account, not of the ledger: no money
is lost or created, it simply stops circulating. Stage 3 replaces the stand-in
with households that earn wages, save and borrow, which is what makes money
circulate in a real economy. A long-run test (at least 80 quarters without the
economy seizing up) should be part of the Stage 3 checklist.

## Run it and look around

```
cp .env.example .env        # then put your own random text in SECRET_KEY
docker compose up --build
```

Open http://localhost:5173 and create an account. You will be asked for a 6-digit
code; on your own computer it is shown on the same screen. Then:

- **My desk**: what needs you now, the biggest moves in sales, and your account
  history showing the ₦500,000 paid by the Federal Government Treasury.
- **Companies**: all 40, by sector, with sales, profit and credit rating.
- Click any company: its chart, why sales moved, the three statements quarter by
  quarter, why it has its rating, who owns it and what it owes.
- **Profile**: change your profile picture.

If you ran Stage 1 before, run `docker compose down -v` first. This wipes the old
database so the new world can be created.
