import { useEffect, useState } from "react";

/**
 * Suggest a symbol from a fragment.
 *
 * Calls our own `/api/v1/symbols/search`, not StockSaathi.
 *
 * It used to call theirs. Their instrument master is the same NSE list,
 * but it sits behind row level security with no anon policy -- correct of
 * them -- so it needed a new endpoint in a different product's repository,
 * and that endpoint was written but never deployed. This hook has been
 * disabling itself on every load ever since, which is why the symbol field
 * has only ever been a plain text box.
 *
 * So the universe is seeded from NSE's own published equity list into our
 * own instruments table instead (scripts/sync_instruments.py), and the
 * search reads that. Same answers, no cross-product deploy to wait on, and
 * same-origin -- so it carries the session cookie and cannot be scraped by
 * anybody who is not signed in.
 *
 * **It still degrades to nothing.** The failure handling below is kept
 * exactly as it was: an endpoint that is missing or unhappy resolves to
 * "no suggestions" and the field stays an ordinary text box that works.
 * The server checks the symbol on save either way, which is what actually
 * prevents a wrong one being stored; this only saves somebody guessing.
 *
 * `available` is what a screen uses to decide whether to promise anything.
 * Offering "start typing to search" against an endpoint that is not there
 * is worse than offering nothing.
 */

const SEARCH_URL = "/api/v1/symbols/search";

/** The server's minimum too. Below this every query matches hundreds. */
const MIN_LENGTH = 2;

/**
 * Long enough that a fast typist makes one request rather than eight,
 * short enough that the list feels like it is keeping up. Below about
 * 150ms the saving disappears; above about 400ms the pause is noticeable.
 */
const SETTLE_MS = 220;

export interface Suggestion {
  symbol: string;
  name: string | null;
  exchange: string | null;
  sector: string | null;
  isin: string | null;
}

export interface SymbolSearch {
  suggestions: Suggestion[];
  searching: boolean;
  /** False once the endpoint has proved it is not there. */
  available: boolean;
}

// Remembered for the life of the tab. Once the endpoint has proved it is
// not there, asking again on every keystroke of every field is pure waste,
// and promising a search that cannot happen is worse than promising none.
let endpointMissing = false;

/**
 * Consecutive failures before giving up for the session.
 *
 * Same-origin now, so a missing endpoint really does arrive as a readable
 * 404 and the branch below can act on it directly -- which it could not
 * when this was cross-origin, because the other host's 404 page carried no
 * Access-Control-Allow-Origin and the browser would not let script see the
 * status at all.
 *
 * The counter stays for what it was always also doing: distinguishing a
 * genuinely broken endpoint from one bad moment on the train, without a
 * single blip disabling the feature for the rest of the session.
 */
const GIVE_UP_AFTER = 3;
let failures = 0;

export function useSymbolSearch(term: string): SymbolSearch {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [searching, setSearching] = useState(false);
  const [available, setAvailable] = useState(!endpointMissing);

  const trimmed = term.trim();

  useEffect(() => {
    if (endpointMissing || trimmed.length < MIN_LENGTH) {
      setSuggestions([]);
      setSearching(false);
      return;
    }

    // Abort rather than ignore: a typist outruns the network, and without
    // this the answer to "rel" can arrive after the answer to "relia" and
    // overwrite it with the wrong list.
    const cancel = new AbortController();
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        // same-origin, not omit: this endpoint is behind require_user now,
        // so the session cookie has to go with it.
        const response = await fetch(
          `${SEARCH_URL}?q=${encodeURIComponent(trimmed)}`,
          { credentials: "same-origin", signal: cancel.signal });

        if (response.status === 404) {
          // Same-origin, so this is reachable and conclusive.
          failures = GIVE_UP_AFTER;
          endpointMissing = true;
          setAvailable(false);
          setSuggestions([]);
          return;
        }
        if (!response.ok) {
          // A bad minute upstream. Counted, so a permanently broken
          // endpoint eventually stops being asked, but not fatal on its
          // own.
          if (++failures >= GIVE_UP_AFTER) {
            endpointMissing = true;
            setAvailable(false);
          }
          setSuggestions([]);
          return;
        }

        failures = 0;
        const body = await response.json();
        setSuggestions(Array.isArray(body?.items) ? body.items : []);
      } catch {
        // An aborted request lands here too, and an abort is not a
        // failure -- it is this hook cancelling its own work.
        if (cancel.signal.aborted) return;
        if (++failures >= GIVE_UP_AFTER) {
          endpointMissing = true;
          setAvailable(false);
        }
        setSuggestions([]);
      } finally {
        if (!cancel.signal.aborted) setSearching(false);
      }
    }, SETTLE_MS);

    return () => {
      clearTimeout(timer);
      cancel.abort();
    };
  }, [trimmed]);

  return { suggestions, searching, available };
}
