"""
Database configuration for SpendInCheck.

Kept separate from db.py so credentials are in exactly one place.

DB_PASSWORD is set to the password of the local MySQL server this project
was tested against. Change it if your MySQL root password is different, and
blank it out before submitting if you would rather not hand in a password.
"""

DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "root"
DB_NAME = "spendincheck"
