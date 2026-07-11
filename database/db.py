# Step 1 — Database Setup
#
# Replaces the student-facing stub with a working SQLite data layer.
# Spec: .claude/specs/01-database-setup.md
#
# Public surface (used by app.py and tests):
#   DB_PATH     — path to the SQLite file, project-root relative
#   CATEGORIES  — the fixed list of expense categories (spec §10)
#   get_db()    — open a connection with row_factory and foreign_keys ON
#   init_db()   — CREATE TABLE IF NOT EXISTS for users + expenses (idempotent)
#   seed_db()   — insert the demo user + 8 sample expenses, only if empty

import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

# Resolve relative to the project root (parent of this file's package),
# not the current working directory, so the DB lives at the repo root
# regardless of where `python app.py` is run from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, "expense_tracker.db")

# Spec §10 — fixed category list, used by seed_db() and by future form rendering.
CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def get_db():
    """Open a SQLite connection with row_factory and FK enforcement enabled.

    Each call returns a fresh connection — keep it that way (Step 2 may add
    request-scoped caching via flask.g if needed). Spec §5A, §11, §12.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # PRAGMA must be issued on every connection — it is per-connection state.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create the users and expenses tables. Safe to call repeatedly.

    Schema mirrors spec §4 exactly. All FK-bearing columns reference
    users.id; ON DELETE CASCADE is intentional so that removing a user
    also removes their expenses (matches user expectation in later steps).
    """
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL    NOT NULL,
                category    TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                description TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db():
    """Insert the demo user and 8 sample expenses — once.

    Returns the number of expenses inserted. If users already exist, this
    is a no-op (spec §5C, §12). All inserts use parameterized SQL (spec §11).
    """
    conn = get_db()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if existing:
            return 0

        # Demo user — password "demo123" hashed with werkzeug's default pbkdf2:sha256.
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        demo_user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()[0]

        # 8 sample expenses, spread across the current month, covering all 7
        # fixed categories — one category (Food) repeats since 8 rows > 7 cats.
        today = date.today()
        first_of_month = today.replace(day=1)
        # Day offsets from the 1st of the month — spread through ~3 weeks.
        day_offsets = [1, 3, 5, 8, 11, 14, 18, 22]

        sample = [
            ("Food",          320.00, "Lunch at the corner cafe"),
            ("Transport",     150.00, "Monthly metro pass"),
            ("Bills",       2400.00, "Electricity bill"),
            ("Health",        650.00, "Pharmacy restock"),
            ("Entertainment", 499.00, "Movie tickets"),
            ("Shopping",      899.00, "New running shoes"),
            ("Other",         200.00, "Misc cash"),
            ("Food",          410.00, "Dinner with friends"),
        ]

        assert len(sample) == 8, "Spec requires exactly 8 sample expenses"
        assert len(sample) == len(day_offsets), "day_offsets must align with sample"

        for (category, amount, description), offset in zip(sample, day_offsets):
            expense_date = first_of_month + timedelta(days=offset - 1)
            conn.execute(
                """
                INSERT INTO expenses (user_id, amount, category, date, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (demo_user_id, amount, category, expense_date.isoformat(), description),
            )

        conn.commit()
        return len(sample)
    finally:
        conn.close()
