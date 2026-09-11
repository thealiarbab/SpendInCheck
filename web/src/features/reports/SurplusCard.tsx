import { useState } from "react";
import { externalLinkProps, surplusHref } from "../../lib/links";
import { formatMoney } from "../../lib/money";
import type { Minor } from "../../lib/money";
import { Button } from "../../ui";
import { monthName } from "./align";
import { shouldOffer } from "./surplus";
import styles from "./Reports.module.css";

/**
 * Shown when a month has finished and finished under budget.
 *
 * One of three placements in the whole app, and the rules below are what
 * keep it from being a fourth.
 *
 * When it may be shown at all is decided in surplus.ts, where it can be
 * tested: every one of those rules fails quietly if it is wrong -- the
 * card simply appears when it should not, which looks like a feature to
 * everyone except the person being sold to at the wrong moment.
 *
 * **Dismissible, and it stays dismissed.** Per month, in localStorage,
 * because it is a per-browser convenience and not something the server
 * should be asked to remember about somebody's feelings toward a card.
 */

const DISMISSED = "sic.surplus.dismissed";

function dismissedMonths(): string[] {
  try {
    const held = JSON.parse(localStorage.getItem(DISMISSED) ?? "[]");
    return Array.isArray(held) ? held : [];
  } catch {
    // Private mode can throw on access, and a corrupted value is not worth
    // a screen. Nothing dismissed is the safe reading.
    return [];
  }
}

function remember(month: string): void {
  try {
    localStorage.setItem(DISMISSED,
      JSON.stringify([...new Set([...dismissedMonths(), month])].slice(-24)));
  } catch {
    // Failing to remember a dismissal is a card shown twice, not a bug
    // worth reporting to anyone.
  }
}

export function SurplusCard(
  { month, budgeted, difference }:
  { month: string; budgeted: Minor; difference: Minor },
) {
  // The whole list, not "is this month dismissed". Seeding a boolean from
  // the month at mount time looks identical and is wrong the moment the
  // month picker moves: the component does not remount, so a month
  // dismissed earlier comes back as soon as you navigate to it again.
  const [dismissed, setDismissed] = useState(dismissedMonths);

  // Both are YYYY-MM, which sorts correctly as text -- see surplus.ts,
  // where the judgement lives and is tested.
  const today = new Date().toISOString().slice(0, 7);
  if (!shouldOffer({ month, today, budgeted, difference,
                     dismissed: dismissed.includes(month) })) return null;

  return (
    <div className={styles.nudge} role="note">
      <div>
        <p className={styles.nudgeLead}>
          You finished {monthName(month)} <strong>{formatMoney(difference)}</strong> under
          budget.
        </p>
        <p className={styles.nudgeBody}>
          Money left over is the easiest money to put to work, because nothing else
          was counting on it.{" "}
          <a href={surplusHref} {...externalLinkProps}>
            See where to put it ↗
          </a>
        </p>
      </div>
      <Button kind="quiet" small
              onClick={() => {
                remember(month);
                setDismissed((months) => [...months, month]);
              }}>
        Dismiss
      </Button>
    </div>
  );
}
