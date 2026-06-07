from flask import g
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = None
SessionLocal = None


def init_engine(database_url: str):
    global engine, SessionLocal
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_engine():
    if engine is None:
        raise RuntimeError("Database engine is not initialized.")
    return engine


def get_session():
    if "db_session" not in g:
        if SessionLocal is None:
            raise RuntimeError("Database session factory is not initialized.")
        g.db_session = SessionLocal()
    return g.db_session


def close_session(error=None):
    session = g.pop("db_session", None)
    if session is not None:
        if error is not None:
            session.rollback()
        session.close()
