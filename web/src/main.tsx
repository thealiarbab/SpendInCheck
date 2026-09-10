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
      staleTime: 30_000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          {/* basename matches vite's base. Phase 8 flips both to "/". */}
          <BrowserRouter basename="/app">
            <SessionProvider>
              <App />
            </SessionProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
