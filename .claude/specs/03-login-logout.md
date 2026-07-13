# Spec: Login and Logout

## Overview

Replace the placeholder `GET /login` and `GET /logout` routes in `app.py`
with a real authentication round-trip. Users submit an email and password
through the existing `login.html` form; the server looks up the user by
email, verifies the password against the stored `password_hash` using
`werkzeug.security.check_password_hash`, and on success starts a session
and redirects to `/profile`. The new `/logout` route clears the session
and redirects to the landing page. This step pairs with Step 2
(Registration) to give Spendly a complete sign-in / sign-out flow — every
later feature assumes the user can be identified via `session["user_id"]`.

## Depends on

- **Step 1 — Database Setup** (✅ done). The `users` table with
  `id`, `email`, and `password_hash` already exists, and `get_db()` is
  in `database/db.py`.
- **Step 2 — Registration** (✅ done). `app.secret_key` is already set,
  `session["user_id"]` is the established session shape, and the
  registration route already writes the `user_id` into the session on
  success. Login must match that convention exactly.

## Routes

- `GET  /login` — render `templates/login.html` (optionally with
  `?next=…` preserved in a hidden form field) — public
- `POST /login` — validate input, look up user by email, verify the
  password with `check_password_hash`, start a session, redirect to
  `/profile` (or to a safe `next` target) on success, or re-render
  `login.html` with a generic error on failure — public
- `GET  /logout` — clear `session`, redirect to `GET /` (landing) — any
  (idempotent — logging out while not logged in is a no-op redirect)

No other routes change. (`/profile` remains a placeholder returning a
string in this step, but it must exist as a route so the redirect
target is valid.)

## Database changes

No database changes. The `users` table from Step 1 already supports
this feature. `init_db()` and `seed_db()` are untouched.

## Templates

- **Modify:** `templates/login.html`
  - Add a hidden `<input type="hidden" name="next" value="{{ next or '' }}">`
    inside the existing form so the safe `next` target survives a
    re-render. No other structural change — the form already has
    `{% if error %}` and posts to `/login` with `email` and `password`
    fields.

No new templates.

## Files to change

- `app.py` — convert the `/login` route to accept both GET and POST,
  add session handling, add a real `/logout` route that clears the
  session, and import `check_password_hash` from `werkzeug.security`.
  - `urllib.parse.urlparse` / `urljoin` (or equivalent) is needed to
    validate the `next` parameter so an attacker cannot use
    `?next=https://evil.example` to phish the post-login redirect.

## Files to create

None. All logic lives in `app.py` so the routes are the single source
of truth for the flow, matching the pattern set by the registration
step.

## New dependencies

No new dependencies.

- `werkzeug.security.check_password_hash` is already installed
  (Werkzeug is in `requirements.txt`); it ships in the same module as
  `generate_password_hash`, which Step 2 already imports.
- `flask.session` and `flask.redirect` / `flask.url_for` are already
  imported in `app.py`.

## Rules for implementation

- **Single Flask app, plain function routes, no blueprints** — match
  the style of the existing routes in `app.py`.
- **No ORMs, no SQLAlchemy.** Use the existing `get_db()` from
  `database/db.py` and parameterised SQL.
- **Parameterised queries only** — never use f-strings or `%` /
  `.format()` to build SQL. The existing `db.py` and the registration
  route already follow this; match them.
- **Verify passwords with `werkzeug.security.check_password_hash`**.
  Never compare the raw submitted password against `password_hash`
  directly, and never store or log the plaintext password.
- **Generic error message on failure.** When the email does not exist
  *or* the password is wrong, render `login.html` with the exact
  message `Invalid email or password.` and a 200 response. Do **not**
  distinguish "no such user" from "wrong password" — that is a user
  enumeration leak. Do **not** reveal whether the account exists.
- **Validate on the server**, not in JS. The `login.html` form has
  `required` on every field — that is browser-side nicety only.
  Re-check that `email` and `password` are non-empty server-side.
- **Normalise email** by stripping leading/trailing whitespace and
  lowercasing before the lookup, exactly as the registration route
  does. Email comparison is case-insensitive.
