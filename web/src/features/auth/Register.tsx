import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { useSession } from "../../app/SessionProvider";
import { Button, Card, Field, FormActions, Notice, PageHead } from "../../ui";
import styles from "./auth.module.css";

/**
 * Create an account.
 *
 * The rules -- three characters, a real address, eight characters of
 * password -- are the server's, and they are stated here before the field
 * rather than only reported after a rejected submit. The server still
 * enforces every one of them; this only saves a round trip to be told
 * something that could have been said up front.
 */
export function Register() {
  const { join } = useSession();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiError | null>(null);

  const fields = failure?.isValidation ? failure.fields : {};

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await join(username.trim(), email.trim(), password);
      navigate("/", { replace: true });
    } catch (error) {
      setFailure(error instanceof ApiError ? error
        : new ApiError(0, "unreachable", "Could not reach the server."));
      setBusy(false);
    }
  }

  return (
    <div className={styles.frame}>
      <PageHead
        title="Create an account"
        subtitle="A ledger of your own, kept as long as you want it."
      />

      <Card>
        <form onSubmit={submit} className={styles.stack}>
          {failure && !failure.isValidation && <Notice>{failure.message}</Notice>}

          <Field
            label="Username"
            name="username"
            autoComplete="username"
            autoFocus
            required
            minLength={3}
            maxLength={30}
            placeholder="3–30 letters, digits or underscores"
            value={username}
            error={fields.username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <Field
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            error={fields.email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Field
            label="Password"
            name="password"
            type="password"
            /* new-password, not current-password: this is what tells a
               password manager to offer to generate one rather than to
               fill in something already saved. */
            autoComplete="new-password"
            required
            minLength={8}
            placeholder="At least 8 characters"
            value={password}
            error={fields.password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <FormActions>
            <Button type="submit" disabled={busy}>
              {busy ? "Creating it…" : "Create account"}
            </Button>
          </FormActions>
        </form>
      </Card>

      <p className={styles.footnote}>
        Already have one? <Link to="/sign-in">Sign in</Link>.
      </p>
    </div>
  );
}
