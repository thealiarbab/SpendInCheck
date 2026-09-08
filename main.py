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
