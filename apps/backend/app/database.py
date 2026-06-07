from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Lazily construct the SQLAlchemy engine on first use (audit B-MAJ-7).

    Building it at import time made engine creation + ``get_settings()`` an import
    side-effect; deferring it keeps ``import app.database`` cheap and lets tests and
    tooling import the app without a database configured.

    A ``sqlite`` URL (the host/local-dev DB — see .gitignore "local SQLite dev DB used by a host
    uvicorn run") needs ``check_same_thread=False`` + ``StaticPool`` so the FastAPI threadpool can
    share one connection instead of a fresh empty DB per checkout; the Postgres path is unchanged.
    """
    url = get_settings().database_url
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def get_session() -> Generator[Session, None, None]:
    db = get_sessionmaker()()
    try:
        yield db
    except Exception:
        # Roll back any partial/uncommitted work before returning the
        # connection to the pool, so a request that raised mid-transaction
        # can't leak a dirty session to the next checkout.
        db.rollback()
        raise
    finally:
        db.close()

