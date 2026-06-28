import threading
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

commit_lock = threading.Lock()

DATABASE_URL = "sqlite:///./jockey_driver.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

_migration_checked = False

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    global _migration_checked
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()
    if not _migration_checked:
        try:
            cursor2 = dbapi_connection.cursor()
            cursor2.execute("SELECT race_odds_json FROM prices LIMIT 1")
            cursor2.close()
        except Exception:
            try:
                cursor2 = dbapi_connection.cursor()
                cursor2.execute("ALTER TABLE prices ADD COLUMN race_odds_json TEXT")
                dbapi_connection.commit()
                cursor2.close()
            except Exception:
                pass
        _migration_checked = True

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
