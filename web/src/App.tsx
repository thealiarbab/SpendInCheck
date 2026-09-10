import { Route, Routes } from "react-router-dom";
import { Shell } from "./app/Shell";
import { SignedOut } from "./app/SignedOut";
import { useSession } from "./app/SessionProvider";
import { Dashboard } from "./features/dashboard/Dashboard";
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
        <Route path="transactions" element={<Placeholder title="Transactions" />} />
        <Route path="budgets" element={<Placeholder title="Budgets" />} />
        <Route path="investments" element={<Placeholder title="Holdings" />} />
        <Route path="reports" element={<Placeholder title="Reports" />} />
        {/* Development-only: the brass/paper comparison. Tree-shaken from
            production builds by the import.meta.env.DEV guard below. */}
        {import.meta.env.DEV && <Route path="__theme" element={<ThemeLab />} />}
        <Route path="*" element={<Placeholder title="Not found" />} />
      </Route>
    </Routes>
  );
}
