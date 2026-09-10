import { NavLink } from "react-router-dom";
import { externalLinkProps, investHref } from "../lib/links";
import { useTheme } from "./ThemeProvider";
import styles from "./Nav.module.css";

const PAGES = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/transactions", label: "Transactions" },
  { to: "/categories", label: "Categories" },
  { to: "/budgets", label: "Budgets" },
  { to: "/investments", label: "Holdings" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
];

export function Nav({ username }: { username?: string }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        <span className={styles.brand}>
          Spend<span className={styles.brandMark}>InCheck</span>
        </span>
        <nav className={styles.links} aria-label="Main">
          {PAGES.map((page) => (
            <NavLink
              key={page.to}
              to={page.to}
              end={page.end}
              /* NavLink sets aria-current="page" when active, so the active
                 styling keys off that in CSS rather than a second class. */
              className={styles.link}
            >
              {page.label}
            </NavLink>
          ))}

        </nav>
      </div>

      {/*
        Invest sits OUTSIDE the scrolling link row on purpose. Inside it, a
        narrow screen scrolls it out of sight, and an offer nobody can see is
        not an offer. Here it stays pinned at every width.

        It leaves the app for StockSaathi, and three things keep that honest:
        the divider separating it from the internal pages, the arrow, and
        target=_blank. See lib/links.ts for the UTM tagging.
      */}
      <div className={styles.investWrap}>
        <span className={styles.divider} aria-hidden="true" />
        <a
          className={styles.invest}
          href={investHref}
          {...externalLinkProps}
          title="Opens StockSaathi, for markets and research"
        >
          Invest
          <span className={styles.arrow} aria-hidden="true">
            ↗
          </span>
          <span className="sr-only">(opens StockSaathi in a new tab)</span>
        </a>
      </div>

      <div className={styles.right}>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={`Switch to the ${theme === "brass" ? "paper" : "brass"} theme`}
        >
          {theme === "brass" ? "Paper" : "Brass"}
        </button>
        {username ? <span className={styles.who}>{username}</span> : null}
      </div>
    </header>
  );
}
