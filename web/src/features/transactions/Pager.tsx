import type { PageInfo } from "../../lib/api";
import { Button } from "../../ui";
import styles from "./Pager.module.css";

/**
 * Move between pages, and say where you are.
 *
 * Deliberately not a numbered list of every page. A ledger can run to
 * hundreds, and "page 47" is not a thing anyone means to go to -- the
 * useful moves are the next one, the previous one, and back to the start.
 */
export function Pager(
  { page, onGo }: { page: PageInfo; onGo: (number: number) => void },
) {
  if (page.pages <= 1) return null;

  const first = (page.number - 1) * page.per_page + 1;
  const last = Math.min(page.number * page.per_page, page.total);

  return (
    <div className={styles.pager}>
      <span className={styles.range}>
        {first}–{last} of {page.total}
      </span>
      <div className={styles.buttons}>
        <Button
          kind="quiet" small
          disabled={page.number <= 1}
          onClick={() => onGo(page.number - 1)}
        >
          Previous
        </Button>
        <span className={styles.position}>
          Page {page.number} of {page.pages}
        </span>
        <Button
          kind="quiet" small
          disabled={page.number >= page.pages}
          onClick={() => onGo(page.number + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
