import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Account } from "../lib/api";
import { readSession, signOut as endSession, startDemo } from "../lib/api";

/**
 * Who is signed in, for the whole app.
 *
 * The status is three-valued on purpose. "checking" is not the same as
 * "signed out": collapsing them makes the app flash its signed-out state at
 * somebody who is already signed in, every single load.
 */
export type SessionStatus = "checking" | "signed-in" | "signed-out";

interface SessionValue {
  status: SessionStatus;
  account: Account | null;
  /** Set when the session call itself failed, which is not the same as being signed out. */
  unreachable: boolean;
  beginDemo: () => Promise<void>;
  leave: () => Promise<void>;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("checking");
  const [account, setAccount] = useState<Account | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const user = await readSession();
      setAccount(user);
      setStatus(user ? "signed-in" : "signed-out");
      setUnreachable(false);
    } catch {
      // The API being down is a different problem from being signed out, and
      // telling someone to sign in when the server is unreachable sends them
      // round a loop that cannot succeed.
      setUnreachable(true);
      setStatus("signed-out");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const beginDemo = useCallback(async () => {
    setAccount(await startDemo());
    setStatus("signed-in");
    setUnreachable(false);
  }, []);

  const leave = useCallback(async () => {
    await endSession();
    setAccount(null);
    setStatus("signed-out");
  }, []);

  return (
    <SessionContext.Provider
      value={{ status, account, unreachable, beginDemo, leave, refresh }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside a SessionProvider");
  return value;
}
