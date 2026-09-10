import { Route, Routes } from "react-router-dom";
import { Shell } from "./app/Shell";
import { SignedOut } from "./app/SignedOut";
import { useSession } from "./app/SessionProvider";
import { Dashboard } from "./features/dashboard/Dashboard";
import { Transactions } from "./features/transactions/Transactions";
import { Categories } from "./features/categories/Categories";
import { Budgets } from "./features/budgets/Budgets";
import { Holdings } from "./features/holdings/Holdings";
import { Reports } from "./features/reports/Reports";
import { Settings } from "./features/settings/Settings";
import { Loading } from "./ui";
import { ThemeLab } from "./features/themelab/ThemeLab";

function Placeholder({ title }: { title: string }) {
  return (
    <>
      <h1>{title}</h1>
      <p style={{ color: "var(--content-secondary)", marginTop: "var(--space-3)" }}>
        Not built yet. The Jinja app at <code>/</code> still serves this screen.
      </p>
    </>
  );
}

/**
 * Screens that need an account.
 *
 * "Checking" renders as loading rather than as the signed-out screen -- the
 * difference is what stops the app flashing a sign-in prompt at somebody who
 * is already signed in, on every load.
 */
function Private({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  if (status === "checking") return <Loading what="your ledger" />;
  if (status === "signed-out") return <SignedOut />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Private><Dashboard /></Private>} />
        <Route path="transactions" element={<Private><Transactions /></Private>} />
        <Route path="categories" element={<Private><Categories /></Private>} />
        <Route path="budgets" element={<Private><Budgets /></Private>} />
        <Route path="investments" element={<Private><Holdings /></Private>} />
        <Route path="reports" element={<Private><Reports /></Private>} />
        <Route path="settings" element={<Private><Settings /></Private>} />
        {/* Development-only: the brass/paper comparison. Tree-shaken from
            production builds by the import.meta.env.DEV guard below. */}
        {import.meta.env.DEV && <Route path="__theme" element={<ThemeLab />} />}
        <Route path="*" element={<Placeholder title="Not found" />} />
      </Route>
    </Routes>
  );
}
