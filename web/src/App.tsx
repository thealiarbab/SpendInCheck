import { Route, Routes } from "react-router-dom";
import { Shell } from "./app/Shell";
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

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Placeholder title="Dashboard" />} />
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
