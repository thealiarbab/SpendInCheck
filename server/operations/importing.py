"""Reading a CSV of transactions into the ledger.

This is the one feature in the application that can create hundreds of
wrong rows from a single click, which is why it is built last and why it
never writes anything the reader has not seen first.

The flow is two steps, deliberately. `examine` parses and reports; nothing
is written. `commit` takes the rows that came back and inserts them. An
import that wrote as it parsed would leave half a file in the ledger when
row 300 turned out to be malformed.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from psycopg2 import Error
from psycopg2.extras import execute_values
from .. import db
from .accounts import default_account_id

# More than anybody pastes by hand, and small enough that one import cannot
# fill an account faster than somebody can undo it.
MAX_ROWS = 2000

# What the columns may be called. Every bank names them differently and
# none of them asks first, so the header is matched against a set of
# aliases rather than demanding one exact spelling.
COLUMN_ALIASES = {
    "date": ("date", "txn date", "transaction date", "value date", "posted"),
    "description": ("description", "narration", "particulars", "details",
                    "memo", "note", "payee", "remarks"),
    "amount": ("amount", "value", "sum"),
    "debit": ("debit", "withdrawal", "withdrawals", "paid out", "money out"),
    "credit": ("credit", "deposit", "deposits", "paid in", "money in"),
    "category": ("category", "type of expense"),
    "type": ("type", "txn type", "transaction type", "dr/cr"),
}

# The date formats worth trying, in the order a wrong guess is least
# damaging. ISO first because it is unambiguous; day-first before
# month-first because everything this ledger is likely to meet is
# day-first, and 03/04 has to resolve one way or the other.
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%b-%Y",
                "%d %b %Y", "%m/%d/%Y", "%Y/%m/%d")


def _normalise(name):
    """A header cell reduced to something comparable."""
    return " ".join((name or "").strip().lower().replace("_", " ").split())


def map_columns(header):
    """Which column holds what, as {field: index}.

    Unrecognised columns are ignored rather than refused: a bank statement
    carries balances, cheque numbers and reference codes that mean nothing
    here, and rejecting the file over them would reject every real file.
    """
    found = {}
    for index, cell in enumerate(header or []):
        name = _normalise(cell)
        for field, aliases in COLUMN_ALIASES.items():
            if name in aliases and field not in found:
                found[field] = index
    return found


def _read_date(text):
    """A date from any of the formats DATE_FORMATS lists, or None."""
    text = (text or "").strip()
    for shape in DATE_FORMATS:
        try:
            return datetime.strptime(text, shape).date()
        except ValueError:
            continue
    return None


def _read_amount(text):
    """A positive Decimal from a cell, or None.

    Strips the things spreadsheets and banks put around numbers: currency
    signs, thousands separators, and the brackets accountants use for a
    negative. The sign is discarded -- direction is decided by which column
    the figure came from, or by the type column, never by a minus that may
    or may not be there.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    negative = raw.startswith("(") and raw.endswith(")")
    for junk in ("(", ")", ",", "₹", "$", "€", "£", " "):
        raw = raw.replace(junk, "")
    raw = raw.strip().lstrip("+")
    if raw.startswith("-"):
        negative = True
        raw = raw[1:]
    if not raw:
        return None

    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    return (value, negative)


def examine(text, categories, default_category_id=None):
    """Parse a CSV and say what it would do. Writes nothing.

    `categories` is {lowercased name: (id, type)} for the account, so a
    named category in the file can be matched to a real one.

    Returns {"columns": {...}, "rows": [...], "problems": [...]}, where each
    row carries either a ready-to-insert record or the reason it cannot be
    used. Every row is reported, good or bad, because a reader deciding
    whether to import 300 rows needs to see the 4 that will be skipped.
    """
    # utf-8-sig, because a file exported from Excel begins with a byte order
    # mark and it would otherwise become part of the first header's name.
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        # A single-column file, or one too short to sniff. Comma is the
        # right guess and a wrong guess here shows up as an unmapped header
        # rather than as silent corruption.
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = next(reader)
    except StopIteration:
        return {"columns": {}, "rows": [], "problems": ["The file is empty."]}

    columns = map_columns(header)
    problems = []
    if "date" not in columns:
        problems.append("No date column. Expected one called Date.")
    if not ({"amount", "debit", "credit"} & set(columns)):
        problems.append("No amount column. Expected Amount, or Debit and Credit.")
    if problems:
        return {"columns": columns, "rows": [], "problems": problems}

    rows = []
    for number, record in enumerate(reader, start=2):
        if number - 1 > MAX_ROWS:
            problems.append(
                f"Only the first {MAX_ROWS} rows were read. Split the file.")
            break
        if not any((cell or "").strip() for cell in record):
            continue
        rows.append(_examine_row(number, record, columns, categories,
                                 default_category_id))

    return {"columns": columns, "rows": rows, "problems": problems}


