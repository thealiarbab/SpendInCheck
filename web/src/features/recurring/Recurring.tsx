import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { Cadence, Category, RecurringRule } from "../../lib/api";
import { formatMoney, toMinor } from "../../lib/money";
import {
  Button, Card, Confirm, Empty, Field, Form, FormActions, Loading, Notice,
  Picker, RowActions, Table, Tag, cell, row as rowStyle,
} from "../../ui";
import styles from "./Recurring.module.css";

const CADENCES: { value: Cadence; label: string }[] = [
  { value: "monthly", label: "Every month" },
  { value: "weekly", label: "Every week" },
  { value: "yearly", label: "Every year" },
];

interface Draft {
  id: number | null;
  description: string;
  category_id: string;
  account_id: string;
  amount: string;
  cadence: Cadence;
  next_run_on: string;
  ends_on: string;
}

function today(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

const blank = (): Draft => ({
  id: null, description: "", category_id: "", account_id: "", amount: "",
  cadence: "monthly", next_run_on: today(), ends_on: "",
});

function readableDate(date: string): string {
  return new Date(date + "T00:00:00").toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
  });
}

/**
 * Rules that write transactions on a schedule.
 *
 * A rule is a template, not a container: it writes ordinary rows that can
 * be edited, deleted and reported on like any other. Changing a rule never
 * rewrites what it already wrote, which is why the table shows how many
 * rows each has produced rather than pretending the rule is the history.
 */
