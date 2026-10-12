"""The kinds of news the wire can carry (design document, section 12).

Every kind lists the facts a headline may use. A wording may use only those
facts, so nothing can be printed that the game's records do not hold.

`sample` is one made-up set of facts for each kind. The tests fill every
wording with it, to prove that no wording asks for a fact that is not there.
"""

from __future__ import annotations

from dataclasses import dataclass

OUTLETS = {
    "herald": "The Lagoon Herald",        # a general daily: people, streets, traders, families
    "ogene": "Ogene News Network",        # a broadcaster: short, urgent, present tense
    "ledger": "The Naira Ledger",         # a financial paper: sober, figures first
}


@dataclass(frozen=True)
class NewsKind:
    name: str
    importance: int                # where it starts on the front page, 0 to 100
    sample: dict[str, str]         # the facts a wording may use, with an example of each

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(self.sample)


_PLACE = {"location": "Port Harcourt", "severity": "serious",
          "companies": "Bonny Tide Shipping, Ibom Solar Power and 3 other companies based there"}
_SECTOR = {"sector": "telecoms", "severity": "serious", "companies": "Lekki Fibre Networks and 3 other companies"}
_COMPANY = {"company": "Kainji Textiles", "ticker": "KTX", "location": "Kano", "sector": "manufacturing",
            "severity": "serious"}
_PRICE = {"commodity": "energy", "size": "about 15%"}
_RATE = {"rate": "13.5%", "old_rate": "12.5%", "inflation": "7.8%", "target": "6%",
         "run": "the second rise in a row"}
_PRICES = {"inflation": "9.4%", "previous": "8.1%", "target": "6%", "band": "3% to 9%", "driver": "dearer energy"}
_RESULT = {"company": "Kainji Textiles", "ticker": "KTX", "location": "Kano", "sector": "manufacturing",
           "quarter": "Year 2 Q3", "profit": "₦1.2 billion", "previous_profit": "₦800 million",
           "sales": "₦14.6 billion", "change": "50%",
           "cause": "A new product sold well: its sales rose about 9%."}
_RATING = {"company": "Kainji Textiles", "ticker": "KTX", "location": "Kano", "sector": "manufacturing",
           "rating": "BB", "old_rating": "BBB"}
_OWES = {"company": "Kainji Textiles", "ticker": "KTX", "location": "Kano", "sector": "manufacturing",
         "amount": "₦3.4 billion"}
_JOBS = {"company": "Kainji Textiles", "ticker": "KTX", "location": "Kano", "sector": "manufacturing",
         "jobs": "about 1,200", "staff": "about 14,000"}
_WATCH = {"reason": "Money grew 14% over the year while the economy's sales grew 6%: faster than the economy.",
          "money_growth": "14%", "output_growth": "6%",
          "action": "The Central Bank leans harder on its interest rate: half a point above what its rule alone would set."}

_FIRM = {"company": "Kainji Textiles", "ticker": "KTX", "location": "Kano", "sector": "manufacturing"}
_BID = {"bidder": "Idanre Cement", "target": "Kainji Textiles", "ticker": "KTX", "price": "₦42.50", "premium": "32%",
        "stake": "60%", "value": "₦11 billion"}

