"""Wordings for news that happens on a day to a city or to a whole kind of business."""

KINDS = ("flood", "power_failure", "security_incident", "port_disruption", "pipeline_incident", "drought",
         "local_boom", "sector_strike", "sector_demand_surge", "good_harvest", "network_outage",
         "new_competition")

WORDINGS = {
    "flood": {
        "herald": [
            ("Flood water disrupts life and trade in {location}",
             "Flooding hit {location} today, and traders, commuters and shop owners are counting the cost. "
             "Early reports call the damage {severity}. Those affected include {companies}."),
            ("Flooding in {location} leaves traders and families counting the cost",
             "Families and shop owners in {location} are dealing with flood water today. The disruption to "
             "business is described as {severity}, and the full cost is not yet known. The flood has hit "
             "{companies}."),
            ("A hard day for {location} as flood slows business",
             "Work has slowed across {location} after a flood struck the city. For {companies}, it means lost "
             "trading time and damage to put right. The damage so far is described as {severity}."),
        ],
        "ogene": [
            ("{location}: flood hits the city, business disrupted",
             "Flood water is disrupting business in {location} right now. Damage is rated {severity}."),
            ("Breaking: flooding in {location}",
             "A flood strikes {location}. Hit so far: {companies}. The full cost is not yet known."),
            ("Flood slows trade in {location}",
             "{location} is flooded and trade is slowing. Early reports call the damage {severity}."),
        ],
        "ledger": [
            ("{location} flood: damage called {severity}, cost not yet counted",
             "A flood in {location} has interrupted business today. Early reports call the damage {severity}, "
             "but no figure has been put on the cost. Those facing losses include {companies}."),
            ("Flood in {location} puts sales at risk and adds repair costs",
             "A flood has struck {location}, and investors are watching {companies}. Lost sales and repair "
             "bills are the main worries. The effect on trade is described as {severity}."),
            ("Insurers and lenders weigh {location} flood losses",
             "Flooding in {location} is expected to cost local companies sales and cash. The damage is rated "
             "{severity} so far. Insurers may face claims, which are requests from customers to be paid for "
             "their losses, from {companies}."),
        ],
    },
    "power_failure": {
        "herald": [
            ("Lights out in {location} as power fails",
             "A power failure has left shops, offices and workshops in {location} without electricity today. "
             "The disruption is described as {severity}. Those affected include {companies}."),
            ("{location} shop owners struggle through power failure",
             "Shop owners and workers in {location} are trying to keep going after the power failed. For "
             "{companies}, every hour without electricity means lost work. It is not yet known what the "
             "failure will cost."),
            ("Power failure slows the working day in {location}",
             "The power went out in {location} today, slowing work across the city. Early reports call the "
             "effect on business {severity}. The failure has hit {companies}."),
        ],
        "ogene": [
            ("{location}: power fails across the city",
             "Electricity is down in {location}. Disruption to business is rated {severity}."),
            ("Power failure hits {location} businesses",
             "The power is out in {location}. Hit so far: {companies}."),
            ("Blackout: {location} loses power",
             "{location} is without power and work is slowing. The cost is not yet known. The disruption is "
             "described as {severity}."),
        ],
        "ledger": [
            ("{location} power failure: disruption rated {severity}",
             "A power failure in {location} has interrupted work today. The disruption is rated {severity}, "
             "and the cost in lost sales has not yet been counted. Those hit include {companies}."),
            ("Power failure in {location} threatens sales and raises costs",
             "Electricity has failed in {location}. Companies there lose sales while they cannot work, and "
             "any backup power costs extra. Those facing the bill include {companies}."),
            ("Investors count the cost of {location} power failure",
             "The power failure in {location} is expected to cut into the sales and cash of {companies}. The "
             "effect on trade is described as {severity}. No figure for the loss is available yet."),
        ],
    },
    "security_incident": {
        "herald": [
            ("Security incident unsettles {location}",
             "A security incident in {location} today has disrupted the normal run of business, and "
             "trade has slowed. The disruption is described as {severity}. Those affected include "
             "{companies}."),
            ("{location} traders face a quiet day after security incident",
             "Shops and offices in {location} are seeing fewer customers after a security incident in the "
             "city. For {companies}, that means less business today. The full cost is not yet known."),
            ("Worry in {location} as security incident slows business",
             "Business in {location} slowed today following a security incident. Early reports call the "
             "effect on trade {severity}. The incident has touched {companies}."),
        ],
        "ogene": [
            ("{location}: security incident disrupts business",
             "A security incident is disrupting business in {location}. The disruption is rated {severity}."),
            ("Security incident reported in {location}",
             "Trade slows in {location} after a security incident. Affected: {companies}."),
            ("{location} on alert after security incident",
             "A security incident hits {location}. Details are still few. The effect on trade is described "
             "as {severity}."),
        ],
        "ledger": [
            ("{location} security incident: disruption rated {severity}",
             "A security incident in {location} has interrupted business today. The disruption is rated "
             "{severity}. No figure has yet been put on lost sales at {companies}."),
            ("Security incident in {location} puts local sales at risk",
             "Companies in {location} face lost sales after a security incident in the "
             "city. Those affected include {companies}. The size of the loss is not yet known."),
            ("Investors weigh cost of {location} security incident",
             "A security incident has struck {location}, and investors are watching {companies}. Fewer "
             "customers and extra spending on safety are the main worries. The effect on trade is described "
             "as {severity}."),
        ],
    },
    "port_disruption": {
        "herald": [
            ("Goods stuck as port disruption hits {location}",
             "Work at the port in {location} has been disrupted today, holding up goods that traders and "
             "shop owners are waiting for. The disruption is described as {severity}. Those affected include "
             "{companies}."),
            ("{location} traders wait as port work slows",
             "Traders in {location} face delays after a disruption at the port. For {companies}, goods that "
             "cannot move are goods that cannot be sold. Nobody yet knows what the delay will cost."),
            ("Port trouble in {location} slows deliveries",
             "Deliveries are running late in {location} after trouble at the port today. Early reports call "
             "the effect on trade {severity}. The disruption has hit {companies}."),
        ],
        "ogene": [
            ("{location}: port disruption holds up goods",
             "Goods are held up at the port in {location}. The disruption is rated {severity}."),
            ("Port disruption hits {location}",
             "The port in {location} is disrupted and goods are moving slowly. Affected: {companies}."),
            ("Delays at {location} port, trade slows",
             "Port work in {location} is disrupted. The cost is not yet known. The effect on trade is "
             "described as {severity}."),
        ],
        "ledger": [
            ("{location} port disruption: effect on trade rated {severity}",
             "A disruption at the port in {location} has slowed the movement of goods today. The effect on "
             "trade is rated {severity}. Those facing delays include {companies}."),
            ("Port delays in {location} threaten sales and tie up cash",
             "Goods are being held up at the port in {location}. Companies cannot sell what they cannot "
             "receive or ship, and their money stays tied up in goods that are waiting. Those affected "
             "include {companies}."),
            ("Importers and exporters count cost of {location} port disruption",
             "The port disruption in {location} is expected to cut into the sales of {companies}. The "
             "disruption is described as {severity}. No figure for the loss is available yet."),
        ],
    },
    "pipeline_incident": {
        "herald": [
            ("Pipeline incident in {location} raises fear of dearer fuel",
             "A pipeline incident in {location} today has disrupted business and is pushing energy prices "
             "up. Families and drivers may soon pay more for fuel and power. The disruption is described as "
             "{severity}."),
            ("{location} businesses hit by pipeline incident",
             "Workers and business owners in {location} are dealing with a pipeline incident in the city. "
             "Those affected include {companies}. Energy is also getting dearer, which touches every "
             "household."),
            ("Energy prices climb after pipeline incident in {location}",
             "Energy became more expensive today after an incident on a pipeline in {location}. Early "
             "reports call the effect on business there {severity}. The incident has hit {companies}."),
        ],
        "ogene": [
            ("{location}: pipeline incident, energy prices rise",
             "A pipeline incident hits {location}. Energy prices are going up. The disruption is rated "
             "{severity}."),
            ("Pipeline incident disrupts {location}",
             "Business is disrupted in {location} after a pipeline incident. Affected: {companies}."),
            ("Energy dearer as pipeline incident strikes {location}",
             "A pipeline in {location} is hit by an incident and energy costs more. The full cost is not yet "
             "known."),
        ],
        "ledger": [
            ("{location} pipeline incident lifts energy prices",
             "An incident on a pipeline in {location} has pushed energy prices higher today. The disruption "
             "to business in the city is rated {severity}. Those hit include {companies}."),
            ("Pipeline incident in {location}: disruption rated {severity}",
             "Energy costs are rising after a pipeline incident in {location}. That raises bills for every "
             "company that buys fuel or power, and threatens the sales of {companies}. No figure for the "
             "loss is available yet."),
            ("Dearer energy follows {location} pipeline incident",
             "A pipeline incident has struck {location}, and investors are watching {companies}. Dearer "
             "energy also adds to costs across the economy. The effect on trade in the city is described as "
             "{severity}."),
        ],
    },
    "drought": {
        "herald": [
            ("Drought around {location} threatens dearer food",
             "A drought has struck the {location} area, and farm produce is getting more expensive. Families "
             "may feel it at the market. The effect on business is described as {severity}."),
            ("Drought hits {location} farmers and traders",
             "Farmers and market traders around {location} are facing a drought. Those affected include "
             "{companies}. With less produce to sell, prices are rising."),
            ("{location} drought pushes up the price of farm produce",
             "Farm produce cost more today as drought took hold around {location}. Early reports call the "
             "effect on trade {severity}. The drought has hit {companies}."),
        ],
        "ogene": [
            ("{location}: drought hits, farm produce prices rise",
             "Drought strikes the {location} area. Farm produce is getting dearer. The disruption is rated "
             "{severity}."),
            ("Drought disrupts business in {location}",
             "A drought is hurting business in {location}. Affected: {companies}."),
            ("Farm produce dearer as drought grips {location}",
             "Drought grips {location} and produce prices climb. The full cost is not yet known."),
        ],
        "ledger": [
            ("{location} drought lifts farm produce prices",
             "A drought in the {location} area has pushed the price of farm produce higher today. The effect "
             "on business there is rated {severity}. Those hit include {companies}."),
            ("Drought in {location}: effect on trade rated {severity}",
             "Farm produce is costing more after drought struck {location}. That raises costs for companies "
             "that buy produce and may feed into shop prices. No figure has yet been put on losses at "
             "{companies}."),
            ("Investors weigh {location} drought as produce costs rise",
             "A drought has struck {location}, and investors are watching {companies}. Lower sales and "
             "dearer produce are the main worries. The effect on trade is described as {severity}."),
        ],
    },
    "local_boom": {
        "herald": [
            ("Business is booming in {location}",
             "Shops, markets and offices in {location} are unusually busy today, and traders "
             "have more customers than usual. The lift to trade is described as {severity}. Those doing well "
             "include {companies}."),
            ("Good times for {location} traders as business picks up",
             "There is a spring in the step of {location} today, with business running above normal. For "
             "{companies}, it means more customers and more sales. How long it lasts is not yet known."),
            ("{location} enjoys a busy spell",
             "Customers are spending freely in {location} and local businesses are feeling the benefit. "
             "Early reports call the boost {severity}. The busy spell is good news for {companies}."),
        ],
        "ogene": [
            ("{location}: business booms",
             "Trade is unusually brisk in {location}. The boost is rated {severity}."),
            ("Boom time in {location}",
             "Business is surging in {location}. Gaining: {companies}."),
            ("Brisk trade lifts {location}",
             "Customers are out in force in {location}. The lift to trade is described as {severity}."),
        ],
        "ledger": [
            ("{location} boom: lift to trade rated {severity}",
             "Business in {location} is running above normal today. The lift to trade is rated {severity}. "
             "Those set to benefit include {companies}."),
            ("Brisk trade in {location} points to higher sales",
             "Sales are rising in {location} as customers spend more than usual. That means more cash coming "
             "in for {companies}. No figure for the extra sales is available yet."),
            ("Investors eye {location} companies as local trade surges",
             "A burst of business has reached {location}, and investors are watching {companies}. Higher "
             "sales are expected while it lasts. The boost is described as {severity}."),
        ],
    },
    "sector_strike": {
        "herald": [
            ("Workers down tools across the {sector} business",
             "Workers in the {sector} business have gone on strike today, and customers are feeling it. The "
             "disruption is described as {severity}. Those affected include {companies}."),
            ("Strike brings a hard day for {sector} companies and customers",
             "A strike has spread across {sector} companies, leaving work undone and customers waiting. For "
             "{companies}, each day without staff is a day of lost business. Nobody yet knows how long it "
             "will last."),
            ("Customers wait as strike hits the {sector} business",
             "People who rely on {sector} companies faced delays today as staff walked out. Early reports "
             "call the effect on business {severity}. The strike has hit {companies}."),
        ],
        "ogene": [
            ("Strike: workers walk out at {sector} companies",
             "Workers at {sector} companies are on strike. The disruption is rated {severity}."),
            ("Strike halts work in the {sector} business",
             "A strike is under way across the {sector} business. Affected: {companies}."),
            ("Walkout hits {sector} companies",
             "Staff are out and work is stopping at {sector} companies. The cost is not yet known. The "
             "effect is described as {severity}."),
        ],
        "ledger": [
            ("Strike in the {sector} business: disruption rated {severity}",
             "A strike across the {sector} business has stopped work today. The disruption is rated "
             "{severity}. Those hit include {companies}."),
            ("Strike threatens sales at {sector} companies",
             "Companies in {sector} are losing sales while their workers are on strike. Many costs, such as "
             "rent and loan payments, still have to be paid. Those affected include {companies}."),
            ("Investors count cost as strike hits the {sector} business",
             "A strike in the {sector} business is expected to cut into the sales and cash of {companies}. "
             "The effect is described as {severity}. No figure for the loss is available yet."),
        ],
    },
    "sector_demand_surge": {
        "herald": [
            ("Customers flock to {sector} companies",
             "Customers are buying more than usual from {sector} companies today. The lift to business is "
             "described as {severity}. Those doing well include {companies}."),
            ("Busy days for workers in the {sector} business",
             "Staff across the {sector} business are being kept busy by a sudden rush of customers. For "
             "{companies}, it means more orders and more sales. How long the rush lasts is not yet known."),
            ("Sudden rush of buyers lifts the {sector} business",
             "Demand has jumped in the {sector} business, which simply means more people want to buy. Early "
             "reports call the boost {severity}. The rush is good news for {companies}."),
        ],
        "ogene": [
            ("Demand surges for {sector} companies",
             "Customers are rushing to {sector} companies. The boost is rated {severity}."),
            ("Buyers pile in: the {sector} business booms",
             "Sales are jumping across the {sector} business. Gaining: {companies}."),
            ("Orders jump in the {sector} business",
             "Demand is surging at {sector} companies right now. The lift to sales is described as "
             "{severity}."),
        ],
        "ledger": [
            ("Demand surge in the {sector} business: boost rated {severity}",
             "Customers are buying more from companies in {sector} today. The boost to sales is rated "
             "{severity}. Those set to benefit include {companies}."),
            ("Rising demand points to higher sales at {sector} companies",
             "Sales are climbing across the {sector} business as more customers come to buy. That means more "
             "cash coming in for {companies}. No figure for the extra sales is available yet."),
            ("Investors watch {sector} companies as customers spend more",
             "A surge in buying has reached the {sector} business, and investors are watching {companies}. "
             "Higher sales are expected while it lasts. The boost is described as {severity}."),
        ],
    },
    "good_harvest": {
        "herald": [
            ("Good harvest cheers the {sector} business and shoppers alike",
             "Farms have brought in a good harvest, and farm produce is getting cheaper. That is welcome "
             "news for families at the market. Those with more to sell include {companies}."),
            ("Plenty to sell: a good harvest for {sector} companies",
             "It has been a good harvest, and {sector} companies have plenty to sell. Early reports call the "
             "boost {severity}. With more produce about, prices are coming down."),
            ("Fuller baskets ahead as the harvest comes in well",
             "A good harvest is pushing down the price of farm produce, which should help household budgets. "
             "For {companies}, it means more to sell. The lift to the {sector} business is described as "
             "{severity}."),
        ],
        "ogene": [
            ("Good harvest: farm produce prices fall",
             "The harvest is good and produce is getting cheaper. The boost to the {sector} business is "
             "rated {severity}."),
            ("Harvest boost for {sector} companies",
             "A good harvest lifts {sector} companies. Gaining: {companies}."),
            ("Good crop lifts the {sector} business",
             "Crops are in and the harvest is good. Farm produce prices are falling. The lift is described "
             "as {severity}."),
        ],
        "ledger": [
            ("Good harvest in the {sector} business: boost rated {severity}",
             "A good harvest has raised the amount of farm produce for sale today. The boost to the {sector} "
             "business is rated {severity}. Those set to benefit include {companies}."),
            ("Farm produce prices fall after good harvest",
             "A good harvest is pushing the price of farm produce down. That lowers costs for companies that "
             "buy produce and may ease shop prices. More produce to sell should lift sales at {companies}."),
            ("Investors watch {sector} companies after good harvest",
             "The harvest has come in well, and investors are watching {companies}. They have more produce "
             "to sell, though at lower prices. The effect on the {sector} business is described as "
             "{severity}."),
        ],
    },
    "network_outage": {
        "herald": [
            ("Network goes down, leaving {sector} customers cut off",
             "A network outage struck the {sector} business today, leaving customers unable to use services "
             "they rely on. The disruption is described as {severity}. Those affected include {companies}."),
            ("Frustration as outage hits {sector} companies",
             "Customers and staff of {sector} companies are waiting for services to come back after a "
             "network outage. For {companies}, every hour offline is lost business. Nobody yet knows what it "
             "will cost."),
            ("A day of failed connections in the {sector} business",
             "Networks failed across the {sector} business today, disrupting work for the people who depend "
             "on them. Early reports call the effect {severity}. The outage has hit {companies}."),
        ],
        "ogene": [
            ("Network outage hits {sector} companies",
             "Networks are down at {sector} companies. The disruption is rated {severity}."),
            ("Outage: services down across the {sector} business",
             "A network outage is disrupting the {sector} business. Affected: {companies}."),
            ("Networks fail in the {sector} business",
             "Services are offline at {sector} companies. The cost is not yet known. The effect is described "
             "as {severity}."),
        ],
        "ledger": [
            ("Network outage in the {sector} business: disruption rated {severity}",
             "A network outage has interrupted services across the {sector} business today. The disruption "
             "is rated {severity}. Those hit include {companies}."),
            ("Outage threatens sales at {sector} companies",
             "Companies in {sector} cannot sell their services while their networks are down. Fixing the "
             "fault adds to their costs. Those affected include {companies}."),
            ("Investors count cost of outage in the {sector} business",
             "The network outage in the {sector} business is expected to cut into the sales of {companies}. "
             "The effect is described as {severity}. No figure for the loss is available yet."),
        ],
    },
    "new_competition": {
        "herald": [
            ("New rivals arrive in the {sector} business",
             "New companies have entered the {sector} business and are winning customers. Shoppers have more "
             "choice, but the older names feel the squeeze. Those losing customers include {companies}."),
            ("More choice for customers as newcomers take on {sector} companies",
             "Customers of {sector} companies now have new names to choose from. For {companies}, that means "
             "fighting harder to keep every customer. The effect on their business is described as "
             "{severity}."),
            ("Old hands in the {sector} business face fresh competition",
             "Fresh competition reached the {sector} business today, with newcomers drawing customers away. "
             "Early reports call the effect on existing companies {severity}. The newcomers are a challenge "
             "for {companies}."),
        ],
        "ogene": [
            ("New rivals enter the {sector} business",
             "Newcomers are taking customers from {sector} companies. The effect is rated {severity}."),
            ("Competition heats up for {sector} companies",
             "New rivals are in the {sector} business. Under pressure: {companies}."),
            ("Newcomers challenge the {sector} business",
             "New companies are winning customers in the {sector} business. The hit to existing companies is "
             "described as {severity}."),
        ],
        "ledger": [
            ("New competition in the {sector} business: effect rated {severity}",
             "New rivals have entered the {sector} business and are taking customers. The effect on existing "
             "companies is rated {severity}. Those losing sales include {companies}."),
            ("New rivals threaten sales at {sector} companies",
             "Companies in {sector} face lower sales as new rivals win customers. They may also have to cut "
             "prices to compete, which leaves less profit on each sale. Those affected include {companies}."),
            ("Investors weigh new competition in the {sector} business",
             "New entrants in the {sector} business are expected to cut into the sales of {companies}. The "
             "effect is described as {severity}. No figure for the lost sales is available yet."),
        ],
    },
}
