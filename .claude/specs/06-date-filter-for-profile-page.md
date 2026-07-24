# Spec: Date Filter For Profile Page

## Overview
Step 6 adds a date range filter to the `/profile` page so that the
summary stats, transaction list, and category breakdown all reflect
only the expenses that fall inside a user-selected window. The current
profile page queries the entire `expenses` history for the logged-in
user; this step introduces a `from` / `to` query-string filter (plus a
one-click "All time" reset) that the route forwards into every DB
read. The goal is to make the profile page useful once a user has more
than a handful of expenses — they can answer questions like "what did
I spend on Food in the last 30 days?" without leaving the page.

## Depends on
- Step 1: Database setup (the `expenses.date` column stores ISO `YYYY-MM-DD` and is filterable)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 4: Profile page UI (the four-section layout is in place)
- Step 5: Backend routes for the profile page (live DB queries exist in `profile()`)

## Routes
No new routes. The existing `GET /profile` route is modified to accept
optional query parameters:
- `?from=YYYY-MM-DD` — inclusive lower bound on `expenses.date`
- `?to=YYYY-MM-DD` — inclusive upper bound on `expenses.date`

When both are present, the route filters all four data sections
(user-info card stays unchanged, but summary stats, transaction list,
and category breakdown) to expenses where `date BETWEEN from AND to`.
When neither is present, behaviour is identical to Step 5 — show all
time. The "All time" link is implemented as a plain `<a>` to
`/profile` with no query string, not as a button.

## Database changes
No database changes. The `expenses` table already has the `date`
column (`TEXT NOT NULL`, ISO `YYYY-MM-DD`) and is filterable with a
parameterised `BETWEEN` clause. `init_db()` and `seed_db()` are
untouched.

## Templates
- **Modify**: `templates/profile.html`
  - Add a date-filter bar above the four existing sections. The bar
    contains two `<input type="date">` fields (`from`, `to`), an
    "Apply" submit button, and an "All time" reset link to
    `url_for("profile")`.
  - The bar must pre-fill the inputs with the values that were
    submitted (so the user sees the active range after the page
    reloads), and fall back to empty inputs when no filter is set.
  - Render an "Active filter" badge only when a filter is applied;
    the badge text is e.g. `Jan 1, 2026 – Jan 31, 2026` (formatted
    from the ISO bounds).
  - When a filter is active and the result set is empty, the
    transaction table and category breakdown must render their
    existing empty states cleanly (no error). The summary stat for
    `Total Spent` should show `₹0`, the `Transactions` count should
    show `0`, and `Budget Left` stays `—`.

- **Modify**: `static/css/style.css`
  - Add styles for the date-filter bar, the two date inputs, the
    "Apply" button, and the "All time" reset link. Use the existing
    CSS custom properties (no new hex values). Match the visual
    language of the existing profile sections.

## Files to change
- `app.py` — the `profile()` view function:
  - Read `from` and `to` from `request.args`.
  - Validate each bound: if present, it must parse as `YYYY-MM-DD`;
    on parse failure, ignore the bound (treat as if absent) and do
    not raise.
  - If `from` is after `to`, swap them so the `BETWEEN` clause is
    always well-formed and the user gets a sensible result.
  - Add a `date_filter` clause to the three expense queries
    (summary total, summary count, transactions list, category
    breakdown) using a parameterised fragment:
    `AND date BETWEEN ? AND ?` (with the validated, swapped bounds)
    when both bounds are present; `AND date >= ?` when only `from`
    is present; `AND date <= ?` when only `to` is present; and
    no clause when neither is present.
  - Pass `from_value`, `to_value`, `filter_active`, and
    `filter_label` to the template so the filter bar can re-render
    itself correctly.

- `templates/profile.html` — see "Templates" above.

- `static/css/style.css` — see "Templates" above.

## Files to create
None. All logic lives in the existing `profile()` view so the route
remains the single source of truth for what the profile page shows,
matching the pattern set by Step 5.

## New dependencies
No new dependencies. `datetime.strptime` / `strftime` for date
parsing and formatting is already imported in `app.py` (`_format_iso_to_mon_dd`
and `_format_iso_month_year` are precedents). No JavaScript framework
or pip package is required — the form is a plain HTML `<form method="get">`
that submits via the browser.

## Rules for implementation
- **Single Flask app, plain function routes, no blueprints** — match
  the style of the existing routes in `app.py`.
- **No ORMs, no SQLAlchemy.** Use the existing `get_db()` from
  `database/db.py` and parameterised SQL.
- **Parameterised queries only** — never use f-strings or `%` /
  `.format()` to build SQL. The date bounds must be passed as `?`
  placeholders, not interpolated into the SQL string.
- **Validate `from` and `to` server-side.** Both are optional, and
  when present must parse as `YYYY-MM-DD` via `datetime.strptime`.
  On parse failure, ignore the bound (do not 400, do not raise).
  This mirrors the lenient parsing pattern already used by
  `_format_iso_to_mon_dd` and `_format_iso_month_year`.
