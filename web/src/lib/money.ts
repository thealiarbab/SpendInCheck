/**
 * Rupee handling.
 *
 * The API sends money as a STRING ("1234.50"), never a JSON number. Binary
 * floating point cannot represent 0.1 exactly, so `0.1 + 0.2 === 0.30000000000000004`
 * and a column of rupees drifts by a paisa at a time. The rule here:
 *
 *   parse to integer paise -> do all arithmetic in paise -> format once, at render.
 *
 * Never do arithmetic on a formatted string, and never format twice.
 */

/** Money as an exact integer count of paise. 100 paise = 1 rupee. */
export type Paise = number;

/**
 * Parse an API money string (or number) into integer paise.
 *
 * Accepts "1234.5", "1,234.50", "-99", "₹1,234", 1234.5. Returns 0 for null,
 * undefined or unparseable input, so a missing field renders as ₹0.00 rather
 * than "NaN".
 */
export function toPaise(value: string | number | null | undefined): Paise {
  if (value === null || value === undefined || value === "") return 0;

  const text = String(value).replace(/[₹,\s]/g, "");
  if (!/^-?\d*\.?\d*$/.test(text) || text === "" || text === "-") return 0;

  const negative = text.startsWith("-");
  const [whole = "0", fraction = ""] = text.replace("-", "").split(".");

  // Pad or truncate to exactly two decimal places, rounding the third digit.
  const twoDigits = fraction.padEnd(3, "0").slice(0, 3);
  const paise =
    Number(whole) * 100 +
    Number(twoDigits.slice(0, 2)) +
    (Number(twoDigits[2]) >= 5 ? 1 : 0);

  return negative ? -paise : paise;
}

/** Convert integer paise back to the decimal string the API expects. */
export function toApiString(paise: Paise): string {
  const negative = paise < 0;
  const absolute = Math.abs(Math.round(paise));
  const rupees = Math.floor(absolute / 100);
  const remainder = absolute % 100;
  return `${negative ? "-" : ""}${rupees}.${String(remainder).padStart(2, "0")}`;
}

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const inrWhole = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/**
 * Format paise as rupees with Indian digit grouping: ₹12,34,567.89, not
 * ₹1,234,567.89. `Intl` with the en-IN locale handles the lakh/crore grouping,
 * which is exactly the sort of thing that is miserable to hand-roll.
 */
export function formatRupees(paise: Paise, options?: { whole?: boolean }): string {
  const formatter = options?.whole ? inrWhole : inr;
  return formatter.format(paise / 100);
}

/** Format with an explicit sign, for deltas and P&L. */
export function formatSigned(paise: Paise, options?: { whole?: boolean }): string {
  const formatted = formatRupees(Math.abs(paise), options);
  if (paise > 0) return `+${formatted}`;
  if (paise < 0) return `-${formatted}`;
  return formatted;
}

/** Compact form for tight spaces: ₹1.2L, ₹3.4Cr. Falls back to full below ₹1,000. */
export function formatCompact(paise: Paise): string {
  const rupees = Math.abs(paise) / 100;
  const sign = paise < 0 ? "-" : "";
  if (rupees >= 1e7) return `${sign}₹${(rupees / 1e7).toFixed(2)}Cr`;
  if (rupees >= 1e5) return `${sign}₹${(rupees / 1e5).toFixed(2)}L`;
  if (rupees >= 1e3) return `${sign}₹${(rupees / 1e3).toFixed(1)}K`;
  return formatRupees(paise, { whole: true });
}

/** Percentage with a fixed one decimal place, guarding division by zero. */
export function formatPercent(part: Paise, whole: Paise): string {
  if (whole === 0) return "—";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

/**
 * Which semantic colour a figure should take.
 * Returns a CSS custom property name, so callers never hardcode a colour.
 */
export function moneyTone(paise: Paise): "credit" | "debit" | "level" {
  if (paise > 0) return "credit";
  if (paise < 0) return "debit";
  return "level";
}

/**
 * A holding's quantity, as many places as it actually has.
 *
 * Stored as DECIMAL(10,4) and sent as "500.0000", because units are not
 * money and rounding them to paise loses real precision -- 12.3456 units of
 * a fund is a different holding from 12.35. Trailing zeros are dropped here
 * rather than on the wire, so the exact figure survives the trip and only
 * the display is tidied.
 */
export function formatQuantity(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  if (!text.includes(".")) return text;
  const trimmed = text.replace(/0+$/, "").replace(/\.$/, "");
  return trimmed === "" ? "0" : trimmed;
}
