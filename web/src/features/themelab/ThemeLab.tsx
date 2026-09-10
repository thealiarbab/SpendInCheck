import { useEffect, useRef, useState } from "react";
import { formatRupees, formatSigned, toPaise } from "../../lib/money";
import { contrastRatio, gradeContrast, resolveToken } from "./contrast";
import type { Theme } from "../../app/ThemeProvider";
import styles from "./ThemeLab.module.css";

/* Realistic figures, so the comparison is judged on real content rather than
   placeholder text. Amounts are API-shaped strings, parsed the way the app does. */
const HOLDINGS = [
  { name: "Reliance Industries", ticker: "RELIANCE", buy: "1180.00", now: "1279.00", qty: 12 },
  { name: "TCS", ticker: "TCS", buy: "3420.00", now: "3128.40", qty: 5 },
  { name: "HDFC Bank", ticker: "HDFCBANK", buy: "1502.50", now: "1688.25", qty: 20 },
];

const BUDGETS = [
  { category: "Groceries", limit: "9000.00", spent: "7420.00" },
  { category: "Dining out", limit: "4000.00", spent: "5310.50" },
  { category: "Transport", limit: "3000.00", spent: "3000.00" },
];

/** The token pairs worth checking: a foreground against the ground it sits on. */
const CONTRAST_PAIRS: Array<{
  fg: string;
  bg: string;
  label: string;
  large?: boolean;
  decorative?: boolean;
}> = [
  { fg: "--content-primary", bg: "--surface-page", label: "Body text on page" },
  { fg: "--content-secondary", bg: "--surface-raised", label: "Secondary on card" },
  { fg: "--content-muted", bg: "--surface-raised", label: "Muted on card" },
  { fg: "--accent-default", bg: "--surface-page", label: "Accent on page" },
  { fg: "--content-on-accent", bg: "--accent-default", label: "Text on accent fill" },
  { fg: "--money-credit", bg: "--surface-raised", label: "Credit figure" },
  { fg: "--money-debit", bg: "--surface-raised", label: "Debit figure" },
  { fg: "--state-error", bg: "--surface-raised", label: "Error text" },
  { fg: "--accent-invest", bg: "--surface-page", label: "Invest link" },
  /* Decorative separators are not UI components under WCAG 1.4.11, so this
     row is measured for information but not graded. */
  { fg: "--line-default", bg: "--surface-page", label: "Hairline rule (decorative)", decorative: true },
];

