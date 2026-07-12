# Spec: Registration

## Overview

Turn the placeholder `GET /register` route in `app.py` into a working
end-to-end registration flow. Users submit a name, email, and password
through the existing `register.html` form; the server validates the
input, hashes the password with werkzeug, and persists a new row in
the `users` table. On success the user is shown with the succes message and logged in immediately
(via a session cookie) and redirected to their profile. On failure,
the form re-renders with a human-readable error.

This is the first step that turns Spendly from a static marketing
site into a real multi-user application — every later feature
(profile, expense CRUD, dashboards) assumes a logged-in user.

---

## Depends on

- **Step 1 — Database Setup** (✅ done). The `users` table with
  `name`, `email`, `password_hash`, and the `UNIQUE` constraint on
  `email` already exists. The `get_db()` helper and `werkzeug.security`
  are already used in `database/db.py`.

---

## Routes

- `GET  /register` — render `templates/register.html` — public
- `POST /register` — validate input, create user, start session,
  redirect to `GET /profile` on success or re-render the form with
  an error on failure — public

No other routes change. (`/login`, `/logout`, `/profile` remain as
they are — `/profile` is still a placeholder returning a string in
this step, but it must exist as a route so the redirect target is
valid.)

---

## Database changes

No database changes. The `users` table from Step 1 already supports
this feature. `init_db()` and `seed_db()` are untouched.

---

## Templates

- **Modify:** `templates/register.html`
  - Already shows `{% if error %}`. No structural change needed —
    the backend just needs to pass `error=` on the unhappy path.
  - Keep the existing form fields (`name`, `email`, `password`) and
    copy. Do **not** add a confirm-password field (out of scope for
    this step; the spec deliberately keeps validation minimal).

No new templates.

---

## Files to change

- `app.py` — convert the `/register` route to accept both GET and
  POST, add session handling, and import the new helpers below.

---

## Files to create

None. All logic lives in `app.py` so the route is the single source
of truth for the flow.

---

## New dependencies

No new dependencies.

- `werkzeug.security.generate_password_hash` is already used in
  `database/db.py`; `werkzeug` is in `requirements.txt`.
- Flask's built-in `session` (which needs `app.secret_key`) is the
  only new surface used. **Set `app.secret_key` in `app.py`** to a
  stable value (env var with a dev fallback is fine — see Rules).

---

## Rules for implementation

- **Single Flask app, plain function routes, no blueprints** — match
  the style of the existing routes in `app.py`.
- **No ORMs, no SQLAlchemy.** Use the existing `get_db()` from
  `database/db.py` and parameterised SQL.
- **Parameterised queries only** — never use f-strings or `%` /
  `.format()` to build SQL. The existing `db.py` already follows
  this; match it.
- **Hash passwords with `werkzeug.security.generate_password_hash`**
  using its default scheme (pbkdf2:sha256, same as `seed_db()`).
- **Validate on the server**, not in JS. The `register.html` form
  has `required` on every field — that is browser-side nicety only.
  Re-validate every field server-side.
- **Use `flask.session`** to mark the user as logged in. Store
  `session["user_id"]` (the integer primary key) on success. Do
  **not** store the email, name, or password hash in the session.
- **Set `app.secret_key`** in `app.py`. Prefer reading
  `os.environ.get("SECRET_KEY")` and falling back to a hardcoded
  dev string with a clear `# dev only` comment. The fallback must
  be stable across restarts so existing sessions survive a reload
  during development.
- **On successful registration**, redirect to `/profile` with
  `flask.redirect`. Do **not** return a 200 with a "welcome" page —
  POST/Redirect/Get is the standard pattern and prevents the
  "are you sure you want to resubmit the form?" dialog on refresh.
- **On validation failure**, re-render `register.html` and pass
  `error="..."` so the existing `{% if error %}` block shows it.
  Preserve nothing about the submitted values (a simple empty
  re-render is fine — re-typing is acceptable for v1).
- **Email uniqueness**: rely on the `UNIQUE` constraint from Step 1.
  Catch the `sqlite3.IntegrityError` from the insert and map it to
  a user-friendly `"An account with that email already exists."`
  error. Do **not** pre-check with a `SELECT` — that opens a
  race condition and is the wrong pattern.
- **Normalise email** by stripping leading/trailing whitespace and
  lowercasing before insert and before the duplicate check. Do not
  silently strip whitespace from `name` — show it as-typed.
- **Use CSS variables** for any new styling. No new colors. The
  existing `.auth-error` class in `style.css` already styles the
  error banner — no new CSS is required for this step.
- **All templates must extend `base.html`.** `register.html`
  already does — leave it alone.
- **Do not** add CSRF protection in this step. The course does not
  introduce it until later; adding it now would block later
  learning material.

---

## Definition of done

- [ ] `app.secret_key` is set in `app.py` (env var with a dev
      fallback).
- [ ] `GET /register` still renders `register.html` (no regression).
- [ ] `POST /register` with a valid new email creates a row in
      `users` with a hashed password (verify by inspecting
      `expense_tracker.db`).
- [ ] `POST /register` then redirects (HTTP 302) to `/profile`.
- [ ] After redirect, `session` contains `user_id` matching the
      newly inserted user (verify in the Flask debug output or
      with a temporary `print`).
- [ ] `POST /register` with an email that already exists re-renders
      the form with the error
      `An account with that email already exists.` and a **200**
      response (no redirect).
- [ ] `POST /register` with a missing or empty `name` / `email` /
      `password` re-renders the form with a clear validation error
      and a **200** response. No row is inserted.
- [ ] The password stored in the DB is **not** the plaintext — it
      starts with `pbkdf2:sha256:` (or whatever werkzeug's current
      default prefix is).
- [ ] Email comparison is case-insensitive: registering
      `Alice@Example.com` then `alice@example.com` fails with the
      duplicate-email error.
- [ ] No new pip packages were installed.
- [ ] No SQLAlchemy or any other ORM is imported anywhere.
- [ ] Every SQL statement uses `?` placeholders — no f-strings,
      `%`, or `.format()` in SQL.
- [ ] App still starts without errors and `seed_db()` is still
      idempotent (no double-seeding of the demo user).
