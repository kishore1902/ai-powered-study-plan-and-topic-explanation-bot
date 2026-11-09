"""Database setup.

Local: SQLite file (zero setup).
Vercel: set DATABASE_URL (or POSTGRES_URL) to a Postgres database such as Neon or Supabase,
because Vercel functions have no persistent disk.
"""
import os
import threading
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from . import auth, models


def _url() -> str:
    raw = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or os.environ.get("POSTGRES_URL_NON_POOLING")
    if raw:
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://"):]
        p = urlparse(raw)
        q = [(k, v) for k, v in parse_qsl(p.query) if k not in ("pgbouncer", "supa")]
        return urlunparse(p._replace(query=urlencode(q)))
    if os.environ.get("VERCEL"):
        return "sqlite:////tmp/gapfinder.db"  # temporary: wiped on cold starts
    return "sqlite:///gapfinder.db"


URL = _url()
IS_SQLITE = URL.startswith("sqlite")
IS_TEMPORARY = IS_SQLITE and bool(os.environ.get("VERCEL"))

if IS_SQLITE:
    engine = create_engine(URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(URL, poolclass=NullPool, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
_ready = False
_lock = threading.Lock()


def init():
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        try:
            models.Base.metadata.create_all(engine)
        except Exception:
            pass  # tables may already exist (race between cold starts)
        auth.seed_demo(SessionLocal)
        _ready = True


def get_db():
    init()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
