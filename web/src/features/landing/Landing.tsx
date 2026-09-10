import { useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/SessionProvider";
import { Button, Notice } from "../../ui";
import styles from "./landing.module.css";

/* Six things the app does, in the order somebody meets them. Kept as data
   rather than as six copies of the same markup, so the grid cannot drift
   card to card. */
const FEATURES = [
  {
    title: "The ledger",
    body: "Every amount in and out, filed under a category and an account. " +
      "Search it, filter it, sort it, and take the whole thing away as CSV.",
  },
  {
    title: "Budget against actual",
    body: "A monthly limit per category, with what you actually spent beside " +
      "it. What is left over can roll into next month, or not — your choice.",
  },
  {
    title: "What you hold",
    body: "Stocks, funds and deposits, with buy price against today's, giving " +
      "profit or loss per holding and across everything at once.",
  },
  {
    title: "Money that moves itself",
    body: "Rent on the first, salary on the last. A recurring rule writes the " +
      "row on the day, once, however many times the sweep runs.",
  },
  {
    title: "Accounts and transfers",
    body: "Current, cash, card. Moving money between two of them is not " +
      "income and not spending, and the reports know the difference.",
  },
  {
    title: "Yours to leave with",
    body: "Import a bank statement as CSV, export any view as CSV. Nothing " +
      "here is a format only this app can read.",
  },
];

/**
 * The public front page.
 *
 * Shown at "/" to anybody not signed in. The demo is the first thing
 * offered because it is the only one that costs a stranger nothing to
 * accept: their own ledger, three months of figures already in it,
 * discarded when they leave.
 */
export function Landing() {
  const { beginDemo, unreachable } = useSession();
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  async function start() {
    setStarting(true);
    setFailed(null);
    try {
      await beginDemo();
    } catch {
      setFailed("The demo could not be started. Try again in a moment.");
      setStarting(false);
    }
  }

  return (
    <>
      <section className={styles.hero}>
        <span className={styles.pill}>Track it · Budget it · Stay on it</span>

        <h1 className={styles.title}>
          Track every rupee.
          <br />
          <span className={styles.claim}>Stay on budget.</span>
        </h1>

        <p className={styles.tagline}>
          Most trackers only tell you where the money went. SpendInCheck tells you the
          thing that actually matters — <strong>are you over or under what you planned,
          and by how much?</strong> Set a monthly limit per category, log what you
          spend, and watch the gap as the month goes.
        </p>

        {unreachable && <Notice>Cannot reach the server. The API may not be running.</Notice>}
        {failed && <Notice>{failed}</Notice>}

        <div className={styles.actions}>
          <Button onClick={start} disabled={starting}>
            {starting ? "Setting it up…" : "Try the demo — no signup"}
          </Button>
          <Link to="/register" style={{ textDecoration: "none" }}>
            <Button kind="quiet">Create an account</Button>
          </Link>
        </div>

        <p className={styles.note}>
          Already have one? <Link to="/sign-in">Sign in</Link>. The demo is your own
          private copy loaded with three months of figures — edit and delete anything
          in it — and it is discarded when you leave.
        </p>
      </section>

      <section className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>What it does</h2>
        <p className={styles.sectionSub}>
          Six jobs most trackers keep apart, joined up by one database.
        </p>
      </section>

      <div className={styles.grid}>
        {FEATURES.map((feature) => (
          <article className={styles.feature} key={feature.title}>
            <h3 className={styles.featureTitle}>{feature.title}</h3>
            <p className={styles.featureBody}>{feature.body}</p>
          </article>
        ))}
      </div>
    </>
  );
}
