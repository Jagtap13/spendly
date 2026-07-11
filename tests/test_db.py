"""Tests for the database layer (Step 1, spec .claude/specs/01-database-setup.md).

Every test points `database.db.DB_PATH` at a fresh file inside `tmp_path`,
so the real `expense_tracker.db` in the project root is never touched and
tests can run in any order without leaking state.
"""

import sqlite3

import pytest
from werkzeug.security import check_password_hash

import database.db as db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Redirect the DB to a temp file and return its path."""
    db_file = tmp_path / "test_expense_tracker.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


# --- get_db() ----------------------------------------------------------------


def test_get_db_sets_row_factory_and_foreign_keys(fresh_db):
    conn = db.get_db()
    try:
        # Spec §5A + §12: row_factory is sqlite3.Row, foreign keys are ON.
        assert conn.row_factory is sqlite3.Row
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


# --- init_db() ---------------------------------------------------------------


def test_init_db_creates_both_tables(fresh_db):
    db.init_db()

    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in rows}
        assert "users" in names
        assert "expenses" in names
    finally:
        conn.close()


def test_init_db_is_idempotent(fresh_db):
    # Spec §5B: safe to call multiple times. We invoke it three times; the
    # third call must not raise (CREATE TABLE IF NOT EXISTS handles it).
    db.init_db()
    db.init_db()
    db.init_db()

    conn = db.get_db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name IN ('users','expenses')"
        ).fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_users_schema_matches_spec(fresh_db):
    db.init_db()
    conn = db.get_db()
    try:
        cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(users)")}
        assert "id" in cols and cols["id"]["pk"] == 1
        assert cols["id"]["type"] == "INTEGER"
        assert cols["name"]["notnull"] == 1 and cols["name"]["type"] == "TEXT"
        assert cols["email"]["notnull"] == 1 and cols["email"]["type"] == "TEXT"
        assert cols["password_hash"]["notnull"] == 1
        assert "created_at" in cols
    finally:
        conn.close()


def test_expenses_schema_matches_spec(fresh_db):
    db.init_db()
    conn = db.get_db()
    try:
        cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(expenses)")}
        assert cols["id"]["pk"] == 1
        assert cols["user_id"]["notnull"] == 1
        assert cols["amount"]["notnull"] == 1 and cols["amount"]["type"] == "REAL"
        assert cols["category"]["notnull"] == 1
        assert cols["date"]["notnull"] == 1
        # description is nullable per spec §4.
        assert cols["description"]["notnull"] == 0
        assert "created_at" in cols
    finally:
        conn.close()


# --- seed_db() ---------------------------------------------------------------


def test_seed_db_inserts_demo_user_and_8_expenses(fresh_db):
    db.init_db()
    inserted = db.seed_db()
    assert inserted == 8

    conn = db.get_db()
    try:
        users = conn.execute("SELECT * FROM users").fetchall()
        assert len(users) == 1
        user = users[0]
        assert user["name"] == "Demo User"
        assert user["email"] == "demo@spendly.com"
        # Spec §11: password must be hashed, not stored in cleartext.
        assert user["password_hash"] != "demo123"
        assert check_password_hash(user["password_hash"], "demo123") is True

        expenses = conn.execute("SELECT * FROM expenses").fetchall()
        assert len(expenses) == 8
        # Every expense belongs to the demo user (FK link).
        assert all(e["user_id"] == user["id"] for e in expenses)
        # Dates in YYYY-MM-DD format, all in the current month.
        for e in expenses:
            assert len(e["date"]) == 10 and e["date"][4] == "-" and e["date"][7] == "-"
        # Spec §5C: at least one expense per category — i.e. all 7 covered.
        cats = {e["category"] for e in expenses}
        assert cats == set(db.CATEGORIES)
    finally:
        conn.close()


def test_seed_db_is_idempotent(fresh_db):
    db.init_db()
    first = db.seed_db()
    second = db.seed_db()
    third = db.seed_db()

    assert first == 8
    assert second == 0
    assert third == 0

    conn = db.get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 8
    finally:
        conn.close()


# --- Constraints (spec §13) --------------------------------------------------


def test_duplicate_email_raises_integrity_error(fresh_db):
    db.init_db()
    db.seed_db()  # creates demo@spendly.com

    conn = db.get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Imposter", "demo@spendly.com", "x"),
            )
        conn.rollback()
    finally:
        conn.close()


def test_expense_with_invalid_user_id_raises_integrity_error(fresh_db):
    db.init_db()
    # No seed_db() — we want a guaranteed-empty users table.
    conn = db.get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date) "
                "VALUES (?, ?, ?, ?)",
                (9999, 100.0, "Food", "2026-07-11"),
            )
        conn.rollback()
    finally:
        conn.close()
