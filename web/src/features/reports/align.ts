import { toMinor } from "../../lib/money.ts";  // extensioned so node --test can resolve it, as in money.test.ts

/**
 * Line up a sparse series against a continuous run of months.
 *
 * The trend and cashflow endpoints omit months that had no rows at all --
 * deliberately, because a table should not invent them. A chart wants the
 * opposite: a missing March drawn as a gap would put April where March
 * belongs and quietly redraw the whole year. So the months a chart plots
 * come from the net-worth series, which is generated from a calendar and is
 * therefore always complete, and every other series is fitted onto it.
 */
export function alignTo<Row extends { month: string }>(
  months: string[], rows: Row[], read: (row: Row) => string,
): number[] {
  const found = new Map(rows.map((row) => [row.month, toMinor(read(row))]));
  return months.map((month) => found.get(month) ?? 0);
}

/**
 * The same, for a series that accumulates.
 *
 * A running total has no gaps: a month with no transactions did not reset
 * the balance to zero, it left it exactly where it was. Filling those with
 * zero would draw a sawtooth out of a figure that never moved.
 */
export function alignRunning<Row extends { month: string }>(
  months: string[], rows: Row[], read: (row: Row) => string,
): number[] {
  const found = new Map(rows.map((row) => [row.month, toMinor(read(row))]));
  let carried = 0;
  return months.map((month) => {
    const value = found.get(month);
    if (value !== undefined) carried = value;
    return carried;
  });
}


/**
 * "2026-08" as "August 2026".
 *
 * Here rather than in either screen because both the reports page and the
 * surplus card name the same month, and two copies of a date format is how
 * one screen says "August 2026" while the other says "Aug 2026".
 */
export function monthName(month: string): string {
  const [year, index] = month.split("-").map(Number);
  if (!year || !index) return month;
  return new Date(year, index - 1, 1)
    .toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

/**
 * The month it is where the person is, as YYYY-MM.
 *
 * toISOString() is UTC, and this is compared against a month somebody
 * picked from a control showing their own calendar. In IST that is five
 * and a half hours on the first of every month when the two disagree --
 * the picker offering October while UTC still says September -- and the
 * surplus card, which is the one thing that asks "is this month over yet",
 * got it wrong for exactly that window.
 *
 * Two copies of this existed: Reports corrected for the offset and
 * SurplusCard did not, which is the version of this bug that is hardest to
 * see, because both look right on their own.
 */
export function thisMonth(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 7);
}
