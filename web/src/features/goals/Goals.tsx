import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { Goal } from "../../lib/api";
import { formatMoney, formatPercent, toMinor } from "../../lib/money";
import {
  Button, Card, Confirm, Empty, Field, Form, FormActions, Loading, Notice,
  Picker, RowActions,
} from "../../ui";
import { Contributions } from "./Contributions";
import styles from "./Goals.module.css";

interface Draft {
  id: number | null;
  name: string;
  target: string;
  target_date: string;
  account_id: string;
}

const blank = (): Draft => ({
  id: null, name: "", target: "", target_date: "", account_id: "",
});

/** How far off the target a goal is, and whether its deadline has passed. */
function progressOf(goal: Goal) {
  const saved = toMinor(goal.saved);
  const target = toMinor(goal.target);
  return {
    saved,
    target,
    left: target - saved,
    reached: saved >= target,
    // Clamped for the bar only. The figures beside it are never clamped,
    // because overshooting a goal is worth seeing rather than hiding.
    width: target <= 0 ? 0 : Math.min(100, Math.max(0, (saved / target) * 100)),
    overdue: goal.target_date !== null && !(saved >= target)
             && goal.target_date < new Date().toISOString().slice(0, 10),
  };
}

function readableDate(date: string): string {
  return new Date(date + "T00:00:00").toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
  });
}

/**
 * Savings goals.
 *
 * What is saved is summed by the server from the contributions, never
 * stored, so nothing here can show a total the contributions do not add up
 * to. The same rule as account balances.
 */
