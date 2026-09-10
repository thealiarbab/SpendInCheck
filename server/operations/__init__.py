"""All business logic and SQL for SpendInCheck (PostgreSQL / Supabase build).

Every function here opens its own connection, runs one or more parameterized
queries, and returns plain Python data (tuples, lists of tuples, dictionaries).
Nothing in this package prints anything -- formatting is the caller's job.
That split is what let the console app and the web API share one copy of
every query instead of each growing their own.

The functions used to live in a single 745-line module. They are grouped by
domain now, but this package re-exports every public name, so callers still
write `operations.add_transaction(...)` and never import the submodules.
"""

from .users import (STARTER_ACCOUNT, STARTER_CATEGORIES, create_user, get_currency,
                    get_user_by_login, set_currency, user_exists, username_taken)
from .demo import (DEMO_BUDGETS, DEMO_CATEGORIES, DEMO_INVESTMENTS,
                   DEMO_TRANSACTIONS, create_demo_user, delete_demo_user,
                   delete_stale_demo_users, reset_demo_data)
from .accounts import (ACCOUNT_KINDS, TRANSFER_CATEGORY, account_exists,
                       add_account, count_account_use, default_account_id,
                       delete_account, delete_transfer, list_accounts,
                       set_archived, transfer, update_account)
from .categories import (add_category, category_exists, count_category_use,
                         delete_category, get_all_categories, rename_category)
from .transactions import (DEFAULT_PER_PAGE, MAX_PER_PAGE, SORT_COLUMNS,
                           SORT_DIRECTIONS, add_transaction, delete_transaction,
                           get_all_transactions, get_transaction_by_id,
                           recent_and_holdings, search_transactions,
                           update_transaction)
from .tags import (MAX_TAG_LENGTH, add_tag, delete_tag, list_tags, rename_tag,
                   set_transaction_tags, tag_exists, tags_for_transactions)
from .goals import (add_contribution, add_goal, delete_contribution,
                    delete_goal, goal_exists, list_contributions, list_goals,
                    set_goal_archived, update_goal)
from .recurring import (CADENCES, MAX_CATCHUP, add_rule, delete_rule,
                        list_rules, materialise_due, next_date_after,
                        rule_exists, set_rule_paused, update_rule)
from .importing import MAX_ROWS as MAX_IMPORT_ROWS
from .importing import commit as commit_import
from .importing import examine, map_columns
from .budgets import (categories_with_rollover, get_all_budgets,
                      refresh_rollover, set_budget)
from .reports import (SERIES_MONTHS, budget_vs_actual, cashflow_series,
                      category_wise_spend, dashboard_summary, monthly_trend,
                      net_worth_series, top_merchants)
from .investments import (add_investment, delete_investment, get_all_investments,
                          investment_exists, portfolio_pnl,
                          update_investment_price)

# Named explicitly rather than star-imported so that deleting a function
# anywhere below breaks this import loudly instead of silently shrinking
# the public surface.
__all__ = [
    "STARTER_ACCOUNT", "STARTER_CATEGORIES", "create_user", "get_currency", "get_user_by_login",
    "set_currency", "user_exists", "username_taken",
    "DEMO_BUDGETS", "DEMO_CATEGORIES", "DEMO_INVESTMENTS", "DEMO_TRANSACTIONS",
    "create_demo_user", "delete_demo_user", "delete_stale_demo_users",
    "reset_demo_data",
    "ACCOUNT_KINDS", "TRANSFER_CATEGORY", "account_exists", "add_account",
    "count_account_use", "default_account_id", "delete_account",
    "delete_transfer", "list_accounts", "set_archived", "transfer",
    "update_account",
    "add_category", "category_exists", "count_category_use", "delete_category",
    "get_all_categories", "rename_category",
    "DEFAULT_PER_PAGE", "MAX_PER_PAGE", "SORT_COLUMNS", "SORT_DIRECTIONS",
    "add_transaction", "delete_transaction", "get_all_transactions",
    "get_transaction_by_id", "recent_and_holdings", "search_transactions",
    "update_transaction",
    "MAX_TAG_LENGTH", "add_tag", "delete_tag", "list_tags", "rename_tag",
    "set_transaction_tags", "tag_exists", "tags_for_transactions",
    "add_contribution", "add_goal", "delete_contribution", "delete_goal",
    "goal_exists", "list_contributions", "list_goals", "set_goal_archived",
    "update_goal",
    "CADENCES", "MAX_CATCHUP", "add_rule", "delete_rule", "list_rules",
    "materialise_due", "next_date_after", "rule_exists", "set_rule_paused",
    "update_rule",
    "MAX_IMPORT_ROWS", "commit_import", "examine", "map_columns",
    "categories_with_rollover", "get_all_budgets", "refresh_rollover",
    "set_budget",
    "SERIES_MONTHS", "budget_vs_actual", "cashflow_series",
    "category_wise_spend", "dashboard_summary", "monthly_trend",
    "net_worth_series", "top_merchants",
    "add_investment", "delete_investment", "get_all_investments",
    "investment_exists", "portfolio_pnl", "update_investment_price",
]
