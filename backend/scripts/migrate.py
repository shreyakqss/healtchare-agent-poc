"""Apply pending CareFlow database migrations without creating or dropping application data."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


if __name__ == "__main__":
    from app.db.migrations import migrate_database

    migrate_database()
    print("CareFlow database is at the latest migration.")
