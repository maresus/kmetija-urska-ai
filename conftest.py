"""Pytest configuration for Kmetija Urška bot tests."""
import sys
import os
from pathlib import Path

# Ensure project root is on sys.path so `main` and `app` are importable
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# SQLite mode (no PostgreSQL needed for local tests)
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
