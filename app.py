import os
import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for

from werkzeug.security import generate_password_hash

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


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
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

        # Log the user in immediately, then POST/Redirect/GET to /profile.
        session["user_id"] = user_id
        return redirect(url_for("profile"))

    # GET — just render the form.
    return render_template("register.html")


@app.route("/login")
def login():
    return render_template("login.html")


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
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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