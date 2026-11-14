// A "?" beside a financial word opens its meaning in one plain line, with a small example.
// The list is the game's own glossary; nothing here depends on the player or the world.

import { useEffect, useId, useRef, useState } from "react";

export const GLOSSARY: Record<string, { means: string; example?: string }> = {
  "BSX 50": { means: "The price of the shares on the exchange, taken together. It started at 1,000.", example: "1,042 means they are worth 4.2% more than when it started." },
  "Market value": { means: "The share price times every share: what the whole company is worth on the exchange.", example: "₦38.50 × 5 billion shares = ₦192.5 billion." },
  "P/E": { means: "Price to earnings: how many years of today’s profit the price pays for. Lower can mean cheaper.", example: "A P/E of 8 means the price is 8 years of profit." },
  "Dividend": { means: "Cash a company pays its owners out of profit, so much for each share.", example: "5.2% a year: ₦5.20 for every ₦100 of shares." },
  "EBITDA": { means: "Profit before interest, tax and the wearing-out of equipment: what the business itself earns.", example: "Lenders compare debts with it." },
  "Debt to EBITDA": { means: "How many years of earnings the company’s debts are. Higher is riskier.", example: "2.1× means its debts are 2.1 years of earnings." },
  "Credit rating": { means: "How safe lenders think the company is, from AAA (safest) down to D (has failed to pay).", example: "AA pays less interest than BB." },
  "Bond": { means: "A loan you can buy and sell. The borrower pays interest, then repays ₦1,000 at the end.", example: "Its price falls when interest rates rise." },
  "Bill": { means: "A three-month loan to the Government. The safest place for cash you do not need for a few weeks." },
  "Yield": { means: "The yearly return you get from a bond if you buy at today’s price and hold it to the end." },
  "Yield curve": { means: "The yearly return investors want for lending to the Government, by length of loan.", example: "Longer loans usually pay more." },
  "Order book": { means: "Buyers and the prices they offer, sellers and the prices they ask. A trade happens where they meet." },
  "Limit order": { means: "An order at your own price: it waits until someone will trade at that price or better." },
  "Market order": { means: "An order at the best price available right now. Quick, but the price is not fixed." },
  "Spread": { means: "The gap between the best price a buyer offers and the lowest a seller asks." },
  "Exchange fee": { means: "Every trade pays 0.5% to the exchange. It is not returned." },
  "Exchange rate": { means: "How many naira one US dollar costs. More naira for a dollar means a weaker naira.", example: "₦1,560 instead of ₦1,500: the naira is 4% weaker, and goods bought abroad cost more." },
  "Inflation": { means: "How much prices in the shops rose over a year.", example: "6% means what cost ₦100 now costs ₦106." },
  "Rental yield": { means: "A year’s rent as a share of a building’s price. Property investors want more of it when interest rates are high.", example: "₦12m rent on a ₦100m building is a 12% yield." },
  "Guide value": { means: "What a property was worth when it was listed: its rent over the yield investors ask, less for wear, plus any bubble in its district.", example: "A guide, not the seller’s lowest price, which nobody sees." },
  "Loan-to-value": { means: "A mortgage as a share of what the property is worth. Above 100% the loan is bigger than the building.", example: "₦60m owed on a ₦80m house is 75%." },
  "Margin loan": { means: "A loan against shares and bonds you hold. If their value falls far enough, the bank calls for cash (a margin call) or sells some.", example: "₦50m borrowed against ₦100m of shares: a 30% fall brings a call." },
  "Short selling": { means: "Borrowing shares and selling them, to buy them back later and give them back. It gains if the price falls and loses, without limit, if it rises." },
  "Call option": { means: "The right to the gain if a price ends above an agreed level (the strike) by a set date. The most you can lose is what you paid for it." },
  "Put option": { means: "The right to the gain if a price ends below the strike by a set date. Owners of shares buy puts as protection." },
  "Future": { means: "An agreement on a price now for something settled later. It gains or loses with the price, one for one, and is settled every night." },
  "Default fund": { means: "Money the clearing house keeps from every trade's fee. When a loser cannot pay, the fund pays the winners and the loser owes the fund." },
  "Swap": { means: "Two sides agree to swap payments each quarter: one pays a fixed amount, the other one that floats with a rate or a price. Only the difference changes hands.", example: "Pay a fixed 18% on ₦1bn and receive the Central Bank's rate: if the rate rises to 20%, you receive the 2% difference." },
  "Preferred share": { means: "A share paying a fixed dividend before ordinary shareholders get anything. It has no vote, and its price moves with interest rates more than with profits." },
  "Warrant": { means: "The right to buy new shares from the company at a set price until a date. If used, the company issues new shares and receives the money." },
  "Mezzanine debt": { means: "A loan ranked after the bank's, so it charges more and usually takes a small share of the company too." },
  "Earn-out": { means: "Part of a price paid later, only if the company reaches a target. Sellers value it below its face because it may never come." },
  "Sale and leaseback": { means: "Selling a building and renting it back: cash today, the use of the building kept, and rent to pay each quarter." },
  "Zoning": { means: "What the planning office allows on a plot: homes, offices and shops, factories, farms, oil and gas, or a mix. A building must fit its zone." },
  "Construction loan": { means: "A bank loan for building, paid out stage by stage as the work is done, and turned into a mortgage when it is finished." },
  "Scoop": { means: "Being first with a confirmed fact, before the news wire carries it. It earns a bonus, readers and reputation." },
  "Declared interest": { means: "Telling readers that your empire holds a position in a company you write about. Hiding it is an offence anyone can expose." },
  "Credibility": { means: "How far readers trust a journalist's name, from 0 to 100. Corrections lower it; a late one lowers it more." },
  "The Ripple": { means: "The chain of causes behind an event: what led to what, kept for good. \u201cWhy?\u201d shows it in one line, in full, or with the numbers." },
  "Deposit guarantee": { means: "Money kept as savings is a claim on the bank. If the bank fails, the Deposit Guarantee Fund makes sure the first ₦5 million each saver has at each bank is safe. Above that, savers bear their share of the bank's losses." },
  "Bank run": { means: "When savers stop trusting a bank they draw their money out. A bank lends most of what it holds, so it cannot pay everyone at once: it must find cash, borrow from the Central Bank, or be closed." },
  "Confidential information": { means: "Information from someone inside a company that the market does not have. Trading on it while it is useful is dealing on confidential information: it is kept for the courts." },
  "Sealed Tip": { means: "One sealed piece of information each real day, matched to your build. It may be valuable, false or worthless; once opened it is useful for four hours." },
  "Intelligence Market": { means: "Where players sell copies of what they know. A buyer sees what a piece is about and how good it looks, and reads it only once bought." },
  "The Chronicle": { means: "The world's memory: your own story, each company's turning points, and the world's big events, with journalists' signed accounts." },
  "Property fund": { means: "A fund that owns buildings. You buy units of it; each unit's value rises and falls with the buildings and their rent." },
  "Volatility": { means: "How much a price swings, worked out from its past daily moves and scaled to a year.", example: "30% a year: in a typical year it might end 30% up or down." },
  "Beta": { means: "How much a share moves with the whole market. 1 moves with it; 1.5 moves half as much again; 0.5 half as much." },
  "Policy rate": { means: "The Central Bank’s interest rate. Banks’ lending and savings rates follow it." },
  "Net worth": { means: "Everything you own at today’s prices: cash, shares and bonds (not retirement savings)." },
  "Cost-to-income": { means: "How much of each naira a bank earns goes on running it. Lower is better.", example: "52% means ₦52 of every ₦100 earned is spent running the bank." },
  "Cash flow": { means: "Money that actually came in and went out, not just what was earned on paper." },
  "Revenue": { means: "Sales: everything customers paid the company before any costs." },
  "Margin": { means: "How much of each naira of sales is left as profit.", example: "A 12% margin keeps ₦12 of every ₦100 sold." },
  "Rights issue": { means: "New shares offered first to the people who already own the company, usually below the market price." },
  "Takeover": { means: "Buying more than half of a company’s shares, so the buyer controls it." },
  "Convertible bond": { means: "A bond that can be swapped for a fixed number of the company’s shares." },
  "Fair value": { means: "What something is worth when worked out from its cash and risks, not from today’s trading." },
  "Covenant": { means: "A promise made to a lender, such as keeping debts below a limit. Breaking it lets the lender act." },
  "Concentration": { means: "How much of your money sits in one place. More in one place means one bad quarter hurts more." },
};

