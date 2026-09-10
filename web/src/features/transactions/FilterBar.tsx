import { useEffect, useState } from "react";
import type { AccountRow, Category, Tag, TransactionFilters } from "../../lib/api";
import { Button } from "../../ui";
import styles from "./FilterBar.module.css";

/**
 * The controls that narrow the ledger.
 *
 * Every one writes to the URL rather than to component state, so a filtered
 * view has an address: it can be bookmarked, shared, and reached again with
 * the back button. That is also why the search box debounces instead of
 * filtering per keystroke -- one history entry per letter typed would make
 * the back button useless.
 */
export function FilterBar(
  { filters, categories, accounts, tags, total, onChange, onClear, exportHref }: {
    filters: TransactionFilters;
    categories: Category[];
    accounts: AccountRow[];
    tags: Tag[];
    total: number;
    onChange: (next: Partial<TransactionFilters>) => void;
    onClear: () => void;
    exportHref: string;
  },
) {
  const [text, setText] = useState(filters.q ?? "");

  // The box is typed into locally and pushed to the URL a beat later. The
  // dependency on filters.q is what keeps the back button honest: stepping
  // back to an earlier search puts that text back in the box.
  useEffect(() => setText(filters.q ?? ""), [filters.q]);

  useEffect(() => {
    if (text === (filters.q ?? "")) return;
    const timer = setTimeout(() => onChange({ q: text }), 300);
    return () => clearTimeout(timer);
  }, [text, filters.q, onChange]);

  // Which controls are actually narrowing anything, so "Clear" can say so
  // and can be hidden when there is nothing to clear.
  const active = (["q", "from", "to", "type", "category_id", "account_id",
                   "tag_id", "min", "max"] as const)
    .filter((name) => filters[name]);

  return (
    <div className={styles.bar}>
      <div className={styles.line}>
        <input
          className={styles.search}
          type="search"
          value={text}
          placeholder="Search descriptions and categories…"
          aria-label="Search transactions"
          onChange={(event) => setText(event.target.value)}
        />

        <select
          className={styles.control}
          value={filters.type ?? ""}
          aria-label="Type"
          onChange={(event) => onChange({ type: event.target.value })}
        >
          <option value="">Any type</option>
          <option value="Income">Income</option>
          <option value="Expense">Expense</option>
        </select>

        <select
          className={styles.control}
          value={filters.category_id ?? ""}
          aria-label="Category"
          onChange={(event) => onChange({ category_id: event.target.value })}
        >
          <option value="">Any category</option>
          {categories.map((one) => (
            <option key={one.id} value={one.id}>{one.name}</option>
          ))}
        </select>

        {/* Only shown once there is a choice to make. With a single account
            every row is on it, so the control would narrow nothing and only
            add something to read past. */}
        {accounts.length > 1 && (
          <select
            className={styles.control}
            value={filters.account_id ?? ""}
            aria-label="Account"
            onChange={(event) => onChange({ account_id: event.target.value })}
          >
            <option value="">Any account</option>
            {accounts.map((one) => (
              <option key={one.id} value={one.id}>{one.name}</option>
            ))}
          </select>
        )}

        {/* Hidden until there is a tag to filter by, so an account that
            does not use tags never sees a control for them. */}
        {tags.length > 0 && (
          <select
            className={styles.control}
            value={filters.tag_id ?? ""}
            aria-label="Tag"
            onChange={(event) => onChange({ tag_id: event.target.value })}
          >
            <option value="">Any tag</option>
            {tags.map((one) => (
              <option key={one.id} value={one.id}>{one.name} ({one.uses})</option>
            ))}
          </select>
        )}
      </div>

      <div className={styles.line}>
        <label className={styles.pair}>
          <span className={styles.tag}>From</span>
          <input
            className={styles.control} type="date" value={filters.from ?? ""}
            onChange={(event) => onChange({ from: event.target.value })}
          />
        </label>
        <label className={styles.pair}>
          <span className={styles.tag}>To</span>
          <input
            className={styles.control} type="date" value={filters.to ?? ""}
            onChange={(event) => onChange({ to: event.target.value })}
          />
        </label>
        <label className={styles.pair}>
          <span className={styles.tag}>Min</span>
          <input
            className={styles.number} type="number" step="0.01" min="0"
            value={filters.min ?? ""} placeholder="0"
            onChange={(event) => onChange({ min: event.target.value })}
          />
        </label>
        <label className={styles.pair}>
          <span className={styles.tag}>Max</span>
          <input
            className={styles.number} type="number" step="0.01" min="0"
            value={filters.max ?? ""} placeholder="∞"
            onChange={(event) => onChange({ max: event.target.value })}
          />
        </label>

        <div className={styles.right}>
          <span className={styles.count}>
            {total} {total === 1 ? "row" : "rows"}
            {active.length ? ` · ${active.length} filter${active.length === 1 ? "" : "s"}` : ""}
          </span>
          {active.length > 0 && (
            <Button kind="quiet" small onClick={onClear}>Clear</Button>
          )}
          {/* A plain link, not a fetch: letting the browser do the download
              means the file lands in the normal place with the name the
              server gave it, and needs no blob held in memory. */}
          <a className={styles.download} href={exportHref} download>
            Export CSV
          </a>
        </div>
      </div>
    </div>
  );
}
