from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import database as db
from app.config import BASE_DIR, get_config
from app.logging_config import get_logger, setup_logging
from app.routers import admin, auth, backup, books, exports, holdings, imports, projects, selections

setup_logging()
logger = get_logger("main")

DEFAULT_SESSION_SECRET_PLACEHOLDER = "<generate-a-random-secret>"
SESSION_MAX_AGE_SECONDS = 8 * 3600


def _validate_session_secret(secret: str | None) -> str:
    if not secret or not secret.strip() or secret.strip() == DEFAULT_SESSION_SECRET_PLACEHOLDER:
        raise RuntimeError(
            "config.yaml 的 auth.session_secret_key 尚未設定或仍為預設佔位符，"
            "請先執行 setup_first_run.py 或手動填入隨機密鑰後再啟動。"
        )
    return secret


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting School Library Procurement server")
    db.run_migrations()
    db.ensure_initial_data()
    logger.info("Database migrations and initial data ready")
    yield
    logger.info("Shutting down School Library Procurement server")


app = FastAPI(title="School Library Procurement", lifespan=lifespan)

cfg = get_config()
session_secret = _validate_session_secret(cfg.session_secret_key)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    max_age=SESSION_MAX_AGE_SECONDS,
    same_site="lax",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"系統發生未預期錯誤（{ts}），請查看 data/app.log 或聯絡管理員。"},
    )


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(imports.router)
app.include_router(books.router)
app.include_router(selections.router)
app.include_router(exports.router)
app.include_router(holdings.router)
app.include_router(backup.router)
app.include_router(admin.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/projects.html", status_code=302)


app.mount("/", StaticFiles(directory=str(BASE_DIR / "app" / "static"), html=True), name="static")
