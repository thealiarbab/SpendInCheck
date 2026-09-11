import { Suspense, lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Shell } from "./app/Shell";
import { useSession } from "./app/SessionProvider";
import { Landing } from "./features/landing/Landing";
import { Loading, PageHead } from "./ui";
import { ThemeLab } from "./features/themelab/ThemeLab";

/* Landing is imported directly above, and everything else is fetched when
   somebody actually goes there.

   A stranger arriving at "/" is the common first visit, and they need the
   front page and nothing else -- yet every screen behind the sign-in was
   being downloaded, parsed and executed before that page could paint. None
   of it is reachable without an account.

   .then(...) because these are named exports and React.lazy wants a default. */
const Dashboard = lazy(() => import("./features/dashboard/Dashboard")
  .then((m) => ({ default: m.Dashboard })));
const SignIn = lazy(() => import("./features/auth/SignIn")
  .then((m) => ({ default: m.SignIn })));
const Register = lazy(() => import("./features/auth/Register")
  .then((m) => ({ default: m.Register })));
const Transactions = lazy(() => import("./features/transactions/Transactions")
  .then((m) => ({ default: m.Transactions })));
const Accounts = lazy(() => import("./features/accounts/Accounts")
  .then((m) => ({ default: m.Accounts })));
const Categories = lazy(() => import("./features/categories/Categories")
  .then((m) => ({ default: m.Categories })));
const Import = lazy(() => import("./features/importing/Import")
  .then((m) => ({ default: m.Import })));
const Budgets = lazy(() => import("./features/budgets/Budgets")
  .then((m) => ({ default: m.Budgets })));
const Holdings = lazy(() => import("./features/holdings/Holdings")
  .then((m) => ({ default: m.Holdings })));
const Reports = lazy(() => import("./features/reports/Reports")
  .then((m) => ({ default: m.Reports })));
const Settings = lazy(() => import("./features/settings/Settings")
  .then((m) => ({ default: m.Settings })));

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
  return <Screen>{children}</Screen>;
}

/** Sign in and register, which are pointless once you are signed in. */
function Public({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  if (status === "checking") return <Loading what="your ledger" />;
  if (status === "signed-in") return <Navigate to="/" replace />;
  return <Screen>{children}</Screen>;
}

/**
 * Waits for a screen's code to arrive.
 *
 * The boundary sits here rather than around the whole router so that the
 * nav and the frame stay on screen while a chunk loads. Put it above Shell
 * and every navigation would blank the entire page instead of the part that
 * is actually changing.
 */
function Screen({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<Loading what="this screen" />}>{children}</Suspense>;
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
  // Landing is the one screen not split out: it is what a stranger sees
  // first, so fetching it separately would only add a round trip to the
  // paint that matters most.
  if (status === "signed-out") return <Landing />;
  return <Screen><Dashboard /></Screen>;
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
