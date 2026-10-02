//! The order-matching engine of the Broad Street Exchange.
//!
//! It does one thing: given the orders waiting in a share's order book and
//! one new order, it says which waiting orders the new one trades with, at
//! what price and for how many shares. It also runs the opening auction.
//!
//! It holds nothing between calls and moves no money. The server keeps the
//! order book in the database, asks the engine who trades with whom, and
//! then settles each trade through the ledger. So the engine can never
//! create or lose a naira or a share: it only proposes pairings, and the
//! server checks every one before acting on it.
//!
//! The rules (design document, section 11):
//!   * Best price first. A buyer is matched with the cheapest seller, a
//!     seller with the highest bidder.
//!   * At the same price, whoever placed their order first goes first.
//!   * A trade happens at the price of the order that was waiting.
//!   * Nothing trades outside the day's price limits.
//!
//! Prices are whole kobo per share. Quantities are whole shares.

/// One order waiting in the book.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Resting {
    pub id: i64,
    pub price: i64,
    pub quantity: i64,
    /// The order in which orders arrived. Lower is earlier.
    pub seq: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Side {
    Buy,
    Sell,
}

/// One pairing in ordinary trading: the new order trades with a waiting one.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Fill {
    pub resting_id: i64,
    pub price: i64,
    pub quantity: i64,
}

/// One pairing in the opening auction.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuctionFill {
    pub buy_id: i64,
    pub sell_id: i64,
    pub quantity: i64,
}

/// An order in the opening auction.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuctionOrder {
    pub id: i64,
    pub side: Side,
    pub price: i64,
    pub quantity: i64,
    pub seq: i64,
}

/// Match one new order against the waiting orders on the other side of the book.
///
/// `limit` is the worst price the new order accepts: the most a buyer will
/// pay, the least a seller will take. `None` means "the best price available"
/// (a market order). `low` and `high` are the day's price limits; waiting
/// orders priced outside them cannot trade today and are passed over.
///
/// Returns the pairings, best first, and how many shares of the new order are left.
pub fn match_order(
    side: Side,
    limit: Option<i64>,
    quantity: i64,
    opposite: &[Resting],
    low: i64,
    high: i64,
) -> Result<(Vec<Fill>, i64), String> {
    if quantity <= 0 {
        return Err("the quantity must be more than zero".into());
    }
    if low <= 0 || high < low {
        return Err("the price limits are not valid".into());
    }
    if let Some(price) = limit {
        if price <= 0 {
            return Err("the price must be more than zero".into());
        }
    }
    let mut book: Vec<&Resting> = Vec::with_capacity(opposite.len());
    for order in opposite {
        if order.price <= 0 || order.quantity <= 0 {
            return Err(format!("order {} in the book is not valid", order.id));
        }
        if order.price >= low && order.price <= high {
            book.push(order);
        }
    }
    // Best price first; at the same price, first come first served.
    match side {
        Side::Buy => book.sort_by_key(|o| (o.price, o.seq, o.id)),
        Side::Sell => book.sort_by_key(|o| (-o.price, o.seq, o.id)),
    }

    let mut left = quantity;
    let mut fills = Vec::new();
    for order in book {
        if left == 0 {
            break;
        }
        let acceptable = match (side, limit) {
            (_, None) => true,
            (Side::Buy, Some(most)) => order.price <= most,
            (Side::Sell, Some(least)) => order.price >= least,
        };
        if !acceptable {
            break; // the book is sorted, so nothing further on is acceptable either
        }
        let traded = left.min(order.quantity);
        fills.push(Fill { resting_id: order.id, price: order.price, quantity: traded });
        left -= traded;
    }
    Ok((fills, left))
}

