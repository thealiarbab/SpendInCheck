import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { Holding } from "../../lib/api";
import { formatChange, formatQuantity, formatMoney, toMinor } from "../../lib/money";
import { discoverHref, externalLinkProps, investHref, stockHref } from "../../lib/links";
import { useLiveQuotes } from "../../hooks/useLiveQuotes";
import {
  Button, Card, Confirm, Empty, Field, Form, FormActions, Loading, Money, Notice,
  PageHead, Picker, RowActions, Stat, StatRow, Table, cell,
} from "../../ui";
import { Sparkline } from "../../ui/charts";
import { SymbolField } from "./SymbolField";
import styles from "./Holdings.module.css";

const ASSET_TYPES = ["Stock", "Mutual Fund", "FD"];

function today(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

// No auto_price, and its absence is the point. The server reads a missing
// auto_price as "decide from whether there is a symbol" and an explicit
// "0" as somebody saying no -- so sending "0" here, which this did, opted
// every new holding out of the pricing it had just been given a symbol for.
const blank = () => ({
  asset_name: "", asset_type: "Stock", buy_date: today(),
  buy_price: "", quantity: "", ticker: "",
});

/**
 * Holdings: what is owned, what it cost, and what it is worth now.
 *
 * This screen is the markets zone, and the only one. Live prices, day
 * moves, symbols and links out to StockSaathi are confined here on
 * purpose -- the dashboard, the ledger and the budgets stay about money in
 * and money out, and a ticker tape in the shell would quietly turn a
 * budgeting app into a half-broker.
 *
 * One price per row, and it keeps itself current. This used to show two --
 * "Valued at", the stored figure every total and P&L is worked out from,
 * beside "Live", what the market said this minute -- because showing a live
 * number next to a P&L computed from a different one is how a screen stops
 * being believed. That reasoning was right and the conclusion was not: the
 * answer is not to show the stale figure too, it is to stop it being stale.
 *
 * So while the exchange is open and the browser is polling anyway, a price
 * that has moved is written back through refresh-prices, and the whole
 * screen -- price, P&L, totals -- is worked out from one number again.
 * Nothing is written when the market is shut, when nothing has moved, or
 * for a holding priced by hand, which is what auto_price means.
 */
export function Holdings() {
  const client = useQueryClient();
  const [draft, setDraft] = useState(blank);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [repricing, setRepricing] = useState<number | null>(null);
  const [price, setPrice] = useState("");
  const [tracking, setTracking] = useState<number | null>(null);
  const [ticker, setTicker] = useState("");
  const [trackAuto, setTrackAuto] = useState(true);

  // One request. The portfolio report carries the editable fields as well
  // as the worked-out profit and loss, so asking /investments separately
  // was a second trip to Mumbai for columns already on the way back.
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio });
  const holdings = portfolio;

  const rows = portfolio.data?.items ?? [];
  const totals = portfolio.data?.totals;
  const pnl = totals ? toMinor(totals.pnl) : 0;

  // Every symbol on the screen, whether or not it is being written to the
  // database. Somebody who recorded a ticker without switching on automatic
  // pricing still wants to see what it is doing.
  const symbols = rows.map((row) => row.ticker).filter((t): t is string => !!t);
  const market = useLiveQuotes(symbols);

  // The last month per symbol, out of this app's own records rather than
  // from StockSaathi. Only asked for once there is a symbol to ask about,
  // so an account of deposits costs nothing.
  //
  // A second round trip, which this project otherwise refuses. It is kept
  // separate rather than folded into /reports/portfolio because that query
  // shares its column list with the dashboard's, and widening it would put
  // thirty closes per holding into the opening screen's payload to draw
  // nothing. The cost is paid where it buys something, and it is not paid
  // up front: the table renders from the portfolio query and the sparkline
  // column fills in when this arrives, so nothing waits on it.
  const history = useQuery({
    queryKey: ["holdings-history"],
    queryFn: api.holdingsHistory,
    enabled: symbols.length > 0,
  });

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["investments"] });
    client.invalidateQueries({ queryKey: ["portfolio"] });
    client.invalidateQueries({ queryKey: ["holdings-history"] });
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

  const setPricing = useMutation({
    mutationFn: (id: number) => api.setPricing(id, ticker.trim(), trackAuto),
    onSuccess: () => {
      refresh();
      setTracking(null);
      setTicker("");
    },
  });

  // What the last saved symbol turned out to be. Shown once, above the
  // table, because it is the answer to a question nobody can check for
  // themselves: RELIANCE, RELIABLE and RELINFRA are three real companies
  // and a wrong guess prices the holding plausibly every day.
  const saved = setPricing.data;

  const updatePrices = useMutation({
    mutationFn: api.refreshPrices,
    onSuccess: refresh,
  });

  // Written back rather than merely displayed, so that "Update prices" is
  // no longer the only thing standing between a price and the truth.
  //
  // Guarded three ways, because this fires from a poll and a write loop
  // would be invisible: nothing happens unless the exchange is open, unless
  // some automatic holding's stored price actually differs from the quote,
  // and unless this exact set of quotes has not already been applied. That
  // last one is what stops the refetch this triggers from triggering it
  // again.
  const applied = useRef("");
  useEffect(() => {
    if (!market.ready || !market.marketOpen || updatePrices.isPending) return;

    const signature = Object.entries(market.quotes)
      .map(([symbol, quote]) => symbol + ":" + quote.price).sort().join(",");
    if (!signature || signature === applied.current) return;

    const moved = (portfolio.data?.items ?? []).some((holding) => {
      if (!holding.auto_price || !holding.ticker) return false;
      const quote = market.quotes[holding.ticker];
      return quote && toMinor(quote.price) !== toMinor(holding.current_price);
    });
    if (!moved) return;

    applied.current = signature;
    updatePrices.mutate();
  }, [market, portfolio.data, updatePrices]);

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteInvestment(id),
    onSuccess: () => {
      refresh();
      setConfirming(null);
    },
  });

  const failure = add.error instanceof ApiError ? add.error : null;
  const fields = failure?.isValidation ? failure.fields : {};
  const pricingFailure = setPricing.error instanceof ApiError ? setPricing.error : null;

  function startReprice(holding: Holding) {
    setRepricing(holding.id);
    setPrice(holding.current_price);
    setTracking(null);
    setConfirming(null);
  }

  function startTracking(holding: Holding) {
    setTracking(holding.id);
    setTicker(holding.ticker ?? "");
    setTrackAuto(holding.auto_price || !holding.ticker);
    setRepricing(null);
    setConfirming(null);
    setPricing.reset();
  }

  const automatic = rows.filter((row) => row.auto_price).length;

  return (
    <>
      <PageHead title="Investments" subtitle="What you own, against what it cost." />

      {portfolio.isPending && !totals ? (
        <Loading what="your position" shape="stats" rows={3} />
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
          {/* No current price is asked for. Something bought is worth what
              it cost until the market says otherwise, so the field had one
              sensible answer and it was already on the screen two rows up.
              Worse, a holding with a symbol and automatic pricing has
              whatever was typed here overwritten at the next refresh, so
              the field invited a number and then quietly threw it away.
              Correcting a price later is what Price by hand is for, and
              the server defaults current_price to buy_price when the
              field is absent, so nothing needs to be sent. */}
          <div className={styles.symbolSlot}>
            <label className={styles.symbolLabel} htmlFor="add-ticker">
              Symbol or fund code
            </label>
            <SymbolField
              id="add-ticker"
              label="Symbol or fund code"
              placeholder="optional — RELIANCE, or 118989"
              value={draft.ticker}
              onChange={(ticker) => setDraft({ ...draft, ticker })}
              /* Taking a suggestion fills the asset name too, but only
                 when it is still empty. Somebody who typed "my Infosys
                 shares" first meant it, and overwriting that with the
                 legal name is the app correcting their own records. */
              onPick={(found) => setDraft((current) => ({
                ...current,
                ticker: found.symbol,
                asset_name: current.asset_name.trim() || found.name || found.symbol,
              }))}
            />
            {fields.ticker && <p className={styles.symbolError}>{fields.ticker}</p>}
          </div>
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
          Give it a symbol and it is priced from the market from the moment you
          save — you do not have to have bought it today. Without one it is worth
          what it cost until you price it by hand.
        </p>
        {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
        {add.isSuccess && <Notice ok>Saved.</Notice>}
      </Card>

      <div style={{ height: "var(--space-5)" }} />

      <Card title="All holdings" flush>
        {rows.length > 0 && (
          <div className={styles.marketLine}>
            <span>
              {automatic === 0
                ? "No holding is priced automatically yet."
                : market.unreachable
                ? "Cannot reach the market right now — showing the last prices fetched."
                : market.marketOpen
                ? `Live for ${symbols.length} symbol${symbols.length === 1 ? "" : "s"}.`
                : "Market closed — these are the last traded prices."}
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
              {automatic > 0 && (
                <Button kind="quiet" small disabled={updatePrices.isPending}
                        onClick={() => updatePrices.mutate()}>
                  {updatePrices.isPending ? "Updating…" : "Update prices now"}
                </Button>
              )}
              <span className={styles.attribution}>
                Prices by{" "}
                <a href={investHref} {...externalLinkProps}>StockSaathi ↗</a>
              </span>
            </span>
          </div>
        )}

        {setPricing.isSuccess && saved?.ticker && (
          <div style={{ padding: "0 var(--space-5)" }}>
            <Notice ok>
              {saved.instrument?.name
                ? `${saved.ticker} — ${saved.instrument.name}${
                    saved.instrument.sector ? `, ${saved.instrument.sector}` : ""}.`
                : `${saved.ticker} saved.`}
              {saved.priced > 0 && " Priced from the market."}
            </Notice>
          </div>
        )}

        {updatePrices.isSuccess && (
          <div style={{ padding: "0 var(--space-5)" }}>
            <Notice ok>
              {/* "Priced", not "revalued": the count is how many holdings
                  the market answered for, and on a quiet day that is the
                  same number with nothing changed. Claiming a revaluation
                  that did not happen is worse than saying less. */}
              {updatePrices.data.priced === 0
                ? "Nothing to price — no holding is set to fetch its own."
                : `Priced ${updatePrices.data.priced} holding${
                    updatePrices.data.priced === 1 ? "" : "s"} from the market.`}
            </Notice>
          </div>
        )}

        {holdings.isPending && !holdings.data ? (
          <Loading what="holdings" shape="table" rows={4}
                   columns={["55%", "40%", "60%", "#55%", "#40%", "#60%",
                             "#50%", "70%", "#55%", "30%"]} />
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
                <th className={cell.numeric}>Price</th>
                <th>Month · 52 weeks</th>
                <th className={cell.numeric}>P&amp;L</th>
                <th />
              </tr>
            }
          >
            {rows.map((holding) => {
              const quote = holding.ticker ? market.quotes[holding.ticker] : undefined;
              // Minor units, because that is what every other figure on
              // this screen is measured in and the chart only needs the
              // shape to be to scale.
              const closes = (holding.ticker
                ? history.data?.items[holding.ticker] ?? []
                : []).map((point) => toMinor(point.close));
              // What the symbol is, written down by the nightly job. The
              // lookup behind it takes three seconds cold, which is why
              // this is read from our own table and not asked for here.
              const what = holding.ticker
                ? history.data?.instruments[holding.ticker]
                : undefined;
              return (
                <tr key={holding.id}>
                  <td className={cell.primary}>
                    {holding.asset_name}
                    {holding.ticker && (
                      <span className={styles.tickerLine}>
                        {/* By ticker, not by name: a page for "Reliance
                            Industries" does not exist, and the symbol is
                            what their router matches. */}
                        <a className={styles.tickerLink} href={stockHref(holding.ticker)}
                           /* The company the symbol belongs to, on hover.
                              Not in the cell: asset_name is what its owner
                              called it, and printing both would be the app
                              correcting somebody's own records. */
                           title={[what?.name, what?.sector]
                             .filter(Boolean).join(" · ") || undefined}
                           {...externalLinkProps}>
                          {holding.ticker} ↗
                        </a>
                        {holding.auto_price && (
                          <span className={styles.tracking}
                                title="Priced automatically">●</span>
                        )}
                      </span>
                    )}
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
                    ) : (
                      <>
                        {/* The quote when there is one, the stored figure
                            when there is not -- a shut exchange, a holding
                            priced by hand, a feed that did not answer. The
                            two agree while the market is open, because the
                            effect above writes the quote back; this is not
                            two numbers competing, it is one with a
                            fallback. */}
                        {formatMoney(toMinor(quote ? quote.price
                                                   : holding.current_price))}
                        {quote && (
                          <span className={`${styles.live} ${
                            (quote.change ?? 0) > 0 ? styles.up
                            : (quote.change ?? 0) < 0 ? styles.down : ""}`}>
                            {formatChange(quote.change)}
                          </span>
                        )}
                      </>
                    )}
                  </td>
                  <td>
                    {/* An em-dash when there is nothing to draw, matching
                        the Price column beside it. A holding with no symbol
                        has no price history and never will -- a deposit has
                        no market -- so the cell is empty by nature rather
                        than by failure. Left blank the two columns
                        disagreed about how to say that, and a blank cell in
                        a row of figures reads as something not having
                        loaded. */}
                    {closes.length <= 1 && !(what?.low_52w && what?.high_52w) && "—"}
                    {closes.length > 1 && (
                      <Sparkline values={closes}
                                 label={`${holding.ticker} over the last month`} />
                    )}
                    {what?.low_52w && what.high_52w && (
                      /* Under the month's shape rather than in a column of
                         its own: the table is already wide, and a year's
                         range is context for the line above it rather
                         than a figure anybody reads on its own. */
                      <span className={styles.range}
                            title="52-week range">
                        {/* Whole rupees, not compact: 1,728 becomes "1.7K"
                            in compact notation, and the digits it drops
                            are the ones a price range is read for. The
                            paise are dropped instead -- nobody compares a
                            year's high to two decimal places. */}
                        {formatMoney(toMinor(what.low_52w), { whole: true })} –{" "}
                        {formatMoney(toMinor(what.high_52w), { whole: true })}
                      </span>
                    )}
                  </td>
                  <td className={cell.numeric}>
                    <Money value={holding.pnl} signed />
                  </td>
                  <td>
                    {confirming === holding.id ? (
                      <Confirm
                        busy={remove.isPending}
                        onYes={() => remove.mutate(holding.id)}
                        onNo={() => setConfirming(null)}
                      />
                    ) : tracking === holding.id ? (
                      <div>
                        <SymbolField
                          value={ticker}
                          onChange={setTicker}
                          label={`Symbol for ${holding.asset_name}`}
                          id={`symbol-${holding.id}`}
                        />
                        <label className={styles.trackRow}>
                          <input
                            type="checkbox" checked={trackAuto}
                            disabled={ticker.trim() === ""}
                            onChange={(e) => setTrackAuto(e.target.checked)}
                          />
                          Fetch the price for me
                        </label>
                        <RowActions>
                          <Button small disabled={setPricing.isPending}
                                  onClick={() => setPricing.mutate(holding.id)}>
                            {setPricing.isPending ? "Checking…" : "Save"}
                          </Button>
                          <Button kind="quiet" small onClick={() => setTracking(null)}>
                            Cancel
                          </Button>
                        </RowActions>
                        {pricingFailure && (
                          <p className={styles.trackRow} style={{ color: "var(--state-error)" }}>
                            {pricingFailure.fields.ticker ?? pricingFailure.message}
                          </p>
                        )}
                      </div>
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
                        {/* One control, and only the one that can do
                            something.

                            There used to be two on every row -- "Price by
                            hand" and "Market pricing" -- which was one
                            question asked twice and, on an automatically
                            priced holding, a straight lie: you could type
                            a price and the next poll would overwrite it.

                            So a holding the market prices offers only the
                            symbol, and a holding priced by hand offers
                            only the price. The other control is not
                            disabled, it is absent, because a disabled
                            button still asks somebody to work out why. */}
                        {holding.auto_price ? (
                          <Button kind="quiet" small
                                  onClick={() => startTracking(holding)}>
                            Symbol
                          </Button>
                        ) : (
                          <>
                            <Button kind="quiet" small
                                    onClick={() => startReprice(holding)}>
                              Set price
                            </Button>
                            <Button kind="quiet" small
                                    onClick={() => startTracking(holding)}>
                              Use the market
                            </Button>
                          </>
                        )}
                        <Button kind="danger" small
                                onClick={() => { setRepricing(null); setTracking(null);
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
            <a className={styles.saathiLink} href={discoverHref}
               {...externalLinkProps}>Find something worth holding ↗</a>
          </Empty>
        )}
        {reprice.error && <Notice>{(reprice.error as Error).message}</Notice>}
        {remove.error && <Notice>{(remove.error as Error).message}</Notice>}
        {updatePrices.error && <Notice>{(updatePrices.error as Error).message}</Notice>}
      </Card>
    </>
  );
}
