/**
 * The one place the client talks to the API.
 *
 * Two things every call needs and no screen should have to remember: the
 * session cookie must be sent, and every write must carry the CSRF token the
 * server handed out. Both live here so a component only ever asks for data.
 */

export type ApiFieldErrors = Record<string, string>;

/** A failure the server described, as opposed to the network giving up. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: ApiFieldErrors;

  constructor(status: number, code: string, message: string, fields: ApiFieldErrors = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }

  /** True when the message belongs against particular inputs. */
  get isValidation(): boolean {
    return this.code === "validation_failed";
  }
}

export interface Account {
  id: number;
  username: string;
  is_demo: boolean;
  /** ISO 4217 code the ledger is kept in. Decides scale, not just symbol. */
  currency: string;
}

const BASE = "/api/v1";

// Held in memory rather than localStorage: the token is only useful alongside
// the session cookie, and anything script can read from storage is one XSS
// away from being readable by somebody else's script.
let csrfToken = "";

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Internal: stops a refreshed token from retrying forever. */
  retried?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};

  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = csrfToken;

  const response = await fetch(BASE + path, {
    method,
    headers,
    // Same origin in both development and production, but stating it means a
    // future move to a separate API host fails loudly rather than silently
    // dropping the session.
    credentials: "same-origin",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (response.status === 204) return undefined as T;

  let payload: any = null;
  try {
    payload = await response.json();
  } catch {
    // A non-JSON body means something upstream answered instead of the API.
    throw new ApiError(response.status, "unreadable",
      "The server sent something this app could not read.");
  }

  if (response.ok) return payload as T;

  const error = payload?.error ?? {};

  // A stale token is the expected result of leaving a tab open overnight, so
  // fetch a fresh one and try the write once more before troubling anyone.
  if (error.code === "csrf_failed" && !options.retried) {
    await readSession();
    return request<T>(path, { ...options, retried: true });
  }

  throw new ApiError(response.status, error.code ?? "error",
    error.message ?? "Something went wrong.", error.fields ?? {});
}

/**
 * Who is signed in, and a fresh CSRF token.
 *
 * The call every load starts with. It answers 200 with a null account when
 * nobody is signed in, so "signed out" and "still loading" stay distinct --
 * without that the app flashes its sign-in screen at people who are already
 * signed in.
 */
export async function readSession(): Promise<Account | null> {
  const body = await request<{ user: Account | null; csrf_token: string }>("/auth/session");
  csrfToken = body.csrf_token;
  return body.user;
}

/** Create a private demonstration account and sign into it. */
export async function startDemo(): Promise<Account> {
  const body = await request<{ user: Account; csrf_token: string }>(
    "/auth/demo", { method: "POST" });
  csrfToken = body.csrf_token;
  return body.user;
}

/** Abandon the session. A demonstration account is deleted on the way out. */
export async function signOut(): Promise<void> {
  const body = await request<{ csrf_token: string }>("/auth/sign-out", { method: "POST" });
  csrfToken = body.csrf_token;
}

export interface Holding {
  asset_name: string;
  asset_type: string;
  buy_price: string;
  current_price: string;
  quantity: string;
  pnl: string;
  current_value: string;
}

export interface PortfolioReport {
  items: Holding[];
  totals: { value: string; pnl: string; holdings: number };
}

export interface TransactionRow {
  id: number;
  date: string;
  category: string;
  amount: string;
  type: "Income" | "Expense";
  description: string | null;
}

export interface Category {
  id: number;
  name: string;
  type: "Income" | "Expense";
}

export interface BudgetRow {
  id: number;
  category: string;
  month: string;
  limit: string;
}

export interface BudgetVsActualRow {
  category: string;
  limit: string;
  actual: string;
  difference: string;
}

export interface InvestmentRow {
  id: number;
  asset_name: string;
  asset_type: string;
  buy_date: string;
  buy_price: string;
  quantity: string;
  current_price: string;
}

/** How much still points at a category, so a delete can say what it moves. */
export interface CategoryUsage {
  transactions: number;
  budgets: number;
}

export interface TransactionSubmission {
  date: string;
  category_id: number;
  amount: string;
  type: string;
  description?: string;
}

const query = (params: Record<string, string>) =>
  "?" + new URLSearchParams(params).toString();

export const api = {
  categories: () => request<{ items: Category[] }>("/categories"),
  addCategory: (name: string, type: string) =>
    request<void>("/categories", { method: "POST", body: { name, type } }),
  renameCategory: (id: number, name: string, type: string) =>
    request<void>("/categories/" + id, { method: "PATCH", body: { name, type } }),
  categoryUsage: (id: number) =>
    request<CategoryUsage>("/categories/" + id + "/usage"),
  // The target rides in the query string rather than a body: a DELETE with a
  // body is poorly supported by enough intermediaries to be worth avoiding.
  deleteCategory: (id: number, reassignTo?: number) =>
    request<void>("/categories/" + id +
      (reassignTo === undefined ? "" : query({ reassign_to: String(reassignTo) })),
      { method: "DELETE" }),

  transactions: () => request<{ items: TransactionRow[] }>("/transactions"),
  transaction: (id: number) => request<TransactionSubmission & { id: number }>(
    "/transactions/" + id),
  addTransaction: (body: TransactionSubmission) =>
    request<void>("/transactions", { method: "POST", body }),
  editTransaction: (id: number, body: TransactionSubmission) =>
    request<void>("/transactions/" + id, { method: "PATCH", body }),
  deleteTransaction: (id: number) =>
    request<void>("/transactions/" + id, { method: "DELETE" }),

  budgets: () => request<{ items: BudgetRow[] }>("/budgets"),
  setBudget: (category_id: number, month: string, limit: string) =>
    request<void>("/budgets", { method: "PUT", body: { category_id, month, limit } }),

  investments: () => request<{ items: InvestmentRow[] }>("/investments"),
  addInvestment: (body: Record<string, string>) =>
    request<void>("/investments", { method: "POST", body }),
  deleteInvestment: (id: number) =>
    request<void>("/investments/" + id, { method: "DELETE" }),
  reprice: (id: number, current_price: string) =>
    request<void>("/investments/" + id + "/price",
      { method: "PATCH", body: { current_price } }),

  currencies: () => request<{ items: string[]; current: string }>(
    "/settings/currencies"),
  setCurrency: (currency: string) =>
    request<{ currency: string; decimals: number }>(
      "/settings/currency", { method: "PUT", body: { currency } }),

  portfolio: () => request<PortfolioReport>("/reports/portfolio"),
  categorySpend: (month: string) =>
    request<{ items: { category: string; total: string }[] }>(
      "/reports/category-spend" + query({ month })),
  budgetVsActual: (month: string) =>
    request<{ items: BudgetVsActualRow[] }>(
      "/reports/budget-vs-actual" + query({ month })),
};
