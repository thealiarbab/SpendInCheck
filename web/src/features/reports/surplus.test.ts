import { test } from "node:test";
import assert from "node:assert/strict";
import { MATERIAL, shouldOffer } from "./surplus.ts";

/**
 * The rules that keep one of three placements from becoming an advert.
 *
 * Every one of these fails quietly if it is wrong: the card simply appears
 * when it should not, which looks like a feature rather than a bug to
 * everyone except the person being sold to at the wrong moment.
 */

const base = {
  month: "2026-08", today: "2026-09",
  budgeted: 100_000, difference: 20_000, dismissed: false,
};

test("a finished month that came in under budget earns the card", () => {
  assert.equal(shouldOffer(base), true);
});

test("the month being lived in never does", () => {
  // The important one. On the third of the month everybody is under
  // budget, and telling them to invest the difference is telling them to
  // spend money they are about to need on rent.
  assert.equal(shouldOffer({ ...base, month: "2026-09" }), false);
  assert.equal(shouldOffer({ ...base, month: "2026-10" }), false,
    "nor a month that has not started");
});

test("going over budget is not a surplus", () => {
  assert.equal(shouldOffer({ ...base, difference: -5_000 }), false);
  assert.equal(shouldOffer({ ...base, difference: 0 }), false);
});

test("a month with no limits set cannot be under them", () => {
  // Otherwise every month with no budgets looks like a windfall, because
  // budgeted minus spent is zero minus zero.
  assert.equal(shouldOffer({ ...base, budgeted: 0, difference: 0 }), false);
});

test("a trivial surplus is not worth a card", () => {
  const budgeted = 100_000;
  assert.equal(shouldOffer({ ...base, budgeted, difference: 4_000 }), false);
  assert.equal(shouldOffer({ ...base, budgeted, difference: 5_000 }), true,
    "exactly at the floor counts");
});

test("the floor is a share, so it holds at any scale", () => {
  // An absolute figure would be right in rupees and absurd in yen, which
  // has no minor unit at all, or in dinars, which have three.
  for (const budgeted of [1_000, 100_000, 100_000_000]) {
    assert.equal(
      shouldOffer({ ...base, budgeted, difference: budgeted * MATERIAL }), true);
    assert.equal(
      shouldOffer({ ...base, budgeted, difference: budgeted * MATERIAL - 1 }), false);
  }
});

test("dismissed stays dismissed, whatever else is true", () => {
  assert.equal(shouldOffer({ ...base, dismissed: true }), false);
});

test("a month at the turn of a year is still just a string comparison", () => {
  // YYYY-MM sorts correctly as text, which is the whole reason these are
  // compared rather than parsed. December before January is the case that
  // would catch a naive month-number comparison.
  assert.equal(shouldOffer({ ...base, month: "2025-12", today: "2026-01" }), true);
  assert.equal(shouldOffer({ ...base, month: "2026-01", today: "2025-12" }), false);
});
