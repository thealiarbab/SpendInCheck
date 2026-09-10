import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "./app/ThemeProvider";
import { SessionProvider } from "./app/SessionProvider";
import { ErrorBoundary } from "./app/ErrorBoundary";
import App from "./App";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Financial figures should not silently re-fetch under the user while
      // they read them; an explicit action refreshes instead.
      refetchOnWindowFocus: false,
      // Five minutes rather than thirty seconds. Every write already
      // invalidates the keys it touches by hand, so this only decides how
      // long an untouched list is trusted -- and at thirty seconds, simply
      // walking between screens re-fetched the categories on each one, at
      // roughly two hundred milliseconds a time, to be told the same eight
      // rows. Nothing here goes stale on its own: a ledger only changes
      // when somebody in this tab changes it.
      staleTime: 300_000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <SessionProvider>
              <App />
            </SessionProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
