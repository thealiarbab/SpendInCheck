"""
FinTrack -- console menu.

This is the CBSE deliverable: a plain text menu that reads user input,
validates it, calls the matching function in operations.py, and prints
the result. No SQL lives in this file -- that separation is what lets a
Flask frontend be added later without changing operations.py at all.
"""

from datetime import datetime

import operations
