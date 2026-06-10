from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.config import DATABASE_URL
from backend.db.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Columns added after a table first shipped. create_all() doesn't alter existing
# tables, so patch them in here for databases created before the column existed.
_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, DDL type/default)
    ("sportsbook_lines", "is_alt", "BOOLEAN NOT NULL DEFAULT 0"),
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table, column, ddl in _MIGRATIONS:
            cols = await conn.execute(text(f"PRAGMA table_info({table})"))
            if column not in {row[1] for row in cols}:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