- **If `from` is later than `to`, swap them** before issuing the
  query. This avoids surprising empty results when a user types the
  bounds in the wrong order.
- **Use a GET form, not POST.** The filter lives in the query string
  so the URL is shareable and bookmarkable, and the browser's back
  button works correctly.
- **Currency must always display as ₹** — never £ or $.
- **Use CSS variables** for any new styling — never hardcode hex
  values. Reuse the existing design tokens in `style.css`.
- **All templates must extend `base.html`.** `profile.html` already
  does — leave the structure intact and only add the filter bar.
- **Vanilla JS only.** The filter form is a plain HTML `<form>` with
  `method="get"` and `action="{{ url_for('profile') }}"`. No JS is
  required to wire it up. Do not introduce a JS framework, do not
  add a `fetch()` for filter submission.
- **No inline styles.** All new styling lives in `style.css`.
- **The user-info card is not affected by the filter.** Name, email,
  member-since, and initials always reflect the logged-in user
  regardless of the date range — only expenses are filtered.
- **Empty states must be graceful.** When the filter returns no
  expenses, the summary stats show zeros, the transaction table
  shows an empty `<tbody>`, and the category breakdown list is
  empty. No 500s, no "no data" exceptions.

## Tests to write

### Unit / route tests
File: `tests/test_date_filter.py`

Use the standard Spendly fixtures: an isolated in-memory DB with the
schema initialised, a `client` test client, and an `auth_client`
fixture that registers and logs in a user.

| Scenario | Input | Expected result |
|---|---|---|
| `GET /profile` no params | (none) | 200, all 8 seed expenses appear in the transaction list (regression — must match Step 5 behaviour) |
| `GET /profile?from=<seed-month-1st>&to=<seed-month-last>` | full current month | 200, all 8 seed expenses appear; `Total Spent` is unchanged |
| `GET /profile?from=<future-date>` | from after every seed expense | 200, `Total Spent` is `₹0`, transaction list is empty, category breakdown is empty |
| `GET /profile?to=<before-seed-month>` | to before the seed month | 200, `Total Spent` is `₹0`, transaction list is empty |
| `GET /profile?from=<day-1>&to=<day-2>` | narrow 2-day window | 200, only expenses on those two days appear in the transaction list, `Total Spent` equals their sum, category breakdown contains only categories that have an expense in that window |
| `GET /profile?from=garbage&to=garbage` | invalid bounds | 200, no filter applied (same as no params); the page does not 500 |
| `GET /profile?from=<day-22>&to=<day-1>` | reversed bounds | 200, treated as if swapped — the seed month is fully covered, all 8 expenses appear |
| `GET /profile` unauthenticated | (none) | 302 redirect to `/login` (regression — filter must not bypass auth) |
| `GET /profile?from=...` unauthenticated | filtered | 302 redirect to `/login` (filter must not bypass auth) |

### Manual smoke test
- Log in as `demo@spendly.com` / `demo123`, visit `/profile`, set
  `from` and `to` to a 2-day window inside the seed month, click
  "Apply", and confirm the transaction list, total, and category
  breakdown all reflect only those 2 days.
- Click "All time" and confirm the page reverts to showing all 8
  seed expenses.

## Definition of done
- [ ] `GET /profile` without any query parameter behaves exactly as
      it did at the end of Step 5 (regression-clean).
- [ ] A date-filter bar is visible above the four profile sections,
      with two `<input type="date">` fields, an "Apply" button, and
      an "All time" link.
- [ ] Submitting the form with valid `from` and `to` query params
      re-renders the page with the inputs pre-filled to those
      values, and the summary stats, transaction list, and category
      breakdown all reflect only expenses in the range.
- [ ] Submitting with only `from` filters expenses on or after that
      date.
- [ ] Submitting with only `to` filters expenses on or before that
      date.
- [ ] Submitting with `from` later than `to` is treated as if the
      bounds were swapped (page still shows the full reversed range).
- [ ] Submitting with unparseable bounds (e.g. `from=garbage`) does
      not 500 and behaves as if the bad bound were absent.
- [ ] When the filter excludes every expense, the page shows `₹0`
      total, 0 transactions, an empty transaction table, and an
      empty category list.
- [ ] When a filter is active, an "Active filter" badge displays the
      formatted range (e.g. `Jan 1, 2026 – Jan 31, 2026`); when no
      filter is active, the badge is not rendered.
- [ ] The user-info card (name, email, member-since, initials) is
      unaffected by the filter.
- [ ] Currency on every total, transaction amount, and category
      total is rendered with the ₹ symbol.
- [ ] Unauthenticated `GET /profile?from=...&to=...` still redirects
      to `/login` — the filter does not bypass auth.
- [ ] No new pip packages were installed.
- [ ] No SQLAlchemy or any other ORM is imported anywhere.
- [ ] Every SQL statement uses `?` placeholders — no f-strings, `%`,
      or `.format()` in SQL.
- [ ] No new JavaScript framework is introduced; the filter is
      implemented as a plain HTML `<form method="get">`.
- [ ] No inline styles; all new styling lives in `static/css/style.css`
      and uses the existing CSS custom properties.
