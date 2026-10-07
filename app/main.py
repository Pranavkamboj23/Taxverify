from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.cases import router as cases_router
from app.routes.clients import router as clients_router
from app.routes.dashboard import router as dashboard_router


app = FastAPI(
    title=settings.app_name,
    description="TaxVerify tax data processing platform",
    version="0.1.0",
    debug=settings.debug,
)


app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)


app.include_router(
    dashboard_router
)

app.include_router(
    clients_router
)

app.include_router(
    cases_router
)


@app.get("/")
async def root():
    return RedirectResponse(
        url="/dashboard"
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "0.1.0",
        "supported_brokers": [
            "GROWW",
        ],
    }