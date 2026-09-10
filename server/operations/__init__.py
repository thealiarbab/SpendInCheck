"""All business logic and SQL for SpendInCheck (PostgreSQL / Supabase build).

Every function here opens its own connection, runs one or more parameterized
queries, and returns plain Python data (tuples, lists of tuples, dictionaries).
Nothing in this package prints anything -- formatting is the caller's job.
That split is what lets the Jinja pages and the JSON API share one copy of
every query instead of each growing their own.

The functions used to live in a single 745-line module. They are grouped by
domain now, but this package re-exports every public name, so callers still
write `operations.add_transaction(...)` and never import the submodules.
"""

from .users import STARTER_CATEGORIES, create_user, get_user_by_login, username_taken
from .demo import (DEMO_BUDGETS, DEMO_CATEGORIES, DEMO_INVESTMENTS,
                   DEMO_TRANSACTIONS, ensure_demo_user, reset_demo_data)
from .categories import add_category, category_exists, get_all_categories
from .transactions import (add_transaction, delete_transaction,
                           get_all_transactions, get_transaction_by_id,
                           update_transaction)
from .budgets import get_all_budgets, set_budget
from .reports import budget_vs_actual, category_wise_spend
from .investments import (add_investment, get_all_investments, investment_exists,
                          portfolio_pnl, update_investment_price)

# Named explicitly rather than star-imported so that deleting a function
# anywhere below breaks this import loudly instead of silently shrinking
# the public surface.
__all__ = [
    "STARTER_CATEGORIES", "create_user", "get_user_by_login", "username_taken",
    "DEMO_BUDGETS", "DEMO_CATEGORIES", "DEMO_INVESTMENTS", "DEMO_TRANSACTIONS",
    "ensure_demo_user", "reset_demo_data",
    "add_category", "category_exists", "get_all_categories",
    "add_transaction", "delete_transaction", "get_all_transactions",
    "get_transaction_by_id", "update_transaction",
    "get_all_budgets", "set_budget",
    "budget_vs_actual", "category_wise_spend",
    "add_investment", "get_all_investments", "investment_exists",
    "portfolio_pnl", "update_investment_price",
]
