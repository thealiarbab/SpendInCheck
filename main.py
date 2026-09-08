"""
FinTrack -- console menu.

This is the CBSE deliverable: a plain text menu that reads user input,
validates it, calls the matching function in operations.py, and prints
the result. No SQL lives in this file -- that separation is what lets a
Flask frontend be added later without changing operations.py at all.
"""

from datetime import datetime

import operations


def read_non_empty_string(prompt_text):
    """Keep asking until the user types something that is not blank."""
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        print("This field cannot be empty. Please try again.")


def read_positive_amount(prompt_text):
    """Keep asking until the user enters a number greater than zero."""
    while True:
        raw_value = input(prompt_text).strip()
        try:
            amount = float(raw_value)
            if amount > 0:
                return amount
            print("Amount must be greater than 0.")
        except ValueError:
            print("Please enter a valid number.")


def read_non_negative_number(prompt_text):
    """Keep asking until the user enters a number >= 0 (used for quantity/price)."""
    while True:
        raw_value = input(prompt_text).strip()
        try:
            value = float(raw_value)
            if value >= 0:
                return value
            print("Value cannot be negative.")
        except ValueError:
            print("Please enter a valid number.")


def read_valid_date(prompt_text):
    """Keep asking until the user enters a date in YYYY-MM-DD format that
    is not in the future."""
    while True:
        raw_value = input(prompt_text).strip()
        try:
            entered_date = datetime.strptime(raw_value, "%Y-%m-%d").date()
            if entered_date > datetime.now().date():
                print("Date cannot be in the future.")
                continue
            return entered_date
        except ValueError:
            print("Please enter the date as YYYY-MM-DD.")


def read_month_year(prompt_text):
    """Keep asking until the user enters a month in YYYY-MM format."""
    while True:
        raw_value = input(prompt_text).strip()
        try:
            datetime.strptime(raw_value, "%Y-%m")
            return raw_value
        except ValueError:
            print("Please enter the month as YYYY-MM, e.g. 2026-07.")


def read_choice_from(prompt_text, valid_choices):
    """Keep asking until the user picks one of the given valid choices."""
    choices_display = "/".join(valid_choices)
    while True:
        raw_value = input(f"{prompt_text} ({choices_display}): ").strip()
        for choice in valid_choices:
            if raw_value.lower() == choice.lower():
                return choice
        print(f"Please enter one of: {choices_display}")


def read_valid_category_id(prompt_text):
    """Show all categories, then keep asking until the user enters an
    existing category_id."""
    show_categories()
    while True:
        raw_value = input(prompt_text).strip()
        if raw_value.isdigit() and operations.category_exists(int(raw_value)):
            return int(raw_value)
        print("That category_id does not exist. Please pick one from the list above.")


# ---------------------------------------------------------------------------
# TRANSACTIONS
# ---------------------------------------------------------------------------

def add_transaction_menu():
    print("\n-- Add Transaction --")
    txn_date = read_valid_date("Date (YYYY-MM-DD): ")
    category_id = read_valid_category_id("Category ID: ")
    amount = read_positive_amount("Amount: ")
    txn_type = read_choice_from("Type", ["Income", "Expense"])
    description = input("Description (optional): ").strip()

    success = operations.add_transaction(txn_date, category_id, amount, txn_type, description)
    print("Transaction added." if success else "Failed to add transaction.")


def view_transactions_menu():
    print("\n-- All Transactions --")
    rows = operations.get_all_transactions()
    if not rows:
        print("No transactions found.")
        return
    print(f"{'ID':<5}{'Date':<12}{'Category':<15}{'Amount':>10}  {'Type':<8} Description")
    for transaction_id, txn_date, category_name, amount, txn_type, description in rows:
        print(f"{transaction_id:<5}{str(txn_date):<12}{category_name:<15}{amount:>10.2f}  {txn_type:<8} {description or ''}")


def update_transaction_menu():
    print("\n-- Update Transaction --")
    view_transactions_menu()
    raw_id = input("Enter transaction_id to update: ").strip()
    if not raw_id.isdigit() or operations.get_transaction_by_id(int(raw_id)) is None:
        print("That transaction_id does not exist.")
        return
    transaction_id = int(raw_id)

    txn_date = read_valid_date("New date (YYYY-MM-DD): ")
    category_id = read_valid_category_id("New category ID: ")
    amount = read_positive_amount("New amount: ")
    txn_type = read_choice_from("New type", ["Income", "Expense"])
    description = input("New description (optional): ").strip()

    success = operations.update_transaction(transaction_id, txn_date, category_id, amount, txn_type, description)
    print("Transaction updated." if success else "Failed to update transaction.")


def delete_transaction_menu():
    print("\n-- Delete Transaction --")
    view_transactions_menu()
    raw_id = input("Enter transaction_id to delete: ").strip()
    if not raw_id.isdigit() or operations.get_transaction_by_id(int(raw_id)) is None:
        print("That transaction_id does not exist.")
        return
    transaction_id = int(raw_id)

    confirm = input(f"Are you sure you want to delete transaction {transaction_id}? (y/n): ").strip().lower()
    if confirm != "y":
        print("Deletion cancelled.")
        return

    success = operations.delete_transaction(transaction_id)
    print("Transaction deleted." if success else "Failed to delete transaction.")


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------

def add_category_menu():
    print("\n-- Add Category --")
    category_name = read_non_empty_string("Category name: ")
    category_type = read_choice_from("Category type", ["Income", "Expense"])
    success = operations.add_category(category_name, category_type)
    print("Category added." if success else "Failed to add category (name may already exist).")


def show_categories():
    rows = operations.get_all_categories()
    if not rows:
        print("No categories found.")
        return
    print(f"{'ID':<5}{'Name':<20}Type")
    for category_id, category_name, category_type in rows:
        print(f"{category_id:<5}{category_name:<20}{category_type}")


def view_categories_menu():
    print("\n-- All Categories --")
    show_categories()


# ---------------------------------------------------------------------------
# BUDGETS
# ---------------------------------------------------------------------------

def set_budget_menu():
    print("\n-- Set Monthly Budget --")
    category_id = read_valid_category_id("Category ID: ")
    month_year = read_month_year("Month (YYYY-MM): ")
    budget_limit = read_positive_amount("Budget limit: ")
    success = operations.set_budget(category_id, month_year, budget_limit)
    print("Budget saved." if success else "Failed to save budget.")


def view_budgets_menu():
    print("\n-- All Budgets --")
    rows = operations.get_all_budgets()
    if not rows:
        print("No budgets found.")
        return
    print(f"{'ID':<5}{'Category':<15}{'Month':<10}Limit")
    for budget_id, category_name, month_year, budget_limit in rows:
        print(f"{budget_id:<5}{category_name:<15}{month_year:<10}{budget_limit:.2f}")


# ---------------------------------------------------------------------------
# REPORTS
# ---------------------------------------------------------------------------

def category_wise_spend_menu():
    print("\n-- Report: Category-wise Spend --")
    month_year = read_month_year("Month (YYYY-MM): ")
    rows = operations.category_wise_spend(month_year)
    if not rows:
        print("No expenses found for that month.")
        return
    print(f"{'Category':<20}Total Spent")
    for category_name, total_spent in rows:
        print(f"{category_name:<20}{total_spent:.2f}")