/// The opening auction: every order collected before the market opens trades
/// at ONE price, the price at which the most shares change hands.
///
/// If several prices trade the same number of shares, the one that leaves the
/// fewest shares unmatched wins; if still tied, the one closest to yesterday's
/// closing price (`reference`); if still tied, the lower one.
///
/// Returns that price and the pairings, or `None` if no buyer and seller agree.
pub fn uncross(
    orders: &[AuctionOrder],
    low: i64,
    high: i64,
    reference: i64,
) -> Result<Option<(i64, Vec<AuctionFill>)>, String> {
    if low <= 0 || high < low {
        return Err("the price limits are not valid".into());
    }
    let mut buys: Vec<&AuctionOrder> = Vec::new();
    let mut sells: Vec<&AuctionOrder> = Vec::new();
    for order in orders {
        if order.price <= 0 || order.quantity <= 0 {
            return Err(format!("order {} is not valid", order.id));
        }
        if order.price < low || order.price > high {
            continue;
        }
        match order.side {
            Side::Buy => buys.push(order),
            Side::Sell => sells.push(order),
        }
    }
    if buys.is_empty() || sells.is_empty() {
        return Ok(None);
    }

    let mut prices: Vec<i64> = buys.iter().chain(sells.iter()).map(|o| o.price).collect();
    prices.sort_unstable();
    prices.dedup();

    // (shares traded, shares left unmatched, distance from yesterday's close, price)
    let mut best: Option<(i128, i128, i64, i64)> = None;
    for &price in &prices {
        let demand: i128 = buys.iter().filter(|o| o.price >= price).map(|o| o.quantity as i128).sum();
        let supply: i128 = sells.iter().filter(|o| o.price <= price).map(|o| o.quantity as i128).sum();
        let volume = demand.min(supply);
        if volume == 0 {
            continue;
        }
        let candidate = (volume, (demand - supply).abs(), (price - reference).abs(), price);
        let better = match best {
            None => true,
            Some((v, imbalance, distance, p)) => {
                (candidate.0 > v)
                    || (candidate.0 == v && candidate.1 < imbalance)
                    || (candidate.0 == v && candidate.1 == imbalance && candidate.2 < distance)
                    || (candidate.0 == v && candidate.1 == imbalance && candidate.2 == distance && candidate.3 < p)
            }
        };
        if better {
            best = Some(candidate);
        }
    }
    let Some((volume, _, _, price)) = best else {
        return Ok(None);
    };

    // The keenest orders trade first: highest bids, lowest offers; then first come first served.
    let mut willing_buys: Vec<&AuctionOrder> = buys.into_iter().filter(|o| o.price >= price).collect();
    let mut willing_sells: Vec<&AuctionOrder> = sells.into_iter().filter(|o| o.price <= price).collect();
    willing_buys.sort_by_key(|o| (-o.price, o.seq, o.id));
    willing_sells.sort_by_key(|o| (o.price, o.seq, o.id));

    let mut fills = Vec::new();
    let mut left = volume;
    let (mut b, mut s) = (0usize, 0usize);
    let mut buy_left = willing_buys[0].quantity;
    let mut sell_left = willing_sells[0].quantity;
    while left > 0 {
        let traded = buy_left.min(sell_left).min(left as i64);
        fills.push(AuctionFill { buy_id: willing_buys[b].id, sell_id: willing_sells[s].id, quantity: traded });
        left -= traded as i128;
        buy_left -= traded;
        sell_left -= traded;
        if left == 0 {
            break;
        }
        if buy_left == 0 {
            b += 1;
            buy_left = willing_buys[b].quantity;
        }
        if sell_left == 0 {
            s += 1;
            sell_left = willing_sells[s].quantity;
        }
    }
    Ok(Some((price, fills)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn r(id: i64, price: i64, quantity: i64, seq: i64) -> Resting {
        Resting { id, price, quantity, seq }
    }
    fn a(id: i64, side: Side, price: i64, quantity: i64) -> AuctionOrder {
        AuctionOrder { id, side, price, quantity, seq: id }
    }

    #[test]
    fn a_buyer_gets_the_cheapest_seller_first() {
        let book = [r(1, 1050, 100, 1), r(2, 1000, 100, 2), r(3, 1020, 100, 3)];
        let (fills, left) = match_order(Side::Buy, Some(1030), 250, &book, 900, 1100).unwrap();
        assert_eq!(fills, vec![
            Fill { resting_id: 2, price: 1000, quantity: 100 },
            Fill { resting_id: 3, price: 1020, quantity: 100 },
        ]);
        assert_eq!(left, 50); // the seller at 1050 wants more than this buyer will pay
    }

    #[test]
    fn a_seller_gets_the_highest_bidder_first() {
        let book = [r(1, 980, 100, 1), r(2, 1000, 60, 2), r(3, 990, 100, 3)];
        let (fills, left) = match_order(Side::Sell, Some(985), 200, &book, 900, 1100).unwrap();
        assert_eq!(fills, vec![
            Fill { resting_id: 2, price: 1000, quantity: 60 },
            Fill { resting_id: 3, price: 990, quantity: 100 },
        ]);
        assert_eq!(left, 40);
    }

    #[test]
    fn at_the_same_price_first_come_is_first_served() {
        let book = [r(7, 1000, 100, 30), r(8, 1000, 100, 10), r(9, 1000, 100, 20)];
        let (fills, _) = match_order(Side::Buy, Some(1000), 150, &book, 900, 1100).unwrap();
        assert_eq!(fills.iter().map(|f| (f.resting_id, f.quantity)).collect::<Vec<_>>(), vec![(8, 100), (9, 50)]);
    }

    #[test]
    fn the_trade_is_at_the_waiting_orders_price() {
        let (fills, _) = match_order(Side::Buy, Some(1090), 10, &[r(1, 1000, 10, 1)], 900, 1100).unwrap();
        assert_eq!(fills[0].price, 1000); // the buyer offered 1090 and pays 1000
    }

    #[test]
    fn a_market_order_takes_the_best_prices_available_and_no_more_than_there_is() {
        let book = [r(1, 1000, 30, 1), r(2, 1010, 30, 2)];
        let (fills, left) = match_order(Side::Buy, None, 100, &book, 900, 1100).unwrap();
        assert_eq!(fills.iter().map(|f| f.quantity).sum::<i64>(), 60);
        assert_eq!(left, 40);
    }

    #[test]
    fn nothing_trades_outside_the_days_price_limits() {
        let book = [r(1, 850, 100, 1), r(2, 1150, 100, 2), r(3, 1000, 10, 3)];
        let (fills, left) = match_order(Side::Buy, None, 50, &book, 900, 1100).unwrap();
        assert_eq!(fills, vec![Fill { resting_id: 3, price: 1000, quantity: 10 }]);
        assert_eq!(left, 40);
        let (fills, _) = match_order(Side::Sell, None, 50, &[r(1, 1150, 100, 1)], 900, 1100).unwrap();
        assert!(fills.is_empty());
    }

    #[test]
    fn never_more_than_was_asked_for_and_never_more_than_an_order_holds() {
        let book: Vec<Resting> = (1..=50).map(|i| r(i, 1000 + (i % 7), 1 + (i * 37) % 90, i)).collect();
        for wanted in [1, 7, 90, 500, 100_000] {
            let (fills, left) = match_order(Side::Buy, None, wanted, &book, 900, 1100).unwrap();
            let traded: i64 = fills.iter().map(|f| f.quantity).sum();
            assert_eq!(traded + left, wanted);
            for f in &fills {
                let order = book.iter().find(|o| o.id == f.resting_id).unwrap();
                assert!(f.quantity > 0 && f.quantity <= order.quantity && f.price == order.price);
            }
            let mut ids: Vec<i64> = fills.iter().map(|f| f.resting_id).collect();
            ids.dedup();
            assert_eq!(ids.len(), fills.len()); // no order is used twice
            assert!(fills.windows(2).all(|w| w[0].price <= w[1].price)); // cheapest first
        }
    }

    #[test]
    fn nonsense_is_refused() {
        assert!(match_order(Side::Buy, Some(1000), 0, &[], 900, 1100).is_err());
        assert!(match_order(Side::Buy, Some(1000), -5, &[], 900, 1100).is_err());
        assert!(match_order(Side::Buy, Some(0), 5, &[], 900, 1100).is_err());
        assert!(match_order(Side::Buy, Some(1000), 5, &[r(1, 1000, -3, 1)], 900, 1100).is_err());
        assert!(match_order(Side::Buy, Some(1000), 5, &[], 1100, 900).is_err());
        assert!(match_order(Side::Buy, Some(1000), 5, &[], 0, 900).is_err());
    }

    #[test]
    fn the_auction_picks_the_price_that_trades_the_most_shares() {
        let orders = [
            a(1, Side::Buy, 1020, 100), a(2, Side::Buy, 1010, 100), a(3, Side::Buy, 1000, 100),
            a(4, Side::Sell, 990, 100), a(5, Side::Sell, 1010, 100), a(6, Side::Sell, 1030, 100),
        ];
        let (price, fills) = uncross(&orders, 900, 1100, 1000).unwrap().unwrap();
        assert_eq!(price, 1010); // at 1010: buyers 200, sellers 200
        assert_eq!(fills.iter().map(|f| f.quantity).sum::<i64>(), 200);
        assert_eq!(fills, vec![
            AuctionFill { buy_id: 1, sell_id: 4, quantity: 100 },
            AuctionFill { buy_id: 2, sell_id: 5, quantity: 100 },
        ]);
    }

    #[test]
    fn the_auction_does_nothing_when_buyers_and_sellers_do_not_meet() {
        let orders = [a(1, Side::Buy, 990, 100), a(2, Side::Sell, 1010, 100)];
        assert_eq!(uncross(&orders, 900, 1100, 1000).unwrap(), None);
        assert_eq!(uncross(&[a(1, Side::Buy, 990, 100)], 900, 1100, 1000).unwrap(), None);
        assert_eq!(uncross(&[], 900, 1100, 1000).unwrap(), None);
    }

    #[test]
    fn auction_ties_go_to_the_price_nearest_yesterdays_close() {
        // One buyer at 1040 and one seller at 960: every price between trades the same 100 shares.
        let orders = [a(1, Side::Buy, 1040, 100), a(2, Side::Sell, 960, 100)];
        let (price, _) = uncross(&orders, 900, 1100, 1030).unwrap().unwrap();
        assert_eq!(price, 1040);
        let (price, _) = uncross(&orders, 900, 1100, 970).unwrap().unwrap();
        assert_eq!(price, 960);
    }

    #[test]
    fn the_auction_never_trades_more_than_either_side_offered() {
        let mut orders = Vec::new();
        for i in 1..=40 {
            let side = if i % 2 == 0 { Side::Buy } else { Side::Sell };
            orders.push(a(i, side, 950 + (i * 13) % 100, 10 + (i * 7) % 50));
        }
        let (price, fills) = uncross(&orders, 900, 1100, 1000).unwrap().unwrap();
        for order in &orders {
            let traded: i64 = fills.iter()
                .filter(|f| f.buy_id == order.id || f.sell_id == order.id).map(|f| f.quantity).sum();
            assert!(traded <= order.quantity);
            if traded > 0 {
                match order.side {
                    Side::Buy => assert!(order.price >= price),   // nobody pays more than they offered
                    Side::Sell => assert!(order.price <= price),  // nobody receives less than they asked
                }
            }
        }
        assert!(fills.iter().all(|f| f.quantity > 0));
    }

    #[test]
    fn auction_orders_outside_the_limits_take_no_part() {
        let orders = [a(1, Side::Buy, 1200, 100), a(2, Side::Sell, 1000, 100), a(3, Side::Buy, 1000, 40)];
        let (price, fills) = uncross(&orders, 900, 1100, 1000).unwrap().unwrap();
        assert_eq!((price, fills), (1000, vec![AuctionFill { buy_id: 3, sell_id: 2, quantity: 40 }]));
    }
}
