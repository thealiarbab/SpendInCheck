import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError, api } from "../../lib/api";
import type { Tag } from "../../lib/api";
import {
  Button, Card, Confirm, Empty, Field, Form, FormActions, Loading, Notice,
  RowActions, Table, cell, row as rowStyle,
} from "../../ui";
import styles from "./TagList.module.css";

/**
 * Managing tags: rename and delete, and see what is actually being used.
 *
 * Adding is not here. A tag is made at the moment of filing something --
 * "this was for the Goa trip" -- so the place to make one is the form where
 * that happens, not a screen somebody has to remember to visit first. This
 * card is for tidying up afterwards.
 */
export function TagList() {
  const client = useQueryClient();
  const [editing, setEditing] = useState<Tag | null>(null);
  const [name, setName] = useState("");
  const [confirming, setConfirming] = useState<number | null>(null);

  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  const items = tags.data?.items ?? [];

  // A rename shows on every row carrying the tag, and a delete takes the
  // label off them, so the ledger has to be refetched either way.
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["tags"] });
    client.invalidateQueries({ queryKey: ["transactions"] });
  };

  const rename = useMutation({
    mutationFn: () => api.renameTag(editing!.id, name),
    onSuccess: () => { refresh(); stop(); },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteTag(id),
    onSuccess: () => { refresh(); setConfirming(null); },
  });

  function start(tag: Tag) {
    setEditing(tag);
    setName(tag.name);
    rename.reset();
  }

  function stop() {
    setEditing(null);
    setName("");
    rename.reset();
  }

  const failure = rename.error instanceof ApiError ? rename.error : null;
  const fields = failure?.isValidation ? failure.fields : {};

  return (
    <Card title="Tags" flush>
      {tags.isPending && !tags.data ? (
        <Loading what="tags" />
      ) : tags.error ? (
        <Notice>{(tags.error as Error).message}</Notice>
      ) : items.length ? (
        <>
          <Table
            head={
              <tr>
                <th>Tag</th>
                <th className={cell.numeric}>On</th>
                <th />
              </tr>
            }
          >
            {items.map((tag) => (
              <tr key={tag.id}
                  className={tag.id === editing?.id ? rowStyle.editing : undefined}>
                <td className={cell.primary}>{tag.name}</td>
                <td className={cell.numeric + " " + styles.uses}>
                  {tag.uses === 0 ? (
                    <span className={styles.unused}>unused</span>
                  ) : (
                    // Straight to the rows it is on, which is the question
                    // a count immediately raises.
                    <Link className={styles.count} to={`/transactions?tag_id=${tag.id}`}>
                      {tag.uses} row{tag.uses === 1 ? "" : "s"}
                    </Link>
                  )}
                </td>
                <td>
                  {confirming === tag.id ? (
                    <Confirm
                      busy={remove.isPending}
                      onYes={() => remove.mutate(tag.id)}
                      onNo={() => setConfirming(null)}
                    />
                  ) : (
                    <RowActions>
                      <Button kind="quiet" small onClick={() => start(tag)}>
                        Rename
                      </Button>
                      <Button kind="danger" small onClick={() => setConfirming(tag.id)}>
                        Delete
                      </Button>
                    </RowActions>
                  )}
                </td>
              </tr>
            ))}
          </Table>

          {editing && (
            <div className={styles.panel}>
              <Form>
                <Field
                  label={`Renaming ${editing.name}`} name="name" maxLength={40}
                  value={name} error={fields.name}
                  onChange={(event) => setName(event.target.value)}
                />
                <FormActions>
                  <Button disabled={!name.trim() || rename.isPending}
                          onClick={() => rename.mutate()}>
                    {rename.isPending ? "Saving…" : "Save"}
                  </Button>
                  <Button kind="quiet" onClick={stop}>Cancel</Button>
                </FormActions>
              </Form>
              {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}
            </div>
          )}

          <p className={styles.explain}>
            Deleting a tag takes the label off the transactions carrying it and
            leaves everything else alone — unlike a category, a transaction with
            no tags is perfectly ordinary.
          </p>
        </>
      ) : (
        <Empty>
          No tags yet. They are made on the transaction form, where you are
          already saying what a row was for.
        </Empty>
      )}
    </Card>
  );
}
