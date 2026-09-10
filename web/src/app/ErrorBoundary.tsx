import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/**
 * Catches render errors so a single broken screen shows a readable message
 * instead of blanking the whole app to a white page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled render error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div style={{ padding: "var(--space-10) var(--page-gutter)", maxWidth: "60ch" }}>
        <h1>Something broke on this screen</h1>
        <p style={{ color: "var(--content-secondary)", marginTop: "var(--space-3)" }}>
          The rest of the app is fine. Reload to try again.
        </p>
        <pre
          style={{
            marginTop: "var(--space-5)",
            padding: "var(--space-4)",
            background: "var(--surface-raised)",
            border: "1px solid var(--line-default)",
            color: "var(--state-error)",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-sm)",
            whiteSpace: "pre-wrap",
          }}
        >
          {this.state.error.message}
        </pre>
      </div>
    );
  }
}
