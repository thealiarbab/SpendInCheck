import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { formatRupees, toPaise } from "../../lib/money";
import { Card, Empty, Loading, Money, Notice, PageHead, Stat, StatRow, Table, Tag, cell } from "../../ui";

/**
 * The opening screen: what the holdings are worth, and what happened lately.
 *
 * Deliberately the same two questions the old dashboard answered, so the
 * numbers can be diffed against it side by side while both are running.
 */
export function Dashboard() {
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio });
  const transactions = useQuery({ queryKey: ["transactions"], queryFn: api.transactions });

  const totals = portfolio.data?.totals;
  const pnl = totals ? toPaise(totals.pnl) : 0;
  const recent = transactions.data?.items.slice(0, 8) ?? [];

  return (
    <>
      <PageHead
        title="Dashboard"
        subtitle="What you hold, and what you have been spending."
      />

      {portfolio.error && <Notice>{(portfolio.error as Error).message}</Notice>}

      {portfolio.isPending && !totals ? (
        <Card><Loading what="your position" /></Card>
      ) : (
        <StatRow>
          <Stat
            label="Portfolio value"
            value={totals ? formatRupees(toPaise(totals.value)) : "—"}
          />
          <Stat
            label="Total profit / loss"
            value={totals ? (pnl >= 0 ? "+" : "") + formatRupees(pnl) : "—"}
            tone={pnl > 0 ? "credit" : pnl < 0 ? "debit" : undefined}
          />
          <Stat label="Holdings" value={String(totals?.holdings ?? 0)} />
        </StatRow>
      )}

      <Card title="Holdings" flush>
        {portfolio.isPending && !portfolio.data ? (
          <Loading what="holdings" />
        ) : portfolio.data?.items.length ? (
          <Table
            head={
              <tr>
                <th>Asset</th>
                <th>Type</th>
                <th className={cell.numeric}>Bought</th>
                <th className={cell.numeric}>Now</th>
                <th className={cell.numeric}>Qty</th>
                <th className={cell.numeric}>P&amp;L</th>
              </tr>
            }
          >
            {portfolio.data.items.map((holding) => (
              <tr key={holding.asset_name}>
                <td className={cell.primary}>{holding.asset_name}</td>
                <td>{holding.asset_type}</td>
                <td className={cell.numeric}>{formatRupees(toPaise(holding.buy_price))}</td>
                <td className={cell.numeric}>{formatRupees(toPaise(holding.current_price))}</td>
                <td className={cell.numeric}>{holding.quantity}</td>
                <td className={cell.numeric}><Money value={holding.pnl} signed /></td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>Nothing held yet.</Empty>
        )}
      </Card>

      <div style={{ height: "var(--space-5)" }} />

      <Card title="Recent transactions" flush>
        {transactions.isPending && !transactions.data ? (
          <Loading what="transactions" />
        ) : recent.length ? (
          <Table
            head={
              <tr>
                <th>Date</th>
                <th>Category</th>
                <th>Type</th>
                <th className={cell.numeric}>Amount</th>
                <th>Description</th>
              </tr>
            }
          >
            {recent.map((row) => (
              <tr key={row.id}>
                <td className={cell.numeric} style={{ textAlign: "left" }}>{row.date}</td>
                <td className={cell.primary}>{row.category}</td>
                <td><Tag kind={row.type} /></td>
                <td className={cell.numeric + " " + (row.type === "Income" ? cell.credit : "")}>
                  {formatRupees(toPaise(row.amount))}
                </td>
                <td>{row.description || "—"}</td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No transactions yet.</Empty>
        )}
      </Card>
    </>
  );
}
