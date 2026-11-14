# Government, part 2: the leader's powers and lobbying

Branch `government-2`, built on `government`. Migration 051.

## What the leader can now do

- **Decree the Central Bank rate.** Once a quarter. The decree sets next quarter's rate, but the close holds it within
  3 points of what the Central Bank's own rule would have set. A decree has a cost that quarter: prices rise 0.5% faster
  and confidence falls 5 points. The rate's reason line says it was set by decree, and what the rule would have set.
- **Propose a levy on one empire.** Up to 2% of that empire's cash, with a reason, one before the Assembly at a time.
  The Assembly counts it at the close: heads vote as they choose; computer-run members who favour high taxes back it,
  the rest protect the empires. Passed, the money goes to the Treasury (taken up to what the empire has).
- **Be paid.** ₦3m a quarter from the Treasury while in office.

## Lobbying

The head of an empire run by players can pay ₦5m to the Treasury to win over one computer-run member on an open vote
(a budget, a no-confidence motion or a levy). The member then votes as the head's seat did, so the head must vote first.
At most 3 members per empire per vote, one empire per member, and every payment is listed on the page. A lobby, once
paid, is kept.

## Where it shows

Economy → Government: a "leader's powers" panel (decree and levy forms for the leader), a "Lobbying" panel (for heads,
plus the public list), and "Levies this year" with voting buttons for heads.

## Tests

`tests/test_government_powers.py`: decree limits and clamp, a decree's cost in the quarter's economy measure, levy limits
and collection, lobbying rules and their effect on the count, and the leader's pay.
