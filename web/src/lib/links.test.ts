import { test } from "node:test";
import assert from "node:assert/strict";
import { discoverHref, investHref, stockHref } from "./links.ts";

/**
 * These exist because the deep link was wrong for two phases and nothing
 * said so. It pointed at /stock/RELIANCE, which answers 404; StockSaathi
 * routes on the hash. A broken outbound link fails silently -- on somebody
 * else's site, in a tab this app never sees again.
 */

test("a holding links to the page that exists", () => {
  const href = stockHref("RELIANCE");
  assert.ok(href.includes("#/stocks/RELIANCE"), href);
  assert.ok(!href.includes("/stock/"), "the 404 path must not come back");
});

test("the tags land before the hash, where analytics can read them", () => {
  // After the '#' they are part of the fragment, which is never sent to the
  // server and never recorded. This is the whole reason these are built
  // with URL rather than by joining strings.
  const href = stockHref("TCS");
  assert.ok(href.indexOf("utm_source=spendincheck") < href.indexOf("#"), href);
  assert.ok(href.indexOf("utm_medium=holding_row") < href.indexOf("#"), href);
});

test("every outbound link is tagged", () => {
  for (const href of [investHref, discoverHref, stockHref("INFY")]) {
    assert.ok(href.includes("utm_source=spendincheck"), href);
    assert.ok(/utm_medium=[a-z_]+/.test(href), href);
  }
});

test("a symbol with an ampersand travels unencoded", () => {
  // Their route matches [A-Za-z0-9&\-_.]+ against the raw hash, so M%26M
  // misses it entirely. M&M and BAJAJ-AUTO are both real symbols.
  assert.ok(stockHref("M&M").endsWith("#/stocks/M&M"));
  assert.ok(stockHref("BAJAJ-AUTO").endsWith("#/stocks/BAJAJ-AUTO"));
});

test("a symbol is upper-cased and stripped of what cannot be routed", () => {
  assert.ok(stockHref("reliance").endsWith("#/stocks/RELIANCE"));
  assert.ok(stockHref("IN FY/X").endsWith("#/stocks/INFYX"));
});

test("the empty state points at the markets browser, not the front page", () => {
  // Somebody who clicked "find something worth holding" has already decided
  // to look at instruments; a landing page asks them to decide again.
  assert.ok(discoverHref.includes("#/stocks"), discoverHref);
});
