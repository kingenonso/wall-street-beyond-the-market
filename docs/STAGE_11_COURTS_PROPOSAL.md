# Stage 11 proposal: the courts, as a docket

**This is a proposal for the owner to approve. Nothing has been built.**

Written on 6 November 2026. The build stands at Part 4c (six new industries), which is built but not
closed: items 35, 36 and 38 of `docs/PART_4C_CHECKLIST.md` are still open.

The owner's answers, given on 6 November 2026:

- ten case types, in four groups, rather than the three first proposed;
- the regulator and players both bring cases, players posting a bond;
- a Court page of its own.

## The principle: a docket, not a courtroom

The court's subject is money, its evidence is the ledger, and its remedy is money moving. It is not a
place where guilt is decided. It is a place where a number is proved and paid.

That single choice decides most of what follows. The game already has the two things a financial court
needs and almost no other game has: a complete ledger, where every naira has a recorded payer, and a
hard separation between what a company files (`company_reports`) and what is true (`company_results`).
So the court never asserts a loss. It computes one, and the verdict reads like arithmetic.

## What is cut from the earlier plan

Earlier stages promised Stage 11 a great deal. These are dropped, and the reason is given so that
nobody reopens them from an old report.

1. **Juries.** Stage 6 promised "courts and juries (Stage 11)". A jury decides guilt, and guilt is the
   one question a financial court does not need to ask. The question is quantum, and quantum is read
   off the ledger. The human judgment in this system is the regulator's decision to bring a case at
   all, and that is a better place for it.
2. **Criminal guilt, and anything that implies prison.** Several reports say wrongdoing will be
   "prosecuted". The remedy here is money and market access: disgorgement, damages, fines, trading
   bans, licence revocation. Nobody goes to jail; they go broke.
3. **The courtroom as a scene.** No gallery, no testimony, no cross-examination, no judge's remarks.
   The screen is a docket: a list of claims, each with a number, and a settle-or-fight decision.
4. **Forensic cases as a standalone feature.** Stage 5 lists "forensic cases (Stage 11)" as its own
   thing. It is not. Forensic accounting is the evidence mechanic inside every case — what turns a
   suspicion into a number. As a separate feature it is a minigame; as the evidence layer it is the
   accountant build's reason to exist.
5. **Conveyancing disputes.** `simulation/conveyancing.py` says a dispute nobody settles fades after
   eight quarters "in Stage 11". It keeps fading. A title dispute is property law, it belongs to a
   different build, and it would drag a second subject matter into a stage about markets.
6. **The assumption that every recorded wrongdoing becomes a trial.** The game already records planted
   rumours, confidential dealings, false accounts and proved thefts. If each becomes a hearing, the
   docket drowns. Enforcement is probabilistic instead: the records raise the chance of a case, and
   only some become one. That is the better model, not a shortcut — enforcement risk is what prices
   behaviour, and certainty of prosecution teaches nothing about risk.
7. **The criminal standard of proof.** "Beyond reasonable doubt" is uncomputable and invites argument.
   The standard is financial: the claim is proved if the ledger supports the number.
8. **The former partner's claim on a sold company.** `simulation/firm_deals.py` already sends it to
   court the quarter after a sale, and it works. It is not rebuilt here; the new docket reads it.

## The case types

Ten kinds of financial wrong, in four groups. Each is chosen because the evidence already exists in
the database, and each has a number that can be read off the record rather than argued about.

### Against the market

#### 1. Dealing on confidential information

**Evidence.** `confidential_dealings`, recorded since Stage 10B
(`database/migrations/033_stage10b_intelligence.sql`). Every trade made on a tip while the tip was
still useful is already there, with the player, the account, the company and the time.

**The number.** The profit on the informed trade: the difference between the price paid and the price
at the close of the position, read from `market_trades`.

**The remedy.** Disgorgement of the profit, plus a fine of the same again. The profit goes to the
compensation fund; the fine to the Government.

**Who brings it.** The regulator, or a player who can show they traded the other side of the informed
trade.

#### 2. Manipulation — ramping and wash trading

**Evidence.** `market_orders` and `market_trades`. A wash trade is one where buyer and seller are the
same account, and the portfolio code already has a branch for exactly that case — "traded with itself:
only the fees moved" (`simulation/marketview.py`). Ramping is a run of buys that lifts the price,
followed by sales into the rise.

