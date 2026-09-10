import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { Category, TransactionFilters, TransactionSubmission } from "../../lib/api";
import { FilterBar } from "./FilterBar";
import { Pager } from "./Pager";
import styles from "./Transactions.module.css";
import { formatMoney, toMinor } from "../../lib/money";
import {
  Button, Card, Confirm, Derived, Empty, Field, Form, FormActions, Loading, Notice,
  PageHead, Picker, RowActions, Table, Tag, cell, row as rowStyle,
} from "../../ui";

/** Today in the YYYY-MM-DD that the date input and the API both speak. */
function today(): string {
  const now = new Date();
  // Shift by the offset before slicing: toISOString is UTC, so a Mumbai
  // evening is already tomorrow there, and the form would open on a date the
  // server then rejects as being in the future.
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

interface Draft {
  id: number | null;
  date: string;
  category_id: string;
  amount: string;
  description: string;
}

const blank = (): Draft => ({
  id: null, date: today(), category_id: "", amount: "", description: "",
});

/** The filter names that live in the URL, in the order they read best. */
const FILTER_NAMES = [
  "q", "type", "category_id", "from", "to", "min", "max",
  "sort", "direction", "page", "per_page",
] as const;

/**
 * The ledger: everything in and out, with the form that adds to it.
 *
 * One form serves adding and editing. A separate edit screen would mean a
 * second copy of the same five fields and the same five validation messages,
 * which is exactly the duplication that lets two forms drift apart.
 */
export function Transactions() {
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft>(blank);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [params, setParams] = useSearchParams();

  // The URL is the state, not a copy of it. A filtered view therefore has
  // an address that can be shared and returned to, and the back button
  // walks the filters rather than leaving the screen.
  const filters = useMemo(() => {
    const read: TransactionFilters = {};
    for (const name of FILTER_NAMES) {
      const value = params.get(name);
      if (value) read[name] = value;
    }
    return read;
  }, [params]);

  const update = useCallback((next: Partial<TransactionFilters>) => {
    setParams((current) => {
      const updated = new URLSearchParams(current);
      for (const [name, value] of Object.entries(next)) {
        if (value) updated.set(name, value);
        else updated.delete(name);
      }
      // Any change to what is being looked for starts again at page one.
      // Staying on page 4 of a narrower result is how a search looks empty
      // when it is not.
      if (!("page" in next)) updated.delete("page");
      return updated;
    });
    // Pushed, not replaced. Changing a filter is a deliberate act, so the
    // back button should undo it rather than leave the screen entirely.
    // The search box debounces, which is what stops this becoming one
    // history entry per letter typed.
  }, [setParams]);

  const clear = useCallback(() => setParams(new URLSearchParams()), [setParams]);

  const categories = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  // Keyed by the filters, so going back to a view already seen is instant
  // and each distinct search is cached in its own right.
  const transactions = useQuery({
    queryKey: ["transactions", filters],
    queryFn: () => api.transactions(filters),
    // Rows stay on screen while the next page loads, rather than the table
    // emptying and jumping on every keystroke.
    placeholderData: (previous) => previous,
  });

  const chosen: Category | undefined = categories.data?.items
    .find((one) => String(one.id) === draft.category_id);

  // Everything a write changes: the list, the reports that count it, and
  // the opening screen, which shows the most recent rows.
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["transactions"] });
    client.invalidateQueries({ queryKey: ["report"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const save = useMutation({
    mutationFn: (body: TransactionSubmission) =>
      draft.id === null ? api.addTransaction(body) : api.editTransaction(draft.id, body),
    onSuccess: () => {
      refresh();
      // Keep the date, clear the rest: entering a day's spending is several
      // rows sharing one date, and retyping it each time is the tedious part.
      setDraft({ ...blank(), date: draft.date });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteTransaction(id),
    onSuccess: () => {
      refresh();
      setConfirming(null);
      // Clear the form's "Saved." from an earlier edit: a success message
      // still standing after a delete reads as if the delete produced it.
      save.reset();
    },
  });

  /** Load a row back into the form, in the shape the form holds. */
  async function edit(id: number) {
    // The list carries a category name; the form needs its id, so the single
    // record has to be fetched rather than read out of the row on screen.
    const record = await api.transaction(id);
    setDraft({
      id: record.id,
      date: record.date,
      category_id: String(record.category_id),
      amount: record.amount,
      description: record.description ?? "",
    });
    save.reset();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function submit() {
    if (!chosen) return;
    save.mutate({
      date: draft.date,
      category_id: chosen.id,
      amount: draft.amount,
      // The category decides whether this is money in or out, so the type is
      // reported beside the picker rather than asked for a second time. The
      // old form let you file an Income under Groceries.
      type: chosen.type,
      description: draft.description,
    });
  }

  const failure = save.error instanceof ApiError ? save.error : null;
  const fields = failure?.isValidation ? failure.fields : {};
  const rows = transactions.data?.items ?? [];
  const page = transactions.data?.page;

  /** Click a heading to sort by it; click it again to reverse. */
  const sortBy = (column: string) => () => update({
    sort: column,
    direction: filters.sort === column && filters.direction !== "asc" ? "asc" : "desc",
  });

  const sortMark = (column: string) =>
    filters.sort !== column ? "" : filters.direction === "asc" ? " ▲" : " ▼";

  return (
    <>
      {/* Not "every rupee": the ledger can be kept in any of 162
          currencies, and naming one of them here would be wrong for most. */}
      <PageHead title="Transactions" subtitle="Everything in and out, tied to a category." />

      <Card title={draft.id === null ? "Add a transaction" : `Editing #${draft.id}`}>
        <Form>
          <Field
            label="Date" name="date" type="date" max={today()} value={draft.date}
            error={fields.date}
            onChange={(event) => setDraft({ ...draft, date: event.target.value })}
          />
          <Picker
            label="Category" name="category_id" value={draft.category_id}
            error={fields.category_id}
            onChange={(event) => setDraft({ ...draft, category_id: event.target.value })}
          >
            <option value="">Choose…</option>
            {categories.data?.items.map((one) => (
              <option key={one.id} value={one.id}>{one.name}</option>
            ))}
          </Picker>
          <Derived>{chosen ? <Tag kind={chosen.type} /> : null}</Derived>
          <Field
            label="Amount" name="amount" type="number" step="0.01" min="0.01" numeric
            value={draft.amount} error={fields.amount} placeholder="0.00"
            onChange={(event) => setDraft({ ...draft, amount: event.target.value })}
          />
          <Field
            label="Description" name="description" maxLength={255}
            value={draft.description} error={fields.description}
            onChange={(event) => setDraft({ ...draft, description: event.target.value })}
          />
          <FormActions>
            <Button onClick={submit} disabled={!chosen || save.isPending}>
              {save.isPending ? "Saving…" : draft.id === null ? "Add" : "Save"}
            </Button>
            {draft.id !== null && (
              <Button kind="quiet" onClick={() => { setDraft(blank()); save.reset(); }}>
                Cancel
              </Button>
            )}
          </FormActions>
        </Form>

        {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
        {save.isSuccess && <Notice ok>Saved.</Notice>}
      </Card>

      <div style={{ height: "var(--space-5)" }} />

      <Card title="All transactions" flush>
        <FilterBar
          filters={filters}
          categories={categories.data?.items ?? []}
          total={page?.total ?? rows.length}
          onChange={update}
          onClear={clear}
          exportHref={api.exportUrl(filters)}
        />

        {transactions.isPending && !transactions.data ? (
          <Loading what="transactions" />
        ) : transactions.error ? (
          <Notice>{(transactions.error as Error).message}</Notice>
        ) : rows.length ? (
          <div className={transactions.isPlaceholderData ? styles.stale : undefined}>
          <Table
            head={
              <tr>
                <th>
                  <button className={styles.sortable + (filters.sort === "date" || !filters.sort
                          ? " " + styles.sortedOn : "")}
                          onClick={sortBy("date")}>
                    Date{sortMark("date") || (!filters.sort ? " ▼" : "")}
                  </button>
                </th>
                <th>
                  <button className={styles.sortable + (filters.sort === "category"
                          ? " " + styles.sortedOn : "")}
                          onClick={sortBy("category")}>
                    Category{sortMark("category")}
                  </button>
                </th>
                <th>
                  <button className={styles.sortable + (filters.sort === "type"
                          ? " " + styles.sortedOn : "")}
                          onClick={sortBy("type")}>
                    Type{sortMark("type")}
                  </button>
                </th>
                <th className={cell.numeric}>
                  <button className={styles.sortable + (filters.sort === "amount"
                          ? " " + styles.sortedOn : "")}
                          onClick={sortBy("amount")}>
                    Amount{sortMark("amount")}
                  </button>
                </th>
                <th>Description</th>
                <th />
              </tr>
            }
          >
            {rows.map((row) => (
              <tr key={row.id} className={row.id === draft.id ? rowStyle.editing : undefined}>
                <td className={cell.numeric} style={{ textAlign: "left" }}>{row.date}</td>
                <td className={cell.primary}>{row.category}</td>
                <td><Tag kind={row.type} /></td>
                <td className={cell.numeric + (row.type === "Income" ? " " + cell.credit : "")}>
                  {formatMoney(toMinor(row.amount))}
                </td>
                <td>{row.description || "—"}</td>
                <td>
                  {confirming === row.id ? (
                    <Confirm
                      busy={remove.isPending}
                      onYes={() => remove.mutate(row.id)}
                      onNo={() => setConfirming(null)}
                    />
                  ) : (
                    <RowActions>
                      <Button kind="quiet" small onClick={() => edit(row.id)}>Edit</Button>
                      <Button kind="danger" small onClick={() => setConfirming(row.id)}>
                        Delete
                      </Button>
                    </RowActions>
                  )}
                </td>
              </tr>
            ))}
          </Table>
          </div>
        ) : (
          <Empty>
            {Object.keys(filters).length
              ? "Nothing matches those filters."
              : "No transactions yet."}
          </Empty>
        )}

        {page && <Pager page={page} onGo={(number) => update({ page: String(number) })} />}
        {remove.error && <Notice>{(remove.error as Error).message}</Notice>}
      </Card>
    </>
  );
}
