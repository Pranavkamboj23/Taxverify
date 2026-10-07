from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BrokerReport, Client, TaxCase


router = APIRouter()

templates = Jinja2Templates(
    directory="app/templates"
)


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    client_count = (
        db.query(func.count(Client.id))
        .scalar()
        or 0
    )

    case_count = (
        db.query(func.count(TaxCase.id))
        .scalar()
        or 0
    )

    report_count = (
        db.query(func.count(BrokerReport.id))
        .scalar()
        or 0
    )

    recent_clients = (
        db.query(Client)
        .order_by(Client.id.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Dashboard",
            "client_count": client_count,
            "case_count": case_count,
            "report_count": report_count,
            "recent_clients": recent_clients,
        },
    )