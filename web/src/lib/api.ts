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

/**
 * Create a private demonstration account and sign into it.
 *
 * The dashboard rides along in the response, so the caller can put it
 * straight into the cache: the server already had the rows open, and asking
 * for them again is two more round trips to Mumbai while somebody watches a
 * spinner.
 */
export async function startDemo(): Promise<{ user: Account; dashboard: DashboardPayload }> {
  const body = await request<{ user: Account; csrf_token: string;
                               dashboard: DashboardPayload }>(
    "/auth/demo", { method: "POST" });
  csrfToken = body.csrf_token;
  return { user: body.user, dashboard: body.dashboard };
}

/**
 * Exchange a username or email plus password for a session.
 *
 * The server answers 401 with one message whichever half was wrong, so this
 * cannot be used to discover which accounts exist. Nothing here softens that
 * into something more helpful.
 */
export async function signIn(login: string, password: string): Promise<Account> {
  const body = await request<{ user: Account; csrf_token: string }>(
    "/auth/sign-in", { method: "POST", body: { login, password } });
  csrfToken = body.csrf_token;
  return body.user;
}

/** Create an account and sign into it. Field errors come back per field. */
export async function register(
  username: string, email: string, password: string,
): Promise<Account> {
  const body = await request<{ user: Account; csrf_token: string }>(
    "/auth/register", { method: "POST", body: { username, email, password } });
  csrfToken = body.csrf_token;
  return body.user;
}

/** Abandon the session. A demonstration account is deleted on the way out. */
export async function signOut(): Promise<void> {
  const body = await request<{ csrf_token: string }>("/auth/sign-out", { method: "POST" });
  csrfToken = body.csrf_token;
}

