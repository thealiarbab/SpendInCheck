import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { BudgetRow } from "../../lib/api";
import { formatRupees, toPaise } from "../../lib/money";
import {
  Button, Card, Empty, Field, Form, FormActions, Loading, Notice, PageHead, Picker,
  RowActions, Table, cell, row as rowStyle,
} from "../../ui";
import styles from "./Budgets.module.css";

/** The current month as YYYY-MM, which is what <input type="month"> speaks. */
function thisMonth(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 7);
}

/** "2026-08" as "August 2026". The stored form is for sorting, not reading. */
function monthName(month: string): string {
  const [year, index] = month.split("-");
  const date = new Date(Number(year), Number(index) - 1, 1);
  return date.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

/**
 * Monthly spending limits, one per category per month.
 *
 * Setting a limit twice replaces it rather than adding a second -- the
 * endpoint is a PUT onto the (category, month) pair. The old page said so
 * in its subtitle and left the reader to trust it; here the form fills
 * itself with the existing limit when you pick a pair that already has one,
 * so the replacement is visible before it happens.
 */
export function Budgets() {
  const client = useQueryClient();
  const [month, setMonth] = useState(thisMonth);
  const [category, setCategory] = useState("");
  const [limit, setLimit] = useState("");

  const categories = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const budgets = useQuery({ queryKey: ["budgets"], queryFn: api.budgets });

  // Budgets only ever constrain spending, so offering income categories
  // would only produce limits nothing can ever be measured against.
  const spendable = categories.data?.items.filter((one) => one.type === "Expense") ?? [];
  const chosen = spendable.find((one) => String(one.id) === category);

  const rows = budgets.data?.items ?? [];
  const existing: BudgetRow | undefined = rows.find(
    (row) => chosen !== undefined && row.category === chosen.name && row.month === month);

  const save = useMutation({
    mutationFn: () => api.setBudget(chosen!.id, month, limit),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["budgets"] });
      client.invalidateQueries({ queryKey: ["report"] });
      setLimit("");
      setCategory("");
    },
  });

  /** Load an existing limit into the form, so saving is visibly a replacement. */
  function edit(row: BudgetRow) {
    const match = spendable.find((one) => one.name === row.category);
    if (!match) return;
    setMonth(row.month);
    setCategory(String(match.id));
    setLimit(row.limit);
    save.reset();
  }

  const failure = save.error instanceof ApiError ? save.error : null;
  const fields = failure?.isValidation ? failure.fields : {};

  // Grouped by month, newest first: a budget is read a month at a time, and
  // the flat list the old page showed made you scan for the month yourself.
  const months = [...new Set(rows.map((row) => row.month))].sort().reverse();

  return (
    <>
      <PageHead
        title="Budgets"
        subtitle="A monthly spending limit per category. Setting one twice replaces it."
      />

      <Card title={existing ? `Replacing ${existing.category}'s limit` : "Set a budget"}>
        <Form>
          <Picker
            label="Category" name="category_id" value={category}
            error={fields.category_id}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option value="">Choose…</option>
            {spendable.map((one) => (
              <option key={one.id} value={one.id}>{one.name}</option>
            ))}
          </Picker>
          <Field
            label="Month" name="month" type="month" value={month} error={fields.month}
            onChange={(event) => setMonth(event.target.value)}
          />
          <Field
            label="Limit" name="limit" type="number" step="0.01" min="0.01" numeric
            value={limit} error={fields.limit} placeholder="0.00"
            onChange={(event) => setLimit(event.target.value)}
          />
          <FormActions>
            <Button
              onClick={() => save.mutate()}
              disabled={!chosen || limit === "" || save.isPending}
            >
              {save.isPending ? "Saving…" : existing ? "Replace" : "Save"}
            </Button>
          </FormActions>
        </Form>

        {existing && (
          <p className={styles.replacing}>
            {existing.category} already has a limit of{" "}
            {formatRupees(toPaise(existing.limit))} for {monthName(month)}. Saving
            replaces it.
          </p>
        )}
        {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
        {save.isSuccess && <Notice ok>Saved.</Notice>}
      </Card>

      <div style={{ height: "var(--space-5)" }} />

      {budgets.isPending && !budgets.data ? (
        <Card><Loading what="budgets" /></Card>
      ) : budgets.error ? (
        <Card><Notice>{(budgets.error as Error).message}</Notice></Card>
      ) : months.length ? (
        months.map((each) => {
          const forMonth = rows.filter((row) => row.month === each);
          const total = forMonth.reduce((sum, row) => sum + toPaise(row.limit), 0);
          return (
            <div key={each} className={styles.month}>
              <Card title={monthName(each)} flush>
                <Table
                  head={
                    <tr>
                      <th>Category</th>
                      <th className={cell.numeric}>Limit</th>
                      <th />
                    </tr>
                  }
                >
                  {forMonth.map((row) => (
                    <tr
                      key={row.id}
                      className={row.id === existing?.id ? rowStyle.editing : undefined}
                    >
                      <td className={cell.primary}>{row.category}</td>
                      <td className={cell.numeric}>{formatRupees(toPaise(row.limit))}</td>
                      <td>
                        <RowActions>
                          <Button kind="quiet" small onClick={() => edit(row)}>Change</Button>
                        </RowActions>
                      </td>
                    </tr>
                  ))}
                  {/* Budgeted for the month: the figure you are really setting,
                      which no screen showed before. */}
                  <tr className={styles.total}>
                    <td className={cell.primary}>Budgeted</td>
                    <td className={cell.numeric}>{formatRupees(total)}</td>
                    <td />
                  </tr>
                </Table>
              </Card>
            </div>
          );
        })
      ) : (
        <Card><Empty>No budgets set yet.</Empty></Card>
      )}
    </>
  );
}
