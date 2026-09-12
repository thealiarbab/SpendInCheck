import { useState } from "react";
import type { Tag } from "../../lib/api";
import styles from "./TagChooser.module.css";

/**
 * Pick any number of tags, and make one that does not exist yet.
 *
 * Checkboxes rather than a multi-select: a native multiple select needs
 * ctrl-click to add a second option and to keep the first, which almost
 * nobody knows, and it silently replaces the whole selection when they get
 * it wrong. Here every tag is one click, and what is chosen is visible
 * without opening anything.
 *
 * Creating from inside the form matters more than it looks. Tags are made
 * at the moment of filing something -- "this was for the Goa trip" -- and
 * sending somebody to another screen to make the tag first means they file
 * the row untagged and never come back.
 */
export function TagChooser(
  { tags, chosen, onChange, onCreate, creating, error }: {
    tags: Tag[];
    chosen: number[];
    onChange: (next: number[]) => void;
    /** May return a promise; the typed name clears only when it settles. */
    onCreate: (name: string) => void | Promise<unknown>;
    creating?: boolean;
    error?: string;
  },
) {
  const [fresh, setFresh] = useState("");

  function toggle(id: number) {
    onChange(chosen.includes(id)
      ? chosen.filter((one) => one !== id)
      : [...chosen, id]);
  }

  const typed = fresh.trim();
  // Case-insensitively, because the server matches that way too: offering
  // "Add holiday" when "Holiday" exists would be a button that fails.
  const alreadyExists = tags.some(
    (tag) => tag.name.toLowerCase() === typed.toLowerCase());

  function create() {
    if (!typed || alreadyExists || creating) return;
    // Cleared on success, not on submission. It used to clear immediately,
    // so a refused name -- a duplicate the case check missed, a server
    // having a bad minute -- took the typed word with it and said nothing.
    // Retyping something you already typed, with no reason given, is the
    // worst version of a failure.
    //
    // The rejection is caught here rather than left to float: onCreate
    // returns the mutation's promise, and an uncaught rejection from a
    // handled failure is noise in the console for something the screen has
    // already dealt with.
    Promise.resolve(onCreate(typed)).then(() => setFresh(""), () => {});
  }

  return (
    <div className={styles.chooser}>
      <span className={styles.label}>Tags</span>

      {tags.length > 0 && (
        <div className={styles.options}>
          {tags.map((tag) => (
            <label
              key={tag.id}
              className={chosen.includes(tag.id)
                ? styles.chip + " " + styles.chosen : styles.chip}
            >
              <input
                type="checkbox"
                checked={chosen.includes(tag.id)}
                onChange={() => toggle(tag.id)}
              />
              {tag.name}
            </label>
          ))}
        </div>
      )}

      <div className={styles.adder}>
        <input
          className={styles.input}
          value={fresh}
          maxLength={40}
          placeholder={tags.length ? "New tag…" : "Add your first tag…"}
          aria-label="New tag"
          onChange={(event) => setFresh(event.target.value)}
          // Enter inside a form would submit the transaction rather than
          // make the tag, so it is caught here and turned into the thing
          // the reader plainly meant.
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              create();
            }
          }}
        />
        <button
          type="button" className={styles.add}
          disabled={!typed || alreadyExists || creating}
          onClick={create}
        >
          {creating ? "Adding…" : "Add"}
        </button>
      </div>

      {alreadyExists && <p className={styles.hint}>You already have that tag.</p>}
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
