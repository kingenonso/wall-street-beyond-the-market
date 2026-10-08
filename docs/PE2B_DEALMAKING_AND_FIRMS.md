# Private equity stage, Part 2B: the deal-making around companies, and firms players found

What this part adds (items 26 to 31 of the Part 2 checklist): firms that players found and run (audit
firms, small banks, risk consultancies, advisory firms), the work those firms do for other empires and
for founders, takeover offers between empires with rival offers and defences, building a stake, blocks of
shares between empires, the private-equity portfolio, truces, mergers and spin-offs, and the shadow side
inside a company an empire owns. Every naira and every share moves through the ledger.

Tests at the end of this part: **950 on the server** (of which 43 are new: 16 in
`tests/test_dealmaking.py`, 10 in `tests/test_dealmaking_loopholes.py`, 17 in `tests/test_dealmaking_review.py`),
13 on the order-matching engine, 12 on the website. All pass.

## Checklist

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| 26 | Investment Banker: run a deal start to finish, take a company public, the pitch book, underwriting, the mergers desk with hostile bids and defences, debt restructuring | Yes. An advisory firm runs a large sale for its founders (or for an empire that names it): its pitch book, if it holds up, lifts the bids by 3%, and it is paid 1% when the sale completes. Listings can be underwritten by a small bank. The banker drafts takeover offers for listed companies; the head signs; another empire may top it by 5%; an empire holding 5% of the target can have its banker write the board's defence. A failing company's loan can be restructured, paid only if it works | `test_an_advisory_firm_runs_a_sale_...`, `test_a_bank_stands_behind_a_listing_...`, `test_an_empire_offers_for_a_listed_company_a_rival_tops_it_...`, `test_a_defence_that_holds_up_...`, `test_an_advisory_firm_restructures_...` |
| 27 | Accountant: audit firms players found, refusing to sign, site visits | Yes. When founders put a company up for sale, the best audit firm audits it: accounts against the bank, the assets' age (the site visit), fees paid to insiders, then a clean opinion or a refusal. Buyers see the opinion in the data room. Signing dressed-up accounts clean costs the firm 15 points of reputation. An empire can have a company it owns audited too | `test_founders_have_a_company_on_sale_audited_...`, `test_money_taken_out_of_an_owned_company_is_found_by_an_audit_firm_...` |
| 28 | Asset Manager: stake building, block trades between empires, private-equity holdings | Yes. A stake is bought a little at each bell, up to a target below 30%; every 5% held is made public. Blocks change hands between empires within a tenth of the market price. The portfolio shows each private holding at cost and at its latest valuation, with the multiple of money | `test_a_stake_is_built_at_the_bell_...`, `test_a_block_changes_hands_...` |
| 29 | Firms players found: audit firms, small banks, risk consultancies, run from a seat; 60/40 fee split | Yes, and advisory firms. Each is founded by the matching build from a seat in an empire run by players. Of every fee, 60% goes to that empire and 40% to the founder. A small bank lends to empires from its founder's capital and can pay out its profit | `test_a_firm_is_founded_...`, `test_an_empire_sends_a_check_to_an_outside_firm_...`, `test_a_small_bank_lends_...` |
| 30 | Dealing with other heads: truces and joint bids; merging and splitting empires | Yes. A truce is a new kind of pact: no poaching, no offers or stake-building against each other's companies. (Joint bids were built in 2A as partners.) Mergers and spin-offs are voted by the members of every empire concerned; owners keep what their part was worth | `test_a_truce_stops_poaching_...`, `test_two_empires_merge_...`, `test_a_company_is_split_off_...` |
| 31 | Fair play: every naira through the ledger; nothing created by a deal; the shadow side, audits and consequences inside an owned company | Yes. A member may pay themselves "consulting fees" out of a company their empire controls. It is written in the empire's books as a cost and counts against their signing limit. The empire's own audits, or an audit firm's, can find it: the money goes back to the company, with a fine, and the member loses their seat | the loophole tests; `test_r09_...` |

## Decisions I made that you did not specify

