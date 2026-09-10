"""The server-rendered Jinja pages.

This is the original web interface, unchanged in behaviour. It is being
replaced screen by screen by the React client under /app, and this whole
module is deleted once that port is complete -- which is why the routes are
still attached straight to the app rather than to a Blueprint. A Blueprint
would namespace every endpoint (dashboard -> web.dashboard) and force an edit
to all fourteen url_for() calls across the templates, for a layer with a
known expiry date.

Contains no SQL. Every route calls a function from server.operations.
"""

from datetime import datetime

from flask import (flash, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from server import operations


PUBLIC_ENDPOINTS = ("landing", "sign_in", "register", "demo_login", "static")

# A public account anyone can try. The credentials are fixed here rather than
# stored as changeable settings, and its data is rebuilt on every sign-in and
# sign-out, so visitors can edit and delete freely without spoiling it.
DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@spendincheck.com"
DEMO_PASSWORD = "demo1234"


def demo_user_id():
    """The demo account's id, creating the account on first use."""
    return operations.ensure_demo_user(
        DEMO_USERNAME, DEMO_EMAIL, generate_password_hash(DEMO_PASSWORD))


def is_demo(user_id):
    """True when this session is using the shared demo account."""
    return user_id is not None and user_id == session.get("demo_id")


def current_user_id():
    """The signed-in account's id, or None when nobody is signed in."""
    return session.get("user_id")


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


def register(app):
    """Attach every page route to the given app.

    Called by the factory. Taking the app as an argument rather than
    importing it is what keeps this module free of a circular import
    back into server.app.
    """
    @app.context_processor
    def template_flags():
        """Make the demo state available to every template."""
        return {"in_demo": is_demo(current_user_id())}


    @app.before_request
    def require_sign_in():
        """Send anyone who is not signed in to the sign-in page.

        Every page except the landing page, sign-in and registration needs an
        account, because all data is stored per user and there is nothing
        meaningful to show without knowing whose ledger to read.
        """
        if current_user_id() or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        return redirect(url_for("sign_in"))


    @app.route("/register", methods=["GET", "POST"])
    def register():
        """Create a new account, then sign it in."""
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not (3 <= len(username) <= 30) or not username.replace("_", "").isalnum():
                flash("Username must be 3-30 characters, letters, digits or underscores.", "error")
            elif "@" not in email or "." not in email.split("@")[-1]:
                flash("Please enter a valid email address.", "error")
            elif len(password) < 8:
                flash("Password must be at least 8 characters.", "error")
            else:
                if username.lower() == DEMO_USERNAME or email.lower() == DEMO_EMAIL:
                    flash("That name is reserved for the public demo.", "error")
                    return redirect(url_for("register"))
                taken = operations.username_taken(username, email)
                if taken:
                    flash(taken, "error")
                else:
                    user_id = operations.create_user(
                        username, email, generate_password_hash(password))
                    if user_id:
                        session["user_id"] = user_id
                        session["username"] = username
                        flash(f"Welcome, {username}. Your ledger is ready.", "success")
                        return redirect(url_for("dashboard"))
                    flash("Could not create that account.", "error")
            return redirect(url_for("register"))
        return render_template("register.html")


    @app.route("/sign-in", methods=["GET", "POST"])
    def sign_in():
        """Sign in with a username or email plus password."""
        if request.method == "POST":
            login = request.form.get("login", "").strip()
            password = request.form.get("password", "")
            account = operations.get_user_by_login(login)
            # One message for both cases, so this cannot be used to discover
            # which usernames exist.
            if account and check_password_hash(account[3], password):
                # Reaching the demo through the ordinary form must behave the same
                # as the /demo link, or its data would drift.
                if account[1] == DEMO_USERNAME:
                    return redirect(url_for("demo_login"))
                session["user_id"] = account[0]
                session["username"] = account[1]
                return redirect(url_for("dashboard"))
            flash("Incorrect username or password.", "error")
            return redirect(url_for("sign_in"))
        return render_template("sign_in.html")


    @app.route("/demo")
    def demo_login():
        """Sign in to the shared demo account, rebuilding its data first."""
        user_id = demo_user_id()
        if user_id is None:
            flash("The demo is unavailable right now.", "error")
            return redirect(url_for("landing"))
        operations.reset_demo_data(user_id)
        session.clear()
        session["user_id"] = user_id
        session["username"] = DEMO_USERNAME
        session["demo_id"] = user_id
        flash("You are exploring the demo account. Anything you change here is "
              "reset when you sign out.", "success")
        return redirect(url_for("dashboard"))


    @app.route("/sign-out")
    def sign_out():
        """Clear the session and return to the front page.

        If this was the demo account, its data is rebuilt on the way out so the
        next visitor starts from the same place.
        """
        if is_demo(current_user_id()):
            operations.reset_demo_data(current_user_id())
        session.clear()
        return redirect(url_for("landing"))

    @app.route("/")
    def landing():
        """Public front page. Shown to everyone, signed in or not."""
        return render_template("landing.html", signed_in=bool(current_user_id()))


    @app.route("/dashboard")
    def dashboard():
        """Landing page: portfolio totals plus the most recent transactions."""
        holdings = operations.portfolio_pnl(current_user_id())
        total_value = sum(float(row[6]) for row in holdings)
        total_pnl = sum(float(row[5]) for row in holdings)
        recent_transactions = operations.get_all_transactions(current_user_id())[:8]
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
            elif not raw_category.isdigit() or not operations.category_exists(current_user_id(), int(raw_category)):
                flash("Please choose a valid category.", "error")
            elif txn_type not in ("Income", "Expense"):
                flash("Type must be Income or Expense.", "error")
            elif operations.add_transaction(current_user_id(), txn_date, int(raw_category), amount, txn_type,
                                            request.form.get("description", "").strip()):
                flash("Transaction added.", "success")
            else:
                flash("Could not add that transaction.", "error")
            return redirect(url_for("transactions"))

        return render_template(
            "transactions.html",
            transactions=operations.get_all_transactions(current_user_id()),
            categories=operations.get_all_categories(current_user_id()),
            today=datetime.now().date().isoformat(),
        )


    @app.route("/transactions/<int:transaction_id>/delete", methods=["POST"])
    def delete_transaction(transaction_id):
        """Delete one transaction, then return to the list."""
        if operations.delete_transaction(current_user_id(), transaction_id):
            flash(f"Transaction {transaction_id} deleted.", "success")
        else:
            flash(f"No transaction with id {transaction_id}.", "error")
        return redirect(url_for("transactions"))


    @app.route("/categories", methods=["GET", "POST"])
    def categories():
        """List categories and handle the add-category form."""
        if request.method == "POST":
            category_name = request.form.get("category_name", "").strip()
            category_type = request.form.get("category_type")
            if not category_name:
                flash("Category name cannot be empty.", "error")
            elif category_type not in ("Income", "Expense"):
                flash("Type must be Income or Expense.", "error")
            elif operations.add_category(current_user_id(), category_name, category_type):
                flash(f"Category '{category_name}' added.", "success")
            else:
                flash("Could not add that category -- the name may already exist.", "error")
            return redirect(url_for("categories"))

        return render_template("categories.html", categories=operations.get_all_categories(current_user_id()))


    @app.route("/budgets", methods=["GET", "POST"])
    def budgets():
        """List budgets and handle the set-budget form."""
        if request.method == "POST":
            raw_category = request.form.get("category_id", "")
            month_year = request.form.get("month_year", "")
            budget_limit = parse_amount(request.form.get("budget_limit"))

            if not raw_category.isdigit() or not operations.category_exists(current_user_id(), int(raw_category)):
                flash("Please choose a valid category.", "error")
            elif not is_valid_month(month_year):
                flash("Month must be in YYYY-MM format.", "error")
            elif budget_limit is None:
                flash("Budget limit must be a number greater than 0.", "error")
            elif operations.set_budget(current_user_id(), int(raw_category), month_year, budget_limit):
                flash("Budget saved.", "success")
            else:
                flash("Could not save that budget.", "error")
            return redirect(url_for("budgets"))

        return render_template(
            "budgets.html",
            budgets=operations.get_all_budgets(current_user_id()),
            categories=operations.get_all_categories(current_user_id()),
            this_month=datetime.now().strftime("%Y-%m"),
        )


    @app.route("/investments", methods=["GET", "POST"])
    def investments():
        """List investments and handle the add-investment form."""
        if request.method == "POST":
            asset_name = request.form.get("asset_name", "").strip()
            asset_type = request.form.get("asset_type")
            buy_date = parse_past_date(request.form.get("buy_date"))
            buy_price = parse_amount(request.form.get("buy_price"))
            quantity = parse_amount(request.form.get("quantity"))
            current_price = parse_amount(request.form.get("current_price"))

            if not asset_name:
                flash("Asset name cannot be empty.", "error")
            elif asset_type not in ("Stock", "Mutual Fund", "FD"):
                flash("Asset type must be Stock, Mutual Fund or FD.", "error")
            elif buy_date is None:
                flash("Buy date must be a real date and cannot be in the future.", "error")
            elif None in (buy_price, quantity, current_price):
                flash("Prices and quantity must all be numbers greater than 0.", "error")
            elif operations.add_investment(current_user_id(), asset_name, asset_type, buy_date,
                                           buy_price, quantity, current_price):
                flash(f"Investment '{asset_name}' added.", "success")
            else:
                flash("Could not add that investment.", "error")
            return redirect(url_for("investments"))

        return render_template(
            "investments.html",
            investments=operations.get_all_investments(current_user_id()),
            today=datetime.now().date().isoformat(),
        )


    @app.route("/investments/<int:investment_id>/price", methods=["POST"])
    def update_price(investment_id):
        """Update one investment's current price, then return to the list."""
        new_price = parse_amount(request.form.get("current_price"))
        if new_price is None:
            flash("Price must be a number greater than 0.", "error")
        elif operations.update_investment_price(current_user_id(), investment_id, new_price):
            flash(f"Price updated for investment {investment_id}.", "success")
        else:
            flash(f"No investment with id {investment_id}.", "error")
        return redirect(url_for("investments"))


    @app.route("/reports")
    def reports():
        """Show both monthly reports for the month given in the query string."""
        month_year = request.args.get("month", "")
        if not is_valid_month(month_year):
            month_year = datetime.now().strftime("%Y-%m")

        return render_template(
            "reports.html",
            month_year=month_year,
            spend_rows=operations.category_wise_spend(current_user_id(), month_year),
            budget_rows=operations.budget_vs_actual(current_user_id(), month_year),
        )
