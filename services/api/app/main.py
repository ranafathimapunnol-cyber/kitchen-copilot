from app.api.routes import dashboard
import hmac  # noqa: I001
import re

from fastapi import FastAPI, Request  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.responses import JSONResponse # type: ignore
from app.api.routes import waste
from app.api.routes import password
from app.api.routes import supplier_payments
from app.api.routes import purchase_reports
from app.api.routes import purchase_attachments
from app.api.routes import purchase_orders
from app.api.routes import stock
from app.api.routes import kitchen
from app.api.routes import stock_counts
from app.api.routes import meals
from app.api.routes import planning
from app.api.routes import outsourced
from app.api.routes import analytics
from app.api.routes import reports
from app.api.routes import admin_users, agent, audit, campus_media, platform
from app.services.attachment_storage import StorageNotConfigured
from app.api.routes import auth, master_data, purchases, receipts
from app.core.config import settings
from app.api.routes import (
    auth,
    authorization,
    master_data,
    purchases,
    receipts,
    
)
app = FastAPI(
    title="Kitchen Copilot API",
    version="0.1.0",
    description="Kitchen and Mess Management System",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:3000",
    "http://localhost:3001",
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Lets the web app read the file name of a report export.
    expose_headers=["Content-Disposition"],
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


ATTACHMENT_UPLOAD_PATH = re.compile(r"^/api/purchases/\d+/attachments$")
# The file limit plus room for the multipart envelope and form fields.
ATTACHMENT_UPLOAD_MAX_BODY = purchase_attachments.MAX_BYTES + 512 * 1024


@app.middleware("http")
async def limit_attachment_uploads(request: Request, call_next):
    """Refuse an oversized bill attachment from its declared length,
    before the body is read. The endpoint checks the real size again.

    The form body is parsed before the user's permission is checked, so a
    body of undeclared length (chunked) is refused too: it could be any
    size. Browsers always declare the length of a file upload, and the
    server never reads past a declared length."""
    if request.method == "POST" and ATTACHMENT_UPLOAD_PATH.match(request.url.path):
        length = request.headers.get("content-length", "")
        if not length.isdigit():
            return JSONResponse(
                status_code=411,
                content={"detail": "The upload must declare its size."},
            )
        if int(length) > ATTACHMENT_UPLOAD_MAX_BODY:
            return JSONResponse(
                status_code=413,
                content={"detail": "A file can be at most 10 MB."},
            )
    return await call_next(request)


@app.exception_handler(StorageNotConfigured)
async def storage_not_configured(_request: Request, exc: StorageNotConfigured):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(auth.router)
app.include_router(password.router)
app.include_router(master_data.router)
app.include_router(purchases.router)
app.include_router(supplier_payments.router)
app.include_router(purchase_reports.router)
app.include_router(purchase_attachments.router)
app.include_router(purchase_orders.router)
app.include_router(receipts.router)
app.include_router(stock.router)
app.include_router(kitchen.router)
app.include_router(stock_counts.router)
app.include_router(meals.router)
app.include_router(planning.items_router)
app.include_router(planning.standards_router)
app.include_router(planning.plans_router)
app.include_router(outsourced.orders_router)
app.include_router(outsourced.deliveries_router)
app.include_router(outsourced.lines_router)
app.include_router(outsourced.report_router)
app.include_router(outsourced.bills_router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(admin_users.router)
app.include_router(audit.router)
app.include_router(agent.router)
app.include_router(platform.router)
app.include_router(campus_media.router)
app.include_router(authorization.router)
app.include_router(waste.router)

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
    from sqlalchemy import text  # type: ignore

    from app.db.session import engine

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "connected",
    }

app.include_router(dashboard.router)
