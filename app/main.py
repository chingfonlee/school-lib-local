from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_config
from app import database as db
from app.routers import auth, projects, imports, books, selections, exports, holdings, backup

app = FastAPI(title="School Library Procurement")

cfg = get_config()
app.add_middleware(SessionMiddleware, secret_key=cfg.session_secret_key)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(imports.router)
app.include_router(books.router)
app.include_router(selections.router)
app.include_router(exports.router)
app.include_router(holdings.router)
app.include_router(backup.router)


@app.on_event("startup")
async def startup():
    db.run_migrations()
    db.ensure_initial_data()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/projects.html", status_code=302)


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
