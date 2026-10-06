"""Apply one additive migration file to the configured database.

Usage:
    python -m backend.scripts.apply_migration backend/db/migrations/008_multi_factory.sql

Only ever run files made of additive statements (CREATE/ALTER ... IF NOT
EXISTS). Never run anything with DROP/DELETE against shared data.
"""
import sys
from pathlib import Path

import psycopg

from backend.core.config import settings


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m backend.scripts.apply_migration <file.sql>")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"file not found: {path}")
        return 2
    sql = path.read_text(encoding="utf-8")
    # psycopg accepts SQLAlchemy-style URLs; strip the driver suffix.
    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print(f"applied {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
