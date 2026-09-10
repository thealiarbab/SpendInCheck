import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { formatRupees, formatSigned, toPaise } from "../lib/money";
import styles from "./ui.module.css";

/* Shared primitives. Everything here reads its colours from semantic tokens,
   so a screen built out of these is correct in brass and paper at once and no
   later screen has to remember which theme it is in. */

export function PageHead(
  { title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode },
) {
  return (
    <header className={styles.pageHead}>
      <div>
        <h1 className={styles.pageTitle}>{title}</h1>
        {subtitle && <p className={styles.pageSubtitle}>{subtitle}</p>}
      </div>
      {children}
    </header>
  );
}

export function Card(
  { title, children, flush }: { title?: string; children: ReactNode; flush?: boolean },
) {
  return (
    <section className={styles.card}>
      {title && (
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>{title}</h2>
        </div>
      )}
      <div className={flush ? styles.cardBodyFlush : styles.cardBody}>{children}</div>
    </section>
  );
}

export function StatRow({ children }: { children: ReactNode }) {
  return <div className={styles.statRow}>{children}</div>;
}

export function Stat(
  { label, value, tone, note }:
  { label: string; value: string; tone?: "credit" | "debit" | "level"; note?: string },
) {
  const toneClass = tone ? " " + styles[tone] : "";
  return (
    <div className={styles.stat}>
      <p className={styles.statLabel}>{label}</p>
      <p className={styles.statValue + toneClass}>{value}</p>
      {note && <p className={styles.statNote}>{note}</p>}
    </div>
  );
}

/** A money figure, coloured by whether it helps or hurts. */
export function Money({ value, signed }: { value: string; signed?: boolean }) {
  const paise = toPaise(value);
  const tone = paise > 0 ? styles.credit : paise < 0 ? styles.debit : "";
  return (
    <span className={signed ? tone : ""}>
      {signed ? formatSigned(paise) : formatRupees(paise)}
    </span>
  );
}

export function Tag({ kind }: { kind: "Income" | "Expense" }) {
  return (
    <span className={styles.tag + " " + (kind === "Income" ? styles.tagCredit : styles.tagDebit)}>
      {kind}
    </span>
  );
}

export function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className={styles.scroller}>
      <table className={styles.table}>
        <thead>{head}</thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export const cell = {
  numeric: styles.numeric,
  primary: styles.primaryCell,
  credit: styles.credit,
  debit: styles.debit,
  level: styles.level,
};

export function Form({ children }: { children: ReactNode }) {
  return <div className={styles.form}>{children}</div>;
}

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  numeric?: boolean;
}

/**
 * A labelled input that shows its own error.
 *
 * The message sits under the input it belongs to rather than in a banner at
 * the top of the page, which is what the old pages did -- leaving the reader
 * to work out which of six fields the complaint was about.
 */
export function Field({ label, error, numeric, ...rest }: FieldProps) {
  const id = rest.id ?? "field-" + rest.name;
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>{label}</label>
      <input
        {...rest}
        id={id}
        className={
          styles.input + (numeric ? " " + styles.inputNumeric : "") +
          (error ? " " + styles.invalid : "")
        }
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? id + "-error" : undefined}
      />
      {error && <p className={styles.fieldError} id={id + "-error"}>{error}</p>}
    </div>
  );
}

interface PickerProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
  children: ReactNode;
}

export function Picker({ label, error, children, ...rest }: PickerProps) {
  const id = rest.id ?? "field-" + rest.name;
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>{label}</label>
      <select
        {...rest}
        id={id}
        className={styles.input + (error ? " " + styles.invalid : "")}
        aria-invalid={error ? true : undefined}
      >
        {children}
      </select>
      {error && <p className={styles.fieldError}>{error}</p>}
    </div>
  );
}

type ButtonKind = "primary" | "quiet" | "danger";

export function Button(
  { kind = "primary", small, children, ...rest }:
  { kind?: ButtonKind; small?: boolean; children: ReactNode } &
  React.ButtonHTMLAttributes<HTMLButtonElement>,
) {
  const variant =
    kind === "quiet" ? " " + styles.buttonQuiet
    : kind === "danger" ? " " + styles.buttonDanger
    : "";
  return (
    <button
      type="button"
      {...rest}
      className={styles.button + variant + (small ? " " + styles.buttonSmall : "")}
    >
      {children}
    </button>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className={styles.empty}>{children}</p>;
}

export function Loading({ what }: { what: string }) {
  return <p className={styles.skeleton}>Loading {what}…</p>;
}

export function Notice({ children, ok }: { children: ReactNode; ok?: boolean }) {
  return (
    <p className={styles.notice + (ok ? " " + styles.noticeOk : "")} role="status">
      {children}
    </p>
  );
}

/* --- acting on a row ------------------------------------------------------
   Every list screen has the same two-step delete, so it lives here rather
   than being re-typed per screen and drifting in wording. */

export function RowActions({ children }: { children: ReactNode }) {
  return <div className={styles.rowActions}>{children}</div>;
}

/**
 * A confirmation that replaces the buttons in the row it is about.
 *
 * Not window.confirm: a browser dialog can only name a record by its id,
 * asks about it somewhere else on the screen, and cannot be styled to say
 * what a particular delete will actually do.
 */
export function Confirm(
  { question = "Delete?", busy, onYes, onNo }:
  { question?: string; busy?: boolean; onYes: () => void; onNo: () => void },
) {
  return (
    <div className={styles.confirm}>
      <span>{question}</span>
      <Button kind="danger" small disabled={busy} onClick={onYes}>Yes</Button>
      <Button kind="quiet" small onClick={onNo}>No</Button>
    </div>
  );
}

/** The buttons that submit a Form, sitting on its grid like a field. */
export function FormActions({ children }: { children: ReactNode }) {
  return <div className={styles.formActions}>{children}</div>;
}

/** A slot on the form grid holding something derived rather than asked for. */
export function Derived({ children }: { children: ReactNode }) {
  return <div className={styles.derived}>{children}</div>;
}

export const row = { editing: styles.editing };