export function Recurring({ categories }: { categories: Category[] }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank);
  const [confirming, setConfirming] = useState<number | null>(null);

  // Not fetched until the card is opened. Most visits to the ledger are not
  // about recurring rules, and a request nobody asked for is a request
  // somebody waits behind.
  const rules = useQuery({
    queryKey: ["recurring"],
    queryFn: api.recurring,
    enabled: open,
  });
  const accounts = useQuery({
    queryKey: ["accounts", false],
    queryFn: () => api.accounts(false),
    enabled: open,
  });
  const items = rules.data?.items ?? [];

  const chosen = categories.find((one) => String(one.id) === draft.category_id);

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["recurring"] });
    client.invalidateQueries({ queryKey: ["transactions"] });
    client.invalidateQueries({ queryKey: ["report"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
    client.invalidateQueries({ queryKey: ["accounts"] });
  };

  const save = useMutation({
    mutationFn: (body: Draft) => {
      const payload = {
        description: body.description,
        category_id: Number(body.category_id),
        amount: body.amount,
        // The category decides the direction, exactly as on the ledger
        // form. A rule that could disagree with its category would file
        // salary as an expense.
        type: chosen?.type,
        cadence: body.cadence,
        next_run_on: body.next_run_on,
        ends_on: body.ends_on || undefined,
        account_id: body.account_id ? Number(body.account_id) : undefined,
      };
      return body.id === null
        ? api.addRule(payload).then(() => undefined)
        : api.editRule(body.id, payload);
    },
    onSuccess: () => { refresh(); setDraft(blank()); },
  });

  const pause = useMutation({
    mutationFn: (rule: RecurringRule) => api.pauseRule(rule.id, !rule.paused),
    onSuccess: refresh,
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteRule(id),
    onSuccess: () => { refresh(); setConfirming(null); },
  });

  const run = useMutation({ mutationFn: api.runRules, onSuccess: refresh });

  function edit(rule: RecurringRule) {
    setDraft({
      id: rule.id,
      description: rule.description,
      category_id: String(rule.category_id),
      account_id: rule.account_id === null ? "" : String(rule.account_id),
      amount: rule.amount,
      cadence: rule.cadence,
      next_run_on: rule.next_run_on,
      ends_on: rule.ends_on ?? "",
    });
    save.reset();
  }

  const failure = save.error instanceof ApiError ? save.error : null;
  const fields = failure?.isValidation ? failure.fields : {};
  const due = items.filter((one) => !one.paused && one.next_run_on <= today());

  if (!open) {
    return (
      <Card>
        <div className={styles.closed}>
          <div>
            <strong className={styles.title}>Repeating transactions</strong>
            <p className={styles.blurb}>
              Rent, salary, the subscription you would rather not retype twelve
              times a year.
            </p>
          </div>
          <Button kind="quiet" onClick={() => setOpen(true)}>Set up</Button>
        </div>
      </Card>
    );
  }

  return (
    <Card title={draft.id === null ? "Repeating transactions"
                                   : `Editing ${draft.description || "…"}`}>
      <Form>
        <Field
          label="Description" name="description" maxLength={255}
          value={draft.description} error={fields.description}
          placeholder="Rent"
          onChange={(event) =>
            setDraft({ ...draft, description: event.target.value })}
        />
        <Picker
          label="Category" name="category_id" value={draft.category_id}
          error={fields.category_id}
          onChange={(event) =>
            setDraft({ ...draft, category_id: event.target.value })}
        >
          <option value="">Choose…</option>
          {categories.map((one) => (
            <option key={one.id} value={one.id}>{one.name}</option>
          ))}
        </Picker>
        <Field
          label="Amount" name="amount" numeric value={draft.amount}
          error={fields.amount} placeholder="15000.00"
          onChange={(event) => setDraft({ ...draft, amount: event.target.value })}
        />
        <Picker
          label="How often" name="cadence" value={draft.cadence}
          error={fields.cadence}
          onChange={(event) =>
            setDraft({ ...draft, cadence: event.target.value as Cadence })}
        >
          {CADENCES.map((one) => (
            <option key={one.value} value={one.value}>{one.label}</option>
          ))}
        </Picker>
        <Field
          label="Starting" name="next_run_on" type="date" value={draft.next_run_on}
          error={fields.next_run_on}
          onChange={(event) =>
            setDraft({ ...draft, next_run_on: event.target.value })}
        />
        <Field
          label="Until (optional)" name="ends_on" type="date" value={draft.ends_on}
          error={fields.ends_on}
          onChange={(event) => setDraft({ ...draft, ends_on: event.target.value })}
        />
        <Picker
          label="From account" name="account_id" value={draft.account_id}
          error={fields.account_id}
          onChange={(event) =>
            setDraft({ ...draft, account_id: event.target.value })}
        >
          <option value="">Default account</option>
          {(accounts.data?.items ?? []).map((one) => (
            <option key={one.id} value={one.id}>{one.name}</option>
          ))}
        </Picker>
        <FormActions>
          <Button
            onClick={() => save.mutate(draft)}
            disabled={!draft.description.trim() || !chosen || !draft.amount.trim()
                      || save.isPending}
          >
            {save.isPending ? "Saving…" : draft.id === null ? "Add rule" : "Save"}
          </Button>
          {draft.id !== null && (
            <Button kind="quiet" onClick={() => { setDraft(blank()); save.reset(); }}>
              Cancel
            </Button>
          )}
          {draft.id === null && (
            <Button kind="quiet" onClick={() => setOpen(false)}>Close</Button>
          )}
        </FormActions>
      </Form>

      {chosen && (
        <p className={styles.derived}>
          Files as <Tag kind={chosen.type} />, because that is what{" "}
          {chosen.name} is.
        </p>
      )}

      {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
      {save.isSuccess && <Notice ok>Saved.</Notice>}

      <div className={styles.gap} />

      {rules.isPending ? (
        <Loading what="your rules" />
      ) : rules.error ? (
        <Notice>{(rules.error as Error).message}</Notice>
      ) : items.length ? (
        <>
          <Table
            head={
              <tr>
                <th>What</th>
                <th>How often</th>
                <th>Next</th>
                <th className={cell.numeric}>Amount</th>
                <th className={cell.numeric}>Written</th>
                <th />
              </tr>
            }
          >
            {items.map((rule) => (
              <tr key={rule.id}
                  className={rule.id === draft.id ? rowStyle.editing : undefined}>
                <td className={cell.primary}>
                  {rule.description}
                  <span className={styles.where}>
                    {rule.category}{rule.account ? ` · ${rule.account}` : ""}
                  </span>
                </td>
                <td className={styles.quiet}>
                  {CADENCES.find((one) => one.value === rule.cadence)?.label}
                  {rule.ends_on && (
                    <span className={styles.where}>
                      until {readableDate(rule.ends_on)}
                    </span>
                  )}
                </td>
                <td className={styles.quiet}>
                  {rule.paused
                    ? <span className={styles.paused}>paused</span>
                    : readableDate(rule.next_run_on)}
                </td>
                <td className={cell.numeric
                    + (rule.type === "Income" ? " " + cell.credit : "")}>
                  {formatMoney(toMinor(rule.amount))}
                </td>
                <td className={cell.numeric + " " + styles.quiet}>{rule.written}</td>
                <td>
                  {confirming === rule.id ? (
                    <Confirm
                      busy={remove.isPending}
                      onYes={() => remove.mutate(rule.id)}
                      onNo={() => setConfirming(null)}
                    />
                  ) : (
                    <RowActions>
                      <Button kind="quiet" small onClick={() => edit(rule)}>Edit</Button>
                      <Button kind="quiet" small onClick={() => pause.mutate(rule)}>
                        {rule.paused ? "Resume" : "Pause"}
                      </Button>
                      <Button kind="danger" small
                              onClick={() => setConfirming(rule.id)}>
                        Delete
                      </Button>
                    </RowActions>
                  )}
                </td>
              </tr>
            ))}
          </Table>

          <div className={styles.footer}>
            <p className={styles.explain}>
              Rules post on their own each day. Changing one never rewrites what
              it has already written — the rent that went up in August is a fact
              about August.
            </p>
            {due.length > 0 && (
              <Button kind="quiet" disabled={run.isPending}
                      onClick={() => run.mutate()}>
                {run.isPending ? "Posting…"
                  : `Post ${due.length} due now`}
              </Button>
            )}
          </div>

          {run.isSuccess && (
            <Notice ok>
              {run.data.transactions === 0
                ? "Nothing was due."
                : `Wrote ${run.data.transactions} transaction${
                    run.data.transactions === 1 ? "" : "s"}.`}
            </Notice>
          )}
        </>
      ) : (
        <Empty>No repeating transactions yet.</Empty>
      )}
    </Card>
  );
}
