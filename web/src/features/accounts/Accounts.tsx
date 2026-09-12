import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { AccountKind, AccountRow } from "../../lib/api";
import { formatMoney, moneyTone, toMinor } from "../../lib/money";
import {
  Button, Card, Empty, Field, Form, FormActions, Loading, Notice, PageHead,
  Picker, RowActions, Stat, StatRow, Table, cell, row as rowStyle,
} from "../../ui";
import styles from "./Accounts.module.css";

const KINDS: AccountKind[] = ["Bank", "Cash", "Card", "Wallet", "Other"];

interface Draft {
  id: number | null;
  name: string;
  kind: AccountKind;
  opening_balance: string;
}

const blank = (): Draft => ({ id: null, name: "", kind: "Bank", opening_balance: "" });

interface TransferDraft {
  from: string;
  to: string;
  amount: string;
  date: string;
  description: string;
}

function today(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

const blankTransfer = (): TransferDraft => ({
  from: "", to: "", amount: "", date: today(), description: "",
});

/**
 * Accounts: where the money actually is.
 *
 * Every balance on this screen is computed by the server from the rows
 * behind it, never stored, so nothing here can show a figure that the
 * ledger would disagree with.
 */
export function Accounts() {
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft>(blank);
  const [moving, setMoving] = useState<TransferDraft | null>(null);
  const [removing, setRemoving] = useState<AccountRow | null>(null);
  const [target, setTarget] = useState("");
  const [showClosed, setShowClosed] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  // Keyed by whether closed accounts are included, so the toggle is instant
  // the second time and the two lists never overwrite each other.
  const accounts = useQuery({
    queryKey: ["accounts", showClosed],
    queryFn: () => api.accounts(showClosed),
  });
  const items = accounts.data?.items ?? [];
  const live = useMemo(() => items.filter((one) => !one.archived), [items]);

  const usage = useQuery({
    queryKey: ["account-usage", removing?.id],
    queryFn: () => api.accountUsage(removing!.id),
    enabled: removing !== null,
  });

  // A balance is derived from transactions, so anything that writes one
  // moves this screen -- and moving money between accounts changes the
  // ledger, which every other screen reads.
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["accounts"] });
    client.invalidateQueries({ queryKey: ["transactions"] });
    client.invalidateQueries({ queryKey: ["report"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const save = useMutation({
    mutationFn: (body: Draft) => {
      const payload = {
        name: body.name,
        kind: body.kind,
        opening_balance: body.opening_balance.trim() || "0",
      };
      return body.id === null
        ? api.addAccount(payload).then(() => undefined)
        : api.editAccount(body.id, payload);
    },
    onSuccess: () => { refresh(); setDraft(blank()); },
  });

  const archive = useMutation({
    mutationFn: (account: AccountRow) =>
      api.archiveAccount(account.id, !account.archived),
    onSuccess: refresh,
  });

  const send = useMutation({
    mutationFn: (body: TransferDraft) => api.transfer({
      from_account_id: Number(body.from),
      to_account_id: Number(body.to),
      amount: body.amount,
      date: body.date,
      description: body.description || undefined,
    }),
    onSuccess: () => { refresh(); setMoving(blankTransfer()); },
  });

  const remove = useMutation({
    mutationFn: () =>
      api.deleteAccount(removing!.id, target === "" ? undefined : Number(target)),
    onSuccess: () => { refresh(); closePanel(); },
  });

  function closePanel() {
    setRemoving(null);
    setTarget("");
    remove.reset();
  }

  /** Open the delete panel and take the reader to it, since it sits below
      a list that can run past the fold. */
  function beginDelete(account: AccountRow) {
    closePanel();
    setRemoving(account);
    requestAnimationFrame(() =>
      panel.current?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }

  function edit(account: AccountRow) {
    setDraft({
      id: account.id, name: account.name, kind: account.kind,
      opening_balance: account.opening_balance,
    });
    save.reset();
  }

  const failure = save.error instanceof ApiError ? save.error : null;
  const fields = failure?.isValidation ? failure.fields : {};
  const transferFailure = send.error instanceof ApiError ? send.error : null;
  const transferFields = transferFailure?.isValidation ? transferFailure.fields : {};
  const removeFailure = remove.error instanceof ApiError ? remove.error : null;

  // Everything, across every account. Archived ones are included when they
  // are on screen: a closed account with money still in it is a fact, and
  // hiding it from the total would make the total wrong.
  const total = items.reduce((sum, one) => sum + toMinor(one.balance), 0);
  const held = live.length;

  const inUse = (usage.data?.transactions ?? 0) > 0;
  const candidates = live.filter((one) => one.id !== removing?.id);

  return (
    <>
      <PageHead
        title="Accounts"
        subtitle="Where the money is. Every balance is worked out from the rows, not stored."
      >
        <label className={styles.toggle}>
          <input
            type="checkbox" checked={showClosed}
            onChange={(event) => setShowClosed(event.target.checked)}
          />
          Show closed
        </label>
      </PageHead>

      <StatRow>
        <Stat label="Across every account" value={formatMoney(total)}
              tone={moneyTone(total)}
              note={`${held} open account${held === 1 ? "" : "s"}`} />
        <Stat
          label="Biggest balance"
          value={live.length
            ? formatMoney(Math.max(...live.map((one) => toMinor(one.balance))))
            : "—"}
          note={live.length
            ? live.reduce((best, one) =>
                toMinor(one.balance) > toMinor(best.balance) ? one : best).name
            : undefined}
        />
        <Stat
          label="In the red"
          value={String(items.filter((one) => toMinor(one.balance) < 0).length)}
          note="accounts below zero"
        />
      </StatRow>

      <Card title={draft.id === null ? "Open an account" : `Editing ${draft.name || "…"}`}>
        <Form>
          <Field
            label="Name" name="name" maxLength={60} value={draft.name}
            error={fields.name} placeholder="Current account"
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <Picker
            label="Kind" name="kind" value={draft.kind} error={fields.kind}
            onChange={(event) =>
              setDraft({ ...draft, kind: event.target.value as AccountKind })}
          >
            {KINDS.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
          </Picker>
          <Field
            label="Opening balance" name="opening_balance" numeric
            value={draft.opening_balance} error={fields.opening_balance}
            placeholder="0.00"
            onChange={(event) =>
              setDraft({ ...draft, opening_balance: event.target.value })}
          />
          <FormActions>
            <Button
              onClick={() => save.mutate(draft)}
              disabled={draft.name.trim() === "" || save.isPending}
            >
              {save.isPending ? "Saving…" : draft.id === null ? "Open" : "Save"}
            </Button>
            {draft.id !== null && (
              <Button kind="quiet" onClick={() => { setDraft(blank()); save.reset(); }}>
                Cancel
              </Button>
            )}
          </FormActions>
        </Form>

        <p className={styles.explain}>
          What was in it before this ledger starts. A card can open owing money —
          enter a negative figure.
        </p>

        {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
        {save.isSuccess && <Notice ok>Saved.</Notice>}
      </Card>

      <div className={styles.gap} />

      <Card title="All accounts" flush>
        {accounts.isPending && !accounts.data ? (
          <Loading what="your accounts" shape="table" rows={3}
                   columns={["55%", "40%", "#55%", "#35%", "#60%", "30%"]} />
        ) : accounts.error ? (
          <Notice>{(accounts.error as Error).message}</Notice>
        ) : items.length ? (
          <Table
            head={
              <tr>
                <th>Name</th>
                <th>Kind</th>
                <th className={cell.numeric}>Opening</th>
                <th className={cell.numeric}>Rows</th>
                <th className={cell.numeric}>Balance</th>
                <th />
              </tr>
            }
          >
            {items.map((account) => {
              const balance = toMinor(account.balance);
              return (
                <tr
                  key={account.id}
                  className={
                    account.id === draft.id || account.id === removing?.id
                      ? rowStyle.editing : undefined
                  }
                >
                  <td className={cell.primary}>
                    {account.name}
                    {account.archived && <span className={styles.closed}>closed</span>}
                  </td>
                  <td className={styles.kind}>{account.kind}</td>
                  <td className={cell.numeric + " " + styles.quiet}>
                    {formatMoney(toMinor(account.opening_balance))}
                  </td>
                  <td className={cell.numeric + " " + styles.quiet}>
                    {account.transactions}
                  </td>
                  <td className={
                    cell.numeric + " " + (balance < 0 ? cell.debit : "")
                  }>
                    {formatMoney(balance)}
                  </td>
                  <td>
                    <RowActions>
                      <Button kind="quiet" small onClick={() => edit(account)}>Edit</Button>
                      <Button kind="quiet" small
                              onClick={() => archive.mutate(account)}>
                        {account.archived ? "Reopen" : "Close"}
                      </Button>
                      <Button kind="danger" small onClick={() => beginDelete(account)}>
                        Delete
                      </Button>
                    </RowActions>
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : (
          <Empty>No accounts yet.</Empty>
        )}
      </Card>

      <div className={styles.gap} />

      <Card title="Move money between accounts">
        {live.length < 2 ? (
          <Empty>
            A transfer needs two open accounts. Open another one above.
          </Empty>
        ) : moving === null ? (
          <>
            <p className={styles.explain}>
              A transfer is written as two rows — money leaving one account and
              arriving in the other — so each account's balance is right on its
              own. Neither row counts as income or spending, because nothing was
              earned or spent.
            </p>
            <FormActions>
              <Button onClick={() => setMoving(blankTransfer())}>Move money</Button>
            </FormActions>
          </>
        ) : (
          <>
            <Form>
              <Picker
                label="Out of" name="from" value={moving.from}
                error={transferFields.from_account_id}
                onChange={(event) => setMoving({ ...moving, from: event.target.value })}
              >
                <option value="">Choose…</option>
                {live.map((one) => (
                  <option key={one.id} value={one.id}>
                    {one.name} — {formatMoney(toMinor(one.balance))}
                  </option>
                ))}
              </Picker>
              <Picker
                label="Into" name="to" value={moving.to}
                error={transferFields.to_account_id}
                onChange={(event) => setMoving({ ...moving, to: event.target.value })}
              >
                <option value="">Choose…</option>
                {/* The source is left out rather than shown and refused: a
                    transfer to the same account is not a slip worth an error
                    message, it is simply not an option. */}
                {live.filter((one) => String(one.id) !== moving.from).map((one) => (
                  <option key={one.id} value={one.id}>
                    {one.name} — {formatMoney(toMinor(one.balance))}
                  </option>
                ))}
              </Picker>
              <Field
                label="Amount" name="amount" numeric value={moving.amount}
                error={transferFields.amount} placeholder="1000.00"
                onChange={(event) => setMoving({ ...moving, amount: event.target.value })}
              />
              <Field
                label="Date" name="date" type="date" value={moving.date}
                error={transferFields.date}
                onChange={(event) => setMoving({ ...moving, date: event.target.value })}
              />
              <Field
                label="Note" name="description" maxLength={255}
                value={moving.description} error={transferFields.description}
                placeholder="Cash withdrawal"
                onChange={(event) =>
                  setMoving({ ...moving, description: event.target.value })}
              />
              <FormActions>
                <Button
                  disabled={!moving.from || !moving.to || !moving.amount.trim()
                            || send.isPending}
                  onClick={() => send.mutate(moving)}
                >
                  {send.isPending ? "Moving…" : "Move"}
                </Button>
                <Button kind="quiet" onClick={() => { setMoving(null); send.reset(); }}>
                  Cancel
                </Button>
              </FormActions>
            </Form>
            {transferFailure && !transferFailure.isValidation && (
              <Notice>{transferFailure.message}</Notice>
            )}
            {send.isSuccess && <Notice ok>Moved.</Notice>}
          </>
        )}
      </Card>

      {removing && (
        <div ref={panel}>
          <div className={styles.gap} />
          <Card title={`Deleting ${removing.name}`}>
            {usage.isPending ? (
              <Loading what="what sits here" />
            ) : inUse ? (
              <>
                <p className={styles.explain}>
                  {usage.data!.transactions} transaction
                  {usage.data!.transactions === 1 ? "" : "s"} sit on {removing.name}
                  {usage.data!.transfers > 0 &&
                    `, ${usage.data!.transfers} of them ${usage.data!.transfers === 1
                      ? "a leg of a transfer" : "legs of transfers"}`}
                  . They have to go somewhere — nothing is deleted with the account.
                </p>
                {candidates.length ? (
                  <Form>
                    <Picker
                      label="Move them to" name="reassign_to" value={target}
                      error={removeFailure?.fields.reassign_to}
                      onChange={(event) => setTarget(event.target.value)}
                    >
                      <option value="">Choose…</option>
                      {candidates.map((one) => (
                        <option key={one.id} value={one.id}>{one.name}</option>
                      ))}
                    </Picker>
                    <FormActions>
                      <Button
                        kind="danger"
                        disabled={target === "" || remove.isPending}
                        onClick={() => remove.mutate()}
                      >
                        {remove.isPending ? "Moving…" : "Move and delete"}
                      </Button>
                      <Button kind="quiet" onClick={closePanel}>Cancel</Button>
                    </FormActions>
                  </Form>
                ) : (
                  <Notice>
                    There is no other open account to move them to. Open one first.
                  </Notice>
                )}
                {usage.data!.transfers > 0 && (
                  <p className={styles.explain}>
                    A transfer whose two halves end up on the same account is no
                    longer a transfer. Those rows stay — they are still real
                    movements of money — but stop being shown as a pair.
                  </p>
                )}
              </>
            ) : (
              <>
                <p className={styles.explain}>
                  Nothing sits on {removing.name}, so it can go on its own.
                </p>
                <FormActions>
                  <Button kind="danger" disabled={remove.isPending}
                          onClick={() => remove.mutate()}>
                    {remove.isPending ? "Deleting…" : "Delete"}
                  </Button>
                  <Button kind="quiet" onClick={closePanel}>Cancel</Button>
                </FormActions>
              </>
            )}
            {removeFailure && !removeFailure.isValidation && (
              <Notice>{removeFailure.message}</Notice>
            )}
            <p className={styles.explain}>
              Closing an account instead keeps its history and stops offering it
              for new rows.
            </p>
          </Card>
        </div>
      )}
    </>
  );
}