export function Goals() {
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft>(blank);
  const [open, setOpen] = useState<number | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [showDone, setShowDone] = useState(false);

  const goals = useQuery({
    queryKey: ["goals", showDone],
    queryFn: () => api.goals(showDone),
  });
  const accounts = useQuery({
    queryKey: ["accounts", false],
    queryFn: () => api.accounts(false),
  });
  const items = goals.data?.items ?? [];

  const refresh = () => client.invalidateQueries({ queryKey: ["goals"] });

  const save = useMutation({
    mutationFn: (body: Draft) => {
      const payload = {
        name: body.name,
        target: body.target,
        // Empty strings would fail validation as dates and ids; both fields
        // are genuinely optional, so an unset one is simply not sent.
        target_date: body.target_date || undefined,
        account_id: body.account_id ? Number(body.account_id) : undefined,
      };
      return body.id === null
        ? api.addGoal(payload).then(() => undefined)
        : api.editGoal(body.id, payload);
    },
    onSuccess: () => { refresh(); setDraft(blank()); },
  });

  const archive = useMutation({
    mutationFn: (goal: Goal) => api.archiveGoal(goal.id, !goal.archived),
    onSuccess: refresh,
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteGoal(id),
    onSuccess: () => { refresh(); setConfirming(null); setOpen(null); },
  });

  function edit(goal: Goal) {
    setDraft({
      id: goal.id, name: goal.name, target: goal.target,
      target_date: goal.target_date ?? "",
      account_id: goal.account_id === null ? "" : String(goal.account_id),
    });
    save.reset();
  }

  const failure = save.error instanceof ApiError ? save.error : null;
  const fields = failure?.isValidation ? failure.fields : {};

  return (
    <>
      <Card title={draft.id === null ? "Set a goal" : `Editing ${draft.name || "…"}`}>
        <Form>
          <Field
            label="Goal" name="name" maxLength={60} value={draft.name}
            error={fields.name} placeholder="New laptop"
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <Field
            label="Target" name="target" numeric value={draft.target}
            error={fields.target} placeholder="40000.00"
            onChange={(event) => setDraft({ ...draft, target: event.target.value })}
          />
          <Field
            label="By (optional)" name="target_date" type="date"
            value={draft.target_date} error={fields.target_date}
            onChange={(event) =>
              setDraft({ ...draft, target_date: event.target.value })}
          />
          <Picker
            label="Kept in (optional)" name="account_id" value={draft.account_id}
            error={fields.account_id}
            onChange={(event) =>
              setDraft({ ...draft, account_id: event.target.value })}
          >
            <option value="">Not decided</option>
            {(accounts.data?.items ?? []).map((one) => (
              <option key={one.id} value={one.id}>{one.name}</option>
            ))}
          </Picker>
          <FormActions>
            <Button
              onClick={() => save.mutate(draft)}
              disabled={!draft.name.trim() || !draft.target.trim() || save.isPending}
            >
              {save.isPending ? "Saving…" : draft.id === null ? "Set" : "Save"}
            </Button>
            {draft.id !== null && (
              <Button kind="quiet" onClick={() => { setDraft(blank()); save.reset(); }}>
                Cancel
              </Button>
            )}
          </FormActions>
        </Form>

        <p className={styles.explain}>
          Money towards a goal is recorded here, not taken from an account.
          Deciding that 5,000 of what is already in savings is for the laptop
          moves nothing — so nothing should leave your balance to say so.
        </p>

        {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
        {save.isSuccess && <Notice ok>Saved.</Notice>}
      </Card>

      <div className={styles.gap} />

      <Card title="Goals">
        <label className={styles.toggle}>
          <input
            type="checkbox" checked={showDone}
            onChange={(event) => setShowDone(event.target.checked)}
          />
          Show ones put aside
        </label>

        {goals.isPending && !goals.data ? (
          <Loading what="your goals" />
        ) : goals.error ? (
          <Notice>{(goals.error as Error).message}</Notice>
        ) : items.length ? (
          <ul className={styles.list}>
            {items.map((goal) => {
              const progress = progressOf(goal);
              return (
                <li key={goal.id} className={styles.goal}>
                  <div className={styles.head}>
                    <span className={styles.name}>
                      {goal.name}
                      {goal.archived && <span className={styles.aside}>put aside</span>}
                    </span>
                    <span className={styles.figures}>
                      <strong className={progress.reached ? styles.reached : undefined}>
                        {formatMoney(progress.saved)}
                      </strong>
                      <span className={styles.of}>of {formatMoney(progress.target)}</span>
                    </span>
                  </div>

                  <div
                    className={styles.track} role="img"
                    aria-label={`${formatPercent(progress.saved, progress.target)} saved`}
                  >
                    <div
                      className={progress.reached ? styles.barDone : styles.bar}
                      style={{ width: `${progress.width}%` }}
                    />
                  </div>

                  <div className={styles.meta}>
                    <span>
                      {progress.reached
                        ? "Reached"
                        : `${formatMoney(progress.left)} to go`}
                      {" · "}
                      {formatPercent(progress.saved, progress.target)}
                    </span>
                    {goal.target_date && (
                      <span className={progress.overdue ? styles.overdue : undefined}>
                        by {readableDate(goal.target_date)}
                      </span>
                    )}
                    {goal.account && <span>in {goal.account}</span>}
                    <span className={styles.spacer} />
                    {confirming === goal.id ? (
                      <Confirm
                        busy={remove.isPending}
                        onYes={() => remove.mutate(goal.id)}
                        onNo={() => setConfirming(null)}
                      />
                    ) : (
                      <RowActions>
                        <Button kind="quiet" small
                                onClick={() => setOpen(open === goal.id ? null : goal.id)}>
                          {open === goal.id ? "Hide" : `Contributions (${goal.contributions})`}
                        </Button>
                        <Button kind="quiet" small onClick={() => edit(goal)}>Edit</Button>
                        <Button kind="quiet" small onClick={() => archive.mutate(goal)}>
                          {goal.archived ? "Bring back" : "Put aside"}
                        </Button>
                        <Button kind="danger" small
                                onClick={() => setConfirming(goal.id)}>
                          Delete
                        </Button>
                      </RowActions>
                    )}
                  </div>

                  {open === goal.id && <Contributions goalId={goal.id} />}
                </li>
              );
            })}
          </ul>
        ) : (
          <Empty>No goals yet.</Empty>
        )}
      </Card>
    </>
  );
}
