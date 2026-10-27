from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..config import Settings


def make_engine(settings: Settings):
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.database_url, **kwargs)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
