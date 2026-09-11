import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Quote } from "../lib/api";

/**
 * Live prices, fetched from StockSaathi by the browser.
 *
 * Directly, not through this app's server. Their API is CORS-open and needs
 * no key, and routing a ticking screen through Flask would bill a
 * serverless invocation every few seconds for a number this app does not
 * store. When the direct call fails -- a network in the middle blocking the
 * origin is the realistic case, not the API being down -- it falls back to
 * /api/v1/quotes, which does the same fetch server-side.
 *
 * The poll rate is the upstream's own cache TTL rather than a number chosen
 * here. They cache each symbol for a fixed window and serve that copy to
 * everybody; asking more often than that returns the same figure and costs
 * them a request to say so. If they retune it, this retunes with it.
 *
 * And when the market is closed it does not poll at all. A closing price
 * does not change overnight, and a screen left open on a Sunday should not
 * ask 2,000 times.
 */

const LIVE_QUOTE_URL = "https://stocksaathi.co.in/api/live-quote";

/** Never poll faster than this, whatever the upstream says its TTL is. */
const FLOOR_MS = 10_000;

/** Their documented ceiling per request. */
const MAX_SYMBOLS = 80;

export interface LiveQuotes {
  quotes: Record<string, Quote>;
  /** False when the exchange is shut, which is why nothing is moving. */
  marketOpen: boolean;
  /** True once a fetch has come back, so a screen can wait rather than flash. */
  ready: boolean;
  /** Set when neither the direct call nor the fallback worked. */
  unreachable: boolean;
}

interface Fetched {
  quotes: Record<string, Quote>;
  marketOpen: boolean;
  everyMs: number;
}

/** Shape one upstream quote the way the rest of this app reads one. */
function adopt(raw: Record<string, unknown>): Quote | null {
  const price = raw.price;
  if (typeof price !== "number" || !(price > 0)) return null;
  return {
    // Money reaches the rest of the app as a string, as it does from our own
    // API. It arrives from here as a JSON number, which is exactly the
    // format money must not stay in -- lib/money parses this straight to
    // integer minor units and does every sum there.
    price: String(price),
    prev_close: typeof raw.prev_close === "number" ? String(raw.prev_close) : null,
    // The fraction, untouched. -0.0039 is a fifth of a percent.
    change: typeof raw.change_pct === "number" ? raw.change_pct : null,
    as_of: typeof raw.ts_ms === "number" ? raw.ts_ms : null,
    source: typeof raw.source === "string" ? raw.source : null,
  };
}

async function fetchDirect(symbols: string[]): Promise<Fetched> {
  const url = LIVE_QUOTE_URL + "?symbols=" + encodeURIComponent(symbols.join(","));
  // No credentials: this is a public endpoint on another origin, and sending
  // anything of the user's to it would be both useless and wrong.
  const response = await fetch(url, { credentials: "omit" });
  if (!response.ok) throw new Error("live-quote " + response.status);

  const body = await response.json();
  if (!body?.ok) throw new Error("live-quote refused");

  const quotes: Record<string, Quote> = {};
  for (const [symbol, raw] of Object.entries(body.quotes ?? {})) {
    // A symbol they do not know comes back as an explicit null.
    if (!raw || typeof raw !== "object") continue;
    const quote = adopt(raw as Record<string, unknown>);
    if (quote) quotes[symbol] = quote;
  }
  return {
    quotes,
    marketOpen: body.market_open === true,
    everyMs: typeof body.cache_ttl_ms === "number" ? body.cache_ttl_ms : FLOOR_MS,
  };
}

async function fetchViaServer(symbols: string[]): Promise<Fetched> {
  const body = await api.quotes(symbols);
  // Our own endpoint does not report the market's state -- it has no reason
  // to know. Assuming open keeps the fallback path polling; assuming closed
  // would freeze it silently on the one path that is already degraded.
  return { quotes: body.items, marketOpen: true, everyMs: FLOOR_MS };
}

/**
 * Quotes for these symbols, refreshed while the market is open.
 *
 * Pass an empty list and nothing is fetched, which is the case for an
 * account holding only deposits.
 */
export function useLiveQuotes(symbols: string[]): LiveQuotes {
  // Sorted and de-duplicated, so two screens asking for the same holdings in
  // a different order share one cache entry and one request.
  const wanted = [...new Set(symbols.filter(Boolean).map((s) => s.toUpperCase()))]
    .sort()
    .slice(0, MAX_SYMBOLS);

  const result = useQuery<Fetched>({
    queryKey: ["quotes", wanted.join(",")],
    queryFn: () => fetchDirect(wanted).catch(() => fetchViaServer(wanted)),
    enabled: wanted.length > 0,
    // A price is stale the moment it arrives; this is the one thing in the
    // app that should not be trusted for five minutes.
    staleTime: 0,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data?.marketOpen) return false;
      return Math.max(FLOOR_MS, data.everyMs);
    },
    // Background tabs stop asking. This is the default, and it is stated
    // because the whole point of a poll is that it keeps running.
    refetchIntervalInBackground: false,
    // One retry, then fall quiet. A screen that cannot reach the market
    // shows the prices it has, and hammering will not change that.
    retry: 1,
  });

  return {
    quotes: result.data?.quotes ?? {},
    marketOpen: result.data?.marketOpen ?? false,
    ready: result.isSuccess || wanted.length === 0,
    unreachable: result.isError,
  };
}
