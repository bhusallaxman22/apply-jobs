from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


settings = get_settings()
engine = create_engine(settings.database_url, future=True, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_legacy_schema_compatibility()


def _ensure_legacy_schema_compatibility() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "jobs" not in table_names:
        return

    existing_job_columns = {column["name"] for column in inspector.get_columns("jobs")}
    job_column_ddl = {
        "source_id": "ALTER TABLE jobs ADD COLUMN source_id VARCHAR(36)",
        "external_job_id": "ALTER TABLE jobs ADD COLUMN external_job_id VARCHAR(255)",
        "title": "ALTER TABLE jobs ADD COLUMN title VARCHAR(255)",
        "description": "ALTER TABLE jobs ADD COLUMN description TEXT",
        "location": "ALTER TABLE jobs ADD COLUMN location VARCHAR(255)",
        "employment_type": "ALTER TABLE jobs ADD COLUMN employment_type VARCHAR(100)",
        "availability": "ALTER TABLE jobs ADD COLUMN availability VARCHAR(50) NOT NULL DEFAULT 'open'",
        "source_metadata": "ALTER TABLE jobs ADD COLUMN source_metadata JSON NOT NULL DEFAULT '{}'",
    }

    with engine.begin() as connection:
        for column_name, ddl in job_column_ddl.items():
            if column_name not in existing_job_columns:
                connection.execute(text(ddl))
