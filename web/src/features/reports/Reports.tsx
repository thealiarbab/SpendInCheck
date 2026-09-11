import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { formatPercent, formatMoney, formatSigned, toMinor } from "../../lib/money";
import { externalLinkProps, investHref, surplusHref } from "../../lib/links";
import {
  Card, Empty, Field, Loading, Notice, PageHead, Stat, StatRow, Table, cell,
} from "../../ui";
import {
  ChartFrame, Comparison, Legend, LineChart, PairedBars, RankedBars,
} from "../../ui/charts";
import { alignRunning, alignTo, monthName } from "./align";
import { SurplusCard } from "./SurplusCard";
import styles from "./Reports.module.css";

/** How much history the charts show. A year, so seasons are visible. */
const HISTORY = 12;

function thisMonth(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 7);
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
  // Holdings against the market. Its own query rather than part of the
  // summary: it reads quote_history, which the summary never touches, and
  // most accounts have nothing quotable in them -- so folding it in would
  // make every reporting screen pay for a chart it cannot draw.
  const versus = useQuery({ queryKey: ["benchmark"], queryFn: api.benchmark });

  const budget = useQuery({
    queryKey: ["report", "budget-vs-actual", month],
    queryFn: () => api.budgetVsActual(month),
  });

  // Not keyed by month: these are the last twelve months whichever month is
  // being read below, so changing the picker must not refetch them.
  const summary = useQuery({
    queryKey: ["report", "summary", HISTORY],
    queryFn: () => api.summary(HISTORY),
  });

  const spendRows = spend.data?.items ?? [];
  const budgetRows = budget.data?.items ?? [];

  const months = (summary.data?.net_worth ?? []).map((row) => row.month);
  const income = alignTo(months, summary.data?.trend ?? [], (row) => row.income);
  const expense = alignTo(months, summary.data?.trend ?? [], (row) => row.expense);
  const running = alignRunning(months, summary.data?.cashflow ?? [],
                               (row) => row.cumulative);
  const worth = alignTo(months, summary.data?.net_worth ?? [],
                        (row) => row.net_worth);
  const merchants = summary.data?.merchants ?? [];
  // A year of nothing draws twelve flat zeros and says less than a sentence.
  const nothingYet = income.every((value, index) =>
    value === 0 && expense[index] === 0);

  const spent = spendRows.reduce((sum, row) => sum + toMinor(row.total), 0);
  const budgeted = budgetRows.reduce((sum, row) => sum + toMinor(row.limit), 0);
  // Against budgeted categories only, so it agrees with the table below it
  // rather than counting spending the month never had a limit for.
  const measured = budgetRows.reduce((sum, row) => sum + toMinor(row.actual), 0);
  const difference = budgeted - measured;

  return (
    <>
      <PageHead title="Reports" subtitle={`The last twelve months, and ${monthName(month)} in detail.`}>
        <div className={styles.picker}>
          <Field
            label="Month" name="month" type="month" value={month}
            onChange={(event) => event.target.value && setMonth(event.target.value)}
          />
        </div>
      </PageHead>

      <StatRow>
        <Stat label="Spent this month" value={formatMoney(spent)}
              note={spendRows.length ? `across ${spendRows.length} categories` : undefined} />
        <Stat label="Budgeted" value={budgeted ? formatMoney(budgeted) : "—"}
              note={budgetRows.length ? `${budgetRows.length} categories with a limit`
                                      : "no limits set"} />
        <Stat
          label={difference >= 0 ? "Left to spend" : "Over budget"}
          value={budgeted ? formatSigned(difference) : "—"}
          tone={budgeted === 0 ? undefined : difference > 0 ? "credit"
                : difference < 0 ? "debit" : "level"}
        />
      </StatRow>

      {summary.error ? (
        <Notice>{(summary.error as Error).message}</Notice>
      ) : summary.isPending ? (
        <Card><Loading what="the last twelve months" /></Card>
      ) : (
        <div className={styles.charts}>
          <Card>
            <ChartFrame title="Income and expense" note="last 12 months"
                        empty={nothingYet}>
              <PairedBars months={months} income={income} expense={expense} />
              <Legend items={[{ label: "In", kind: "income" },
                              { label: "Out", kind: "expense" }]} />
            </ChartFrame>
          </Card>

          <Card>
            <ChartFrame title="Cashflow, running total" note="income less expense"
                        empty={nothingYet}>
              <LineChart months={months} values={running} fill
                         label="Cumulative cashflow by month" />
            </ChartFrame>
          </Card>

          <Card>
            {/* The note changed with the query. Holdings used to be valued
                at today's price in every month; they are valued at that
                month's close now, and a caption saying otherwise is worse
                than none. */}
            <ChartFrame title="Net worth" note="holdings at each month's close, plus cash"
                        empty={nothingYet && worth.every((value) => value === 0)}>
              <LineChart months={months} values={worth}
                         label="Net worth at the end of each month" />
            </ChartFrame>
          </Card>

          {versus.data && versus.data.items.length > 1 && (
            <Card>
              <ChartFrame
                title="Your holdings against the market"
                note="both from 100, at today's quantities"
              >
                <Comparison
                  months={versus.data.items.map((row) => row.month)}
                  mine={versus.data.items.map((row) => Number(row.basket))}
                  market={versus.data.items.map((row) => Number(row.market))}
                  mineLabel="Your holdings"
                  marketLabel={versus.data.benchmark}
                />
                <Legend items={[
                  { label: "Your holdings", kind: "line" },
                  { label: versus.data.benchmark, kind: "market" },
                ]} />
              </ChartFrame>
              <p className={styles.benchmarkNote}>
                {/* Named as what it is. The NIFTY 50 index itself does not
                    quote through this feed, and calling an ETF by the
                    index's name would be a small lie repeated daily. */}
                Against <strong>{versus.data.benchmark}</strong>
                {versus.data.benchmark_name ? `, ${versus.data.benchmark_name}` : ""},
                which tracks the index. Quantities are held at today's, so buying
                more does not read as a gain, and only holdings with a symbol take
                part — a deposit has no market return to compare. Prices by{" "}
                <a href={investHref} {...externalLinkProps}>StockSaathi ↗</a>.
              </p>
            </Card>
          )}

          <Card>
            <ChartFrame title="Where the money goes" note="last 3 months"
                        empty={merchants.length === 0}>
              <RankedBars rows={merchants.map((row) => ({
                label: row.payee,
                value: toMinor(row.total),
                caption: row.times > 1 ? `${row.times}×` : undefined,
              }))} />
            </ChartFrame>
          </Card>
        </div>
      )}

      <div className={styles.gap} />

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
                <td className={cell.numeric}>{formatMoney(toMinor(row.total))}</td>
                {/* Share of the month, which is the question the ordering
                    is really answering and the old table left you to work
                    out from the figures. */}
                <td className={cell.numeric + " " + styles.share}>
                  {formatPercent(toMinor(row.total), spent)}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No expenses recorded for {monthName(month)}.</Empty>
        )}
      </Card>

      {/* One of three placements in the app, and on Reports rather than the
          dashboard on purpose: anything market-flavoured is confined to
          here and Holdings. See surplus.ts for the rules that keep it rare. */}
      <SurplusCard month={month} budgeted={budgeted} difference={difference} />

      <div className={styles.gap} />

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
              const gap = toMinor(row.difference);
              const limit = toMinor(row.limit);
              // The bar measures spending against the allowance actually
              // available -- the limit plus whatever was carried in.
              // Measuring against the bare limit would show a category as
              // over when its carry had covered it.
              const allowance = limit + toMinor(row.rollover_in);
              const used = allowance <= 0 ? 1
                : Math.min(toMinor(row.actual) / allowance, 1);
              return (
                <tr key={row.category}>
                  <td className={cell.primary}>{row.category}</td>
                  <td className={cell.numeric}>
                  {formatMoney(limit)}
                  {/* The difference already accounts for this, so it has to
                      be visible -- otherwise the arithmetic in the row does
                      not add up on the page. */}
                  {toMinor(row.rollover_in) !== 0 && (
                    <span className={styles.carried}>
                      {formatSigned(toMinor(row.rollover_in))} carried in
                    </span>
                  )}
                </td>
                  <td className={cell.numeric}>{formatMoney(toMinor(row.actual))}</td>
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
                         aria-label={`${formatPercent(toMinor(row.actual), allowance)} of the allowance spent`}>
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
          {formatMoney(difference)} of {monthName(month)}'s budget is unspent.{" "}
          <a href={surplusHref} {...externalLinkProps}>See what it could be earning ↗</a>
        </p>
      )}
    </>
  );
}
