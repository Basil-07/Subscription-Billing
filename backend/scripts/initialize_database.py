"""One-time database initialization command for a new Aiven database.

Run this from a trusted machine with the production DATABASE_URL configured:
    python scripts/initialize_database.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import init_db  # noqa: E402


if __name__ == "__main__":
    init_db()
    print("Database schema and demo data initialized.")
