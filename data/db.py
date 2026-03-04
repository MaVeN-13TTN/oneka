"""
Async SQLAlchemy engine for the data-layer scrapers.

Loads DATABASE_URL from backend/.env and converts it to the asyncpg
dialect so all scrapers can share one session factory.

Also adds the repo root to sys.path so scrapers can import backend models:
    from backend.src.models.procurement import ProcurementRecord
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ── path wiring ──────────────────────────────────────────────────────────────
# data/ is one level below the repo root; adding the root lets scrapers do
# `from backend.src.models.xxx import Xxx` without sys.path hacks in each file.
# backend/ must also be on the path because backend/src uses relative imports
# like `from src.models.base import Base`.
_REPO_ROOT = Path(__file__).parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
for _p in [str(_REPO_ROOT), str(_BACKEND_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── environment ───────────────────────────────────────────────────────────────
load_dotenv(_REPO_ROOT / "backend" / ".env")

_raw_url = os.getenv(
    "DATABASE_URL",
    "postgresql://oneka_user:password@localhost:5432/oneka_dev",
)

# asyncpg requires the postgresql+asyncpg:// scheme
ASYNC_DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# ── engine + session factory ─────────────────────────────────────────────────
engine = create_async_engine(ASYNC_DATABASE_URL, echo=False, pool_pre_ping=True)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
