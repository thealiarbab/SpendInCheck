import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Shell } from "./app/Shell";
import { useSession } from "./app/SessionProvider";
import { Landing } from "./features/landing/Landing";
import { SignIn } from "./features/auth/SignIn";
import { Register } from "./features/auth/Register";
import { Dashboard } from "./features/dashboard/Dashboard";
import { Transactions } from "./features/transactions/Transactions";
import { Accounts } from "./features/accounts/Accounts";
import { Categories } from "./features/categories/Categories";
import { Import } from "./features/importing/Import";
import { Budgets } from "./features/budgets/Budgets";
import { Holdings } from "./features/holdings/Holdings";
import { Reports } from "./features/reports/Reports";
import { Settings } from "./features/settings/Settings";
import { Loading, PageHead } from "./ui";
import { ThemeLab } from "./features/themelab/ThemeLab";

function NotFound() {
  return (
    <PageHead
      title="Not found"
      subtitle="There is no page at this address."
    />
  );
}

/**
 * Screens that need an account.
 *
 * "Checking" renders as loading rather than as the front page -- the
 * difference is what stops the app flashing a sign-in prompt at somebody who
 * is already signed in, on every load.
 */
function Private({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  if (status === "checking") return <Loading what="your ledger" />;
  if (status === "signed-out") return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** Sign in and register, which are pointless once you are signed in. */
function Public({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  if (status === "checking") return <Loading what="your ledger" />;
  if (status === "signed-in") return <Navigate to="/" replace />;
  return <>{children}</>;
}

/**
 * "/" is two different pages.
 *
 * A stranger gets the front page; somebody signed in gets their ledger.
 * One address rather than two means the bookmark, the shared link and the
 * brand in the corner all lead to the right place without anybody having
 * to know which state they are in.
 */
function Home() {
  const { status } = useSession();
  if (status === "checking") return <Loading what="your ledger" />;
  if (status === "signed-out") return <Landing />;
  return <Dashboard />;
}

/**
 * Where the client used to live.
 *
 * Until Phase 8 every screen was served under /app, and those URLs are in
 * the browser history of anyone who was following along. They cost one
 * line to keep working, so they do.
 */
function MovedFromApp() {
  const { pathname, search } = useLocation();
  return <Navigate to={pathname.replace(/^\/app/, "") + search || "/"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        {/* The old Jinja address for the same screen. */}
        <Route path="dashboard" element={<Private><Dashboard /></Private>} />
        <Route path="sign-in" element={<Public><SignIn /></Public>} />
        <Route path="register" element={<Public><Register /></Public>} />
        <Route path="transactions" element={<Private><Transactions /></Private>} />
        <Route path="accounts" element={<Private><Accounts /></Private>} />
        <Route path="categories" element={<Private><Categories /></Private>} />
        <Route path="budgets" element={<Private><Budgets /></Private>} />
        <Route path="investments" element={<Private><Holdings /></Private>} />
        <Route path="reports" element={<Private><Reports /></Private>} />
        <Route path="import" element={<Private><Import /></Private>} />
        <Route path="settings" element={<Private><Settings /></Private>} />
        <Route path="app/*" element={<MovedFromApp />} />
        {/* Development-only: the brass/paper comparison. Tree-shaken from
            production builds by the import.meta.env.DEV guard below. */}
        {import.meta.env.DEV && <Route path="__theme" element={<ThemeLab />} />}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
