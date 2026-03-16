import os
from contextlib import contextmanager
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost:5432/podcast_organizer",
)

pool = ConnectionPool(DATABASE_URL, min_size=2, max_size=10)

@contextmanager
def get_db():
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
