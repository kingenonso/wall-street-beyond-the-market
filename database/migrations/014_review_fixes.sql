-- Stage 4: changes that came out of the independent loophole review.

-- A share whose worth has moved further than a day's price limit allows can find no buyer
-- (or no seller) inside the limits, and so would never trade again. When that happens the
-- exchange moves its price to the limit, once a trading day. This records the day it last did.
ALTER TABLE market_instruments ADD COLUMN marked_session date;
