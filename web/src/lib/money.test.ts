import test from "node:test";
import assert from "node:assert/strict";
import {
  toMinor,
  toApiString,
  formatMoney,
  formatSigned,
  formatChange,
  formatCompact,
  formatPercent,
  formatQuantity,
  moneyTone,
  setCurrency,
  currencyDigits,
} from "./money.ts";

/** Run a block with a currency in force, always restoring the rupee after. */
function inCurrency(code: string, body: () => void) {
  setCurrency(code);
  try {
    body();
  } finally {
    setCurrency("INR");
  }
}

test("parses the money strings the API actually sends", () => {
  assert.equal(toMinor("1234.50"), 123450);
  assert.equal(toMinor("1,234.50"), 123450);
  assert.equal(toMinor("₹1,234"), 123400);
  assert.equal(toMinor("1234.5"), 123450);
  assert.equal(toMinor("-99"), -9900);
  assert.equal(toMinor(1234.5), 123450);
});

test("strips any currency sign, not only the rupee", () => {
  assert.equal(toMinor("$1,234.50"), 123450);
  assert.equal(toMinor("€1.00"), 100);
  assert.equal(toMinor("¥1234"), 123400);
});

test("rounds a place beyond the currency rather than truncating it", () => {
  assert.equal(toMinor("10.005"), 1001);
  assert.equal(toMinor("10.004"), 1000);
});

test("treats missing or unparseable input as zero, never NaN", () => {
  assert.equal(toMinor(null), 0);
  assert.equal(toMinor(undefined), 0);
  assert.equal(toMinor(""), 0);
  assert.equal(toMinor("abc"), 0);
  assert.equal(toMinor("-"), 0);
});

test("round-trips back to the API format", () => {
  assert.equal(toApiString(toMinor("1234.50")), "1234.50");
  assert.equal(toApiString(toMinor("7")), "7.00");
  assert.equal(toApiString(toMinor("-0.05")), "-0.05");
});

test("groups digits the Indian way, not the western way", () => {
  assert.equal(formatMoney(12345678900), "₹12,34,56,789.00");
  assert.equal(formatMoney(123450), "₹1,234.50");
  assert.equal(formatSigned(50000), "+₹500.00");
  assert.equal(formatSigned(-50000), "-₹500.00");
  assert.equal(formatSigned(0), "₹0.00");
});

test("compacts large figures to lakh and crore", () => {
  assert.equal(formatCompact(123456789000), "₹123.46Cr");
  assert.equal(formatCompact(12345600), "₹1.23L");
  assert.equal(formatCompact(500000), "₹5.0K");
});

// --- currencies that are not divided into hundredths ------------------------

test("a currency with no minor unit has a scale of one", () => {
  inCurrency("JPY", () => {
    assert.equal(currencyDigits(), 0);
    // 1234 yen is 1234 minor units, not 123400.
    assert.equal(toMinor("1234"), 1234);
    assert.equal(toMinor("1234.6"), 1235);
    assert.equal(toApiString(1234), "1234");
  });
});

test("a dinar keeps three places", () => {
  inCurrency("KWD", () => {
    assert.equal(currencyDigits(), 3);
    assert.equal(toMinor("1.234"), 1234);
    assert.equal(toMinor("1.2345"), 1235);
    assert.equal(toApiString(1234), "1.234");
  });
});

test("switching currency changes the label, never the magnitude", () => {
  // The same figure, read back under a different currency, is the same size.
  assert.equal(formatMoney(100000), "₹1,000.00");
  inCurrency("USD", () => {
    assert.equal(toApiString(100000), "1000.00");
  });
});

test("a well-formed but unknown code prints as itself", () => {
  // Intl accepts any three letters and shows the code where a symbol would
  // go. The server only ever sends codes from the ISO list, so this is a
  // statement about the floor, not the normal path.
  //
  // The separator is a non-breaking space, which is correct -- a currency
  // must not be left at the end of a line without its figure -- so the
  // comparison normalises it rather than the formatter emitting a plain one.
  inCurrency("ZZZ", () => {
    assert.equal(formatMoney(100000).replace(/ /g, " "), "ZZZ 1,000.00");
  });
});

test("a malformed code falls back rather than taking the screen down", () => {
  // This one really does throw inside Intl, and a currency label is not
  // worth an unrendered page.
  inCurrency("12", () => {
    assert.equal(formatMoney(100000), "₹1,000.00");
  });
});

// --- everything else --------------------------------------------------------

test("percentages guard division by zero", () => {
  assert.equal(formatPercent(5000, 10000), "50.0%");
  assert.equal(formatPercent(5000, 0), "—");
});

test("quantities keep the places they have and lose the ones they do not", () => {
  assert.equal(formatQuantity("500.0000"), "500");
  assert.equal(formatQuantity("12.3456"), "12.3456");
  assert.equal(formatQuantity("12.3400"), "12.34");
  assert.equal(formatQuantity(null), "—");
});

test("tone follows the sign", () => {
  assert.equal(moneyTone(1), "credit");
  assert.equal(moneyTone(-1), "debit");
  assert.equal(moneyTone(0), "level");
});

// --- a day's move ------------------------------------------------------------
//
// The upstream sends a fraction. Everything here is about the one
// multiplication by a hundred, and about it happening once.

test("a fraction becomes a percentage, once", () => {
  setCurrency("INR");
  assert.equal(formatChange(-0.0039), "−0.39%");
  assert.equal(formatChange(0.0212), "+2.12%");
});

test("a flat day is not dressed up with a sign", () => {
  assert.equal(formatChange(0), "0.00%");
});

test("two places, because a tenth of a percent is real money", () => {
  // At one place this is 0.0%, which reads as "nothing happened" on a
  // holding where it is several hundred rupees.
  assert.equal(formatChange(0.0004), "+0.04%");
});

test("no change to report is a dash, not a zero", () => {
  // 0.00% is a claim that the price did not move. Null is the absence of
  // any claim at all, and they must not look the same.
  assert.equal(formatChange(null), "—");
  assert.equal(formatChange(undefined), "—");
  assert.equal(formatChange(NaN), "—");
});

test("a minus sign, not a hyphen", () => {
  // U+2212 lines up with the digits in a column of figures; the hyphen
  // sits high and short and makes a table look ragged.
  assert.ok(formatChange(-0.05).startsWith("−"));
});