export interface Holding {
  id: number;
  asset_name: string;
  asset_type: string;
  buy_date: string;
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

/** Everything the opening screen shows, in one request. */
export interface DashboardPayload {
  portfolio: PortfolioReport;
  recent: TransactionRow[];
}

export interface TransactionRow {
  id: number;
  date: string;
  category: string;
  amount: string;
  type: "Income" | "Expense";
  description: string | null;
  /** Which account the row is on. Null only for rows written before
   *  accounts existed and never edited since. */
  account: string | null;
  /** Shared by the two legs of one transfer, and null on everything else. */
  transfer_group: string | null;
  tags: TagOnRow[];
}

export interface Category {
  id: number;
  name: string;
  type: "Income" | "Expense";
}

/** A label a transaction can carry any number of. */
export interface Tag {
  id: number;
  name: string;
  /** How many transactions carry it, so the list can lead with what matters
   *  and an unused tag is visibly unused. */
  uses: number;
}

/** A tag as it arrives attached to a transaction: no count, since the count
 *  is a fact about the tag and not about this row. */
export interface TagOnRow {
  id: number;
  name: string;
}

/** A savings target and how far along it is. `saved` is summed by the
 *  server on every read, never stored. */
export interface Goal {
  id: number;
  name: string;
  target: string;
  target_date: string | null;
  account_id: number | null;
  account: string | null;
  saved: string;
  contributions: number;
  archived: boolean;
}

/** Money set aside towards a goal. A negative amount is a withdrawal. */
export interface Contribution {
  id: number;
  date: string;
  amount: string;
  note: string | null;
}

/** One line of a CSV, as the server read it. A row carrying `skip` cannot
 *  be imported and says why. */
export interface ImportRow {
  line: number;
  skip?: string;
  date?: string;
  amount?: string;
  type?: "Income" | "Expense";
  description?: string;
  category_id?: number;
  category?: string | null;
}

export interface ImportReading {
  /** Which of the known columns were recognised in the header. */
  columns: string[];
  rows: ImportRow[];
  /** Reasons the whole file is unusable, as opposed to one row. */
  problems: string[];
  summary: { readable: number; skipped: number };
}

export type Cadence = "weekly" | "monthly" | "yearly";

/** A transaction template with a schedule. It writes ordinary rows marked
 *  with its id; it does not own them. */
export interface RecurringRule {
  id: number;
  description: string;
  amount: string;
  type: "Income" | "Expense";
  cadence: Cadence;
  day_of_month: number | null;
  next_run_on: string;
  ends_on: string | null;
  paused: boolean;
  category_id: number;
  category: string;
  account_id: number | null;
  account: string | null;
  /** How many transactions it has written so far. */
  written: number;
}

export type AccountKind = "Bank" | "Cash" | "Card" | "Wallet" | "Other";

/** An account and its balance. The balance is derived by the server on
 *  every read, never stored, so it cannot disagree with the rows. */
export interface AccountRow {
  id: number;
  name: string;
  kind: AccountKind;
  opening_balance: string;
  balance: string;
  transactions: number;
  archived: boolean;
}

/** What sits on an account, so a delete can say what it will move. */
export interface AccountUsage {
  transactions: number;
  transfers: number;
}

export interface TransferSubmission {
  from_account_id: number;
  to_account_id: number;
  amount: string;
  date: string;
  description?: string;
}

export interface BudgetRow {
  id: number;
  category: string;
  month: string;
  limit: string;
  /** Whether what is left over carries into the next month. */
  rollover: boolean;
  /** What the previous month carried in. Negative when it overspent. */
  rollover_in: string;
  category_id: number;
}

export interface BudgetVsActualRow {
  category: string;
  limit: string;
  actual: string;
  /** limit + rollover_in - actual, so it already accounts for the carry. */
  difference: string;
  rollover_in: string;
  rollover: boolean;
}

/* The reporting series. Each is a month plus figures, oldest first, because
 * a chart draws left to right and sorting in the client would be sorting
 * something the database already ordered. */

export interface TrendRow { month: string; income: string; expense: string }
export interface CashflowRow { month: string; net: string; cumulative: string }
export interface NetWorthRow {
  month: string;
  holdings: string;
  cash: string;
  net_worth: string;
}
export interface MerchantRow { payee: string; times: number; total: string }

/** Every series the reporting screen draws, from one request. */
export interface ReportSummary {
  this_month: {
    income: string;
    expense: string;
    net: string;
    transactions: number;
  };
  trend: TrendRow[];
  cashflow: CashflowRow[];
  net_worth: NetWorthRow[];
  merchants: MerchantRow[];
  spend_by_category: { category: string; total: string }[];
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

/** What the server says about the slice of results it just sent. */
export interface PageInfo {
  number: number;
  per_page: number;
  total: number;
  pages: number;
}

/** Every way the ledger can be narrowed. All optional, all from the URL. */
export interface TransactionFilters {
  q?: string;
  from?: string;
  to?: string;
  type?: string;
  category_id?: string;
  account_id?: string;
  tag_id?: string;
  min?: string;
  max?: string;
  sort?: string;
  direction?: string;
  page?: string;
  per_page?: string;
}

export interface TransactionSubmission {
  date: string;
  category_id: number;
  amount: string;
  type: string;
  description?: string;
  /** Optional: the server files the row on the default account when the
   *  form does not say. */
  account_id?: number;
  /** The whole set of tags for this row. Absent leaves them untouched; an
   *  empty list takes them all off. */
  tag_ids?: number[];
}

const query = (params: Record<string, string>) =>
  "?" + new URLSearchParams(params).toString();

/**
 * Build a query string, dropping anything empty.
 *
 * An empty parameter is not the same as an absent one to a reader looking
 * at the URL, and "?q=&type=" in a shared link says a filter is set when
 * none is.
 */
function queryOf(filters: TransactionFilters): string {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(name, value);
  }
  const text = params.toString();
  return text ? "?" + text : "";
}

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

  /** Parse a CSV and report what it would do. Writes nothing. */
  examineImport: (text: string, defaultCategoryId?: number) =>
    request<ImportReading>("/import/examine", {
      method: "POST",
      body: { text, default_category_id: defaultCategoryId },
    }),
  /** Write the rows an examine returned. */
  commitImport: (rows: ImportRow[], accountId?: number) =>
    request<{ written: number }>("/import/commit", {
      method: "POST",
      body: { rows, account_id: accountId },
    }),

  recurring: () => request<{ items: RecurringRule[] }>("/recurring"),
  addRule: (body: Record<string, unknown>) =>
    request<{ id: number }>("/recurring", { method: "POST", body }),
  editRule: (id: number, body: Record<string, unknown>) =>
    request<void>("/recurring/" + id, { method: "PATCH", body }),
  pauseRule: (id: number, paused: boolean) =>
    request<void>("/recurring/" + id + "/pause",
      { method: "POST", body: { paused: paused ? "1" : "0" } }),
  deleteRule: (id: number) => request<void>("/recurring/" + id, { method: "DELETE" }),
  /** Post whatever this account's rules currently owe. */
  runRules: () =>
    request<{ rules: number; transactions: number }>("/recurring/run",
      { method: "POST" }),

