# Stage 10, Part 1: the newsroom

The owner approved Stage 10 on 16 October 2026 with "1. lets do part 1 then part 2 2. yes i accept 3. i do not have
money yet to outsource a paid ai service 4. ok i go with your suggestions 5. now". The checklist is
`notes/stage-10-plan.md`. This report covers Part 1 (items 1 to 14 of the checklist, and the design's own items M30,
M33, M34 and M35). Part 2 (sources, investigations, the empire's press desk, intelligence work, charities, media firms
at the Auction House, the Intelligence Market, the Sealed Tip and rumours) comes next.

Part 1 had ten loophole tests and an independent review. Every review finding was fixed, and each fix has a test.
Nothing on the Part 1 checklist was dropped or put off.

Tests at the end: **1,240 on the server**, 13 on the order-matching engine and 23 on the website. All of them pass.

## Things worth knowing, said plainly

1. **No paid AI service.** As the owner decided, the full articles are written by a writer built into the game. It
   writes only from what is on the record: the wire item, the background (the company, its sector, its last
   results), and "What it means". Every figure in an article is checked against the record, with its unit (₦12
   billion is not 12%); an article that fails the check is not shown, and the plain wire item stays. A place for a
   paid service is left in the code, switched off. If a key is ever added, its articles go through the same check.
   At most 20 articles are written a game day, and only for news from the last three game days.
2. **A story is built from confirmed facts only.** A Journalist picks facts the record already holds (results,
   ratings, takeovers, disclosed stakes, the Central Bank's rate, events, closed share prices, public works and home
   prices), checks each one against where it is kept, may ask for comment, and adds their own view in words. Their
   own words may not hold a figure. Nothing from later in the quarter, and nothing still hidden, can be used.
3. **Being first matters.** The first story with a fact the wire has not yet carried is a scoop: more readers, a
   ₦250,000 bonus from the employer and +2 reputation (paid once a game day, however many scoops). A story that only
   repeats the wire is old news: fewer readers, and it moves no price.
4. **A widely read, true story moves investors a little.** At least 10,000 readers, at most three companies, at most
   2% on how investors value a company, fading over five trading days, one nudge per company a day. The public reads
   it at once, the institutions a day later, foreign money two days later; founders never trade on the news.
5. **No trading around your own story.** From the moment a fact about a company enters the draft until two trading
   days after the story runs, the Journalist and their empire cannot trade that company by any route (shares, short
   sales, options and futures, structured instruments, the dealmaking desk). Their waiting orders are cancelled.
6. **Interviews.** A Journalist may ask up to three companies or empire heads for comment, but only ones the story is
   about (a fact names them, or they have a disclosed stake in a company in it). The head has 24 real hours. An
   answer on the record raises the empire's reputation by 1 when the story runs; a question left to run out lowers
   it by 1. Answers may not hold figures.
7. **Declare your interest.** A Journalist with a seat in an empire must say whether it holds the companies named.
   Anyone may ask the game to check an undeclared story; only the verdict is shown, never the holding. A true
   finding costs the Journalist and their empire; a false alarm costs the accuser.
8. **Corrections.** If a fact a story used is later changed in the record, the story must be corrected within a day;
   a late correction costs more reputation and readers. Honest limit: nothing in the game yet changes filed accounts
   after the fact, so in a normal game no correction is due (the ten-year run had none). The first real cause comes
   with Part 2's rumours and Stage 11's books and courts. The rule is built and tested now.
9. **Every empire has a public reputation**, 0 to 100, starting at 50, on its page and in the league. Fines lower it
   by 2; a clean audit raises it by 1; an unlawful pact that comes to light lowers it by 6 (by 2 for the empire that
   reported it); press answers move it as in point 6, by at most 6 a real day. Honest limit: in Part 1 the tone of
   stories about an empire does not move its reputation by itself; crisis handling, the press desk and charity
   arrive in Part 2.
10. **Pay rises with reach.** An employed Journalist's salary rises with their readers. An independent is paid ₦5 a
    reader by the paper that picks the story up, at most ₦2 million a story, ₦20 million a quarter for one
    Journalist and ₦200 million a quarter for all independents together.
