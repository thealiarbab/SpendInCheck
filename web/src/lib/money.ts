/**
 * Money handling.
 *
 * The API sends money as a STRING ("1234.50"), never a JSON number. Binary
 * floating point cannot represent 0.1 exactly, so `0.1 + 0.2 === 0.30000000000000004`
 * and a column of figures drifts a unit at a time. The rule here:
 *
 *   parse to integer minor units -> do all arithmetic there -> format once, at render.
 *
 * Never do arithmetic on a formatted string, and never format twice.
 *
 * "Minor units" rather than paise, because a rupee's hundredth is not
 * universal: the yen has no minor unit at all and the Gulf dinars are
 * divided into thousandths. `setCurrency` is called once, from the session,
 * and everything below works to that currency's own scale. Intl already
 * knows every currency's symbol, grouping and number of places, so none of
 * that is written down here.
 */

/** Money as an exact integer count of the currency's smallest unit. */
export type Minor = number;

interface Active {
  code: string;
  digits: number;
  scale: number;
  format: Intl.NumberFormat;
  formatWhole: Intl.NumberFormat;
}

/** The locale to group digits by. Indian grouping is a lakh/crore matter. */
const LOCALE = "en-IN";

function build(code: string): Active {
  let digits = 2;
  try {
    // ?? 2 because the type is optional: every currency Intl knows resolves
    // to a real number here, and the fallback is only there so an engine
    // that omitted it cannot turn every amount into NaN.
    digits = new Intl.NumberFormat(LOCALE, { style: "currency", currency: code })
      .resolvedOptions().maximumFractionDigits ?? 2;
  } catch {
    // An unknown code would otherwise throw on every render. Fall back to
    // the default rather than take the screen down over a label.
    code = "INR";
  }
  return {
    code,
    digits,
    scale: 10 ** digits,
    format: new Intl.NumberFormat(LOCALE, {
      style: "currency", currency: code,
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    }),
    formatWhole: new Intl.NumberFormat(LOCALE, {
      style: "currency", currency: code,
      minimumFractionDigits: 0, maximumFractionDigits: 0,
    }),
  };
}

let active = build("INR");

/**
 * Set the currency every figure is parsed and rendered in.
 *
 * Module state rather than a prop threaded through every screen: it is read
 * by nearly every cell that shows a number, it changes on one settings
 * screen, and the formatters are worth building once rather than per row.
 * The screen that changes it reloads, so nothing can be left half-rendered
 * in the old currency.
 */
export function setCurrency(code: string): void {
  if (code && code !== active.code) active = build(code);
}

/** The currency in force. */
export function currencyCode(): string {
  return active.code;
}

/** How many decimal places the current currency is divided into. */
export function currencyDigits(): number {
  return active.digits;
}

/**
 * Parse an API money string (or number) into integer minor units.
 *
 * Accepts "1234.5", "1,234.50", "-99", "₹1,234", 1234.5. Returns 0 for null,
 * undefined or unparseable input, so a missing field renders as zero rather
 * than "NaN".
 */
export function toMinor(value: string | number | null | undefined): Minor {
  if (value === null || value === undefined || value === "") return 0;

  // Strip grouping and any currency symbol. \p{Sc} is every currency sign
  // Unicode knows, so this does not need a list of them either.
  const text = String(value).replace(/[,\s]/g, "").replace(/\p{Sc}/gu, "");
  if (!/^-?\d*\.?\d*$/.test(text) || text === "" || text === "-") return 0;

  const negative = text.startsWith("-");
  const [whole = "0", fraction = ""] = text.replace("-", "").split(".");

  const { digits, scale } = active;
  // One digit beyond the currency's own scale, to round on rather than
  // truncate at.
  const kept = fraction.padEnd(digits + 1, "0").slice(0, digits + 1);
  const minor =
    Number(whole) * scale +
    (digits === 0 ? 0 : Number(kept.slice(0, digits))) +
    (Number(kept[digits]) >= 5 ? 1 : 0);

  return negative ? -minor : minor;
}

/** Convert integer minor units back to the decimal string the API expects. */
export function toApiString(minor: Minor): string {
  const negative = minor < 0;
  const absolute = Math.abs(Math.round(minor));
  const { digits, scale } = active;
  const whole = Math.floor(absolute / scale);
  if (digits === 0) return `${negative ? "-" : ""}${whole}`;
  const remainder = absolute % scale;
  return `${negative ? "-" : ""}${whole}.${String(remainder).padStart(digits, "0")}`;
}

/**
 * Format minor units in the active currency.
 *
 * Intl supplies the symbol, the placement and the grouping, so ₹12,34,567.89
 * groups the Indian way while $1,234,567.89 groups the western way, without
 * either being written down here.
 */
export function formatMoney(minor: Minor, options?: { whole?: boolean }): string {
  const formatter = options?.whole ? active.formatWhole : active.format;
  return formatter.format(minor / active.scale);
}

/** Format with an explicit sign, for deltas and profit and loss. */
export function formatSigned(minor: Minor, options?: { whole?: boolean }): string {
  const formatted = formatMoney(Math.abs(minor), options);
  if (minor > 0) return `+${formatted}`;
  if (minor < 0) return `-${formatted}`;
  return formatted;
}

/**
 * Compact form for tight spaces.
 *
 * Lakh and crore for the rupee, because that is how the figures are spoken
 * where they are used. Every other currency gets Intl's own compact
 * notation, which knows the right abbreviation for its locale rather than
 * having K/L/Cr imposed on it.
 */
export function formatCompact(minor: Minor): string {
  const major = minor / active.scale;
  const size = Math.abs(major);

  if (active.code === "INR") {
    const sign = minor < 0 ? "-" : "";
    if (size >= 1e7) return `${sign}₹${(size / 1e7).toFixed(2)}Cr`;
    if (size >= 1e5) return `${sign}₹${(size / 1e5).toFixed(2)}L`;
    if (size >= 1e3) return `${sign}₹${(size / 1e3).toFixed(1)}K`;
    return formatMoney(minor, { whole: true });
  }

  if (size < 1e3) return formatMoney(minor, { whole: true });
  return new Intl.NumberFormat(LOCALE, {
    style: "currency", currency: active.code,
    notation: "compact", maximumFractionDigits: 1,
  }).format(major);
}

/** Percentage with a fixed one decimal place, guarding division by zero. */
export function formatPercent(part: Minor, whole: Minor): string {
  if (whole === 0) return "—";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

/**
 * Which semantic colour a figure should take.
 * Returns a token name, so callers never hardcode a colour.
 */
export function moneyTone(minor: Minor): "credit" | "debit" | "level" {
  if (minor > 0) return "credit";
  if (minor < 0) return "debit";
  return "level";
}

/**
 * A holding's quantity, as many places as it actually has.
 *
 * Stored as DECIMAL(10,4) and sent as "500.0000", because units are not
 * money and rounding them to a currency's scale loses a real distinction --
 * 12.3456 units of a fund is not the same holding as 12.35. Trailing zeros
 * are dropped here rather than on the wire, so the exact figure survives
 * the trip and only the display is tidied.
 */
export function formatQuantity(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  if (!text.includes(".")) return text;
  const trimmed = text.replace(/0+$/, "").replace(/\.$/, "");
  return trimmed === "" ? "0" : trimmed;
}
