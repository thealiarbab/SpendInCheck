import { Link, NavLink, useNavigate } from "react-router-dom";
import { externalLinkProps, investHref } from "../lib/links";
import { useSession } from "./SessionProvider";
import { useTheme } from "./ThemeProvider";
import styles from "./Nav.module.css";

const PAGES = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/transactions", label: "Transactions" },
  { to: "/accounts", label: "Accounts" },
  { to: "/categories", label: "Categories" },
  { to: "/budgets", label: "Budgets" },
  { to: "/investments", label: "Holdings" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
];

/**
 * The bar across the top, in two states.
 *
 * A visitor who is not signed in gets no page links at all: every one of
 * them leads somewhere that would bounce straight back, and a row of
 * links that cannot be followed is worse than no row. They get the way in
 * instead.
 */
export function Nav() {
  const { theme, toggleTheme } = useTheme();
  const { status, account, leave } = useSession();
  const navigate = useNavigate();
  const signedIn = status === "signed-in";

  async function signOut() {
    await leave();
    navigate("/", { replace: true });
  }

  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        <Link to="/" className={styles.brand}>
          Spend<span className={styles.brandMark}>InCheck</span>
        </Link>
        <nav className={styles.links} aria-label="Main">
          {signedIn && PAGES.map((page) => (
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
        {signedIn ? (
          <>
            <span className={styles.who}>{account?.username}</span>
            {/* A button, not a link: signing out is a POST, and as a link
                any prefetcher or link scanner could trigger it. */}
            <button type="button" onClick={signOut}>Sign out</button>
          </>
        ) : (
          /* Hidden while the session is still being checked, so the bar
             does not offer "Sign in" for a moment to somebody who is. */
          status === "signed-out" && <Link to="/sign-in" className={styles.who}>Sign in</Link>
        )}
      </div>
    </header>
  );
}
