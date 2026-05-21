from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.config import DATABASE_URL
from backend.db.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