def _cell(record, columns, field):
    """One field from a row, or "" when the column is absent or short."""
    index = columns.get(field)
    if index is None or index >= len(record):
        return ""
    return (record[index] or "").strip()


def _examine_row(number, record, columns, categories, default_category_id):
    """Turn one CSV line into either an importable record or a reason why not."""
    when = _read_date(_cell(record, columns, "date"))
    if when is None:
        return {"line": number, "skip": "The date could not be read."}

    # A statement with separate debit and credit columns says the direction
    # by which column the figure is in, which is more reliable than any
    # sign convention.
    debit = _read_amount(_cell(record, columns, "debit"))
    credit = _read_amount(_cell(record, columns, "credit"))
    if debit or credit:
        amount, negative = debit or credit
        txn_type = "Expense" if debit else "Income"
    else:
        parsed = _read_amount(_cell(record, columns, "amount"))
        if parsed is None:
            return {"line": number, "skip": "The amount could not be read."}
        amount, negative = parsed
        stated = _normalise(_cell(record, columns, "type"))
        if stated in ("income", "credit", "cr", "deposit", "in"):
            txn_type = "Income"
        elif stated in ("expense", "debit", "dr", "withdrawal", "out"):
            txn_type = "Expense"
        else:
            # No type column: a bracketed or negative figure is money out,
            # which is the near-universal convention in a single-amount
            # export.
            txn_type = "Expense" if negative else "Income"

    named = _normalise(_cell(record, columns, "category"))
    category = categories.get(named)
    if category is None:
        if default_category_id is None:
            return {"line": number,
                    "skip": f"No category called {named!r}." if named
                            else "No category, and no fallback chosen."}
        category_id, category_type = default_category_id, txn_type
        category_name = None
    else:
        category_id, category_type = category
        category_name = named
        # The category decides the direction everywhere else in this
        # application, so it does here too. A file claiming an Expense under
        # Salary is a file that disagrees with itself.
        if category_type in ("Income", "Expense"):
            txn_type = category_type

    return {
        "line": number,
        "date": when.isoformat(),
        "amount": str(amount),
        "type": txn_type,
        "description": _cell(record, columns, "description")[:255],
        "category_id": category_id,
        "category": category_name,
    }


def commit(user_id, rows, account_id=None):
    """Insert examined rows. Returns how many were written.

    One statement for the whole file rather than one per row: a hundred
    inserts is a hundred round trips, and this is the one place somebody
    hands over a hundred at once.

    An unspecified account means the default one, exactly as it does when a
    row is typed in by hand. Leaving it null instead would import rows that
    belong to no account and therefore appear in no balance -- money in the
    ledger that none of the accounts can see.

    Every row is checked against the account's own categories again here.
    The examined rows came back through the browser, so what returns is not
    necessarily what was sent.
    """
    if not rows:
        return 0

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT category_id FROM categories WHERE user_id = %s",
                       (user_id,))
        allowed = {row[0] for row in cursor.fetchall()}

        if account_id is not None:
            cursor.execute("SELECT account_id FROM accounts "
                           " WHERE account_id = %s AND user_id = %s",
                           (account_id, user_id))
            if cursor.fetchone() is None:
                account_id = None
        if account_id is None:
            account_id = default_account_id(user_id)

        values = [
            (user_id, row["date"], row["category_id"], row["amount"],
             row["type"], row.get("description") or None, account_id)
            for row in rows if row.get("category_id") in allowed
        ]
        if not values:
            return 0

        # execute_values sends the rows in pages, so a large file is
        # several statements. Half an imported file is worse than none.
        with db.transaction(connection):
            execute_values(
                cursor,
                "INSERT INTO transactions (user_id, txn_date, category_id, amount, "
                "        txn_type, description, account_id) VALUES %s",
                values)
            written = cursor.rowcount
        return written
    except Error as e:
        print(f"Error importing transactions: {e}")
        return 0
    finally:
        db.close_connection(connection)
