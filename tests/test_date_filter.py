"""Route tests for the /profile date filter (Step 6, spec 06).

The test database is isolated per-test in tmp_path via the same
monkeypatch pattern used in tests/test_db.py. Each test gets a fresh
client (and therefore a fresh session) so the unauthenticated tests
are guaranteed to be logged out.
"""

import re
from datetime import date, timedelta

import pytest

import app as app_module
import database.db as db


# Match app._format_iso_long exactly: "%b %d, %Y" with leading zero stripped.
# Keep these helpers in sync with app.py — if the route's format changes,
# update them here too.
def _fmt_long(d):
    return d.strftime("%b %d, %Y").replace(" 0", " ")


# --- Fixtures ---------------------------------------------------------


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Isolated DB file in tmp_path. Mirrors tests/test_db.py exactly."""
    db_file = tmp_path / "test_expense_tracker.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


@pytest.fixture
def seeded_db(fresh_db):
    """fresh_db + init_db() + seed_db() — 8 expenses for the demo user
    all dated within the current month."""
    db.init_db()
    db.seed_db()
    return fresh_db


@pytest.fixture
def client(seeded_db):
    """Flask test client pointed at the seeded temp DB."""
    flask_app = app_module.app
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client):
    """Logs the demo user in via the real /login POST flow."""
    rv = client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
        follow_redirects=False,
    )
    assert rv.status_code == 302, f"login should redirect; got {rv.status_code}"
    return client


# --- Helpers ----------------------------------------------------------


def _first_of_this_month():
    return date.today().replace(day=1)


def _last_of_this_month():
    first = _first_of_this_month()
    if first.month == 12:
        next_first = first.replace(year=first.year + 1, month=1)
    else:
        next_first = first.replace(month=first.month + 1)
    return next_first - timedelta(days=1)


def _expense_dates_in_db():
    """Read the 8 seed dates back from the test DB so the test isn't
    tied to seed_db()'s internal day_offsets list."""
    conn = db.get_db()
    try:
        rows = conn.execute("SELECT date FROM expenses ORDER BY date").fetchall()
    finally:
        conn.close()
    return [date.fromisoformat(r["date"]) for r in rows]


def _count_txn_rows_in_html(html):
    """Count <tr> elements inside the page's single <tbody>. The empty
    state (empty <tbody>) naturally yields 0."""
    m = re.search(r"<tbody>(.*?)</tbody>", html, re.DOTALL)
    if not m:
        return 0
    return len(re.findall(r"<tr>", m.group(1)))


# --- 9 scenarios ------------------------------------------------------


def test_profile_no_params_shows_all_8_seed_expenses(auth_client):
    """GET /profile with no params is regression-clean: all 8 seed
    expenses are visible, matching Step 5 behaviour."""
    rv = auth_client.get("/profile")
    assert rv.status_code == 200
    assert _count_txn_rows_in_html(rv.get_data(as_text=True)) == 8
    # No active filter → badge must not be rendered.
    assert "active-filter-badge" not in rv.get_data(as_text=True)


def test_profile_full_current_month_filter(auth_client):
    """A from=first-of-month & to=last-of-month filter reproduces the
    all-time view (all 8 seed expenses are within the current month).
    The active filter badge is rendered with the formatted range."""
    rv = auth_client.get(
        f"/profile?from={_first_of_this_month().isoformat()}"
        f"&to={_last_of_this_month().isoformat()}"
    )
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert _count_txn_rows_in_html(html) == 8
    # Badge is present and includes the formatted start date.
    assert "active-filter-badge" in html
    assert _fmt_long(_first_of_this_month()) in html


def test_profile_from_after_every_seed_returns_empty(auth_client):
    """A from-date in the far future excludes every seed expense.
    Empty state: ₹0 total, 0 transactions, no category items."""
    future = date.today() + timedelta(days=365)
    rv = auth_client.get(f"/profile?from={future.isoformat()}")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert _count_txn_rows_in_html(html) == 0
    # Total Spent stat shows ₹0
    assert "₹0" in html
    # No <li class="category-item"> elements at all
    assert 'class="category-item"' not in html
    # Badge IS present (filter is active, just empty)
    assert "active-filter-badge" in html


def test_profile_to_before_seed_month_returns_empty(auth_client):
    """A to-date in the distant past excludes every seed expense."""
    past = date.today() - timedelta(days=365)
    rv = auth_client.get(f"/profile?to={past.isoformat()}")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert _count_txn_rows_in_html(html) == 0
    assert "₹0" in html
    assert 'class="category-item"' not in html
    assert "active-filter-badge" in html


def test_profile_narrow_2day_window(auth_client):
    """Pick two consecutive seed dates; only those expenses appear."""
    dates = sorted(_expense_dates_in_db())
    day1, day2 = dates[0], dates[1]
    rv = auth_client.get(
        f"/profile?from={day1.isoformat()}&to={day2.isoformat()}"
    )
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    # The first two seed dates are day_offsets 1 and 3, so 2 expenses.
    assert _count_txn_rows_in_html(html) == 2
    # Both dates appear formatted in the badge.
    assert _fmt_long(day1) in html
    assert _fmt_long(day2) in html


def test_profile_garbage_bounds_are_ignored(auth_client):
    """from=garbage&to=garbage must not 500; treated as no filter, so
    all 8 expenses are visible and the badge is not rendered."""
    rv = auth_client.get("/profile?from=garbage&to=garbage")
    assert rv.status_code == 200
    assert _count_txn_rows_in_html(rv.get_data(as_text=True)) == 8
    assert "active-filter-badge" not in rv.get_data(as_text=True)


def test_profile_reversed_bounds_are_swapped(auth_client):
    """from=last-seed-date&to=first-seed-date (reversed) should behave
    as if swapped: the full range is covered, all 8 expenses appear,
    and the form pre-fills with the canonical order."""
    dates = sorted(_expense_dates_in_db())
    later, earlier = dates[-1], dates[0]
    rv = auth_client.get(
        f"/profile?from={later.isoformat()}&to={earlier.isoformat()}"
    )
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert _count_txn_rows_in_html(html) == 8
    # After swap, the from input is pre-filled with the earlier date and
    # the to input with the later date.
    assert f'value="{earlier.isoformat()}"' in html
    assert f'value="{later.isoformat()}"' in html


def test_profile_unauthenticated_no_params_redirects_to_login(client):
    """GET /profile without auth must redirect to /login. The filter
    must not bypass auth."""
    rv = client.get("/profile", follow_redirects=False)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_profile_unauthenticated_with_filter_redirects_to_login(client):
    """GET /profile?from=...&to=... without auth must still redirect."""
    rv = client.get(
        "/profile?from=2026-01-01&to=2026-01-31", follow_redirects=False
    )
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]
