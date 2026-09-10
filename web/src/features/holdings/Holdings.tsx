import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { InvestmentRow } from "../../lib/api";
import { formatQuantity, formatMoney, toMinor } from "../../lib/money";
import { discoverHref, externalLinkProps, stockHref } from "../../lib/links";
import {
  Button, Card, Confirm, Empty, Field, Form, FormActions, Loading, Money, Notice,
  PageHead, Picker, RowActions, Stat, StatRow, Table, cell,
} from "../../ui";
import styles from "./Holdings.module.css";

const ASSET_TYPES = ["Stock", "Mutual Fund", "FD"];

function today(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

const blank = () => ({
  asset_name: "", asset_type: "Stock", buy_date: today(),
  buy_price: "", quantity: "", current_price: "",
});

/**
 * Holdings: what is owned, what it cost, and what it is worth now.
 *
 * Two queries rather than one. /investments is the editable record --
 * prices and quantities as entered; /reports/portfolio is the same rows
 * with profit and loss worked out. The report is what the table shows and
 * the record is what the repricing writes to, so both are needed and the
 * arithmetic stays in SQL rather than being redone here.
 */
export function Holdings() {
  const client = useQueryClient();
  const [draft, setDraft] = useState(blank);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [repricing, setRepricing] = useState<number | null>(null);
  const [price, setPrice] = useState("");

  const holdings = useQuery({ queryKey: ["investments"], queryFn: api.investments });
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio });

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["investments"] });
    client.invalidateQueries({ queryKey: ["portfolio"] });
    // The opening screen shows the same holdings and their totals.
    client.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const add = useMutation({
    mutationFn: () => api.addInvestment(draft),
    onSuccess: () => {
      refresh();
      setDraft(blank());
    },
  });

  const reprice = useMutation({
    mutationFn: (id: number) => api.reprice(id, price),
    onSuccess: () => {
      refresh();
      setRepricing(null);
      setPrice("");
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteInvestment(id),
    onSuccess: () => {
      refresh();
      setConfirming(null);
    },
  });

  const failure = add.error instanceof ApiError ? add.error : null;
  const fields = failure?.isValidation ? failure.fields : {};

  const rows = holdings.data?.items ?? [];
  const totals = portfolio.data?.totals;
  const pnl = totals ? toMinor(totals.pnl) : 0;

  // Profit and loss comes from the report, keyed by name so the editable
  // row and its worked-out figures line up without a second id in the API.
  const worked = new Map(
    (portfolio.data?.items ?? []).map((item) => [item.asset_name, item]));

  function startReprice(holding: InvestmentRow) {
    setRepricing(holding.id);
    setPrice(holding.current_price);
    setConfirming(null);
  }

  return (
    <>
      <PageHead title="Holdings" subtitle="What you own, against what it cost." />

      {portfolio.isPending && !totals ? (
        <Card><Loading what="your position" /></Card>
      ) : (
        <StatRow>
          <Stat label="Portfolio value"
                value={totals ? formatMoney(toMinor(totals.value)) : "—"} />
          <Stat label="Total profit / loss"
                value={totals ? (pnl >= 0 ? "+" : "") + formatMoney(pnl) : "—"}
                tone={pnl > 0 ? "credit" : pnl < 0 ? "debit" : undefined} />
          <Stat label="Holdings" value={String(totals?.holdings ?? 0)} />
        </StatRow>
      )}

      <Card title="Add a holding">
        <Form>
          <Field
            label="Asset name" name="asset_name" maxLength={100}
            value={draft.asset_name} error={fields.asset_name} placeholder="Tata Motors"
            onChange={(e) => setDraft({ ...draft, asset_name: e.target.value })}
          />
          <Picker
            label="Type" name="asset_type" value={draft.asset_type} error={fields.asset_type}
            onChange={(e) => setDraft({ ...draft, asset_type: e.target.value })}
          >
            {ASSET_TYPES.map((one) => <option key={one} value={one}>{one}</option>)}
          </Picker>
          <Field
            label="Buy date" name="buy_date" type="date" max={today()}
            value={draft.buy_date} error={fields.buy_date}
            onChange={(e) => setDraft({ ...draft, buy_date: e.target.value })}
          />
          <Field
            label="Buy price" name="buy_price" type="number" step="0.01" min="0.01" numeric
            value={draft.buy_price} error={fields.buy_price} placeholder="0.00"
            onChange={(e) => setDraft({ ...draft, buy_price: e.target.value })}
          />
          <Field
            label="Quantity" name="quantity" type="number" step="0.0001" min="0.0001" numeric
            value={draft.quantity} error={fields.quantity} placeholder="0"
            onChange={(e) => setDraft({ ...draft, quantity: e.target.value })}
          />
          <Field
            label="Current price" name="current_price" type="number" step="0.01" min="0.01"
            numeric value={draft.current_price} error={fields.current_price}
            placeholder="same as buy"
            onChange={(e) => setDraft({ ...draft, current_price: e.target.value })}
          />
          <FormActions>
            <Button
              onClick={() => add.mutate()}
              disabled={add.isPending || draft.asset_name.trim() === "" ||
                        draft.buy_price === "" || draft.quantity === ""}
            >
              {add.isPending ? "Saving…" : "Add"}
            </Button>
          </FormActions>
        </Form>
        <p className={styles.hint}>
          Leave the current price empty and the holding is worth what it cost until
          you reprice it.
        </p>
        {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
        {add.isSuccess && <Notice ok>Saved.</Notice>}
      </Card>

      <div style={{ height: "var(--space-5)" }} />

      <Card title="All holdings" flush>
        {holdings.isPending && !holdings.data ? (
          <Loading what="holdings" />
        ) : holdings.error ? (
          <Notice>{(holdings.error as Error).message}</Notice>
        ) : rows.length ? (
          <Table
            head={
              <tr>
                <th>Asset</th>
                <th>Type</th>
                <th>Bought</th>
                <th className={cell.numeric}>Buy price</th>
                <th className={cell.numeric}>Qty</th>
                <th className={cell.numeric}>Now</th>
                <th className={cell.numeric}>P&amp;L</th>
                <th />
              </tr>
            }
          >
            {rows.map((holding) => {
              const figures = worked.get(holding.asset_name);
              return (
                <tr key={holding.id}>
                  <td className={cell.primary}>
                    {holding.asset_type === "Stock" ? (
                      // Only a stock has a page to deep-link to; a fixed
                      // deposit has no ticker and never will.
                      <a className={styles.symbol} href={stockHref(holding.asset_name)}
                         {...externalLinkProps}>
                        {holding.asset_name} <span aria-hidden="true">↗</span>
                      </a>
                    ) : holding.asset_name}
                  </td>
                  <td>{holding.asset_type}</td>
                  <td className={cell.numeric} style={{ textAlign: "left" }}>
                    {holding.buy_date}
                  </td>
                  <td className={cell.numeric}>
                    {formatMoney(toMinor(holding.buy_price))}
                  </td>
                  <td className={cell.numeric}>{formatQuantity(holding.quantity)}</td>
                  <td className={cell.numeric}>
                    {repricing === holding.id ? (
                      <input
                        className={styles.priceInput}
                        type="number" step="0.01" min="0.01" value={price}
                        aria-label={`New price for ${holding.asset_name}`}
                        onChange={(e) => setPrice(e.target.value)}
                      />
                    ) : formatMoney(toMinor(holding.current_price))}
                  </td>
                  <td className={cell.numeric}>
                    {figures ? <Money value={figures.pnl} signed /> : "—"}
                  </td>
                  <td>
                    {confirming === holding.id ? (
                      <Confirm
                        busy={remove.isPending}
                        onYes={() => remove.mutate(holding.id)}
                        onNo={() => setConfirming(null)}
                      />
                    ) : repricing === holding.id ? (
                      <RowActions>
                        <Button small disabled={reprice.isPending}
                                onClick={() => reprice.mutate(holding.id)}>
                          {reprice.isPending ? "Saving…" : "Save"}
                        </Button>
                        <Button kind="quiet" small onClick={() => setRepricing(null)}>
                          Cancel
                        </Button>
                      </RowActions>
                    ) : (
                      <RowActions>
                        <Button kind="quiet" small onClick={() => startReprice(holding)}>
                          Reprice
                        </Button>
                        <Button kind="danger" small
                                onClick={() => { setRepricing(null);
                                                 setConfirming(holding.id); }}>
                          Delete
                        </Button>
                      </RowActions>
                    )}
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : (
          <Empty>
            Nothing held yet.{" "}
            <a href={discoverHref} {...externalLinkProps}>Find something to buy ↗</a>
          </Empty>
        )}
        {reprice.error && <Notice>{(reprice.error as Error).message}</Notice>}
        {remove.error && <Notice>{(remove.error as Error).message}</Notice>}
      </Card>
    </>
  );
}
