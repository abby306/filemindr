"use client";

/**
 * AccountProvider — holds the active account (personal ⇄ company) and exposes a
 * request helper bound to it. Every API call in the app goes through `useApi()`
 * so the auth/scoping headers are injected in exactly one place.
 *
 * The active-account id is backed by localStorage and read via
 * `useSyncExternalStore`, which is SSR-safe (server renders the default) and
 * keeps multiple tabs in sync via the `storage` event — no setState-in-effect.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";

import { apiFetch } from "@/lib/api/client";
import {
  ACCOUNTS,
  DEFAULT_ACCOUNT,
  type AccountOption,
} from "@/lib/auth/dev-auth";

const STORAGE_KEY = "filemindr.activeAccountId";
const CHANGE_EVENT = "filemindr:account-change";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

function readAccountId(): string {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored && ACCOUNTS.some((a) => a.id === stored)
    ? stored
    : DEFAULT_ACCOUNT.id;
}

interface AccountContextValue {
  account: AccountOption;
  accounts: AccountOption[];
  setAccount: (id: string) => void;
  /** apiFetch pre-bound to the active account's scope. */
  request: <T = unknown>(
    path: string,
    init?: Omit<Parameters<typeof apiFetch>[1], "accountId">,
  ) => Promise<T>;
}

const AccountContext = createContext<AccountContextValue | null>(null);

export function AccountProvider({ children }: { children: React.ReactNode }) {
  const accountId = useSyncExternalStore(
    subscribe,
    readAccountId,
    () => DEFAULT_ACCOUNT.id,
  );

  const setAccount = useCallback((id: string) => {
    if (!ACCOUNTS.some((a) => a.id === id)) return;
    window.localStorage.setItem(STORAGE_KEY, id);
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  const account = useMemo(
    () => ACCOUNTS.find((a) => a.id === accountId) ?? DEFAULT_ACCOUNT,
    [accountId],
  );

  const request = useCallback<AccountContextValue["request"]>(
    (path, init) => apiFetch(path, { ...init, accountId: account.id }),
    [account.id],
  );

  const value = useMemo<AccountContextValue>(
    () => ({ account, accounts: ACCOUNTS, setAccount, request }),
    [account, setAccount, request],
  );

  return (
    <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
  );
}

export function useAccount(): AccountContextValue {
  const ctx = useContext(AccountContext);
  if (!ctx) {
    throw new Error("useAccount must be used within an AccountProvider");
  }
  return ctx;
}

/** Convenience: the account-bound request function. */
export function useApi() {
  return useAccount().request;
}
