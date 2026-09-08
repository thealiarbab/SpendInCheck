"""
All business logic and SQL for FinTrack lives in this module.

Every function here opens its own connection, runs one or more
parameterized queries, and returns plain Python data (tuples, lists
of tuples, dictionaries). Nothing in this file prints anything to
the screen -- that is main.py's job. Keeping the split this way means
a Flask frontend (or any other frontend) can reuse every function
here without touching a single line of SQL.
"""

from mysql.connector import Error

import db