/** One themed pane: a live miniature of the app under a single theme. */
function Pane({ theme }: { theme: Theme }) {
  const [amount, setAmount] = useState("1250.00");
  const showError = toPaise(amount) <= 0;

  const totalPnl = HOLDINGS.reduce(
    (sum, holding) => sum + (toPaise(holding.now) - toPaise(holding.buy)) * holding.qty,
    0,
  );
  const totalValue = HOLDINGS.reduce(
    (sum, holding) => sum + toPaise(holding.now) * holding.qty,
    0,
  );

  return (
    <div className={styles.pane} data-theme={theme}>
      <p className={styles.paneLabel}>{theme}</p>

      <div className={styles.statRow}>
        <div className={styles.stat}>
          <p className={styles.statLabel}>Portfolio</p>
          <p className={styles.statValue}>{formatRupees(totalValue, { whole: true })}</p>
        </div>
        <div className={styles.stat}>
          <p className={styles.statLabel}>Total P&amp;L</p>
          <p className={totalPnl >= 0 ? styles.statValueCredit : styles.statValueDebit}>
            {formatSigned(totalPnl, { whole: true })}
          </p>
        </div>
        <div className={styles.stat}>
          <p className={styles.statLabel}>Holdings</p>
          <p className={styles.statValue}>{HOLDINGS.length}</p>
        </div>
      </div>

      <div className={styles.card}>
        <h3>Holdings</h3>
        <div className="scroll-x">
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Asset</th>
                <th className={styles.right}>Now</th>
                <th className={styles.right}>P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {HOLDINGS.map((holding) => {
                const pnl = (toPaise(holding.now) - toPaise(holding.buy)) * holding.qty;
                return (
                  <tr key={holding.ticker}>
                    <td>
                      {holding.name}
                      <br />
                      <span className={styles.invest}>{holding.ticker} &#8599;</span>
                    </td>
                    <td className={styles.right}>{formatRupees(toPaise(holding.now))}</td>
                    <td className={pnl >= 0 ? styles.rightCredit : styles.rightDebit}>
                      {formatSigned(pnl, { whole: true })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className={styles.card}>
        <h3>Budgets</h3>
        {BUDGETS.map((budget) => {
          const limit = toPaise(budget.limit);
          const spent = toPaise(budget.spent);
          const over = spent > limit;
          const level = spent === limit;
          const status = over ? "Over" : level ? "Level" : "Under";
          return (
            <div key={budget.category} className={styles.budgetRow}>
              <div className={styles.budgetHead}>
                <span className={styles.budgetName}>{budget.category}</span>
                <span className={styles.budgetFigures}>
                  {formatRupees(spent, { whole: true })} / {formatRupees(limit, { whole: true })}
                  <span className={over ? styles.pillOver : styles.pillUnder}>{status}</span>
                </span>
              </div>
              <div className={styles.meter}>
                <div
                  className={styles.meterFill}
                  data-state={over ? "over" : level ? "level" : "under"}
                  style={{ width: `${Math.min(100, (spent / limit) * 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className={styles.card}>
        <h3>Add a transaction</h3>
        <div className={styles.field}>
          <label className={styles.label} htmlFor={`amount-${theme}`}>
            Amount
          </label>
          <input
            id={`amount-${theme}`}
            className={showError ? styles.inputError : styles.input}
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            aria-invalid={showError}
          />
          {showError ? <span className={styles.errorText}>Must be greater than 0.</span> : null}
        </div>
        <div className={styles.buttons}>
          <button type="button" className={styles.btn}>
            Save
          </button>
          <button type="button" className={styles.btnGhost}>
            Cancel
          </button>
          <button type="button" className={styles.btnDanger}>
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

type ContrastRow = {
  label: string;
  brass: number | null;
  paper: number | null;
  large: boolean;
  decorative: boolean;
};

/** Decorative rows are reported but never marked as failing. */
function cellClass(row: ContrastRow, ratio: number | null): string {
  if (row.decorative) return styles.mono;
  return gradeContrast(ratio, row.large) === "fail" ? styles.fail : styles.pass;
}

/** Measures every token pair in both themes, as the browser resolved them. */
function ContrastTable() {
  const brassRef = useRef<HTMLDivElement>(null);
  const paperRef = useRef<HTMLDivElement>(null);
  const [rows, setRows] = useState<ContrastRow[]>([]);

  useEffect(() => {
    const brass = brassRef.current;
    const paper = paperRef.current;
    if (!brass || !paper) return;

    setRows(
      CONTRAST_PAIRS.map((pair) => ({
        label: pair.label,
        large: Boolean(pair.large),
        decorative: Boolean(pair.decorative),
        brass: contrastRatio(resolveToken(brass, pair.fg), resolveToken(brass, pair.bg)),
        paper: contrastRatio(resolveToken(paper, pair.fg), resolveToken(paper, pair.bg)),
      })),
    );
  }, []);

  return (
    <>
      {/* Off-screen probes: the browser resolves each theme's tokens on these,
          which is more trustworthy than re-deriving the cascade by hand. */}
      <div ref={brassRef} data-theme="brass" className="sr-only" />
      <div ref={paperRef} data-theme="paper" className="sr-only" />

      <table className={styles.tokenTable}>
        <thead>
          <tr>
            <th>Pair</th>
            <th>Brass</th>
            <th>Paper</th>
            <th>Needs</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <td>{row.label}</td>
              <td className={cellClass(row, row.brass)}>
                {row.brass === null ? "—" : `${row.brass.toFixed(2)}:1`}
              </td>
              <td className={cellClass(row, row.paper)}>
                {row.paper === null ? "—" : `${row.paper.toFixed(2)}:1`}
              </td>
              <td className={styles.mono}>{row.decorative ? "n/a" : row.large ? "3:1" : "4.5:1"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function ThemeLab() {
  return (
    <div className={styles.page}>
      <div>
        <h1>Brass or paper</h1>
        <p className={styles.lede}>
          The same screens, the same data, both themes live at once. Clear either amount field
          to see the error state.
        </p>
      </div>

      <div className={styles.panes}>
        <Pane theme="brass" />
        <Pane theme="paper" />
      </div>

      <div>
        <h2>Contrast</h2>
        <p className={styles.lede}>
          Measured from the values the browser resolved, not the hex in the file. A ratio below
          the requirement fails WCAG AA and the token needs adjusting.
        </p>
        <ContrastTable />
      </div>
    </div>
  );
}