/** A word with a "?" beside it that opens the word's meaning. */
export function Term({ word, children }: { word: keyof typeof GLOSSARY | string; children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<{ left: number; top: number; width: number } | null>(null);
  const id = useId();
  const box = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  // The meaning floats above the page, kept inside the screen, so a table that scrolls sideways never cuts it off.
  function toggle() {
    if (open) { setOpen(false); return; }
    const r = button.current?.getBoundingClientRect();
    if (r) {
      const width = Math.min(300, window.innerWidth - 24);
      const left = Math.max(12, Math.min(r.left, window.innerWidth - width - 12));
      const below = r.bottom + 6;
      setPlace({ left, top: below + 140 > window.innerHeight ? Math.max(12, r.top - 146) : below, width });
    }
    setOpen(true);
  }
  const entry = GLOSSARY[word];
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const shut = () => setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    window.addEventListener("scroll", shut, true);
    window.addEventListener("resize", shut);
    return () => {
      document.removeEventListener("mousedown", away); document.removeEventListener("keydown", key);
      window.removeEventListener("scroll", shut, true); window.removeEventListener("resize", shut);
    };
  }, [open]);
  if (!entry) return <>{children ?? word}</>;
  return (
    <span className="term" ref={box}>
      {children ?? word}
      <button ref={button} type="button" className="term-q" aria-expanded={open} aria-controls={id} aria-label={`What does “${word}” mean?`} onClick={toggle}>?</button>
      {open && (
        <span id={id} role="note" className="term-pop" style={place ? { left: place.left, top: place.top, width: place.width } : undefined}>
          <span className="strong">{word}</span>: {entry.means}
          {entry.example && <span className="muted"> For example: {entry.example}</span>}
        </span>
      )}
    </span>
  );
}
