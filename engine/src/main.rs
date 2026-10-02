//! The engine as a small program the server talks to.
//!
//! The server writes a request on the engine's input and reads the answer from
//! its output, one after another, for as long as the server runs. Everything is
//! plain text, one item per line, so either side is easy to check by eye.
//!
//! Ordinary trading:
//!     MATCH <B|S> <limit price, or - for a market order> <quantity> <low> <high> <n>
//!     <id> <price> <quantity> <seq>          n lines: the waiting orders on the other side
//! answered by
//!     OK <k> <quantity left>
//!     <waiting order id> <price> <quantity>  k lines, best first
//!
//! The opening auction:
//!     UNCROSS <low> <high> <yesterday's close> <n>
//!     <id> <B|S> <price> <quantity> <seq>    n lines
//! answered by
//!     OK <k> <the one auction price, or 0 if nothing trades>
//!     <buy order id> <sell order id> <quantity>   k lines
//!
//! Anything the engine cannot make sense of is answered with one line: ERR <why>.

use bsx_engine::{match_order, uncross, AuctionOrder, Resting, Side};
use std::io::{self, BufRead, Write};

const MOST_ORDERS: usize = 200_000;

fn number(text: Option<&str>, what: &str) -> Result<i64, String> {
    text.ok_or_else(|| format!("{what} is missing"))?
        .parse::<i64>()
        .map_err(|_| format!("{what} is not a whole number"))
}

fn side(text: Option<&str>) -> Result<Side, String> {
    match text {
        Some("B") => Ok(Side::Buy),
        Some("S") => Ok(Side::Sell),
        _ => Err("the side must be B or S".into()),
    }
}

fn count(text: Option<&str>) -> Result<usize, String> {
    let n = number(text, "the number of orders")?;
    if n < 0 || n as usize > MOST_ORDERS {
        return Err("too many orders in one request".into());
    }
    Ok(n as usize)
}

fn next_line(lines: &mut impl Iterator<Item = io::Result<String>>) -> Result<String, String> {
    match lines.next() {
        Some(Ok(line)) => Ok(line),
        _ => Err("the request ended early".into()),
    }
}

fn handle(first: &str, lines: &mut impl Iterator<Item = io::Result<String>>) -> Result<String, String> {
    let mut words = first.split_whitespace();
    match words.next() {
        Some("MATCH") => {
            let incoming = side(words.next())?;
            let limit = match words.next() {
                Some("-") => None,
                other => Some(number(other, "the price")?),
            };
            let quantity = number(words.next(), "the quantity")?;
            let low = number(words.next(), "the lower limit")?;
            let high = number(words.next(), "the upper limit")?;
            let n = count(words.next())?;
            // Read every line of the request before judging it, so one bad line
            // cannot leave the rest behind to be mistaken for the next request.
            let mut book = Vec::with_capacity(n);
            let mut problem = None;
            for _ in 0..n {
                let line = next_line(lines)?;
                let mut w = line.split_whitespace();
                let parsed = (|| -> Result<Resting, String> {
                    Ok(Resting {
                        id: number(w.next(), "an order's id")?,
                        price: number(w.next(), "an order's price")?,
                        quantity: number(w.next(), "an order's quantity")?,
                        seq: number(w.next(), "an order's place in the queue")?,
                    })
                })();
                match parsed {
                    Ok(order) => book.push(order),
                    Err(why) => problem = Some(why),
                }
            }
            if let Some(why) = problem {
                return Err(why);
            }
            let (fills, left) = match_order(incoming, limit, quantity, &book, low, high)?;
            let mut out = format!("OK {} {}\n", fills.len(), left);
            for f in fills {
                out.push_str(&format!("{} {} {}\n", f.resting_id, f.price, f.quantity));
            }
            Ok(out)
        }
        Some("UNCROSS") => {
            let low = number(words.next(), "the lower limit")?;
            let high = number(words.next(), "the upper limit")?;
            let reference = number(words.next(), "yesterday's close")?;
            let n = count(words.next())?;
            let mut orders = Vec::with_capacity(n);
            let mut problem = None;
            for _ in 0..n {
                let line = next_line(lines)?;
                let mut w = line.split_whitespace();
                let parsed = (|| -> Result<AuctionOrder, String> {
                    Ok(AuctionOrder {
                        id: number(w.next(), "an order's id")?,
                        side: side(w.next())?,
                        price: number(w.next(), "an order's price")?,
                        quantity: number(w.next(), "an order's quantity")?,
                        seq: number(w.next(), "an order's place in the queue")?,
                    })
                })();
                match parsed {
                    Ok(order) => orders.push(order),
                    Err(why) => problem = Some(why),
                }
            }
            if let Some(why) = problem {
                return Err(why);
            }
            match uncross(&orders, low, high, reference)? {
                None => Ok("OK 0 0\n".into()),
                Some((price, fills)) => {
                    let mut out = format!("OK {} {}\n", fills.len(), price);
                    for f in fills {
                        out.push_str(&format!("{} {} {}\n", f.buy_id, f.sell_id, f.quantity));
                    }
                    Ok(out)
                }
            }
        }
        Some("PING") => Ok("OK 0 0\n".into()),
        _ => Err("unknown request".into()),
    }
}

fn main() {
    let stdin = io::stdin();
    let mut lines = stdin.lock().lines();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    while let Some(Ok(first)) = lines.next() {
        if first.trim().is_empty() {
            continue;
        }
        let answer = match handle(&first, &mut lines) {
            Ok(text) => text,
            Err(why) => format!("ERR {why}\n"),
        };
        if out.write_all(answer.as_bytes()).is_err() || out.flush().is_err() {
            break;
        }
    }
}
