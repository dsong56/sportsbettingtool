from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from backend.config import DATABASE_URL
from backend.db.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def _add_missing_columns(conn: AsyncConnection):
    """
    Lightweight migration shim: create_all() only creates missing *tables*, so
    columns added to a model after the table exists never reach the DB. For each
    model column absent from the live schema, issue ALTER TABLE ADD COLUMN.
    Additive-only by design — renames/drops still need a manual migration.
    """
    for table in Base.metadata.sorted_tables:
        res = await conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")')
        existing = {row[1] for row in res.fetchall()}
        if not existing:  # table doesn't exist yet; create_all will build it fully
            continue
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(dialect=conn.dialect)
                await conn.exec_driver_sql(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'
                )


async def init_db():
    async with engine.begin() as conn:
        await _add_missing_columns(conn)
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
