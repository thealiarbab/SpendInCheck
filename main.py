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


def budget_vs_actual_menu():
    print("\n-- Report: Budget vs Actual --")
    month_year = read_month_year("Month (YYYY-MM): ")
    rows = operations.budget_vs_actual(month_year)
    if not rows:
        print("No budgets found for that month.")
        return
    print(f"{'Category':<15}{'Budget':>10}{'Actual':>10}{'Difference':>14}  Status")
    for category_name, budget_limit, actual_spent, difference in rows:
        if difference < 0:
            status = "Over budget"
        elif difference == 0:
            status = "On budget"
        else:
            status = "Under budget"
        print(f"{category_name:<15}{budget_limit:>10.2f}{actual_spent:>10.2f}{difference:>14.2f}  {status}")


def portfolio_pnl_menu():
    print("\n-- Report: Portfolio P&L --")
    rows = operations.portfolio_pnl()
    if not rows:
        print("No investments found.")
        return
    total_value = 0.0
    total_pnl = 0.0
    print(f"{'Asset':<22}{'Type':<13}{'Buy':>10}{'Current':>10}{'Qty':>10}{'P&L':>12}")
    for asset_name, asset_type, buy_price, current_price, quantity, pnl, current_value in rows:
        print(f"{asset_name:<22}{asset_type:<13}{buy_price:>10.2f}{current_price:>10.2f}{quantity:>10.4f}{pnl:>12.2f}")
        total_value += float(current_value)
        total_pnl += float(pnl)
    print("-" * 89)
    print(f"Total portfolio value: {total_value:.2f}")
    print(f"Total portfolio P&L:   {total_pnl:.2f}")


# ---------------------------------------------------------------------------
# INVESTMENTS
# ---------------------------------------------------------------------------

def add_investment_menu():
    print("\n-- Add Investment --")
    asset_name = read_non_empty_string("Asset name: ")
    asset_type = read_choice_from("Asset type", ["Stock", "Mutual Fund", "FD"])
    buy_date = read_valid_date("Buy date (YYYY-MM-DD): ")
    buy_price = read_positive_amount("Buy price: ")
    quantity = read_positive_amount("Quantity: ")
    current_price = read_non_negative_number("Current price: ")

    success = operations.add_investment(asset_name, asset_type, buy_date, buy_price, quantity, current_price)
    print("Investment added." if success else "Failed to add investment.")


def view_investments_menu():
    print("\n-- All Investments --")
    rows = operations.get_all_investments()
    if not rows:
        print("No investments found.")
        return
    print(f"{'ID':<5}{'Asset':<22}{'Type':<13}{'Buy Date':<12}{'Buy Price':>10}{'Qty':>10}{'Current':>10}")
    for investment_id, asset_name, asset_type, buy_date, buy_price, quantity, current_price in rows:
        print(f"{investment_id:<5}{asset_name:<22}{asset_type:<13}{str(buy_date):<12}{buy_price:>10.2f}{quantity:>10.4f}{current_price:>10.2f}")


def update_investment_menu():
    print("\n-- Update Investment Current Price --")
    view_investments_menu()
    raw_id = input("Enter investment_id to update: ").strip()
    if not raw_id.isdigit() or not operations.investment_exists(int(raw_id)):
        print("That investment_id does not exist.")
        return
    investment_id = int(raw_id)
    new_price = read_non_negative_number("New current price: ")
    success = operations.update_investment_price(investment_id, new_price)
    print("Investment updated." if success else "Failed to update investment.")


# ---------------------------------------------------------------------------
# MENU
# ---------------------------------------------------------------------------

MENU_TEXT = """
=========== FinTrack ===========
 1. Add transaction
 2. View all transactions
 3. Update a transaction
 4. Delete a transaction
 5. Add category
 6. View categories
 7. Set monthly budget
 8. View budgets
 9. Report: category-wise spend
10. Report: budget vs actual
11. Add investment
12. View investments
13. Update investment current price
14. Report: portfolio P&L
15. Exit
=================================
"""

MENU_ACTIONS = {
    "1": add_transaction_menu,
    "2": view_transactions_menu,
    "3": update_transaction_menu,
    "4": delete_transaction_menu,
    "5": add_category_menu,
    "6": view_categories_menu,
    "7": set_budget_menu,
    "8": view_budgets_menu,
    "9": category_wise_spend_menu,
    "10": budget_vs_actual_menu,
    "11": add_investment_menu,
    "12": view_investments_menu,
    "13": update_investment_menu,
    "14": portfolio_pnl_menu,
}


def main():
    """Run the FinTrack console menu loop until the user chooses to exit."""
    while True:
        print(MENU_TEXT)
        choice = input("Enter your choice (1-15): ").strip()
        if choice == "15":
            print("Goodbye!")
            break
        action = MENU_ACTIONS.get(choice)
        if action:
            action()
        else:
            print("Invalid choice. Please enter a number from 1 to 15.")


if __name__ == "__main__":
    main()
