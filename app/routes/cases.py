import re

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.aggregation.summary import (
    build_groww_case_summary,
)
from app.database import get_db
from app.models import (
    BrokerReport,
    Client,
    TaxCase,
)


router = APIRouter()

templates = Jinja2Templates(
    directory="app/templates"
)


FY_PATTERN = re.compile(
    r"^\d{4}-\d{2}$"
)


# =========================================================
# FINANCIAL YEAR VALIDATION
# =========================================================

def is_valid_financial_year(
    value: str,
) -> bool:

    if not FY_PATTERN.fullmatch(
        value
    ):
        return False

    first_year = int(
        value[:4]
    )

    second_year = int(
        value[-2:]
    )

    expected_second_year = (
        first_year + 1
    ) % 100

    return (
        second_year
        == expected_second_year
    )


# =========================================================
# CLIENT DETAIL
# =========================================================

@router.get(
    "/clients/{client_id}",
    response_class=HTMLResponse,
)
async def client_detail(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    client = (
        db.query(Client)
        .filter(
            Client.id == client_id
        )
        .first()
    )

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Client not found.",
        )

    tax_cases = (
        db.query(TaxCase)
        .filter(
            TaxCase.client_id
            == client.id
        )
        .order_by(
            TaxCase.financial_year.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="client_detail.html",
        context={
            "title": client.name,
            "client": client,
            "tax_cases": tax_cases,
        },
    )


# =========================================================
# NEW TAX CASE PAGE
# =========================================================

@router.get(
    "/clients/{client_id}/cases/new",
    response_class=HTMLResponse,
)
async def new_tax_case_page(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    client = (
        db.query(Client)
        .filter(
            Client.id == client_id
        )
        .first()
    )

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Client not found.",
        )

    return templates.TemplateResponse(
        request=request,
        name="tax_case_new.html",
        context={
            "title": "New Tax Case",
            "client": client,
            "financial_year": "",
            "error": None,
        },
    )


# =========================================================
# CREATE TAX CASE
# =========================================================

@router.post(
    "/clients/{client_id}/cases/new",
    response_class=HTMLResponse,
)
async def create_tax_case(
    client_id: int,
    request: Request,
    financial_year: str = Form(...),
    db: Session = Depends(get_db),
):

    client = (
        db.query(Client)
        .filter(
            Client.id == client_id
        )
        .first()
    )

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Client not found.",
        )

    financial_year = (
        financial_year.strip()
    )

    if not is_valid_financial_year(
        financial_year
    ):

        return templates.TemplateResponse(
            request=request,
            name="tax_case_new.html",
            context={
                "title": "New Tax Case",
                "client": client,
                "financial_year": (
                    financial_year
                ),
                "error": (
                    "Enter a valid financial "
                    "year such as 2025-26."
                ),
            },
            status_code=400,
        )

    existing_case = (
        db.query(TaxCase)
        .filter(
            TaxCase.client_id
            == client.id,

            TaxCase.financial_year
            == financial_year,
        )
        .first()
    )

    if existing_case:

        return templates.TemplateResponse(
            request=request,
            name="tax_case_new.html",
            context={
                "title": "New Tax Case",
                "client": client,
                "financial_year": (
                    financial_year
                ),
                "error": (
                    "A TaxVerify case already "
                    "exists for this financial "
                    "year."
                ),
            },
            status_code=409,
        )

    tax_case = TaxCase(
        client_id=client.id,
        financial_year=financial_year,
        status="DRAFT",
    )

    db.add(
        tax_case
    )

    db.commit()

    db.refresh(
        tax_case
    )

    return RedirectResponse(
        url=f"/cases/{tax_case.id}",
        status_code=303,
    )


# =========================================================
# TAX CASE DETAIL
# =========================================================

@router.get(
    "/cases/{case_id}",
    response_class=HTMLResponse,
)
async def tax_case_detail(
    case_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    tax_case = (
        db.query(TaxCase)
        .filter(
            TaxCase.id
            == case_id
        )
        .first()
    )

    if not tax_case:
        raise HTTPException(
            status_code=404,
            detail="Tax case not found.",
        )


    # -----------------------------------------------------
    # Fetch all Groww reports
    # newest first
    # -----------------------------------------------------

    reports = (
        db.query(BrokerReport)
        .filter(
            BrokerReport.tax_case_id
            == tax_case.id,

            BrokerReport.broker
            == "GROWW",
        )
        .order_by(
            BrokerReport.id.desc()
        )
        .all()
    )


    # -----------------------------------------------------
    # Only successful/reviewable reports should
    # appear as the currently active report.
    #
    # Failed uploads must never hide a previously
    # valid report.
    # -----------------------------------------------------

    report_map = {}

    for report in reports:

        if (
            report.processing_status
            not in {
                "PROCESSED",
                "REVIEW_REQUIRED",
            }
        ):
            continue

        if (
            report.report_type
            not in report_map
        ):
            report_map[
                report.report_type
            ] = report


    # -----------------------------------------------------
    # Groww report definitions
    # -----------------------------------------------------

    groww_report_types = [

        {
            "key": "FNO",
            "name": "F&O",
            "description": (
                "Futures and Options "
                "tax P&L report"
            ),
        },

        {
            "key": "COMMODITY",
            "name": "Commodity",
            "description": (
                "Commodity derivatives "
                "tax report"
            ),
        },

        {
            "key": "SHARES",
            "name": "Shares",
            "description": (
                "Equity intraday and "
                "capital gains report"
            ),
        },

        {
            "key": "MUTUAL_FUNDS",
            "name": "Mutual Funds",
            "description": (
                "Mutual fund redemption "
                "and capital gains report"
            ),
        },

    ]


    # -----------------------------------------------------
    # Build final seven-figure summary
    # -----------------------------------------------------

    summary = build_groww_case_summary(
        db=db,
        case_id=tax_case.id,
    )


    # -----------------------------------------------------
    # Render
    # -----------------------------------------------------

    return templates.TemplateResponse(
        request=request,
        name="tax_case_detail.html",
        context={
            "title": (
                f"FY "
                f"{tax_case.financial_year}"
            ),

            "tax_case": tax_case,

            "client": (
                tax_case.client
            ),

            "report_map": (
                report_map
            ),

            "groww_report_types": (
                groww_report_types
            ),

            "summary": (
                summary
            ),
        },
    )