KINDS: tuple[NewsKind, ...] = (
    # --- Things that happen on a day, in a place ---
    NewsKind("flood", 80, _PLACE),
    NewsKind("power_failure", 55, _PLACE),
    NewsKind("security_incident", 78, _PLACE),
    NewsKind("port_disruption", 62, _PLACE),
    NewsKind("pipeline_incident", 72, _PLACE),
    NewsKind("drought", 70, _PLACE),
    NewsKind("local_boom", 50, {**_PLACE, "severity": "strong"}),
    # --- ...to a whole kind of business ---
    NewsKind("sector_strike", 68, _SECTOR),
    NewsKind("sector_demand_surge", 55, {**_SECTOR, "severity": "strong"}),
    NewsKind("good_harvest", 55, {**_SECTOR, "sector": "agriculture", "severity": "strong",
                                  "companies": "Benue Harvest Foods and 2 other companies"}),
    NewsKind("network_outage", 60, _SECTOR),
    NewsKind("new_competition", 50, {**_SECTOR, "severity": "moderate"}),
    # --- ...to one company ---
    NewsKind("company_strike", 60, _COMPANY),
    NewsKind("scandal", 70, _COMPANY),
    NewsKind("contract_win", 55, {**_COMPANY, "severity": "strong"}),
    NewsKind("factory_fire", 72, _COMPANY),
    NewsKind("product_recall", 60, _COMPANY),
    NewsKind("new_product", 50, {**_COMPANY, "severity": "strong"}),
    # --- ...to the price of a commodity ---
    NewsKind("energy_price_jump", 70, _PRICE),
    NewsKind("energy_price_fall", 62, _PRICE),
    NewsKind("metals_price_jump", 55, {**_PRICE, "commodity": "metals"}),
    NewsKind("metals_price_fall", 50, {**_PRICE, "commodity": "metals"}),
    NewsKind("materials_shortage", 55, {**_PRICE, "commodity": "building materials"}),
    # --- The Central Bank ---
    NewsKind("rate_rise", 90, _RATE),
    NewsKind("rate_cut", 90, {**_RATE, "rate": "11.5%", "inflation": "4.1%", "run": "the second cut in a row"}),
    NewsKind("rate_hold", 60, {**_RATE, "rate": "12.5%", "inflation": "6.2%", "run": "the third quarter without a change"}),
    # --- Prices ---
    NewsKind("inflation_high", 85, _PRICES),
    NewsKind("inflation_low", 80, {**_PRICES, "inflation": "2.4%", "previous": "3.6%", "driver": "weak household spending"}),
    NewsKind("inflation_rising", 65, {**_PRICES, "inflation": "7.6%", "previous": "6.3%"}),
    NewsKind("inflation_easing", 60, {**_PRICES, "inflation": "5.2%", "previous": "6.6%", "driver": "cheaper farm produce"}),
    NewsKind("inflation_steady", 40, {**_PRICES, "inflation": "6.1%", "previous": "6.3%", "driver": "steady household spending"}),
    # --- Company results ---
    NewsKind("results_strong", 50, _RESULT),
    NewsKind("results_weak", 52, {**_RESULT, "profit": "₦400 million", "cause": "Power failures in Kano cost it sales of about 3%."}),
    NewsKind("company_loss", 66, {**_RESULT, "profit": "₦600 million", "cause": "A strike by its own staff cut its sales by about 12%."}),
    NewsKind("back_in_profit", 58, {**_RESULT, "previous_profit": "₦300 million"}),
    # --- Credit ---
    NewsKind("rating_upgrade", 55, {**_RATING, "rating": "A", "old_rating": "BBB"}),
    NewsKind("rating_downgrade", 62, _RATING),
    NewsKind("default", 88, _OWES),
    NewsKind("missed_payment", 74, _OWES),
    # --- Jobs, dividends, expansion ---
    NewsKind("job_cuts", 60, _JOBS),
    NewsKind("hiring", 48, _JOBS),
    NewsKind("dividend_cut", 50, {"company": "Kainji Textiles", "ticker": "KTX", "location": "Kano", "sector": "manufacturing"}),
    NewsKind("expansion", 45, _OWES),
    # --- Banks and insurers ---
    NewsKind("bank_loan_losses", 68, {"company": "Harmattan Bank", "ticker": "HMB", "amount": "₦8.2 billion"}),
    NewsKind("bank_central_borrowing", 58, {"amount": "₦420 billion", "new": "₦35 billion"}),
    NewsKind("insurance_claims", 60, {"amount": "₦12.6 billion", "cause": "the flood in Port Harcourt",
                                      "insurers": "Kuka Insurance and 2 other insurers"}),
    NewsKind("event_aftermath", 64, {"event": "the flood in Port Harcourt", "amount": "₦18 billion",
                                     "paid": "₦12.6 billion",
                                     "companies": "Bonny Tide Shipping, Ibom Solar Power and 3 other companies"}),
    # --- The Money Watch ---
    NewsKind("money_watch_amber", 76, _WATCH),
    NewsKind("money_watch_red", 95, {**_WATCH, "action": "The Central Bank leans a full point harder on its interest rate, and new lending is halved next quarter."}),
    NewsKind("money_watch_green", 50, {**_WATCH, "reason": "Money is growing in step with the economy, and is not pooling in one place.",
                                       "action": "No action needed."}),
    # --- The whole economy ---
    NewsKind("household_borrowing_up", 52, {"change": "4.2%", "amount": "₦520 billion", "rate": "19%"}),
    NewsKind("household_borrowing_down", 52, {"change": "2.1%", "amount": "₦480 billion", "rate": "22%"}),
    NewsKind("jobs_report_up", 56, {"jobs": "about 612,000", "change": "about 9,000", "location": "Lagos"}),
    NewsKind("jobs_report_down", 64, {"jobs": "about 590,000", "change": "about 11,000", "location": "Kano"}),
    NewsKind("economy_growing", 58, {"growth": "9.4%", "sales": "₦310 billion"}),
    NewsKind("economy_slowing", 66, {"growth": "3.1%", "sales": "₦290 billion"}),
    NewsKind("commodity_up", 54, {"commodity": "farm produce", "size": "12%"}),
    NewsKind("commodity_down", 50, {"commodity": "farm produce", "size": "9%"}),
    # --- The economy upgrade: the rest of the world ---
    NewsKind("oil_up", 70, {"price": "$82.40 a barrel", "previous": "$75.00", "change": "9.9%"}),
    NewsKind("oil_down", 72, {"price": "$64.10 a barrel", "previous": "$75.00", "change": "14.5%"}),
    NewsKind("naira_weaker", 74, {"rate": "₦1,560", "previous": "₦1,500", "change": "4%", "cause": "cheaper oil"}),
    NewsKind("naira_stronger", 62, {"rate": "₦1,440", "previous": "₦1,500", "change": "4%", "cause": "dearer oil"}),
    NewsKind("foreign_buying", 55, {"amount": "₦3.2 billion", "rate": "13.5%"}),
    NewsKind("foreign_selling", 60, {"amount": "₦2.8 billion", "rate": "11.5%"}),
    # --- Stage 4: companies using the market ---
    NewsKind("takeover_bid", 85, _BID),
    NewsKind("takeover_hostile", 88, _BID),
    NewsKind("takeover_won", 82, {"bidder": "Idanre Cement", "target": "Kainji Textiles", "ticker": "KTX", "price": "₦42.50",
                                  "stake": "63%", "value": "₦11.6 billion"}),
    NewsKind("takeover_failed", 75, {"bidder": "Idanre Cement", "target": "Kainji Textiles", "ticker": "KTX", "price": "₦42.50",
                                     "accepted": "38%"}),
    NewsKind("rights_issue", 70, {**_FIRM, "amount": "₦6.2 billion", "price": "₦18.00", "discount": "25%",
                                  "terms": "one new share for every four held"}),
    NewsKind("share_offer", 62, {**_FIRM, "amount": "₦9.4 billion", "price": "₦31.20", "shares": "300 million"}),
    NewsKind("offer_result", 55, {"company": "Kainji Textiles", "ticker": "KTX", "amount": "₦5.9 billion", "taken": "94%"}),
    NewsKind("share_split", 50, {"company": "Kainji Textiles", "ticker": "KTX", "terms": "two new shares for each one held",
                                 "old_price": "₦120.00", "new_price": "₦60.00"}),
    NewsKind("bond_issue", 55, {**_FIRM, "amount": "₦8 billion", "rate": "16.5%", "bond": "a five-year bond"}),
    NewsKind("government_bonds", 50, {"amount": "₦14 billion", "rate": "13.8%", "total": "₦240 billion"}),
    NewsKind("vote_result", 50, {"company": "Kainji Textiles", "ticker": "KTX", "matter": "its plan to raise ₦6.2 billion from its owners",
                                 "outcome": "approved", "support": "71%"}),
    NewsKind("integration_good", 55, {"bidder": "Idanre Cement", "target": "Kainji Textiles", "ticker": "KTX",
                                      "detail": "Costs at Kainji Textiles came in about 4% lower than before the takeover."}),
    NewsKind("integration_bad", 60, {"bidder": "Idanre Cement", "target": "Kainji Textiles", "ticker": "KTX",
                                     "detail": "Staff have been leaving and customers have gone elsewhere: sales at Kainji Textiles are about 5% lower."}),
    # --- Private equity stage, part 2: private companies and deals ---
    NewsKind("startup", 45, {"company": "Yaba Bike Couriers", "sector": "transport and logistics", "city": "Lagos", "amount": "₦1.2 billion"}),
    NewsKind("company_for_sale", 55, {"company": "Eko Skyways", "sector": "airlines", "how": "by sealed bids", "amount": "₦18.4 billion"}),
    NewsKind("walkout", 60, {"company": "Eko Skyways", "city": "Lagos"}),
    NewsKind("private_deal", 70, {"buyer": "Harbour Lights Capital", "company": "Eko Skyways", "amount": "₦17.9 billion",
                                  "how": "after sealed bids"}),
    NewsKind("administration", 72, {"company": "Garden City Airlines", "city": "Port Harcourt", "owed": "₦9.6 billion",
                                    "recovered": "₦5.1 billion"}),
    NewsKind("deal_of_the_year", 65, {"empire": "Harbour Lights Capital", "company": "Eko Skyways", "gain": "₦6.2 billion",
                                      "year": "Year 2"}),
    # --- Dealmaking between empires in the market ---
    NewsKind("empire_offer", 70, {"bidder": "Harbour Lights Capital", "target": "Kainji Textiles", "ticker": "KTX",
                                  "price": "₦42.50", "premium": "32%", "stake": "60%", "value": "₦11 billion",
                                  "board": "recommends the offer"}),
    NewsKind("empire_offer_won", 68, {"bidder": "Harbour Lights Capital", "target": "Kainji Textiles", "ticker": "KTX",
                                      "price": "₦42.50", "stake": "61%", "value": "₦11.2 billion"}),
    NewsKind("empire_offer_failed", 60, {"bidder": "Harbour Lights Capital", "target": "Kainji Textiles", "ticker": "KTX",
                                         "price": "₦42.50", "accepted": "38%"}),
    NewsKind("offer_topped", 66, {"rival": "Oguta Lake Partners", "bidder": "Harbour Lights Capital",
                                  "target": "Kainji Textiles", "ticker": "KTX", "price": "₦46.00"}),
    NewsKind("defence_published", 58, {"target": "Kainji Textiles", "ticker": "KTX", "worth": "₦51.20", "price": "₦42.50",
                                       "bidder": "Harbour Lights Capital"}),
    NewsKind("stake_disclosed", 50, {"empire": "Oguta Lake Partners", "company": "Zuma Rock Hotels", "ticker": "ZRH",
                                     "stake": "10%"}),
    NewsKind("block_trade", 48, {"seller": "Harbour Lights Capital", "buyer": "Oguta Lake Partners",
                                 "company": "Ikoyi Bank", "ticker": "IKB", "shares": "12 million",
                                 "amount": "₦1.4 billion"}),
    NewsKind("empires_merge", 62, {"empire": "Harbour Lights Capital", "other": "Ogbomoso Gate Investments"}),
    NewsKind("spinoff", 52, {"empire": "Harbour Lights Capital", "company": "Eko Skyways",
                             "new_empire": "Eko Skyways Holdings"}),
    NewsKind("audit_refused", 55, {"company": "Eko Skyways", "firm": "Adebayo Okafor and Partners"}),
    # --- Smaller items, gathered together ---
    NewsKind("roundup_results", 35, {"quarter": "Year 2 Q3", "count": "six",
                                     "list": "Ikoyi Bank (profit up 4%), Kainji Textiles (profit down 6%) and Zuma Rock Hotels (profit up 3%)"}),
    NewsKind("roundup_jobs", 32, {"quarter": "Year 2 Q3", "count": "four",
                                  "list": "Ikoyi Bank (about 300 more staff), Kainji Textiles (about 200 fewer) and Zuma Rock Hotels (about 150 more)"}),
)
BY_NAME = {kind.name: kind for kind in KINDS}

