import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { useSession } from "../../app/SessionProvider";
import { Button, Card, Field, FormActions, Notice, PageHead } from "../../ui";
import styles from "./auth.module.css";

/**
 * Sign in with a username or email.
 *
 * One field for both, because the server accepts either and asking which
 * one somebody is about to type is a question with no purpose. The failure
 * is deliberately vague -- "incorrect username or password" whichever half
 * was wrong -- so this form cannot be used to find out which accounts
 * exist. That is the server's wording; nothing here softens it.
 */
export function SignIn() {
  const { enter } = useSession();
  const navigate = useNavigate();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiError | null>(null);

  const fields = failure?.isValidation ? failure.fields : {};

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await enter(login.trim(), password);
      // replace, not push: the back button should not land on a sign-in
      // form for a session that now exists.
      navigate("/", { replace: true });
    } catch (error) {
      setFailure(error instanceof ApiError ? error
        : new ApiError(0, "unreachable", "Could not reach the server."));
      setBusy(false);
    }
  }

  return (
    <div className={styles.frame}>
      <PageHead title="Sign in" subtitle="Your ledger, where you left it." />

      <Card>
        {/* A real <form>, so Enter submits and a password manager recognises
            the pair. Every other screen in this app posts through a button,
            but those are not credentials. */}
        <form onSubmit={submit} className={styles.stack}>
          {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}

          <Field
            label="Username or email"
            name="login"
            autoComplete="username"
            autoFocus
            required
            value={login}
            error={fields.login}
            onChange={(event) => setLogin(event.target.value)}
          />
          <Field
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            error={fields.password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <FormActions>
            <Button type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </FormActions>
        </form>
      </Card>

      <p className={styles.footnote}>
        No account yet? <Link to="/register">Create one</Link>, or{" "}
        <Link to="/">try the demo</Link> — it needs nothing at all.
      </p>
    </div>
  );
}
