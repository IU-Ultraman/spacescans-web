# backend/tests/test_database.py
import os
import tempfile
from pathlib import Path

def test_database_creates_tables():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        os.environ["DB_PATH"] = str(db_path)
        from app.database import init_db, get_db
        init_db(db_path)
        gen = get_db(db_path)
        db = next(gen)
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert cursor.fetchone() is not None
        gen.close()
