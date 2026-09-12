import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { formatQuantity, formatMoney, toMinor } from "../../lib/money";
import { Card, Empty, Loading, Money, Notice, PageHead, Stat, StatRow, Table, Tag, cell } from "../../ui";

/**
 * The opening screen: what the holdings are worth, and what happened lately.
 *
 * Deliberately the same two questions the old dashboard answered, so the
 * numbers can be diffed against it side by side while both are running.
 */
export function Dashboard() {
  // One request, not two. Both halves come from the same connection on the
  // server, so asking separately costs a second trip to Mumbai for rows it
  // had already opened a connection to read.
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: () => api.dashboard() });

  const portfolio = dashboard;
  const transactions = dashboard;
  const totals = dashboard.data?.portfolio.totals;
  const pnl = totals ? toMinor(totals.pnl) : 0;
  const recent = dashboard.data?.recent ?? [];

  return (
    <>
      <PageHead
        title="Dashboard"
        subtitle="What you hold, and what you have been spending."
      />

      {portfolio.error && <Notice>{(portfolio.error as Error).message}</Notice>}

      {portfolio.isPending && !totals ? (
        /* The stat row itself, not a Card around a line of text: the three
           cells are the shape arriving, so standing in for them keeps the
           holdings table below from jumping up the page when they land. */
        <Loading what="your position" shape="stats" rows={3} />
      ) : (
        <StatRow>
          <Stat
            label="Portfolio value"
            value={totals ? formatMoney(toMinor(totals.value)) : "—"}
          />
          <Stat
            label="Total profit / loss"
            value={totals ? (pnl >= 0 ? "+" : "") + formatMoney(pnl) : "—"}
            tone={pnl > 0 ? "credit" : pnl < 0 ? "debit" : undefined}
          />
          <Stat label="Holdings" value={String(totals?.holdings ?? 0)} />
        </StatRow>
      )}

      <Card title="Holdings" flush>
        {dashboard.isPending && !dashboard.data ? (
          <Loading what="holdings" shape="table" rows={3}
                   columns={["30%", "40%", "#60%", "#60%", "#50%", "#60%"]} />
        ) : dashboard.data?.portfolio.items.length ? (
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
            {dashboard.data.portfolio.items.map((holding) => (
              <tr key={holding.asset_name}>
                <td className={cell.primary}>{holding.asset_name}</td>
                <td>{holding.asset_type}</td>
                <td className={cell.numeric}>{formatMoney(toMinor(holding.buy_price))}</td>
                <td className={cell.numeric}>{formatMoney(toMinor(holding.current_price))}</td>
                <td className={cell.numeric}>{formatQuantity(holding.quantity)}</td>
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
          <Loading what="transactions" shape="table" rows={5}
                   columns={["70%", "45%", "50%", "#55%", "60%"]} />
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
                  {formatMoney(toMinor(row.amount))}
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
