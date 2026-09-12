import { useEffect, useState } from "react";

/**
 * StockSaathi's reading of what somebody meant, in a sentence.
 *
 * A second, slower opinion on the query useSymbolSearch has already
 * answered. Their /api/ai?op=market-search puts a language model in front
 * of our own ranked candidates, so it can say "RELIANCE and RPOWER, because
 * the query mentions Reliance and shares" where a ranked list can only
 * put them in an order.
 *
 * **Deliberately never blocking.** It takes 1.5-4 seconds where the list
 * takes 40ms, so the list renders without it and this arrives afterwards as
 * confirmation. Every failure -- unreachable, slow, no opinion -- is the
 * same outcome: no sentence, and a suggestion list exactly as good as it
 * was before.
 *
 * Settled far longer than the search itself. There is a model and somebody
 * else's bill behind every call, and firing one per keystroke would spend
 * both on queries nobody finished typing.
 */

const READ_URL = "/api/v1/symbols/interpret";

/** Long enough to mean somebody stopped typing, not merely slowed down. */
const SETTLE_MS = 700;

/** Below this a query has no meaning to read. Matches the server. */
const MIN_LENGTH = 2;

export interface Reading {
  /** Symbols it picked, always a subset of what was offered. */
  symbols: string[];
  /** Its one-sentence reason, or "" when there is nothing to say. */
  why: string;
}

const EMPTY: Reading = { symbols: [], why: "" };

// Once the endpoint has proved it is not there, stop asking. Same reasoning
// as useSymbolSearch: promising a reading that cannot happen is worse than
// promising none.
let unavailable = false;

export function useSymbolReading(term: string, enabled: boolean): Reading {
  const [reading, setReading] = useState<Reading>(EMPTY);
  const trimmed = term.trim();

  useEffect(() => {
    if (unavailable || !enabled || trimmed.length < MIN_LENGTH) {
      setReading(EMPTY);
      return;
    }

    const cancel = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(
          `${READ_URL}?q=${encodeURIComponent(trimmed)}`,
          { credentials: "same-origin", signal: cancel.signal });
        if (response.status === 404) { unavailable = true; return; }
        if (!response.ok) return;
        const body = await response.json();
        setReading({
          symbols: Array.isArray(body?.symbols) ? body.symbols : [],
          why: typeof body?.why === "string" ? body.why : "",
        });
      } catch {
        // An abort lands here too, and an abort is this hook cancelling its
        // own work rather than a failure.
      }
    }, SETTLE_MS);

    return () => { clearTimeout(timer); cancel.abort(); };
  }, [trimmed, enabled]);

  // Cleared the moment the term changes, so a stale sentence never sits
  // under a list it no longer describes.
  return trimmed.length < MIN_LENGTH ? EMPTY : reading;
}
