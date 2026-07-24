"""Pytest configuration for the Spendly test suite.

Adds the project root to sys.path so `import app` and
`import database.db` work from inside the tests/ subdirectory.
This is the conventional pattern for small projects without a
packaged `src/` layout.
"""

import os
import sys

# Project root = parent of this conftest.py's parent (tests/ → .).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
