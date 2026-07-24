import os
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, redirect, render_template, request, session, url_for

from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
# Stable dev fallback so existing sessions survive an auto-reload.
# Override with the SECRET_KEY env var in any non-dev environment.
app.secret_key = os.environ.get("SECRET_KEY") or "dev-only-spendly-secret-key"  # dev only

# Ensure the data layer is ready before any route is hit (spec §6).
# init_db() is idempotent; seed_db() short-circuits when users already exist.
with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #


def _safe_next(target):
    """Return `target` only if it is a same-origin path; else fall back to the landing page.

    A safe `next` must:
      - be a non-empty string
      - parse to a URL with no scheme and no netloc
      - start with a single "/" and NOT start with "//" or "/\\"
        (the latter two are protocol-relative URLs that browsers treat as off-site)

    Used by /login to block open-redirect attacks via ?next=https://evil.example/...
    """
    if not target or not isinstance(target, str):
        return url_for("landing")
    # Reject protocol-relative ("//host") and backslash-trick ("/\\host") URLs.
    if target.startswith("//") or target.startswith("/\\"):
        return url_for("landing")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return url_for("landing")
    if not target.startswith("/"):
        return url_for("landing")
    return target


def _format_iso_to_mon_dd(iso_str):
    """Convert an ISO 'YYYY-MM-DD' date string to a 'Mon DD' label.

    The profile template renders `transaction.date` as a short human label
    (e.g. 'Jan 15'). The DB stores dates as ISO strings, so we parse them
    here and reformat. Returns the original string on parse failure so a
    bad row never crashes the profile page.
    """
    if not iso_str:
        return ""
    try:
        return datetime.strptime(iso_str, "%Y-%m-%d").strftime("%b %d")
    except (TypeError, ValueError):
        return iso_str


def _format_iso_month_year(iso_str):
    """Convert an ISO datetime string to a 'Mon YYYY' label (e.g. 'Jan 2023').

    users.created_at is stored as 'YYYY-MM-DD HH:MM:SS' (datetime('now')).
    Returns the original string on parse failure.
    """
    if not iso_str:
        return ""
    # Try the full datetime form first; fall back to date-only.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(iso_str, fmt).strftime("%b %Y")
        except (TypeError, ValueError):
            continue
    return iso_str