  goals: (includeArchived = false) =>
    request<{ items: Goal[] }>("/goals" + (includeArchived ? "?archived=1" : "")),
  addGoal: (body: Record<string, unknown>) =>
    request<{ id: number }>("/goals", { method: "POST", body }),
  editGoal: (id: number, body: Record<string, unknown>) =>
    request<void>("/goals/" + id, { method: "PATCH", body }),
  archiveGoal: (id: number, archived: boolean) =>
    request<void>("/goals/" + id + "/archive",
      { method: "POST", body: { archived: archived ? "1" : "0" } }),
  deleteGoal: (id: number) => request<void>("/goals/" + id, { method: "DELETE" }),
  contributions: (goalId: number) =>
    request<{ items: Contribution[] }>("/goals/" + goalId + "/contributions"),
  contribute: (goalId: number, body: Record<string, unknown>) =>
    request<{ id: number }>("/goals/" + goalId + "/contributions",
      { method: "POST", body }),
  deleteContribution: (id: number) =>
    request<void>("/contributions/" + id, { method: "DELETE" }),

  tags: () => request<{ items: Tag[] }>("/tags"),
  addTag: (name: string) => request<{ id: number }>("/tags", {
    method: "POST", body: { name },
  }),
  renameTag: (id: number, name: string) =>
    request<void>("/tags/" + id, { method: "PATCH", body: { name } }),
  deleteTag: (id: number) => request<void>("/tags/" + id, { method: "DELETE" }),
  /** The whole set, not one tag: an empty list means "no tags", which has
   *  to be expressible. */
  setTransactionTags: (transactionId: number, tag_ids: number[]) =>
    request<void>("/transactions/" + transactionId + "/tags",
      { method: "PUT", body: { tag_ids } }),

  accounts: (includeArchived = false) =>
    request<{ items: AccountRow[] }>(
      "/accounts" + (includeArchived ? "?archived=1" : "")),
  addAccount: (body: Record<string, string>) =>
    request<{ id: number }>("/accounts", { method: "POST", body }),
  editAccount: (id: number, body: Record<string, string>) =>
    request<void>("/accounts/" + id, { method: "PATCH", body }),
  archiveAccount: (id: number, archived: boolean) =>
    request<void>("/accounts/" + id + "/archive",
      { method: "POST", body: { archived: archived ? "1" : "0" } }),
  accountUsage: (id: number) => request<AccountUsage>("/accounts/" + id + "/usage"),
  deleteAccount: (id: number, reassignTo?: number) =>
    request<void>("/accounts/" + id +
      (reassignTo === undefined ? "" : query({ reassign_to: String(reassignTo) })),
      { method: "DELETE" }),
  transfer: (body: TransferSubmission) =>
    request<{ transfer_group: string }>("/accounts/transfer",
      { method: "POST", body: body as unknown as Record<string, string> }),
  deleteTransfer: (group: string) =>
    request<void>("/transfers/" + group, { method: "DELETE" }),

  transactions: (filters: TransactionFilters = {}) =>
    request<{ items: TransactionRow[]; page: PageInfo }>(
      "/transactions" + queryOf(filters)),
  /** Where the browser should be pointed to download the current view. */
  exportUrl: (filters: TransactionFilters = {}) =>
    BASE + "/transactions/export.csv" + queryOf(filters),
  transaction: (id: number) =>
    request<TransactionSubmission & { id: number; tags: TagOnRow[] }>(
      "/transactions/" + id),
  addTransaction: (body: TransactionSubmission) =>
    request<{ id: number }>("/transactions", { method: "POST", body }),
  editTransaction: (id: number, body: TransactionSubmission) =>
    request<void>("/transactions/" + id, { method: "PATCH", body }),
  deleteTransaction: (id: number) =>
    request<void>("/transactions/" + id, { method: "DELETE" }),

  budgets: () => request<{ items: BudgetRow[] }>("/budgets"),
  setBudget: (category_id: number, month: string, limit: string,
              rollover = false) =>
    request<void>("/budgets", {
      method: "PUT",
      body: { category_id, month, limit, rollover: rollover ? "1" : "0" },
    }),

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

  /** The opening screen in one request rather than two. */
  dashboard: () => request<DashboardPayload>("/reports/dashboard"),
  portfolio: () => request<PortfolioReport>("/reports/portfolio"),
  /* Seven queries behind one request. Splitting them into four calls the
     charts could each own would be tidier code and about a second slower,
     because what costs here is reaching the database at all. */
  summary: (months = 12) =>
    request<ReportSummary>("/reports/summary" + query({ months: String(months) })),
  categorySpend: (month: string) =>
    request<{ items: { category: string; total: string }[] }>(
      "/reports/category-spend" + query({ month })),
  budgetVsActual: (month: string) =>
    request<{ items: BudgetVsActualRow[] }>(
      "/reports/budget-vs-actual" + query({ month })),
};
