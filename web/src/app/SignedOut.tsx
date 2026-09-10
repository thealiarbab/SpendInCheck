import { useState } from "react";
import { Button, Card, Notice, PageHead } from "../ui";
import { useSession } from "./SessionProvider";

/**
 * What an unauthenticated visitor sees.
 *
 * The demo is the first thing offered, because it is the only one that costs
 * nothing to accept: a private ledger with three months of real figures,
 * discarded when they leave. Signing in still lives on the old pages until
 * those screens are ported, so this links across rather than duplicating a
 * form that would then need keeping in step.
 */
export function SignedOut() {
  const { beginDemo, unreachable } = useSession();
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  async function start() {
    setStarting(true);
    setFailed(null);
    try {
      await beginDemo();
    } catch {
      setFailed("The demo could not be started. Try again in a moment.");
      setStarting(false);
    }
  }

  return (
    <>
      <PageHead
        title="Track every rupee"
        subtitle="Where the money went, what you planned to spend, and what your holdings are worth."
      />

      {unreachable && <Notice>Cannot reach the server. The API may not be running.</Notice>}
      {failed && <Notice>{failed}</Notice>}

      <Card title="Look around first">
        <p style={{ color: "var(--content-secondary)", margin: "0 0 var(--space-4)", maxWidth: "58ch" }}>
          The demo gives you your own copy, loaded with three months of figures across
          categories, budgets and holdings. Change anything you like — it is discarded
          when you leave, and nobody else sees it.
        </p>
        <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <Button onClick={start} disabled={starting}>
            {starting ? "Setting it up…" : "Open the demo"}
          </Button>
          <a href="/sign-in" style={{ textDecoration: "none" }}>
            <Button kind="quiet">Sign in to your account</Button>
          </a>
        </div>
      </Card>
    </>
  );
}
