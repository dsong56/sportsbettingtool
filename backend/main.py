from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.database import init_db
from backend.routers import jobs, props, admin
from backend.jobs.resolver import start_nightly_resolver


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    resolver_task = await start_nightly_resolver()
    yield
    resolver_task.cancel()


app = FastAPI(title="EV Bets", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(props.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
