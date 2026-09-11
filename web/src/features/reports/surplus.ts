import type { Minor } from "../../lib/money.ts";  // extensioned so node --test can resolve it

/**
 * Whether a month earned the surplus card.
 *
 * Separated from the component because these are the whole of the feature.
 * The card is a paragraph and a link; the judgement about when a person
 * should be shown it at all is the part worth being able to test, and it
 * is three rules that are each easy to get wrong in a way nobody notices.
 */

/** Below this share of the budget there is nothing here worth saying. */
export const MATERIAL = 0.05;

export function shouldOffer(
  { month, today, budgeted, difference, dismissed }: {
    month: string;
    /** Today's month, as YYYY-MM. Passed in so this is testable at all. */
    today: string;
    budgeted: Minor;
    /** Budgeted minus spent. Positive means under. */
    difference: Minor;
    dismissed: boolean;
  },
): boolean {
  if (dismissed) return false;

  // Only once the month is over. Telling somebody on the third that they
  // are twelve thousand under budget is not news, it is arithmetic about a
  // month that has not happened yet -- and suggesting they invest it is
  // advice to spend money they are about to need. A surplus exists only
  // when there is no more spending to come.
  if (month >= today) return false;

  // A month with no limits set cannot be under them.
  if (budgeted <= 0) return false;
  if (difference <= 0) return false;

  // A share rather than an amount, because an amount is wrong in every
  // currency but the one it was chosen for. Five percent under on a small
  // budget is a real surplus; forty rupees left over is not, at any scale.
  return difference >= budgeted * MATERIAL;
}
