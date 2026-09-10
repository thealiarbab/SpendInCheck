import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { formatPercent, formatRupees, formatSigned, toPaise } from "../../lib/money";
import { externalLinkProps, surplusHref } from "../../lib/links";
import {
  Card, Empty, Field, Loading, Notice, PageHead, Stat, StatRow, Table, cell,
} from "../../ui";
import styles from "./Reports.module.css";

function thisMonth(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 7);
}

function monthName(month: string): string {
  const [year, index] = month.split("-");
  return new Date(Number(year), Number(index) - 1, 1)
    .toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

/**
 * The two monthly reports, for whichever month is asked for.
 *
 * The old page took the month as a query parameter and reloaded. Here it is
 * a control that refetches, which is the same thing minus the page flash --
 * and each report keeps showing the previous month's figures until the new
 * ones arrive, rather than blanking out.
 */
export function Reports() {
  const [month, setMonth] = useState(thisMonth);

  // Keyed by month so switching back to one already seen is instant, and
  // "report" as the first segment so a write on any screen invalidates both.
  const spend = useQuery({
    queryKey: ["report", "category-spend", month],
    queryFn: () => api.categorySpend(month),
  });
  const budget = useQuery({
    queryKey: ["report", "budget-vs-actual", month],
    queryFn: () => api.budgetVsActual(month),
  });

  const spendRows = spend.data?.items ?? [];
  const budgetRows = budget.data?.items ?? [];

  const spent = spendRows.reduce((sum, row) => sum + toPaise(row.total), 0);
  const budgeted = budgetRows.reduce((sum, row) => sum + toPaise(row.limit), 0);
  // Against budgeted categories only, so it agrees with the table below it
  // rather than counting spending the month never had a limit for.
  const measured = budgetRows.reduce((sum, row) => sum + toPaise(row.actual), 0);
  const difference = budgeted - measured;

  return (
    <>
      <PageHead title="Reports" subtitle={`Showing ${monthName(month)}.`}>
        <div className={styles.picker}>
          <Field
            label="Month" name="month" type="month" value={month}
            onChange={(event) => event.target.value && setMonth(event.target.value)}
          />
        </div>
      </PageHead>

      <StatRow>
        <Stat label="Spent this month" value={formatRupees(spent)}
              note={spendRows.length ? `across ${spendRows.length} categories` : undefined} />
        <Stat label="Budgeted" value={budgeted ? formatRupees(budgeted) : "—"}
              note={budgetRows.length ? `${budgetRows.length} categories with a limit`
                                      : "no limits set"} />
        <Stat
          label={difference >= 0 ? "Left to spend" : "Over budget"}
          value={budgeted ? formatSigned(difference) : "—"}
          tone={budgeted === 0 ? undefined : difference > 0 ? "credit"
                : difference < 0 ? "debit" : "level"}
        />
      </StatRow>

      <Card title="Category-wise spend" flush>
        {spend.isPending && !spend.data ? (
          <Loading what="the month" />
        ) : spend.error ? (
          <Notice>{(spend.error as Error).message}</Notice>
        ) : spendRows.length ? (
          <Table
            head={
              <tr>
                <th>Category</th>
                <th className={cell.numeric}>Total spent</th>
                <th className={cell.numeric}>Share</th>
              </tr>
            }
          >
            {spendRows.map((row) => (
              <tr key={row.category}>
                <td className={cell.primary}>{row.category}</td>
                <td className={cell.numeric}>{formatRupees(toPaise(row.total))}</td>
                {/* Share of the month, which is the question the ordering
                    is really answering and the old table left you to work
                    out from the figures. */}
                <td className={cell.numeric + " " + styles.share}>
                  {formatPercent(toPaise(row.total), spent)}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No expenses recorded for {monthName(month)}.</Empty>
        )}
      </Card>

      <div style={{ height: "var(--space-5)" }} />

      <Card title="Budget vs actual" flush>
        {budget.isPending && !budget.data ? (
          <Loading what="the budgets" />
        ) : budget.error ? (
          <Notice>{(budget.error as Error).message}</Notice>
        ) : budgetRows.length ? (
          <Table
            head={
              <tr>
                <th>Category</th>
                <th className={cell.numeric}>Budget</th>
                <th className={cell.numeric}>Actual</th>
                <th className={cell.numeric}>Difference</th>
                <th>Status</th>
              </tr>
            }
          >
            {budgetRows.map((row) => {
              const gap = toPaise(row.difference);
              const limit = toPaise(row.limit);
              const used = limit === 0 ? 0 : Math.min(toPaise(row.actual) / limit, 1);
              return (
                <tr key={row.category}>
                  <td className={cell.primary}>{row.category}</td>
                  <td className={cell.numeric}>{formatRupees(limit)}</td>
                  <td className={cell.numeric}>{formatRupees(toPaise(row.actual))}</td>
                  <td className={
                    cell.numeric + " " + (gap < 0 ? cell.debit : gap > 0 ? cell.credit : "")
                  }>
                    {formatSigned(gap)}
                  </td>
                  <td>
                    {/* A bar rather than a word alone: over or under is a
                        matter of degree, and "under budget" reads the same
                        at 99% spent as at 5%. */}
                    <div className={styles.gauge} role="img"
                         aria-label={`${formatPercent(toPaise(row.actual), limit)} of the limit spent`}>
                      <div
                        className={gap < 0 ? styles.barOver : styles.bar}
                        style={{ width: `${Math.round(used * 100)}%` }}
                      />
                    </div>
                    <span className={styles.status}>
                      {gap < 0 ? "Over budget" : gap === 0 ? "On budget" : "Under budget"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : (
          <Empty>No budgets set for {monthName(month)}.</Empty>
        )}
      </Card>

      {budgeted > 0 && difference > 0 && (
        <p className={styles.surplus}>
          {formatRupees(difference)} of {monthName(month)}'s budget is unspent.{" "}
          <a href={surplusHref} {...externalLinkProps}>See what it could be earning ↗</a>
        </p>
      )}
    </>
  );
}