- **Use `flask.session`** to mark the user as logged in. Store
  `session["user_id"]` (the integer primary key) on success. Do
  **not** store the email, name, or password hash in the session.
- **Rate limiting / lockouts are out of scope** for this step. The
  course does not introduce them; keep the implementation minimal.
- **Safe `next` redirect handling.** The login form accepts a `next`
  query parameter (e.g. `/login?next=/expenses/add`). After a
  successful login, redirect to `next` only if it is a same-origin
  path that begins with a single `/` and does not begin with `//` or
  `/\\`. Otherwise fall back to `url_for("profile")`. This blocks
  open-redirect attacks via `?next=https://evil.example/...`.
- **POST/Redirect/Get on success.** On successful login, return a 302
  redirect (do not return 200 with a "welcome" page). This prevents
  the browser "are you sure you want to resubmit the form?" dialog
  on refresh.
- **On validation failure**, re-render `login.html` and pass
  `error="..."` so the existing `{% if error %}` block shows it.
  Preserve the submitted `email` in the form value if login failed
  for an unknown reason is **not** necessary — re-typing is fine, and
  silently preserving input can confuse users on a typo. (Keeping it
  is also acceptable; pick one and stay consistent with the
  registration step's approach, which does not preserve values.)
- **Logout is GET-only** for this step (matches the existing
  placeholder signature and keeps the navbar `<a href="/logout">`
  pattern working). Clear `session` (which removes `user_id` and any
  other keys we may have added) and `redirect(url_for("landing"))`.
  Logging out while not logged in is a harmless no-op — it still
  redirects to `/`.
- **Use CSS variables** for any new styling. No new colors. The
  existing `.auth-error` class in `style.css` already styles the
  error banner — no new CSS is required for this step.
- **All templates must extend `base.html`.** `login.html` already
  does — leave the structure alone and only add the hidden `next`
  field.
- **Do not** add CSRF protection in this step. The course does not
  introduce it until later; adding it now would block later learning
  material.
- **Do not** introduce a login-required decorator in this step. That
  is Step 4's job (profile page protection). Out of scope here.

## Definition of done

- [ ] `app.py` imports `check_password_hash` from `werkzeug.security`.
- [ ] `GET /login` still renders `login.html` (no regression).
- [ ] `POST /login` with a valid email + matching password sets
      `session["user_id"]` to the matching `users.id` and returns a
      302 redirect to `/profile`.
- [ ] `POST /login` with a valid email + wrong password re-renders
      `login.html` with the error `Invalid email or password.` and a
      **200** response. `session` is **not** modified.
- [ ] `POST /login` with an email that does not exist re-renders
      `login.html` with the same generic `Invalid email or password.`
      error and a **200** response. The error message must be
      identical to the wrong-password case (no enumeration leak).
- [ ] `POST /login` with a missing/empty `email` or `password`
      re-renders `login.html` with a clear validation error and a
      **200** response. No DB lookup is performed.
- [ ] Email comparison is case-insensitive: logging in as
      `Demo@Spendly.com` works the same as `demo@spendly.com`.
- [ ] `GET /logout` clears the session (verify `session` no longer
      contains `user_id`) and returns a 302 redirect to `/`.
- [ ] `GET /logout` while not logged in still returns a 302 redirect
      to `/` and does not raise.
- [ ] The `demo@spendly.com` / `demo123` account from `seed_db()`
      can sign in successfully (end-to-end smoke test in the browser).
- [ ] `?next=/expenses/add` after a successful login redirects to
      `/expenses/add`, not to `/profile`.
- [ ] `?next=https://evil.example/x` after a successful login does
      **not** redirect off-site — it falls back to `/profile`.
- [ ] `?next=//evil.example/x` and `?next=/\\evil.example/x` are
      also rejected and fall back to `/profile`.
- [ ] No new pip packages were installed.
- [ ] No SQLAlchemy or any other ORM is imported anywhere.
- [ ] Every SQL statement uses `?` placeholders — no f-strings, `%`,
      or `.format()` in SQL.
- [ ] App still starts without errors and `seed_db()` is still
      idempotent (no double-seeding of the demo user).