11. **Named editors who remember.** Mrs Adaeze Okafor (The Lagoon Herald), Mr Tunde Bakare (The Naira Ledger) and Ms
    Halima Sani (Ogene News Network) give Journalists work, paid by their paper, independents included. Work done well
    raises their trust by 5; done badly, given up or left undone lowers it by 10. Below 30 they stop offering work;
    at 70 they offer the front page. Trust comes back a little each quarter.
12. **The Chronicle** keeps what happened, for good, in three layers: the world (rate changes, big takeovers, the
    year in review each game year), companies (turning points: profit up or down 30% on the year, a fall into loss,
    a return to profit, a loss that narrows or widens), and each player's own story. Journalists may add a signed
    account beside an entry, citing their own published stories about it; each account has a credibility score.
13. **The Ripple and "Why?"** Every result, rating, rate decision, takeover, stake, public work, story and nudge
    keeps a link to what caused it. "Why?" shows the chain in one line, in full, or with the numbers.
14. **Found by the screenshots, and fixed.** A company whose loss shrank was written as "profit up 97.7%". A loss is
    now always written as a loss ("a loss 78% smaller than..."), on the facts, the Chronicle and the Results page.
    The list of facts was also very long; it now shows 12 at a time with a filter by kind.

## Checklist

| # | Agreed | Done | Proved by |
| --- | --- | --- | --- |
| 1 | Events first, news second; one story per event; follow-ups linked | Yes. Each item is tied to its record; duplicates are refused; follow-ups name the first item. Ids are never sent (a reference is sent instead). | `test_news.py`, loophole 9 |
| 2 | Full articles from the record, every figure checked, capped | Yes, by the built-in writer (owner's answer 3); a switched-off place for a paid service, held to the same check | `test_full_articles_are_written_from_the_record_with_every_figure_checked_and_twenty_a_day`, loophole 1 |
| 3 | Works without the service; secrets never given to it | Yes | the same test; loophole 9 |
| 4 | Computer investors read news at different speeds | Yes (public at once, institutions 1 day, foreign 2 days, founders never) | `test_a_widely_read_true_story_nudges_investors_who_read_it_at_their_own_pace` |
| 5 | A permanent, searchable archive | Yes | `test_news.py`, screenshot 08 |
| 6 | Journalists publish under their name, for a paper or independent | Yes | `test_a_journalist_publishes_a_checked_story_under_their_name_and_a_first_with_a_fact_is_a_scoop`, `test_every_fact_is_checked_before_print_and_the_authors_own_view_has_no_figures` |
| 7 | Readers, following, pay with reach | Yes | `test_pay_rises_with_reach_and_an_independent_is_paid_by_the_paper_that_picks_the_story_up` |
| 8 | Scoops: bonus and reputation | Yes | the first test, loophole 5, review test on repeating the wire |
| 9 | Interviews with a deadline | Yes | `test_interviews_answers_refusals_and_deadlines_go_into_the_story`, loophole 7 |
| 10 | Corrections | Yes (see point 8 for the honest limit) | `test_a_story_whose_facts_the_record_changes_must_be_corrected_and_late_costs_more`, loophole 8 |
| 11 | A widely read true story nudges investors, capped, fading | Yes | `test_a_widely_read_true_story_nudges_...`, loophole 4 |
| 12 | Only confirmed facts move anything; no trading around one's story | Yes | `test_no_trading_a_company_from_the_first_draft_until_two_trading_days_after_publication`, loophole 3 |
| 13 | Declare your interest; hiding it can be exposed | Yes | `test_an_undeclared_interest_can_be_exposed_and_only_the_verdict_is_shown`, loopholes 6 and 10 |
| 14 | The empire's public reputation, on the empire page and league | Yes | `test_an_empires_reputation_moves_with_fines_audits_and_answers_and_shows_in_the_league`, screenshots 12 and 13 |
| M30 | The path of a story (from confirmed fact to the record) | Yes for Part 1's path: fact, checked, published, market reacts, corrected or confirmed, recorded. The earlier steps (signal, rumour, lead, sources) are Part 2. | the stage test |
| M33 | The Chronicle, three layers, signed accounts, year in review | Yes | `test_the_ripple_links_causes_and_the_chronicle_keeps_the_quarter`, `test_a_year_in_review_closes_each_game_year`, `test_journalists_write_signed_accounts_beside_the_record_with_a_credibility_score` |
| M34 | The Ripple, "Why?" at three depths | Yes | the Ripple test; screenshots 05 and 10 |
| M35 | The stage test | Yes | `test_the_stage_test_a_journalist_verifies_and_publishes_the_price_reacts_and_the_chronicle_keeps_it_with_its_causes` |
| J | Work for each build, with "How to do this" | Yes. Journalist: checking a story, readers, scoops, nudges, declaring, an exclusive, the front page. Accountant: checking a story's figures. Risk Manager: reputational risk. Legal Counsel: checking a story before it runs. Asset Manager: trading on verified news. Investment Banker: managing an announcement. Named editors give the Journalist's work. | `test_the_news_work_comes_three_ways_with_named_editors_who_remember`, `test_objectives.py`, `test_builds.py` |
| K | Screens | Yes for Part 1: the wire, players' stories, the archive, the Chronicle, my newsroom, questions for an empire's head, reputation on the empire and league, press cards on the desk | screenshots below |

## The ten loophole questions (all tested in `tests/test_stage10a_loopholes.py`)

1. Can a figure reach print that is not on the record? No.
2. Can a fact from the future be used? No.
3. Can the Journalist or their empire trade around the story by another route? No.
4. Can nudges stack past the cap? No.
5. Can one fact earn two scoops, or several scoops in a day earn several bonuses? No.
6. Can anyone see another's draft or an empire's holdings? No.
7. Can someone other than the head answer, or answer after the deadline? No.
8. Can a published story be withdrawn to dodge a correction? No; a late correction costs more.
9. Can anything from later in the quarter be seen? No.
10. Can an exposure be repeated, or made for free? Once per story; a false alarm costs the accuser.

## The ten-year run

Forty quarters with computer Journalists (two at papers, one independent) among the other players, after every fix.
It took about an hour.

| | After ten years |
| --- | --- |
| Players' stories published | 450, of which 283 were scoops |
| Readers in all | 14.2 million |
| Paid to Journalists (bonuses and fees) | ₦72.5 million |
| Price nudges from stories | 317 (each at most 2%, fading over five days) |
| Full articles written by the built-in writer | 277 (only articles that pass the figure check are kept) |
| Chronicle entries | 1,177, with a year in review for each of the ten years |
| Ripple links | 5,541 |
| Corrections due | none (nothing restated the record; see point 8) |
| Money appearing from nowhere or vanishing | none; every book balanced |

What the run showed:
- The Journalists at papers built a following of about 65,000 to 70,000; the independent about 3,000. An
  independent's reach grows much more slowly, as intended: they have no paper's audience behind them.
- Credibility stayed at 50 for all three, because no correction was ever due. It will start to move with Part 2.
- The computer-run empires' reputations stayed at 50: none of them was fined, audited or interviewed. Reputation
  moved as designed for player empires in the tests and screenshots (51 after an answer on the record).
- 18 attempts to publish were refused because every fact had already been printed by the same Journalist. This is the
  rule that stops one fact being sold twice.
- The economy behaved as before Stage 10: the Central Bank's rate moved between 12% and 14%, prices rose 5% to 9% a
  year, and the property and lending checks from the gap stage held.

## Screenshots

`docs/screenshots/stage-10a/`: the newsroom with facts chosen (01), a story checked and a question asked (02), the
question as the head sees it (03), published with readers and a scoop (04), players' stories and "Why?" (05), the
wire and a full article (06, 07), the archive (08), the Chronicle's three layers (09 to 11), reputation on the empire
page and in the league (12, 13), work from the editors (14), the phone (15 to 17) and the light theme (18, 19). The
accessibility check found nothing to fix.
