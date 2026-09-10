import test from "node:test";
import assert from "node:assert/strict";
import { alignTo, alignRunning } from "./align.ts";

/** The axis a chart plots against: always complete, however sparse the data. */
const YEAR = ["2026-01", "2026-02", "2026-03", "2026-04"];

const value = (row: { value: string }) => row.value;

test("a month that has a row keeps its own figure", () => {
  const rows = [{ month: "2026-02", value: "12.50" }];
  assert.deepEqual(alignTo(YEAR, rows, value), [0, 1250, 0, 0]);
});

test("a month with no row reads as zero, not as a gap", () => {
  // The point of this: February must stay in position two. Dropping the
  // absent months instead would slide March a slot to the left and quietly
  // relabel the whole year.
  const rows = [{ month: "2026-01", value: "1" }, { month: "2026-04", value: "4" }];
  assert.deepEqual(alignTo(YEAR, rows, value), [100, 0, 0, 400]);
});

test("months the series does not mention are simply not plotted", () => {
  const rows = [{ month: "2025-12", value: "9" }];
  assert.deepEqual(alignTo(YEAR, rows, value), [0, 0, 0, 0]);
});

test("a running total carries forward across an empty month", () => {
  // The balance did not fall to nothing in February and March; it did not
  // move at all. Zero-filling would draw a cliff and a climb that never
  // happened.
  const rows = [{ month: "2026-01", value: "500" }, { month: "2026-04", value: "800" }];
  assert.deepEqual(alignRunning(YEAR, rows, value), [50000, 50000, 50000, 80000]);
});

test("a running total that starts late reads as zero before it starts", () => {
  const rows = [{ month: "2026-03", value: "70" }];
  assert.deepEqual(alignRunning(YEAR, rows, value), [0, 0, 7000, 7000]);
});

test("a running total carries a negative balance forward too", () => {
  const rows = [{ month: "2026-02", value: "-300" }];
  assert.deepEqual(alignRunning(YEAR, rows, value), [0, -30000, -30000, -30000]);
});

test("an empty axis draws nothing rather than throwing", () => {
  assert.deepEqual(alignTo([], [{ month: "2026-01", value: "1" }], value), []);
  assert.deepEqual(alignRunning([], [], value), []);
});
