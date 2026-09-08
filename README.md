# FinTrack — Personal Finance & Investment Ledger

CBSE Class XII Computer Science (Code 083) practical project. A menu-driven
Python console app backed by MySQL, using `mysql.connector`.

## Requirements

- Python 3.11+
- MySQL Server running locally
- `mysql-connector-python` (see `requirements.txt`)

## Setup

1. Install the Python dependency:

   ```bash
   pip install -r requirements.txt
   ```

2. Create the database and load seed data (you will be prompted for your
   MySQL root password):

   ```bash
   mysql -u root -p < schema.sql
   ```

3. Open `config.py` and fill in `DB_PASSWORD` with your MySQL root password.

4. Run the app:

   ```bash
   python main.py
   ```

## File structure

- `schema.sql` — table definitions and seed data
- `config.py` — database connection settings
- `db.py` — opens/closes the MySQL connection
- `operations.py` — every SQL query, one function per operation
- `main.py` — the console menu (run this file)
- `VIVA_NOTES.md` — plain-English notes to prepare for the viva

## Notes

- All database logic lives in `operations.py`. `main.py` only handles
  input, validation, and printing — it never contains SQL.
- This separation means a Flask web frontend can later reuse every
  function in `operations.py` without duplicating any SQL.
