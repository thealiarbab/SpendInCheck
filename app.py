"""
FinTrack -- optional Flask web frontend.

This layer is NOT part of the CBSE deliverable; main.py is. It exists to show
the same backend driven by a different interface.

It contains zero SQL. Every route calls a function that already exists in
operations.py and renders whatever that function returns, which is the whole
point of keeping operations.py free of print statements: the query layer did
not have to change by even one line to gain a web UI.

Run with:  python app.py    then open http://127.0.0.1:5000
"""

from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, url_for

import operations

app = Flask(__name__)
app.secret_key = "fintrack-dev-key"  # only used for flash messages in local dev


def parse_amount(raw_value):
    """Return the value as a positive float, or None if it is not valid.

    Mirrors the validation main.py does at the prompt, so the web form cannot
    push anything into the database that the CLI would have rejected.
    """
    try:
        amount = float(raw_value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def parse_past_date(raw_value):
    """Return the value as a date that is not in the future, else None."""
    try:
        entered_date = datetime.strptime(raw_value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return entered_date if entered_date <= datetime.now().date() else None


def is_valid_month(raw_value):
    """Return True if the value looks like a 'YYYY-MM' month."""
    try:
        datetime.strptime(raw_value, "%Y-%m")
        return True
    except (TypeError, ValueError):
        return False


@app.route("/")
def dashboard():
    """Landing page: portfolio totals plus the most recent transactions."""
    holdings = operations.portfolio_pnl()
    total_value = sum(float(row[6]) for row in holdings)
    total_pnl = sum(float(row[5]) for row in holdings)
    recent_transactions = operations.get_all_transactions()[:8]
    return render_template(
        "dashboard.html",
        holdings=holdings,
        total_value=total_value,
        total_pnl=total_pnl,
        recent_transactions=recent_transactions,
    )


@app.route("/transactions", methods=["GET", "POST"])
def transactions():
    """List every transaction and handle the add-transaction form."""
    if request.method == "POST":
        txn_date = parse_past_date(request.form.get("txn_date"))
        amount = parse_amount(request.form.get("amount"))
        raw_category = request.form.get("category_id", "")
        txn_type = request.form.get("txn_type")

        if txn_date is None:
            flash("Date must be a real date and cannot be in the future.", "error")
        elif amount is None:
            flash("Amount must be a number greater than 0.", "error")
        elif not raw_category.isdigit() or not operations.category_exists(int(raw_category)):
            flash("Please choose a valid category.", "error")
        elif txn_type not in ("Income", "Expense"):
            flash("Type must be Income or Expense.", "error")
        elif operations.add_transaction(txn_date, int(raw_category), amount, txn_type,
                                        request.form.get("description", "").strip()):
            flash("Transaction added.", "success")
        else:
            flash("Could not add that transaction.", "error")
        return redirect(url_for("transactions"))

    return render_template(
        "transactions.html",
        transactions=operations.get_all_transactions(),
        categories=operations.get_all_categories(),
        today=datetime.now().date().isoformat(),
    )


if __name__ == "__main__":
    app.run(debug=True)
