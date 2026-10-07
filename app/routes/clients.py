import re

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client


router = APIRouter()

templates = Jinja2Templates(
    directory="app/templates"
)


PAN_PATTERN = re.compile(
    r"^[A-Z]{5}[0-9]{4}[A-Z]$"
)


@router.get(
    "/clients",
    response_class=HTMLResponse,
)
async def clients_page(
    request: Request,
    db: Session = Depends(get_db),
):
    clients = (
        db.query(Client)
        .order_by(Client.id.desc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="clients.html",
        context={
            "title": "Clients",
            "clients": clients,
        },
    )


@router.get(
    "/clients/new",
    response_class=HTMLResponse,
)
async def new_client_page(
    request: Request,
):
    return templates.TemplateResponse(
        request=request,
        name="client_new.html",
        context={
            "title": "New Client",
            "error": None,
            "name": "",
            "pan": "",
        },
    )


@router.post(
    "/clients/new",
    response_class=HTMLResponse,
)
async def create_client(
    request: Request,
    name: str = Form(...),
    pan: str = Form(...),
    db: Session = Depends(get_db),
):
    name = name.strip()
    pan = pan.strip().upper()

    if not name:
        return templates.TemplateResponse(
            request=request,
            name="client_new.html",
            context={
                "title": "New Client",
                "error": "Client name is required.",
                "name": name,
                "pan": pan,
            },
            status_code=400,
        )

    if not PAN_PATTERN.fullmatch(pan):
        return templates.TemplateResponse(
            request=request,
            name="client_new.html",
            context={
                "title": "New Client",
                "error": "Enter a valid PAN, for example ABCDE1234F.",
                "name": name,
                "pan": pan,
            },
            status_code=400,
        )

    existing_client = (
        db.query(Client)
        .filter(Client.pan == pan)
        .first()
    )

    if existing_client:
        return templates.TemplateResponse(
            request=request,
            name="client_new.html",
            context={
                "title": "New Client",
                "error": "A client with this PAN already exists.",
                "name": name,
                "pan": pan,
            },
            status_code=409,
        )

    client = Client(
        name=name,
        pan=pan,
    )

    db.add(client)
    db.commit()
    db.refresh(client)

    return RedirectResponse(
        url="/clients",
        status_code=303,
    )