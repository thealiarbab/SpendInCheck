import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import { formatSigned, toMinor } from "../../lib/money";
import { Button, Empty, Loading, Notice } from "../../ui";
import styles from "./Contributions.module.css";

function today(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

/**
 * What has been put towards one goal, and the form that adds to it.
 *
 * Putting in and taking out are one field, not two buttons: the sign is
 * what distinguishes them in the database, and a form that mirrors the
 * storage has one fewer thing to get out of step. "Take out" fills the
 * amount with a minus rather than submitting a different shape.
 */
export function Contributions({ goalId }: { goalId: number }) {
  const client = useQueryClient();
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today);
  const [note, setNote] = useState("");

  const contributions = useQuery({
    queryKey: ["contributions", goalId],
    queryFn: () => api.contributions(goalId),
  });
  const items = contributions.data?.items ?? [];

  // The goal's total is summed from these, so both have to be refetched.
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["contributions", goalId] });
    client.invalidateQueries({ queryKey: ["goals"] });
  };

  const add = useMutation({
    mutationFn: () => api.contribute(goalId, { amount, date, note: note || undefined }),
    onSuccess: () => {
      refresh();
      setAmount("");
      setNote("");
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteContribution(id),
    onSuccess: refresh,
  });

  const failure = add.error instanceof ApiError ? add.error : null;
  const fields = failure?.isValidation ? failure.fields : {};

  /** Flip the sign of whatever is typed, so "take out" is one click. */
  function invert() {
    const typed = amount.trim();
    if (!typed) return;
    setAmount(typed.startsWith("-") ? typed.slice(1) : "-" + typed);
  }

  return (
    <div className={styles.panel}>
      <div className={styles.form}>
        <input
          className={styles.amount} value={amount} inputMode="decimal"
          placeholder="Amount" aria-label="Amount"
          onChange={(event) => setAmount(event.target.value)}
        />
        <button type="button" className={styles.flip} onClick={invert}
                title="Record this as money taken back out">
          ±
        </button>
        <input
          className={styles.date} type="date" value={date} max={today()}
          aria-label="Date"
          onChange={(event) => setDate(event.target.value)}
        />
        <input
          className={styles.note} value={note} maxLength={255}
          placeholder="Note (optional)" aria-label="Note"
          onChange={(event) => setNote(event.target.value)}
        />
        <Button small disabled={!amount.trim() || add.isPending}
                onClick={() => add.mutate()}>
          {add.isPending ? "Adding…" : "Add"}
        </Button>
      </div>

      {(fields.amount || fields.date) && (
        <p className={styles.error}>{fields.amount ?? fields.date}</p>
      )}
      {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}

      {contributions.isPending ? (
        <Loading what="contributions" />
      ) : items.length ? (
        <ul className={styles.list}>
          {items.map((one) => {
            const value = toMinor(one.amount);
            return (
              <li key={one.id} className={styles.row}>
                <span className={styles.when}>{one.date}</span>
                <span className={value < 0 ? styles.out : styles.in}>
                  {formatSigned(value)}
                </span>
                <span className={styles.what}>{one.note || "—"}</span>
                <button
                  type="button" className={styles.drop}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(one.id)}
                  aria-label={`Remove the contribution of ${one.amount}`}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <Empty>Nothing put towards this yet.</Empty>
      )}
    </div>
  );
}