- **Advisory firms are a fourth kind of firm** (beside audit firms, small banks and risk consultancies), since
  the banker's work of running sales, writing pitch books and restructuring loans needed a firm to belong to.
- **An outside check is paid only if it is done well.** A firm cannot be paid for a blank check.
- **Fees are capped by the size of the work:** a check on a deal at 0.5% of the asking price; an audit of an
  owned company at 1% of a quarter's sales, once a quarter.
- **A small bank lends between the Central Bank's rate and 15 points above it**, never to its founder's own
  empire, and must hold the cash to buy a whole listing before it may stand behind it.
- **The firm auditing or running a sale works for the seller**, so the empire its founder sits in may not bid.
- **An offer must be for control** (with what it holds, the bidder asks for more than half) and is held in
  cash from the moment it is announced. Banks and insurers cannot be taken over by an empire.
- **A spin-off pays the registration fee** and the new empire joins the league like any other. In the league,
  an empire merged in is not counted as growth and a company split off is not counted as a loss.
- **A restructuring of a company in a players' empire needs its head's yes.**

## The loophole check

Ten questions, one test each, in `tests/test_dealmaking_loopholes.py`:

1. Can an empire pay a firm run from inside itself, to move its money to a member? No.
2. Can offers (topped, then closed) create money or leave cash or shares held? No.
3. Can an empire offer far above a company's worth to move money to the sellers? No: half as much again at most.
4. Can a block trade move money? No: within a tenth of the market price, when offered and when taken.
5. Can an empire creep to control without an offer to every owner? No: nothing reaches 30%.
6. Can anybody see what a job or a defence is marked against? No.
7. Can a member act for a desk, a firm or an empire that is not theirs? No.
8. Can anything be done between the end of a quarter and its close? No.
9. Can an empire escape its debts by merging away? No.
10. Can a small bank lend money it does not have, or pay out its capital as profit? No.

## The independent review

A second reviewer that did not write the code found 17 problems; all are fixed, each with a test in
`tests/test_dealmaking_review.py`. The most serious: cash held for an empire's own offer was missing from its
worth, so units could have been bought cheaply while an offer stood; heads could pay a friend's firm large fees
outside every control; a selling empire could be given an adviser it never chose; a restructuring changed a
players' company's loan without its owner's consent; a success fee was paid for a failed pitch book; a merger
could leave unfinished business pointing at an empire that no longer existed. Others: a defence could be
blocked by opening it and never handing it in; ordinary trading ignored the 30% rule and truces; stolen money
was repaid to the empire rather than the company; spin-offs skipped the registration fee and could farm league
points; a bank could not sell shares it held; underwriting could be an empty promise; a sale's auditor's empire
could bid; loan offers outlived the quarter; a restructuring could go stale; two routes had no screen; shares
offered to a takeover were not counted as held. Also found by the tests: a restructured loan's record was looked
up the wrong way, and a rival offer would have counted the new bidder's own shares as sold to itself.

## The economy still holds

A ten-year run (40 quarters) with this part in: inflation stayed between 4.5% and 7.2%, the Central Bank's rate
between 11.5% and 13.5%, jobs grew from 572,000 to 743,000, the ledger audit was clean and no money moved
outside normal business. 13 private companies were sold, one failed and was wound up, ten start-ups were founded.
(Firms, offers and the rest are driven by players, so the run shows the new hooks at each bell and close do no harm.)

## Honest limits

- The computer-run empires do not found firms, make offers or build stakes; players do.
- Money taken from a company is repaid to the company; the fine goes to the empire that controls it.
- A merged empire's history stays on its own page; its open thefts nobody has found move with it.

## Screenshots

`docs/screenshots/pe2b/`: 01 founding a firm; 02 an audit job; 03 the data room with the auditor's opinion and
checks that can be sent to an outside firm; 04 drafting an offer; 05 an offer on the table and the board's
defence; 06 stakes, blocks, the portfolio and mergers; 07 a small bank; 08 on a phone.

## Run it

```powershell
cd $HOME\wall-street-beyond-the-market
git pull
docker compose up --build
```

No fresh world is needed for this part: the new tables are added to the world you already have.
