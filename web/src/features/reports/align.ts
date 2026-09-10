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
