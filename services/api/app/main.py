import hmac

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, master_data, purchases, receipts
from app.core.config import settings


app = FastAPI(
    title="Kitchen Copilot API",
    version="0.1.0",
    description="Kitchen and Mess Management System",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}

    if (
        request.url.path.startswith("/api/")
        and request.method in unsafe_methods
    ):
        csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
        csrf_header = request.headers.get(settings.CSRF_HEADER_NAME)

        if (
            not csrf_cookie
            or not csrf_header
            or not hmac.compare_digest(csrf_cookie, csrf_header)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid."},
            )

    return await call_next(request)


app.include_router(auth.router)
app.include_router(master_data.router)
app.include_router(purchases.router)
app.include_router(receipts.router)


@app.get("/")
def root():
    return {
        "message": "Kitchen Copilot API",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "service": "Kitchen Copilot API",
    }


@app.get("/health/db")
def database_health():
    from sqlalchemy import text
    from app.db.session import engine

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "connected",
    }
