import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { Account } from "../lib/api";
import { readSession, signOut as endSession, startDemo } from "../lib/api";
import { setCurrency } from "../lib/money";

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
  const queries = useQueryClient();
  const [status, setStatus] = useState<SessionStatus>("checking");
  const [account, setAccount] = useState<Account | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const user = await readSession();
      // Before anything renders a figure: the currency decides how every
      // amount is parsed as well as shown, so a screen must never draw one
      // in the wrong scale first and correct itself after.
      if (user?.currency) setCurrency(user.currency);
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
    const { user, dashboard } = await startDemo();
    if (user.currency) setCurrency(user.currency);
    // The response already carries the opening screen, so put it in the
    // cache rather than letting the dashboard ask for it again. Without
    // this the visitor waits out two further round trips staring at a
    // spinner, for rows the server had already read.
    if (dashboard) queries.setQueryData(["dashboard"], dashboard);
    setAccount(user);
    setStatus("signed-in");
    setUnreachable(false);
  }, [queries]);

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
