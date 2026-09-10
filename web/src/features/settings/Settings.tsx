import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import { useSession } from "../../app/SessionProvider";
import { useTheme } from "../../app/ThemeProvider";
import { externalLinkProps, investHref } from "../../lib/links";
import { Button, Card, Loading, Notice } from "../../ui";
import styles from "./Settings.module.css";

/**
 * A settings row: what it is on the left, the control on the right.
 *
 * The layout is StockSaathi's -- its settings page states each option and its
 * consequence in prose, then puts the control beside it, rather than leaving
 * a bare label above an input. Only the arrangement is borrowed; every colour
 * here is SpendInCheck's own token, so both themes stay correct.
 */
function Row(
  { title, description, children }:
  { title: string; description: ReactNode; children: ReactNode },
) {
  return (
    <div className={styles.row}>
      <div className={styles.label}>
        <div className={styles.title}>{title}</div>
        <div className={styles.description}>{description}</div>
      </div>
      <div className={styles.control}>{children}</div>
    </div>
  );
}

/**
 * Describe a currency the way a person picks one: code, name, symbol.
 *
 * All three come from Intl, in the reader's own language, so the app ships
 * no list of currency names and cannot have a stale or English-only one.
 */
function describe(code: string): { code: string; name: string; symbol: string } {
  let name = code;
  let symbol = code;
  try {
    name = new Intl.DisplayNames(undefined, { type: "currency" }).of(code) ?? code;
    // The symbol is whatever Intl puts around a number, with the number and
    // its spacing removed -- there is no API that returns it on its own.
    symbol = new Intl.NumberFormat(undefined, {
      style: "currency", currency: code, currencyDisplay: "narrowSymbol",
      minimumFractionDigits: 0, maximumFractionDigits: 0,
    }).format(0).replace(/[\d\s ]/g, "");
  } catch {
    // A code this runtime does not know still lists, just plainly.
  }
  return { code, name, symbol };
}

/** A sample figure, so the choice can be seen rather than imagined. */
function sample(code: string): string {
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: code })
      .format(123456.789);
  } catch {
    return "—";
  }
}

export function Settings() {
  const { account, refresh } = useSession();
  const { theme, setTheme } = useTheme();
  const [chosen, setChosen] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const currencies = useQuery({ queryKey: ["currencies"], queryFn: api.currencies });

  const described = useMemo(
    () => (currencies.data?.items ?? []).map(describe),
    [currencies.data]);

  const matches = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return described;
    return described.filter(
      (one) => one.code.toLowerCase().includes(needle) ||
               one.name.toLowerCase().includes(needle));
  }, [described, filter]);

  const current = account?.currency ?? currencies.data?.current ?? "INR";
  const selected = chosen ?? current;

  const save = useMutation({
    mutationFn: () => api.setCurrency(selected),
    onSuccess: async () => {
      // A full reload rather than a re-render. Every figure on every screen
      // is parsed at the currency's scale, and react-query holds pages of
      // rows already parsed at the old one; reloading is the only way to be
      // certain nothing is left showing figures in two scales at once.
      await refresh();
      window.location.reload();
    },
  });

  const failure = save.error instanceof ApiError ? save.error : null;

  return (
    <div className={styles.page}>
      <h1 className={styles.heading}>Settings</h1>
      <p className={styles.intro}>
        What this ledger counts in, and how it looks.
      </p>

      <Card title="Currency">
        {currencies.isPending ? (
          <Loading what="the currencies" />
        ) : currencies.error ? (
          <Notice>{(currencies.error as Error).message}</Notice>
        ) : (
          <>
            <Row
              title="Ledger currency"
              description={
                <>
                  Every figure in the app is written and rounded in this.
                  Currently <strong>{sample(selected)}</strong> for a hundred and
                  twenty-three thousand.
                </>
              }
            >
              <input
                className={styles.search}
                value={filter}
                placeholder="Search 162…"
                aria-label="Search currencies"
                onChange={(event) => setFilter(event.target.value)}
              />
              <select
                className={styles.select}
                value={selected}
                aria-label="Ledger currency"
                onChange={(event) => setChosen(event.target.value)}
              >
                {matches.map((one) => (
                  <option key={one.code} value={one.code}>
                    {one.code} — {one.name}
                    {one.symbol && one.symbol !== one.code ? ` (${one.symbol})` : ""}
                  </option>
                ))}
              </select>
              <Button
                onClick={() => save.mutate()}
                disabled={selected === current || save.isPending}
              >
                {save.isPending ? "Saving…" : "Save"}
              </Button>
            </Row>

            {filter && (
              <p className={styles.count}>
                {matches.length} of {described.length} currencies match “{filter}”.
              </p>
            )}
            {failure?.fields.currency && (
              <p className={styles.error}>{failure.fields.currency}</p>
            )}

            <Row
              title="Nothing is converted"
              description={
                <>
                  This ledger holds no exchange rates. Changing the currency changes
                  what your figures are <em>labelled</em>, not what they are worth —
                  a balance of 1,000 stays 1,000.
                </>
              }
            >
              <span className={styles.note}>No rates</span>
            </Row>

            <Row
              title="Rounding follows the currency"
              description={
                <>
                  Most currencies keep two decimal places. The yen and the won have
                  none, and the six Gulf and North African dinars have three — so an
                  amount entered after the change is stored to the new currency’s own
                  precision.
                </>
              }
            >
              <span className={styles.note}>
                {selected}: {sample(selected).replace(/[^\d.,]/g, "").split(".")[1]?.length ?? 0} dp
              </span>
            </Row>

            {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
          </>
        )}
      </Card>

      <div className={styles.gap} />

      <Card title="Appearance">
        <Row
          title="Theme"
          description="Brass for the archival ledger, paper for something lighter. Kept in this browser, not on the account."
        >
          <div className={styles.chips}>
            <button
              type="button"
              className={theme === "brass" ? styles.chipOn : styles.chip}
              aria-pressed={theme === "brass"}
              onClick={() => setTheme("brass")}
            >
              Brass
            </button>
            <button
              type="button"
              className={theme === "paper" ? styles.chipOn : styles.chip}
              aria-pressed={theme === "paper"}
              onClick={() => setTheme("paper")}
            >
              Paper
            </button>
          </div>
        </Row>
      </Card>

      <div className={styles.gap} />

      <Card title="Account">
        <Row title="Signed in as" description="Demonstration accounts are discarded when you leave.">
          <span className={styles.value}>
            {account?.username ?? "—"}
            {account?.is_demo ? <span className={styles.note}>demo</span> : null}
          </span>
        </Row>
      </Card>

      <div className={styles.gap} />

      <section className={styles.about}>
        <h2 className={styles.aboutTitle}>About</h2>
        <p>
          <strong>SpendInCheck</strong> — where the money went, what you planned to
          spend, and what your holdings are worth, in one place.
        </p>
        <p className={styles.fine}>
          Holdings are recorded at the prices you enter. SpendInCheck does not fetch
          live market prices, is not a broker or an adviser, and nothing in it is
          investment advice. For markets and research, see{" "}
          <a href={investHref} {...externalLinkProps}>StockSaathi ↗</a>.
        </p>
      </section>
    </div>
  );
}
