# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Spendly — Personal Expense Tracker

A Flask-based personal expense tracking web app. **The codebase is a teaching scaffold** — students fill in features across numbered steps. Several routes in `app.py` are placeholders returning strings like `"Add expense — coming in Step 7"`, and `database/db.py` is a stub waiting for the Step 1 implementation.

## Commands

Install deps (uses pinned versions in `requirements.txt`):
```bash
pip install -r requirements.txt
```

Run the dev server (debug mode, port 5001):
```bash
python app.py
# or: flask --app app run --debug --port 5001
```

Run tests (pytest + pytest-flask are installed, but no test files exist yet — students add them as the course progresses):
```bash
pytest
# single test file: pytest tests/test_foo.py
# single test:    pytest tests/test_foo.py::test_bar
```

No linter, formatter, or build step is configured.

## Architecture

**Single Flask app, server-rendered Jinja2 templates, no JS framework.**

```
app.py                  # All routes. Imports only `flask`. No DB / auth wired up yet.
database/
  __init__.py           # Empty package marker
  db.py                 # STUB — students implement get_db(), init_db(), seed_db() in Step 1
templates/
  base.html             # Navbar + footer shell. All other pages extend this.
                        # Loads `static/css/style.css` and `static/js/main.js`.
  landing.html          # Public homepage with hero, mock dashboard preview, and YouTube modal
  register.html / login.html  # Auth pages (forms POST to themselves; backend not wired)
  terms.html / privacy.html   # Static legal pages
static/
  css/style.css         # Single stylesheet, CSS custom properties for the design system
  js/main.js            # Empty — students add behavior here
file.txt                # Step-by-step task instructions for students (not source)
```

### Template inheritance
Every page extends `base.html`. The base template provides the `content`, `head`, and `scripts` Jinja blocks plus loads the global CSS and a tiny `main.js`. Pages put their CSS in `static/css/style.css` and page-specific JS in a `{% block scripts %}` block (see `landing.html` for the modal pattern).

### Design system (style.css)
Colors and spacing are CSS custom properties on `:root` — `--ink`, `--paper`, `--accent` (dark green), `--accent-2` (warm gold), `--font-display` (DM Serif Display), `--font-body` (DM Sans). Use these variables rather than hardcoding values. Breakpoints: 900px and 600px.

### Currency
All amounts are displayed in Indian rupees (`₹`). The mock dashboard in `landing.html` shows sample figures (₹18,240, etc.) — placeholder copy, not real data.

### YouTube video modal
`landing.html` contains a `video-modal` overlay opened by the "See how it works" link. The placeholder URL is hardcoded as `VIDEO_URL` in an IIFE at the bottom of the template — replace it with the real embed URL when one is provided. Pattern: set `iframe.src` on open, clear it on close (so audio stops).

## Implementation steps (from file.txt)
The course builds the app incrementally. Current state vs. roadmap:
- ✅ Step 0 (done): landing page, auth pages, terms, privacy, hero redesign, video modal
- ⏳ Step 1: `database/db.py` — `get_db()`, `init_db()`, `seed_db()`
- ⏳ Steps 2–3: login/logout backend, sessions
- ⏳ Step 4: profile page (`/profile` is currently a placeholder)
- ⏳ Steps 7–9: expense CRUD (`/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete` are placeholders)

When implementing a new step, follow the placeholder comment in `app.py` (e.g. `"coming in Step 7"`) to know which route to flesh out.

## Conventions
- Flask routes are plain functions, not blueprints.
- Frontend is vanilla JS only — no React/Vue/jQuery. See `landing.html` for the IIFE modal pattern.
- `file.txt` contains the human-readable task list for students; it's checked into the repo and is not source code.
- `.gitignore` excludes `expense_tracker.db`, `venv/`, `__pycache__/`, and `.claude/plans/`.