# What each fact means, for whoever writes wordings.
FIELD_NOTES = {
    "location": "a city: Lagos, Abuja, Port Harcourt, Aba or Kano",
    "severity": "one adjective for how hard it hits: light, moderate, serious or severe (bad news); modest, strong or very strong (good news)",
    "companies": "a noun phrase naming the companies touched, e.g. 'Bonny Tide Shipping, Ibom Solar Power and 3 other companies based there'; it may also read 'businesses in the area'",
    "sector": "a kind of business in lower case, e.g. 'telecoms', 'cement and building materials', 'oil and gas'",
    "company": "a company's full name", "ticker": "its three-letter market code",
    "commodity": "energy, metals, farm produce or building materials",
    "size": "a rough size such as 'about 15%' or '12%'",
    "rate": "the Central Bank's new interest rate", "old_rate": "its rate before the decision",
    "inflation": "how much prices rose over the past year", "previous": "the same figure a quarter earlier",
    "target": "the Central Bank's inflation target", "band": "the range the Central Bank accepts",
    "run": "a phrase that fits after a comma, e.g. 'the second rise in a row' or 'ending three quarters without a change'",
    "driver": "a short noun phrase for the main cause, e.g. 'dearer energy'",
    "quarter": "the game quarter the figures are for, e.g. 'Year 2 Q3'",
    "profit": "profit after tax for the quarter (for company_loss: the size of the loss)",
    "previous_profit": "the quarter before (for back_in_profit: the size of the earlier loss)",
    "sales": "the quarter's sales", "change": "how much profit changed, as a percentage without a sign",
    "cause": "one complete sentence from the company's own filing explaining the quarter",
    "rating": "its new credit rating", "old_rating": "its rating before",
    "amount": "a sum of money in words, e.g. '₦3.4 billion'",
    "jobs": "how many jobs were cut or added", "staff": "how many people the company employs now",
    "new": "how much more the banks borrowed from the Central Bank this quarter",
    "insurers": "a noun phrase naming the insurers", "event": "a noun phrase naming an earlier event, e.g. 'the flood in Port Harcourt'",
    "paid": "what insurers paid", "reason": "one complete sentence from the Money Watch",
    "money_growth": "how fast money grew over the year", "output_growth": "how fast the economy's sales grew",
    "action": "one complete sentence: what the Central Bank does about it",
    "growth": "how much the economy's sales grew over the year",
    "count": "a number in words", "list": "a ready-made list of companies with a figure each",
    # Stage 4: companies using the market.
    "bidder": "the full name of the company making a takeover offer (empire_offer kinds: an empire's name, never a company)",
    "target": "the full name of the company it wants to buy (its market code is `ticker`)",
    "price": "a price per share in naira, e.g. '₦42.50' (for takeovers: what the bidder offers for each share; "
             "for share offers: what each new share costs)",
    "premium": "how far the offer is above the share's last market price, e.g. '32%'",
    "stake": "the part of the company's shares, e.g. '60%' (takeover_bid: what the bidder wants to end up owning; "
             "takeover_won: what it now owns)",
    "value": "what the whole purchase costs the bidder, e.g. '₦11 billion'",
    "accepted": "the part of the target's shares whose owners accepted the offer, e.g. '38%' (it needed more than half)",
    "terms": "a ready-made phrase, e.g. 'one new share for every four held' or 'two new shares for each one held'",
    "discount": "how far the new shares' price is below the market price, e.g. '25%'",
    "shares": "how many new shares, in words, e.g. '300 million'",
    "taken": "the part of the new shares on offer that found buyers, e.g. '94%'",
    "old_price": "the share price before a split", "new_price": "the share price after it",
    "bond": "a noun phrase with its article naming the bond, e.g. 'a five-year bond', 'a bond that can be swapped for "
            "shares', 'a green bond to pay for its solar plant', 'a high-interest bond'",
    "total": "everything the Government now owes on its bonds",
    "matter": "a noun phrase for what shareholders voted on, starting with 'its', e.g. 'its plan to raise ₦6.2 billion from its owners'",
    "outcome": "'approved' or 'rejected'", "support": "the part of the votes cast that were in favour, e.g. '71%'",
    "detail": "one complete sentence from the records saying how the joining of the two businesses is going",
    # Private equity stage, part 2.
    "city": "one of the five cities", "how": "'by sealed bids', 'at auction' (for sale) or 'after sealed bids', 'at auction' (sold)",
    "buyer": "the name of the empire that bought it", "owed": "everything it owed when it failed",
    "recovered": "what selling its assets raised for those it owed", "empire": "an empire's name",
    "gain": "the gain made on the deal", "year": "the game year, e.g. 'Year 2'",
    # Dealmaking between empires.
    "board": "a ready-made verb phrase for what the target's board says: 'recommends the offer' or 'has rejected the offer'",
    "rival": "the name of the empire making a higher, competing offer",
    "worth": "what the target's board says each share is really worth, e.g. '₦51.20'",
    "seller": "the name of the empire selling a block of shares",
    "other": "the name of the empire that joins another and stops being separate",
    "new_empire": "the name of a new empire formed in a spin-off",
    "firm": "the name of an audit firm",
}
