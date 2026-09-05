"""
Pytest configuration file.

This file ensures that the project root is in the Python path,
allowing tests to import from the api and open_notebook modules.
"""

import os
import sys
from pathlib import Path

# Ensure password auth is disabled for tests BEFORE any imports
# The PasswordAuthMiddleware skips auth when this env var is not set
# Set to empty string instead of deleting to prevent it from being reloaded
os.environ["OPEN_NOTEBOOK_PASSWORD"] = ""

# Load environment variables from .env file
# This must be done BEFORE any imports that depend on environment variables
from dotenv import load_dotenv

# Load .env file from project root
dotenv_path = Path(__file__).parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f"Loaded environment variables from {dotenv_path}")
else:
    print(f"Warning: .env file not found at {dotenv_path}")

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.dependencies import get_current_user  # noqa: E402
from api.main import app  # noqa: E402
from open_notebook.domain.user import User  # noqa: E402


def _fake_current_user() -> User:
    """Test-only stand-in for the real Google-session auth dependency.

    Routes protected by get_current_user expect a logged-in owner; without
    this override every protected endpoint returns 401 in tests instead of
    exercising its actual logic.
    """
    return User(id="app_user:test", name="Test User", email="test@example.com")


app.dependency_overrides[get_current_user] = _fake_current_user