**The number.** The gain from the move: the price before the campaign against the price achieved on the
sales.

**The remedy.** Disgorgement, a fine, a trading ban.

**Who brings it.** The regulator.

#### 3. Failure to disclose a stake

**Evidence.** The rule already exists. `simulation/firm_dealmaking.py` says "every 5% step held in a
listed company is made public, by anybody's route to it". A step that was not disclosed is a breach of
a rule the game already enforces, and the holdings record shows the step.

**The number.** The profit on the undisclosed stake, or the loss to those who traded without knowing.

**The remedy.** A fine, disgorgement, and the stake cannot be voted while the case is open.

**Who brings it.** The regulator, or a shareholder.

#### 4. Naked short selling and failure to deliver

**Evidence.** `simulation/lending.py` — shorts are borrowed from the pension funds at 2% a year, with
150% collateral. A short with no borrow behind it, or borrowed shares not returned, is visible in the
same records.

**The number.** The cost to the lender, or the profit on the uncovered short.

**The remedy.** Restitution to the lender, a fine, a trading ban.

**Who brings it.** The lender, or the regulator.

### Against the company

#### 5. False accounts

**Evidence.** `company_reports` against `company_results`. Today they always agree — the migration
says so plainly: "Today every company reports honestly, so the two agree. From Stage 11 a company can
file figures that differ from the truth, and that gap is fraud"
(`database/migrations/003_companies.sql`). This stage is when that sentence becomes true.

**The number.** The gap between filed and true profit, multiplied by the shares bought by people who
were deceived between the filing and its correction, read from `market_trades`. The window is already
defined by the schema: a filing is never changed, and a correction is filed as a new version, so the
period of deception runs from the false version to the correcting one.

**The remedy.** Damages to those buyers, computed from the trade record rather than decided by a judge;
a fine; an entry on the directors' legal records.

**Who brings it.** The regulator, or a shareholder who bought inside the window.

**This is the largest change in the stage.** It means a company can lie, which touches the newsroom,
the credit file and every screen that shows a filed number. It is worth its own checklist item and its
own loophole test.

#### 6. Vendor fraud in a company sale

**Evidence.** `deal_terms` (the warranties given), `deal_finds` (what the seller knew and hid), and
`company_reports` against `company_results` at the time of sale. `deal_claims` already exists as the
mechanism for a buyer's claim, with its amount, what has been paid and whether it was refused.

**The number.** The overpayment: what was paid against what the company was worth on true figures.

**The remedy.** Damages to the buyer from the seller, a fine, a legal record.

**Who brings it.** The buyer, or the regulator.

### Against the client

#### 7. Trading ahead of the empire

**Evidence.** The empire's open orders, and the player's own trades in the same ticker before them.
`empire_trades` records what each member has traded for the empire, so the two sides of the comparison
are both on file. The Asset Manager knows what the empire is about to buy.

**The number.** The profit on the personal trade.

**The remedy.** Disgorgement to the empire, a fine, and for a repeat, loss of the seat.

**Who brings it.** The empire head, or the regulator.

#### 8. Misuse of client or charity money

**Evidence.** `charity_gifts` and `charity_grants` are permanent, and the ledger shows where the money
went. Client money is the same question with a different payer.

**The number.** The amount diverted from its stated purpose.

**The remedy.** Restitution, a fine, a legal record.

**Who brings it.** The charity's donors, the client, or the regulator.

#### 9. Breach of duty

**Evidence.** `empire_cases` — a theft an audit has proved, with its amount, what has been repaid, the
fine and what is left owed (`database/migrations/016_empires.sql`). And the pension shortfall: Stage 5
held back letting an Asset Manager run other players' retirement money, because "the regulator, the
lawsuits and the courts that the design sets against that arrive in Stage 11".

**The number.** The shortfall: what was taken or lost. For a theft it is already `empire_cases.amount`;
for a pension it is the difference between what the fund should hold and what it does.

**The remedy.** Restitution over time, using the `debt_left` shape that already exists; a fine; a
trading ban; and for a pension manager, revocation of the licence to run other people's money.

**Who brings it.** The empire head, the regulator, or a pension member.

### Against the record

#### 10. Unexplained wealth

