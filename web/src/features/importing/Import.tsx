import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { ImportReading, ImportRow } from "../../lib/api";
import { formatMoney, toMinor } from "../../lib/money";
import {
  Button, Card, Empty, Loading, Notice, PageHead, Picker, Table, Tag, cell,
} from "../../ui";
import styles from "./Import.module.css";

/** How many rows of the preview to draw before summarising the rest. */
const PREVIEW = 40;

/**
 * Importing a CSV.
 *
 * Two steps, and the split is the whole point: the first parses and shows,
 * the second writes. Nothing reaches the ledger that has not been on screen
 * first, with the rows that will be skipped and the reason for each -- this
 * is the one screen in the application that can create three hundred wrong
 * rows from a single click.
 */
export function Import() {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [fallback, setFallback] = useState("");
  const [account, setAccount] = useState("");
  const [reading, setReading] = useState<ImportReading | null>(null);
  const [filename, setFilename] = useState("");
  const file = useRef<HTMLInputElement>(null);

  const categories = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const accounts = useQuery({
    queryKey: ["accounts", false],
    queryFn: () => api.accounts(false),
  });

  const examine = useMutation({
    mutationFn: () => api.examineImport(text, fallback ? Number(fallback) : undefined),
    onSuccess: setReading,
  });

  const commit = useMutation({
    mutationFn: (rows: ImportRow[]) =>
      api.commitImport(rows, account ? Number(account) : undefined),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["transactions"] });
      client.invalidateQueries({ queryKey: ["report"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      client.invalidateQueries({ queryKey: ["accounts"] });
      client.invalidateQueries({ queryKey: ["budgets"] });
      setReading(null);
      setText("");
      setFilename("");
      if (file.current) file.current.value = "";
    },
  });

  /** Read a chosen file into the box, so the same path handles both. */
  function take(chosen: File | undefined) {
    if (!chosen) return;
    setFilename(chosen.name);
    setReading(null);
    chosen.text().then(setText);
  }

  const failure = examine.error instanceof ApiError ? examine.error : null;
  const fields = failure?.isValidation ? failure.fields : {};
  const commitFailure = commit.error instanceof ApiError ? commit.error : null;

  const usable = (reading?.rows ?? []).filter((row) => row.skip === undefined);
  const skipped = (reading?.rows ?? []).filter((row) => row.skip !== undefined);
  const spendable = categories.data?.items ?? [];

  return (
    <>
      <PageHead
        title="Import"
        subtitle="Read a CSV into the ledger. Nothing is written until you have seen it."
      />

      <Card title="The file">
        <div className={styles.pick}>
          <input
            ref={file} type="file" accept=".csv,text/csv,text/plain"
            className={styles.file}
            onChange={(event) => take(event.target.files?.[0])}
          />
          {filename && <span className={styles.filename}>{filename}</span>}
        </div>

        <textarea
          className={styles.paste}
          value={text}
          rows={7}
          spellCheck={false}
          placeholder={"Date,Description,Amount,Category\n"
                       + "2026-06-01,Weekly shop,1200.00,Groceries"}
          aria-label="CSV contents"
          onChange={(event) => { setText(event.target.value); setReading(null); }}
        />

        <div className={styles.options}>
          <Picker
            label="If a category is missing" name="default_category_id"
            value={fallback} error={fields.default_category_id}
            onChange={(event) => setFallback(event.target.value)}
          >
            <option value="">Skip the row</option>
            {spendable.map((one) => (
              <option key={one.id} value={one.id}>File under {one.name}</option>
            ))}
          </Picker>
          <Picker
            label="File rows on" name="account_id" value={account}
            onChange={(event) => setAccount(event.target.value)}
          >
            <option value="">Default account</option>
            {(accounts.data?.items ?? []).map((one) => (
              <option key={one.id} value={one.id}>{one.name}</option>
            ))}
          </Picker>
        </div>

        <div className={styles.actions}>
          <Button disabled={!text.trim() || examine.isPending}
                  onClick={() => examine.mutate()}>
            {examine.isPending ? "Reading…" : "Read the file"}
          </Button>
          <p className={styles.note}>
            Reading writes nothing. Columns are matched by name, so Date,
            Value Date and Transaction Date all work — as do Debit and Credit
            instead of one Amount.
          </p>
        </div>

        {fields.text && <Notice>{fields.text}</Notice>}
        {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
      </Card>

      {examine.isPending && <Card><Loading what="the file" /></Card>}

      {reading && (
        <>
          <div className={styles.gap} />
          <Card title="What this would import" flush>
            {reading.problems.length > 0 && (
              <div className={styles.problems}>
                {reading.problems.map((problem) => (
                  <Notice key={problem}>{problem}</Notice>
                ))}
              </div>
            )}

            {reading.rows.length === 0 ? (
              <Empty>Nothing readable in that file.</Empty>
            ) : (
              <>
                <p className={styles.summary}>
                  <strong>{reading.summary.readable}</strong> row
                  {reading.summary.readable === 1 ? "" : "s"} ready
                  {reading.summary.skipped > 0 && (
                    <> · <strong>{reading.summary.skipped}</strong> will be
                    skipped</>
                  )}
                  {reading.columns.length > 0 && (
                    <span className={styles.columns}>
                      matched {reading.columns.join(", ")}
                    </span>
                  )}
                </p>

                <Table
                  head={
                    <tr>
                      <th className={cell.numeric}>Line</th>
                      <th>Date</th>
                      <th>Category</th>
                      <th>Type</th>
                      <th className={cell.numeric}>Amount</th>
                      <th>Description</th>
                    </tr>
                  }
                >
                  {reading.rows.slice(0, PREVIEW).map((row) => (
                    <tr key={row.line}
                        className={row.skip ? styles.skippedRow : undefined}>
                      <td className={cell.numeric + " " + styles.line}>{row.line}</td>
                      {row.skip ? (
                        // The reason spans the row it belongs to: a skipped
                        // line has no figures to put in the columns, and
                        // blank cells would say nothing.
                        <td colSpan={5} className={styles.reason}>{row.skip}</td>
                      ) : (
                        <>
                          <td className={cell.numeric} style={{ textAlign: "left" }}>
                            {row.date}
                          </td>
                          <td className={cell.primary}>
                            {row.category ?? <em className={styles.fallback}>fallback</em>}
                          </td>
                          <td><Tag kind={row.type!} /></td>
                          <td className={cell.numeric}>
                            {formatMoney(toMinor(row.amount!))}
                          </td>
                          <td>{row.description || "—"}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </Table>

                {reading.rows.length > PREVIEW && (
                  <p className={styles.more}>
                    …and {reading.rows.length - PREVIEW} more rows, which will be
                    imported too.
                  </p>
                )}

                <div className={styles.confirm}>
                  <Button
                    disabled={usable.length === 0 || commit.isPending}
                    onClick={() => commit.mutate(usable)}
                  >
                    {commit.isPending ? "Importing…"
                      : `Import ${usable.length} row${usable.length === 1 ? "" : "s"}`}
                  </Button>
                  <Button kind="quiet" onClick={() => setReading(null)}>
                    Cancel
                  </Button>
                  {skipped.length > 0 && (
                    <span className={styles.note}>
                      {skipped.length} unreadable row
                      {skipped.length === 1 ? "" : "s"} will be left out.
                    </span>
                  )}
                </div>

                {commitFailure && <Notice>{commitFailure.message}</Notice>}
              </>
            )}
          </Card>
        </>
      )}

      {commit.isSuccess && (
        <>
          <div className={styles.gap} />
          <Notice ok>
            Imported {commit.data.written} transaction
            {commit.data.written === 1 ? "" : "s"}.
          </Notice>
        </>
      )}
    </>
  );
}
