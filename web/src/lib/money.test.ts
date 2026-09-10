import test from "node:test";
import assert from "node:assert/strict";
import {
  toPaise,
  toApiString,
  formatRupees,
  formatSigned,
  formatCompact,
  formatPercent,
  moneyTone,
} from "./money.ts";

test("parses the money strings the API actually sends", () => {
  assert.equal(toPaise("1234.50"), 123450);
  assert.equal(toPaise("1,234.50"), 123450);
  assert.equal(toPaise("₹1,234"), 123400);
  assert.equal(toPaise("1234.5"), 123450);
  assert.equal(toPaise("-99"), -9900);
  assert.equal(toPaise(1234.5), 123450);
});

test("rounds a third decimal place rather than truncating it", () => {
  assert.equal(toPaise("10.005"), 1001);
  assert.equal(toPaise("10.004"), 1000);
});

test("treats missing or unparseable input as zero, never NaN", () => {
  assert.equal(toPaise(null), 0);
  assert.equal(toPaise(undefined), 0);
  assert.equal(toPaise(""), 0);
  assert.equal(toPaise("abc"), 0);
  assert.equal(toPaise("-"), 0);
});

test("round-trips back to the API format", () => {
  assert.equal(toApiString(toPaise("1234.50")), "1234.50");
  assert.equal(toApiString(toPaise("7")), "7.00");
  assert.equal(toApiString(toPaise("-0.05")), "-0.05");
});

test("groups digits the Indian way, not the western way", () => {
  assert.equal(formatRupees(12345678900), "₹12,34,56,789.00");
  assert.equal(formatRupees(123450), "₹1,234.50");
  assert.equal(formatSigned(50000), "+₹500.00");
  assert.equal(formatSigned(-50000), "-₹500.00");
  assert.equal(formatSigned(0), "₹0.00");
});

test("compacts large figures to lakh and crore", () => {
  assert.equal(formatCompact(123456789000), "₹123.46Cr");
  assert.equal(formatCompact(12345600), "₹1.23L");
  assert.equal(formatCompact(500000), "₹5.0K");
});

test("percentages guard division by zero", () => {
  assert.equal(formatPercent(5000, 10000), "50.0%");
  assert.equal(formatPercent(5000, 0), "—");
});

test("tone follows the sign", () => {
  assert.equal(moneyTone(1), "credit");
  assert.equal(moneyTone(-1), "debit");
  assert.equal(moneyTone(0), "level");
});

test("integer paise arithmetic does not drift where float does", () => {
  let paise = 0;
  let float = 0;
  for (let i = 0; i < 200; i++) {
    paise += toPaise("0.10");
    float += 0.1;
  }
  assert.equal(toApiString(paise), "20.00");
  // The whole reason this module exists:
  assert.notEqual(float, 20);
});
