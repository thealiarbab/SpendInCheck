/**
 * Outbound links to StockSaathi.
 *
 * Every one carries UTM parameters so the referral traffic is measurable, and
 * every one is built here rather than inline, so the tagging can never be
 * forgotten on a new link.
 */

const BASE = "https://stocksaathi.co.in";

function tagged(path: string, medium: string): string {
  const url = new URL(path, BASE);
  url.searchParams.set("utm_source", "spendincheck");
  url.searchParams.set("utm_medium", medium);
  return url.toString();
}

/** The Invest item in the top bar. */
export const investHref = tagged("/", "nav_invest");

/** A holding's ticker, deep-linked to its StockSaathi page. */
export function stockHref(symbol: string): string {
  return tagged(`/stock/${encodeURIComponent(symbol.toUpperCase())}`, "holding_row");
}

/** The empty state on the investments screen. */
export const discoverHref = tagged("/", "investments_empty");

/** The surplus nudge shown when a month closes under budget. */
export const surplusHref = tagged("/", "surplus_nudge");

/** Applied to every outbound anchor: a new tab, and no window.opener handle. */
export const externalLinkProps = {
  target: "_blank",
  rel: "noopener noreferrer",
} as const;