def _parse_iso_date(value):
    """Parse a 'YYYY-MM-DD' string to a datetime.date, or None on any failure.

    Lenient: None, empty string, or anything that doesn't strptime cleanly
    is treated as absent (returns None, never raises). Mirrors the
    safety-first pattern of _format_iso_to_mon_dd / _format_iso_month_year
    so a bad query-string value cannot 500 the profile page.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _format_iso_long(iso_str):
    """Format a 'YYYY-MM-DD' string as 'Mon D, YYYY' (e.g. 'Jan 1, 2026').

    Cross-platform: avoids the POSIX-only `%-d` directive that raises on
    Windows; we strip a leading zero post-format. Returns the original
    string on parse failure.
    """
    if not iso_str:
        return ""
    try:
        d = datetime.strptime(iso_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return iso_str
    # "%b %d, %Y" pads single-digit days to "Jan 01, 2026"; we trim the
    # leading zero so the badge reads "Jan 1, 2026" on every platform.
    return d.strftime("%b %d, %Y").replace(" 0", " ")


@app.context_processor
def inject_current_user():
    """Expose the logged-in user (or None) to every template.

    Templates check `current_user` to render auth-aware navbar items.
    We hit the DB only when there is a session user_id, and we only
    fetch the columns we need (id, name) — never the password hash.
    """
    user_id = session.get("user_id")
    if not user_id:
        return {"current_user": None}
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        # Stale session pointing at a deleted user — clear it so the
        # navbar falls back to the logged-out state.
        session.clear()
        return {"current_user": None}
    return {"current_user": {"id": row["id"], "name": row["name"]}}


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Already signed in? Bounce away from the registration form. We only
    # guard the GET branch — a logged-in user POSTing the form can still
    # legitimately create another account.
    if request.method == "GET" and session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "POST":
        # Form has `required` on every field — that is browser-side nicety only.
        # Re-validate server-side and normalise before insert.
        name = request.form.get("name") or ""
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not name or not email or not password:
            return (
                render_template("register.html", error="All fields are required."),
                200,
            )

        password_hash = generate_password_hash(password)

        # Let the UNIQUE constraint on users.email do the duplicate check —
        # pre-checking with a SELECT would open a race condition. Catch
        # IntegrityError and map it to a user-friendly message.
        conn = get_db()
        try:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            conn.commit()
            user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            return (
                render_template(
                    "register.html",
                    error="An account with that email already exists.",
                ),
                200,
            )
        finally:
            conn.close()

        # Log the user in immediately, then POST/Redirect/GET to the profile page.
        session["user_id"] = user_id
        return redirect(url_for("profile"))

    # GET — just render the form.
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # Already signed in? Don't show the sign-in form. We only guard the
    # GET branch so a logged-in user can still POST credentials to switch
    # accounts.
    if request.method == "GET" and session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "POST":
        # Form has `required` on every field — that is browser-side nicety only.
        # Re-validate server-side and normalise before lookup.
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        # `next` may come from the hidden form field (preserved on re-render)
        # or directly from the query string on a fresh GET that was POSTed.
        next_target = request.form.get("next") or request.args.get("next") or ""

        if not email or not password:
            return (
                render_template(
                    "login.html", error="All fields are required.", next=next_target
                ),
                200,
            )

        # Look up the user by normalised email.
        conn = get_db()
        try:
            user = conn.execute(
                "SELECT id, password_hash FROM users WHERE email = ?", (email,)
            ).fetchone()
        finally:
            conn.close()

        # Single, generic error for both "no such user" and "wrong password" —
        # distinguishes nothing, so it cannot be used to enumerate accounts.
        invalid = "Invalid email or password."
        if user is None or not check_password_hash(user["password_hash"], password):
            return (
                render_template("login.html", error=invalid, next=next_target),
                200,
            )

        # Authenticated — mark the session and POST/Redirect/GET to a safe target.
        session["user_id"] = user["id"]
        # If no next target provided, default to profile page
        if not next_target:
            next_target = url_for("profile")
        return redirect(_safe_next(next_target))

    # GET — render the form, preserving ?next= so it survives re-render.
    next_target = request.args.get("next") or ""
    return render_template("login.html", next=next_target)


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/logout")
def logout():
    # Clear the session (removes user_id and anything else we've added),
    # then bounce to the public landing page. Safe to call when not logged in.
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    # Check if user is logged in
    if not session.get("user_id"):
        return redirect(url_for("login"))

    # --- Date filter (Step 6) -----------------------------------------
    # Read the optional ?from= / ?to= query params. Both are validated
    # leniently via _parse_iso_date — unparseable input is treated as
    # absent so a bad URL never 500s the page. If both bounds are
    # present and the lower bound is later than the upper, swap them
    # so the resulting BETWEEN clause is well-formed.
    from_date = _parse_iso_date(request.args.get("from"))
    to_date = _parse_iso_date(request.args.get("to"))
    if from_date and to_date and from_date > to_date:
        from_date, to_date = to_date, from_date

    # Build a single parameterized WHERE fragment + params tuple. The
    # fragment is one of four STATIC string literals — user input flows
    # only through the ? placeholders. This block is then appended
    # identically to all four expense queries so they cannot drift.
    date_clause, date_params = "", ()
    if from_date and to_date:
        date_clause = " AND date BETWEEN ? AND ?"
        date_params = (from_date.isoformat(), to_date.isoformat())
    elif from_date:
        date_clause = " AND date >= ?"
        date_params = (from_date.isoformat(),)
    elif to_date:
        date_clause = " AND date <= ?"
        date_params = (to_date.isoformat(),)

    user_id = session["user_id"]
    conn = get_db()
    try:
        # User info card — read name, email, and member_since from the DB.
        # Stale-session safety: if the user row was deleted out from under
        # the session, clear the session and bounce to /login.
        user_row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user_row is None:
            session.clear()
            return redirect(url_for("login"))

        # Derive initials from the user's name (first letter of first word +
        # first letter of last word; fall back to first two letters if a
        # single-word name, and to "?" if the name is too short).
        name_parts = user_row["name"].split()
        if len(name_parts) >= 2:
            initials = (name_parts[0][0] + name_parts[-1][0]).upper()
        else:
            initials = user_row["name"][0:2].upper() if len(user_row["name"]) >= 2 else "?"

        # Format member_since as "Mon YYYY" (e.g. "Jan 2023") from the
        # ISO timestamp stored in users.created_at.
        member_since = _format_iso_month_year(user_row["created_at"])

        user_data = {
            "name": user_row["name"],
            "email": user_row["email"],
            "member_since": member_since,
            "initials": initials,
        }

        # Summary stats — derived from the expenses table for the current user.
        # Read-only SELECTs, so no commit is required. The date_clause is
        # appended to the WHERE so stats reflect the active filter.
        total_row = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) AS total "
            f"FROM expenses WHERE user_id = ?{date_clause}",
            (user_id, *date_params),
        ).fetchone()
        total = total_row["total"]

        count_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?{date_clause}",
            (user_id, *date_params),
        ).fetchone()
        txn_count = count_row["n"]

        stats = [
            {
                "label": "Total Spent",
                "value": f"₹{total:,.0f}",
                "meta": "",  # "+12% vs last" is out of scope for this step
            },
            {
                "label": "Transactions",
                "value": str(txn_count),
                "meta": "this month",  # static label; matches the original copy
            },
            {
                "label": "Budget Left",
                "value": "—",  # em-dash; budgets feature not yet implemented
                "meta": "",
            },
        ]

        # Recent transactions for this user — most recent first, capped at 10.
        # All rows in the expenses table are outflows, so amount is always
        # rendered with a leading minus sign (no positive/Income case).
        txn_rows = conn.execute(
            f"""
            SELECT date, description, category, amount
            FROM expenses
            WHERE user_id = ?{date_clause}
            ORDER BY date DESC, id DESC
            LIMIT 10
            """,
            (user_id, *date_params),
        ).fetchall()
        transactions = [
            {
                "date":        _format_iso_to_mon_dd(row["date"]),
                "description": row["description"] or "",
                "category":    row["category"],
                "amount":      f"-₹{row['amount']:,.2f}",
            }
            for row in txn_rows
        ]

        # Category breakdown — sum per category, ordered by total desc.
        # Only categories with at least one expense are included; a user
        # with 0 expenses (or 0 expenses in the filter window) gets an
        # empty list. Empty state is rendered cleanly by the template.
        cat_rows = conn.execute(
            f"""
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE user_id = ?{date_clause}
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id, *date_params),
        ).fetchall()
        categories = [
            {"category": row["category"], "total": f"₹{row['total']:,.0f}"}
            for row in cat_rows
        ]
    finally:
        conn.close()

    # Template context for the date-filter bar. from_value / to_value
    # echo back the validated (and possibly swapped) ISO bounds so the
    # inputs pre-fill on reload. filter_active gates the "Active filter"
    # badge. filter_label is the human-readable range, or "" when no
    # filter is active (the template's {% if filter_active %} then
    # suppresses the badge entirely).
    from_value = from_date.isoformat() if from_date else ""
    to_value = to_date.isoformat() if to_date else ""
    filter_active = bool(from_date or to_date)
    if filter_active:
        if from_date and to_date:
            filter_label = (
                f"{_format_iso_long(from_date.isoformat())} – "
                f"{_format_iso_long(to_date.isoformat())}"
            )
        elif from_date:
            filter_label = f"From {_format_iso_long(from_date.isoformat())}"
        else:
            filter_label = f"Through {_format_iso_long(to_date.isoformat())}"
    else:
        filter_label = ""

    return render_template("profile.html",
                         user=user_data,
                         stats=stats,
                         transactions=transactions,
                         categories=categories,
                         from_value=from_value,
                         to_value=to_value,
                         filter_active=filter_active,
                         filter_label=filter_label)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)