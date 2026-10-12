// The calculator on the work screen (redesign). Figures from the company's accounts can be tapped
// into it, so a player never retypes a number. It only does arithmetic: + − × ÷ and brackets.

/** Works out a sum written with + − × ÷ ( ) and decimals. Null if it is not a sum it can read. Never runs code. */
export function evaluate(text: string): number | null {
  const tokens = text.replace(/,/g, "").replace(/×/g, "*").replace(/÷/g, "/").replace(/−/g, "-").match(/\d+(?:\.\d+)?|[-+*/()]/g);
  if (!tokens || tokens.join("") !== text.replace(/,/g, "").replace(/×/g, "*").replace(/÷/g, "/").replace(/−/g, "-").replace(/\s+/g, "")) return null;
  let at = 0;
  const peek = () => tokens[at];
  const take = () => tokens[at++];
  function primary(): number | null {
    const t = take();
    if (t === undefined) return null;
    if (t === "-") { const v = primary(); return v === null ? null : -v; }
    if (t === "(") { const v = sum(); if (take() !== ")") return null; return v; }
    const n = Number(t);
    return Number.isFinite(n) ? n : null;
  }
  function product(): number | null {
    let left = primary();
    while (left !== null && (peek() === "*" || peek() === "/")) {
      const op = take(); const right = primary();
      if (right === null) return null;
      if (op === "/" && right === 0) return null;
      left = op === "*" ? left * right : left / right;
    }
    return left;
  }
  function sum(): number | null {
    let left = product();
    while (left !== null && (peek() === "+" || peek() === "-")) {
      const op = take(); const right = product();
      if (right === null) return null;
      left = op === "+" ? left + right : left - right;
    }
    return left;
  }
  const result = sum();
  return at === tokens.length && result !== null && Number.isFinite(result) ? result : null;
}

export type Figure = { label: string; value: string };

/** Adds a tapped figure to the sum. A figure straight after a number or a bracket is added with a "+",
 * so two figures never run together into one long number; the player can change the sign. */
export function appendFigure(sum: string, figure: string): string {
  const trimmed = sum.trimEnd();
  return /[\d)]$/.test(trimmed) ? `${trimmed} + ${figure}` : `${trimmed}${trimmed && !/[(]$/.test(trimmed) ? " " : ""}${figure}`;
}

const round = (v: number) => (Math.round(v * 100) / 100).toLocaleString("en-NG", { maximumFractionDigits: 2 });

/** For a percentage answer, the two ways the player can put a result in. Nothing is guessed: they choose. */
export function percentChoices(result: number): { label: string; value: number }[] {
  return [
    { label: `It is already a percentage: put ${round(result)} in`, value: result },
    { label: `It is a fraction: put ${round(result * 100)}% in`, value: result * 100 },
  ];
}

export function Calculator({ text, setText, onUse, percent = false }: {
  text: string;
  setText: (text: string) => void;
  /** Put the result into the answer box. */
  onUse?: (value: number) => void;
  /** The answer is a percentage: the player says whether the result is a fraction or already a percentage. Nothing is guessed. */
  percent?: boolean;
}) {
  const result = text.trim() ? evaluate(text) : null;
  const press = (key: string) => setText(key === "C" ? "" : key === "⌫" ? text.slice(0, -1) : text + key);
  const keys = ["7", "8", "9", "÷", "4", "5", "6", "×", "1", "2", "3", "−", "0", ".", "(", "+", ")", "⌫", "C"];
  const words: Record<string, string> = { "÷": "divide", "×": "times", "−": "minus", "+": "plus", ".": "point", "⌫": "delete the last character", C: "clear", "(": "open bracket", ")": "close bracket" };
  return (
    <div className="calc">
      <label className="calc-line">
        <span className="sr-only">The sum</span>
        <input value={text} onChange={(e) => setText(e.target.value)} inputMode="decimal" placeholder="Tap figures or type a sum" />
      </label>
      <div className="calc-result mono" aria-live="polite">
        {text.trim() === "" ? <span className="muted small">The answer shows here</span>
          : result === null ? <span className="muted small">Not a sum yet</span>
          : <>= {result.toLocaleString("en-NG", { maximumFractionDigits: 6 })}</>}
      </div>
      <div className="calc-keys">
        {keys.map((k) => (
          <button type="button" key={k} className={/[÷×−+]/.test(k) ? "calc-key calc-op" : "calc-key"} aria-label={words[k] ?? k} onClick={() => press(k)}>{k}</button>
        ))}
      </div>
      {onUse && result !== null && !percent && (
        <button type="button" className="button-outline wide" onClick={() => onUse(result)}>Put this in my answer</button>
      )}
      {onUse && result !== null && percent && (
        <div className="calc-use">
          {percentChoices(result).map((choice) => (
            <button type="button" key={choice.label} className="button-outline" onClick={() => onUse(choice.value)}>{choice.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}
