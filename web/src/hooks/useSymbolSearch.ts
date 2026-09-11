import { useEffect, useState } from "react";

/**
 * Suggest a symbol from a fragment.
 *
 * Calls StockSaathi's `/api/search` from the browser, for the same reasons
 * useLiveQuotes calls their quote endpoint directly: it is CORS-open, it
 * needs no key, and a keystroke handler must not bill a serverless
 * invocation per letter.
 *
 * **It degrades to nothing.** That endpoint may not be deployed -- it was
 * written for this and lives in the other repository -- so a 404, a 503 or
 * an unreachable host all resolve to "no suggestions", and the field it
 * decorates stays an ordinary text box that still works. The server checks
 * the symbol on save either way, which is what actually prevents a wrong
 * one being stored; this only saves somebody guessing.
 *
 * `available` is what a screen uses to decide whether to promise anything.
 * Offering "start typing to search" against an endpoint that is not there
 * is worse than offering nothing.
 */

const SEARCH_URL = "https://stocksaathi.co.in/api/search";

/** Their minimum too. Below this every query matches thousands of rows. */
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
 * A missing cross-origin endpoint does not present as a readable 404. The
 * host answers its own 404 page, that page carries no
 * Access-Control-Allow-Origin, and the browser refuses to let script see
 * the status at all -- so fetch rejects and the code never learns what
 * went wrong. Counting failures is what distinguishes "not deployed" from
 * "one bad moment on the train", without a single blip disabling the
 * feature for the rest of the session.
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
        const response = await fetch(
          `${SEARCH_URL}?q=${encodeURIComponent(trimmed)}`,
          { credentials: "omit", signal: cancel.signal });

        if (response.status === 404) {
          // Deployed hosts that answer CORS on their 404 do reach here.
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