**Evidence.** `money_watch_flags` — the private list the Money Watch already keeps of accounts gaining
money faster than honest play allows. It has never been used for anything. Its own docstring says the
list is "for a person to look at".

**The number.** The growth the ledger cannot account for. Because every naira has a recorded payer,
wealth without a lawful source is provable here in a way it is not in life.

**The remedy.** A fine on the unexplained amount, with the burden on the player to show the source. The
ledger settles it either way.

**Who brings it.** The regulator only. This is the one case a player cannot bring, because the evidence
is private.

## Who brings cases

**The regulator** has a budget, funded by the fines it collects. It chooses which cases to bring, so
enforcement is a resource allocation problem: which claims are worth the cost of proving. A regulator
that spends its budget on small cases lets large ones go.

**Players** may bring cases too, but must post a litigation bond, and pay the other side's costs if
they lose. Suing becomes a financial decision with a downside. That is both the control against
griefing and the theme.

## The remedy ladder

In order of how often they are used:

1. **Disgorgement** — the profit is returned.
2. **Damages** — paid to victims computed from the trade record.
3. **Fine** — paid to the Government, and to the regulator's budget.
4. **Trading ban** — no trading for a number of quarters. A financial penalty: you cannot earn.
5. **Licence revocation** — the Asset Manager loses the right to run funds.
6. **Restitution over time** — paid down like `debt_left`, with the debt visible.

## The Court page

A page of its own in the shell, beside Market, Firm and Empire.

- **The docket.** Open cases, each with the claim, the number, the evidence and a settle-or-fight
  choice. Settling is priced: the defendant weighs the expected judgment against the cost of fighting.
- **Your cases.** The ones you brought and the ones you are defending.
- **The legal record.** `legal_records`, which already exists and whose comment says "The courts (a
  later stage) add to it". Public, as the design intends.
- **The regulator.** Its budget, and the cases it has chosen to bring and to drop.

## What the market feels before the verdict

- A company under investigation borrows at a higher rate.
- Its shares carry a discount while the case is open.
- `simulation/standing.py` already moves reputation on a fine or an exposed undeclared interest, so
  that machinery is half-built.
- A trading ban is visible to counterparties.

## Recorded now, prosecuted later

Four case types are deliberately left out of this stage. The records already exist for all four, so
nothing is lost by waiting:

- **Reckless lending and concealment** in a bank crisis.
- **Planted rumours** before a run — `simulation/crisis.py` already keeps the bad stories and who
  planted them, and `simulation/press.py` keeps who started a rumour.
- **Bid rigging at the Auction House** — `auction_bids` and `auction_events` record every bid and every
  price shown, so collusion is provable, but the pattern is harder to define than the others.
- **Misrepresenting a fund or ETF** — the published holdings against the real ones.

## Questions for the owner before any building

1. **The bond.** How large, relative to the claim? I recommend a tenth of the claim, with a floor, so
   that a small claim is still worth bringing and a frivolous one is not.
2. **Is the regulator a computer institution or a player build?** I recommend the computer, with the
   lawyer build earning fees from the cases it brings and defends. A player-run regulator is a
   different game.
3. **Can a case be brought against a computer-run company?** I recommend yes for false accounts, since
   the computer's companies are the ones most likely to be caught, and no for breach of duty, which
   needs a person.
4. **Does the ten-year run need a court in it?** I recommend one staged case, so the run proves the
   docket does not seize up over forty quarters.
5. **Does the lawyer's talent record gain "cases won and lost"?** `docs/TALENT_1_PROVEN_TALENT_2026-10-29.md`
   says it will "appear when that stage is built". I recommend yes, and that it replaces the conduct
   entry that stands in for it today.

## What happens next

Ten case types is a large stage — larger than Part 4c. If it needs splitting, the natural cut is the
four "against the market" cases first: they share the trade record and the same evidence machinery, so
they are the cheapest four to build together, and the other six follow once the docket is proved.

The owner approves or amends this. Then a Stage 11 checklist is written, presented, and only after the
owner says "build" does any code get written. Following working rule 1, this file is a proposal, not a
stage report, and it moves out of `docs/` into the owner's private notes once the stage closes.

Part 4c must close first: items 35, 36 and 38. Working rule 5 says do not start a stage before the
previous one passes.
