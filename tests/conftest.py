"""
Pytest bootstrap: doda projektni root v sys.path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Stub psycopg2 if ni nameščen (da lahko importamo chat_router brez DB odvisnosti)
try:
    import psycopg2  # type: ignore
except ModuleNotFoundError:
    import types

    psycopg2_stub = types.SimpleNamespace()
    psycopg2_extras_stub = types.SimpleNamespace(RealDictCursor=None)
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub
