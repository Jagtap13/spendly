import os
import sqlite3
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

    # Get user info from database (in a real app, we would query the DB)
    # For this step, we're using hardcoded data as specified in the spec
    user_data = {
        "name": "Aditya Jagtap",
        "email": "nitish@example.com",
        "member_since": "Jan 2023"
    }

    # Add initials to user data (first letters of first and last name)
    name_parts = user_data["name"].split()
    if len(name_parts) >= 2:
        user_data["initials"] = (name_parts[0][0] + name_parts[-1][0]).upper()
    else:
        user_data["initials"] = user_data["name"][0:2].upper() if len(user_data["name"]) >= 2 else "?"

    stats = [
        {
            "label": "Total Spent",
            "value": "₹18,240",
            "meta": "+12% vs last"
        },
        {
            "label": "Transactions",
            "value": "42",
            "meta": "this month"
        },
        {
            "label": "Budget Left",
            "value": "₹6,760",
            "meta": "43% remaining"
        }
    ]

    transactions = [
        {
            "date": "Jan 15",
            "description": "Grocery Store",
            "category": "Groceries",
            "amount": "-₹1,240.50"
        },
        {
            "date": "Jan 12",
            "description": "Uber Ride",
            "category": "Transport",
            "amount": "-₹345.00"
        },
        {
            "date": "Jan 10",
            "description": "Salary Credit",
            "category": "Income",
            "amount": "+₹45,000.00"
        },
        {
            "date": "Jan 8",
            "description": "Restaurant",
            "category": "Dining",
            "amount": "-₹890.25"
        }
    ]

    categories = [
        {"category": "Groceries", "total": "₹4,200"},
        {"category": "Transport", "total": "₹1,850"},
        {"category": "Dining", "total": "₹2,100"},
        {"category": "Entertainment", "total": "₹950"},
        {"category": "Utilities", "total": "₹1,300"}
    ]

    return render_template("profile.html",
                         user=user_data,
                         stats=stats,
                         transactions=transactions,
                         categories=categories)


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