import { Outlet } from "react-router-dom";
import { Nav } from "./Nav";
import styles from "./Shell.module.css";

export function Shell() {
  return (
    <>
      <Nav />
      <main className={styles.main}>
        <Outlet />
      </main>
      <footer className={styles.footer}>
        SpendInCheck — spending, budgets and what you hold, in one place.
      </footer>
    </>
  );
}
