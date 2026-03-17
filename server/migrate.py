import os
import glob
from typing import cast, LiteralString
from psycopg import sql
from database import get_db

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def run_migrations():
    with get_db() as conn:
        conn.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT now()
            )
        """))

        applied = {
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }

        migration_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))

        for filepath in migration_files:
            version = os.path.basename(filepath)
            if version in applied:
                continue

            print(f"Applying migration: {version}")
            with open(filepath) as f:
                conn.execute(sql.SQL(cast(LiteralString, f.read())))
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                [version],
            )

        print("Migrations up to date.")
