"""FastAPI application factory.

On startup: create tables, auto-seed the component-list catalog from the committed YAML
(Render durability), and start the single background worker thread. Everything runs in
one process; see the plan's "Process model & deployment" section.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from webapp.config import settings
from webapp.db import Base, SessionLocal, engine
from webapp.routers import admin, jobs, pages
from webapp.seed import seed_from_file_if_present
from webapp.worker import worker

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import models so their tables are registered on Base before create_all.
    import webapp.models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_from_file_if_present(db)
    finally:
        db.close()

    worker.start()
    try:
        yield
    finally:
        worker.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="capinator", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(pages.router)
    app.include_router(jobs.router)
    app.include_router(admin.router)
    return app


app = create_app()
