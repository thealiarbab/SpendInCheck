import { useRef, useState } from "react";
import { useSymbolSearch } from "../../hooks/useSymbolSearch";
import type { Suggestion } from "../../hooks/useSymbolSearch";
import styles from "./Holdings.module.css";

/**
 * A symbol box that suggests, and still works when it cannot.
 *
 * The suggestions come from StockSaathi's instrument master. When that
 * endpoint is not reachable the list simply never appears and this is an
 * ordinary text input -- which is what it was before, and still enough:
 * the server verifies the symbol on save regardless, so the worst case is
 * that somebody types RELIANCE themselves.
 *
 * Why it matters beyond convenience: RELIANCE, RELIABLE and RELINFRA are
 * three different companies, and a holding pointed at the wrong one shows
 * a plausible price every day for years. Choosing from a list that names
 * the company is how that stops being possible.
 */
export function SymbolField(
  { value, onChange, onPick, label, placeholder = "RELIANCE", id }: {
    value: string;
    onChange: (value: string) => void;
    /** Called when a suggestion is taken, with everything it carried. */
    onPick?: (suggestion: Suggestion) => void;
    label: string;
    placeholder?: string;
    id?: string;
  },
) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const { suggestions, available } = useSymbolSearch(open ? value : "");

  const showing = open && available && suggestions.length > 0;

  function take(suggestion: Suggestion) {
    onChange(suggestion.symbol);
    onPick?.(suggestion);
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (!showing) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      // Arrow keys move through the list rather than the text, which is
      // what every other combo box does and what fingers expect.
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((at) => (at + step + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter") {
      const picked = suggestions[active];
      if (picked) {
        // Only swallow Enter when there is something to take. Otherwise
        // it belongs to the form, which may be mid-submit.
        event.preventDefault();
        take(picked);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className={styles.symbolField} ref={box}>
      <input
        id={id}
        className={styles.tickerInput}
        value={value}
        placeholder={placeholder}
        aria-label={label}
        autoComplete="off"
        role="combobox"
        aria-expanded={showing}
        aria-controls={showing ? `${id ?? "symbol"}-suggestions` : undefined}
        onChange={(event) => {
          // Upper-cased as it is typed, because that is how it is stored
          // and shown, and a field that silently rewrites what you typed
          // after you leave it is unsettling.
          onChange(event.target.value.toUpperCase());
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        /* A blur that is a click on a suggestion must not close the list
           before the click lands. The delay is the conventional fix and
           the reason the list is not simply hidden on blur. */
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />

      {showing && (
        <ul className={styles.suggestions} id={`${id ?? "symbol"}-suggestions`}
            role="listbox">
          {suggestions.map((suggestion, index) => (
            <li key={suggestion.symbol}>
              <button
                type="button"
                role="option"
                aria-selected={index === active}
                className={index === active
                  ? `${styles.suggestion} ${styles.suggestionActive}`
                  : styles.suggestion}
                onMouseEnter={() => setActive(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => take(suggestion)}
              >
                <span className={styles.suggestionSymbol}>{suggestion.symbol}</span>
                <span className={styles.suggestionName}>
                  {suggestion.name ?? "—"}
                </span>
                {suggestion.sector && (
                  <span className={styles.suggestionSector}>{suggestion.sector}</span>
                )}
              </button>
            </li>
          ))}
          <li className={styles.suggestionCredit}>instruments by StockSaathi</li>
        </ul>
      )}
    </div>
  );
}
