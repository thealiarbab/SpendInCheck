import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";
import type { Category } from "../../lib/api";
import {
  Button, Card, Empty, Field, Form, FormActions, Loading, Notice, PageHead,
  Picker, RowActions, Table, Tag, row as rowStyle,
} from "../../ui";
import { TagList } from "../tags/TagList";
import styles from "./Categories.module.css";

interface Draft {
  id: number | null;
  name: string;
  type: "Income" | "Expense";
}

const blank = (): Draft => ({ id: null, name: "", type: "Expense" });

/**
 * Categories: the vocabulary transactions and budgets both point at.
 *
 * The Jinja page could only add. Renaming and deleting are new here, and
 * deleting is the only destructive thing in the app that can take other
 * rows with it -- so it asks what points at the category before offering
 * the choice, and says what will happen to it.
 */
export function Categories() {
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft>(blank);
  const [removing, setRemoving] = useState<Category | null>(null);
  const [target, setTarget] = useState("");
  const panel = useRef<HTMLDivElement>(null);

  const categories = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const items = categories.data?.items ?? [];

  // What points at the category being deleted. Asked for only once the
  // reader has actually clicked delete: it is one query per category and
  // most of them will never be deleted.
  const usage = useQuery({
    queryKey: ["category-usage", removing?.id],
    queryFn: () => api.categoryUsage(removing!.id),
    enabled: removing !== null,
  });

  // A category rename shows up in every list that names one, and a delete
  // moves transactions between categories, so both reports move too.
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["categories"] });
    client.invalidateQueries({ queryKey: ["transactions"] });
    client.invalidateQueries({ queryKey: ["budgets"] });
    client.invalidateQueries({ queryKey: ["report"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const save = useMutation({
    mutationFn: (body: Draft) =>
      body.id === null
        ? api.addCategory(body.name, body.type)
        : api.renameCategory(body.id, body.name, body.type),
    onSuccess: () => {
      refresh();
      setDraft(blank());
    },
  });

  const remove = useMutation({
    mutationFn: () =>
      api.deleteCategory(removing!.id, target === "" ? undefined : Number(target)),
    onSuccess: () => {
      refresh();
      close();
    },
  });

  function close() {
    setRemoving(null);
    setTarget("");
    remove.reset();
  }

  /** Open the delete panel, and take the reader to it.

      The panel sits below a list that can run past the fold, so opening it
      without moving looks like the button did nothing. */
  function beginDelete(category: Category) {
    close();
    setRemoving(category);
    requestAnimationFrame(() =>
      panel.current?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }

  function edit(category: Category) {
    setDraft({ id: category.id, name: category.name, type: category.type });
    save.reset();
  }

  const failure = save.error instanceof ApiError ? save.error : null;
  const fields = failure?.isValidation ? failure.fields : {};
  const removeFailure = remove.error instanceof ApiError ? remove.error : null;

  const inUse = (usage.data?.transactions ?? 0) + (usage.data?.budgets ?? 0) > 0;
  // Only a category of the same kind can take the rows: a transaction
  // carries its own Income/Expense marker, and the server refuses a
  // mismatch, so offering one here would only produce a rejected click.
  const candidates = items.filter(
    (one) => removing !== null && one.id !== removing.id && one.type === removing.type);

  return (
    <>
      <PageHead
        title="Categories and tags"
        subtitle={"A category says what a transaction is, and there is exactly one. "
                  + "Tags say everything else, and there can be none."}
      />

      <Card title={draft.id === null ? "Add a category" : `Renaming ${draft.name || "…"}`}>
        <Form>
          <Field
            label="Name" name="name" maxLength={50} value={draft.name}
            error={fields.name} placeholder="Groceries"
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <Picker
            label="Type" name="type" value={draft.type} error={fields.type}
            onChange={(event) =>
              setDraft({ ...draft, type: event.target.value as Draft["type"] })}
          >
            <option value="Expense">Expense</option>
            <option value="Income">Income</option>
          </Picker>
          <FormActions>
            <Button
              onClick={() => save.mutate(draft)}
              disabled={draft.name.trim() === "" || save.isPending}
            >
              {save.isPending ? "Saving…" : draft.id === null ? "Add" : "Save"}
            </Button>
            {draft.id !== null && (
              <Button kind="quiet" onClick={() => { setDraft(blank()); save.reset(); }}>
                Cancel
              </Button>
            )}
          </FormActions>
        </Form>

        {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
        {save.isSuccess && <Notice ok>Saved.</Notice>}
      </Card>

      <div style={{ height: "var(--space-5)" }} />

      <Card title="All categories" flush>
        {categories.isPending && !categories.data ? (
          <Loading what="categories" />
        ) : categories.error ? (
          <Notice>{(categories.error as Error).message}</Notice>
        ) : items.length ? (
          <Table
            head={<tr><th>Name</th><th>Type</th><th /></tr>}
          >
            {items.map((category) => (
              <tr
                key={category.id}
                className={
                  category.id === draft.id || category.id === removing?.id
                    ? rowStyle.editing : undefined
                }
              >
                <td>{category.name}</td>
                <td><Tag kind={category.type} /></td>
                <td>
                  <RowActions>
                    <Button kind="quiet" small onClick={() => edit(category)}>Rename</Button>
                    <Button kind="danger" small onClick={() => beginDelete(category)}>
                      Delete
                    </Button>
                  </RowActions>
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No categories yet.</Empty>
        )}
      </Card>

      {removing && (
        <div ref={panel}>
        <Card title={`Deleting ${removing.name}`}>
          {usage.isPending ? (
            <Loading what="what points here" />
          ) : inUse ? (
            <>
              <p className={styles.explain}>
                {usage.data!.transactions} transaction
                {usage.data!.transactions === 1 ? "" : "s"} and {usage.data!.budgets} budget
                {usage.data!.budgets === 1 ? "" : "s"} are filed under {removing.name}.
                They have to go somewhere — nothing is deleted with the category.
              </p>
              {candidates.length ? (
                <Form>
                  <Picker
                    label={`Move them to`} name="reassign_to" value={target}
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
                    <Button kind="quiet" onClick={close}>Cancel</Button>
                  </FormActions>
                </Form>
              ) : (
                <Notice>
                  There is no other {removing.type.toLowerCase()} category to move them
                  to. Add one first, then delete this.
                </Notice>
              )}
              <p className={styles.explain}>
                A budget landing on a month the other category already has one for is
                added to it, since one category has one budget per month.
              </p>
            </>
          ) : (
            <>
              <p className={styles.explain}>
                Nothing is filed under {removing.name}, so it can go on its own.
              </p>
              <FormActions>
                <Button kind="danger" disabled={remove.isPending}
                        onClick={() => remove.mutate()}>
                  {remove.isPending ? "Deleting…" : "Delete"}
                </Button>
                <Button kind="quiet" onClick={close}>Cancel</Button>
              </FormActions>
            </>
          )}
          {removeFailure && !removeFailure.isValidation && (
            <Notice>{removeFailure.message}</Notice>
          )}
        </Card>
        </div>
      )}

      <div style={{ height: "var(--space-5)" }} />

      <TagList />
    </>
  );
}
