from fastapi import FastAPI
from fastapi.responses import JSONResponse


app = FastAPI(
    title="TaxVerify",
    description="Multi-broker tax data processing and verification system",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {
        "application": "TaxVerify",
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
            "service": "TaxVerify",
        }
    )