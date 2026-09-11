/**
 * Outbound links to StockSaathi.
 *
 * Every one carries UTM parameters so the referral traffic is measurable, and
 * every one is built here rather than inline, so the tagging can never be
 * forgotten on a new link.
 *
 * StockSaathi routes on the hash: a stock is `/#/stocks/RELIANCE`, not
 * `/stock/RELIANCE`. That matters twice. The path this file used to build
 * answered 404, and the query string has to be placed *before* the hash or
 * the tags land inside the fragment where no analytics will ever see them.
 * `new URL` puts them in the right place; it is the reason these are built
 * with it rather than by joining strings.
 */

const BASE = "https://stocksaathi.co.in";

function tagged(path: string, medium: string): string {
  const url = new URL(path, BASE);
  url.searchParams.set("utm_source", "spendincheck");
  url.searchParams.set("utm_medium", medium);
  return url.toString();
}

/**
 * A symbol reduced to what their router will match.
 *
 * Their route is /^\/stocks\/([A-Za-z0-9&\-_.]+)\/?$/ against the raw hash,
 * so percent-encoding is the wrong answer here: M&M must travel as M&M, and
 * encodeURIComponent would send M%26M and miss the route. Anything outside
 * that set cannot be linked to at all, so it is dropped rather than sent.
 */
function routable(symbol: string): string {
  return symbol.toUpperCase().replace(/[^A-Z0-9&\-_.]/g, "");
}

/** The Invest item in the top bar. */
export const investHref = tagged("/", "nav_invest");

/** A holding's ticker, deep-linked to its StockSaathi page. */
export function stockHref(symbol: string): string {
  return tagged(`/#/stocks/${routable(symbol)}`, "holding_row");
}

/**
 * The empty state on the investments screen.
 *
 * Their markets browser rather than their front page: somebody who clicked
 * "find something worth holding" has already decided to look at instruments,
 * and a landing page asks them to decide again.
 */
export const discoverHref = tagged("/#/stocks", "investments_empty");

/** The surplus nudge shown when a month closes under budget. */
export const surplusHref = tagged("/", "surplus_nudge");

/** Applied to every outbound anchor: a new tab, and no window.opener handle. */
export const externalLinkProps = {
  target: "_blank",
  rel: "noopener noreferrer",
} as const;
