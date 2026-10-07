from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import Base, engine

import app.models


Base.metadata.create_all(bind=engine)


app = FastAPI(
    title=settings.app_name,
    description="TaxVerify tax data processing platform",
    version="0.1.0",
    debug=settings.debug,
)


@app.get("/")
async def root():
    return {
        "application": settings.app_name,
        "version": "0.1.0",
        "status": "running",
        "supported_brokers": [
            "GROWW",
        ],
    }


@app.get("/health")
async def health():
    return JSONResponse(
        content={
            "status": "ok",
            "service": settings.app_name,
            "database": "connected",
        }
    )