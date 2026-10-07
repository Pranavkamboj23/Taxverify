from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.brokers.groww.parser import (
    GrowwParseError,
    parse_groww_report,
)
from app.brokers.groww.rules import (
    calculate_groww,
)
from app.brokers.groww.validator import (
    validate_financial_year,
)
from app.config import settings
from app.database import get_db
from app.models import (
    BrokerReport,
    ReportMetric,
    ReportReconciliation,
    TaxCase,
)
from app.services.file_service import (
    FileValidationError,
    calculate_sha256,
    save_report_file,
    validate_excel_filename,
    validate_file_size,
)


router = APIRouter()

templates = Jinja2Templates(
    directory="app/templates"
)


SUPPORTED_REPORT_TYPES = {
    "FNO": "F&O",
    "COMMODITY": "Commodity",
}


def add_metric(
    db: Session,
    report: BrokerReport,
    key: str,
    value,
    source_sheet=None,
    source_cell=None,
    source_label=None,
    derivation=None,
):
    metric = ReportMetric(
        report_id=report.id,
        metric_key=key,
        value=value,
        source_sheet=source_sheet,
        source_cell=source_cell,
        source_label=source_label,
        derivation=derivation,
    )

    db.add(metric)


@router.get(
    "/cases/{case_id}/reports/{report_type}/upload",
    response_class=HTMLResponse,
)
async def upload_report_page(
    case_id: int,
    report_type: str,
    request: Request,
    db: Session = Depends(get_db),
):
    report_type = report_type.upper()

    if report_type not in SUPPORTED_REPORT_TYPES:
        raise HTTPException(
            status_code=404,
            detail="Report type not supported yet.",
        )

    tax_case = (
        db.query(TaxCase)
        .filter(TaxCase.id == case_id)
        .first()
    )

    if not tax_case:
        raise HTTPException(
            status_code=404,
            detail="Tax case not found.",
        )

    return templates.TemplateResponse(
        request=request,
        name="report_upload.html",
        context={
            "title": (
                f"Upload "
                f"{SUPPORTED_REPORT_TYPES[report_type]}"
            ),
            "tax_case": tax_case,
            "client": tax_case.client,
            "report_type": report_type,
            "report_name": (
                SUPPORTED_REPORT_TYPES[
                    report_type
                ]
            ),
            "error": None,
        },
    )


@router.post(
    "/cases/{case_id}/reports/{report_type}/upload",
    response_class=HTMLResponse,
)
async def upload_report(
    case_id: int,
    report_type: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    report_type = report_type.upper()

    if report_type not in SUPPORTED_REPORT_TYPES:
        raise HTTPException(
            status_code=404,
            detail="Report type not supported.",
        )

    tax_case = (
        db.query(TaxCase)
        .filter(TaxCase.id == case_id)
        .first()
    )

    if not tax_case:
        raise HTTPException(
            status_code=404,
            detail="Tax case not found.",
        )

    def upload_error(
        message: str,
        status_code: int = 400,
    ):
        return templates.TemplateResponse(
            request=request,
            name="report_upload.html",
            context={
                "title": (
                    f"Upload "
                    f"{SUPPORTED_REPORT_TYPES[report_type]}"
                ),
                "tax_case": tax_case,
                "client": tax_case.client,
                "report_type": report_type,
                "report_name": (
                    SUPPORTED_REPORT_TYPES[
                        report_type
                    ]
                ),
                "error": message,
            },
            status_code=status_code,
        )

    existing_type = (
        db.query(BrokerReport)
        .filter(
            BrokerReport.tax_case_id
            == tax_case.id,
            BrokerReport.broker
            == "GROWW",
            BrokerReport.report_type
            == report_type,
            BrokerReport.processing_status.in_(
                [
                    "PROCESSED",
                    "REVIEW_REQUIRED",
                ]
            ),
        )
        .first()
    )

    if existing_type:
        return upload_error(
            "A processed Groww report of this "
            "type already exists for this case.",
            409,
        )

    filename = file.filename or ""

    try:
        validate_excel_filename(
            filename
        )

        content = await file.read()

        validate_file_size(
            content
        )

    except FileValidationError as exc:
        return upload_error(
            str(exc)
        )

    file_hash = calculate_sha256(
        content
    )

    duplicate = (
        db.query(BrokerReport)
        .filter(
            BrokerReport.tax_case_id
            == tax_case.id,
            BrokerReport.file_hash
            == file_hash,
        )
        .first()
    )

    if duplicate:
        return upload_error(
            "This exact file has already "
            "been uploaded to this tax case.",
            409,
        )

    stored_path = save_report_file(
        content=content,
        original_filename=filename,
        case_id=tax_case.id,
        report_type=report_type,
    )

    report = BrokerReport(
        tax_case_id=tax_case.id,
        broker="GROWW",
        report_type=report_type,
        original_filename=filename,
        stored_filename=stored_path,
        file_hash=file_hash,
        format_version="GROWW_V1",
        processing_status="PROCESSING",
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    try:
        parsed = parse_groww_report(
            stored_path,
            report_type,
        )

    except GrowwParseError as exc:

        report.processing_status = (
            "VALIDATION_FAILED"
        )

        report.validation_message = str(
            exc
        )

        db.commit()

        return upload_error(
            f"Groww validation failed: {exc}"
        )

    report.broker_client_name = (
        parsed.client_name
    )

    report.broker_client_code = (
        parsed.client_code
    )

    report.period_start = (
        parsed.period_start
    )

    report.period_end = (
        parsed.period_end
    )

    fy_validation = (
        validate_financial_year(
            parsed,
            tax_case.financial_year,
        )
    )

    if not fy_validation.valid:

        report.processing_status = (
            "VALIDATION_FAILED"
        )

        report.validation_message = (
            fy_validation.message
        )

        db.commit()

        return upload_error(
            fy_validation.message
        )

    existing_groww_account = (
        db.query(BrokerReport)
        .filter(
            BrokerReport.tax_case_id
            == tax_case.id,
            BrokerReport.broker
            == "GROWW",
            BrokerReport.id
            != report.id,
            BrokerReport.broker_client_code
            .isnot(None),
            BrokerReport.processing_status.in_(
                [
                    "PROCESSED",
                    "REVIEW_REQUIRED",
                ]
            ),
        )
        .first()
    )

    if (
        existing_groww_account
        and
        existing_groww_account
        .broker_client_code
        != parsed.client_code
    ):

        report.processing_status = (
            "VALIDATION_FAILED"
        )

        report.validation_message = (
            "Groww client code does not "
            "match the other Groww reports "
            "in this tax case."
        )

        db.commit()

        return upload_error(
            report.validation_message,
            409,
        )

    tolerance = Decimal(
        str(
            settings
            .reconciliation_tolerance
        )
    )

    calculation = calculate_groww(
        parsed,
        tolerance,
    )

    add_metric(
        db,
        report,
        "REALISED_PNL",
        calculation.realised_pnl,
        source_sheet=(
            parsed.realised_pnl.sheet
        ),
        source_cell=(
            parsed.realised_pnl.cell
        ),
        source_label=(
            parsed.realised_pnl.label
        ),
    )

    add_metric(
        db,
        report,
        "CHARGES",
        calculation.charges,
        source_sheet=(
            parsed.charges.sheet
        ),
        source_cell=(
            parsed.charges.cell
        ),
        source_label=(
            parsed.charges.label
        ),
    )

    add_metric(
        db,
        report,
        "FINAL_NET_PNL",
        calculation.final_net_pnl,
        derivation=(
            "Groww rule: "
            "Realised P&L - Charges"
        ),
    )

    add_metric(
        db,
        report,
        "TURNOVER",
        calculation.turnover,
        derivation=(
            "Broker reported turnover "
            "when available; otherwise "
            "SUM(ABS(trade-level "
            "Realized P&L))."
        ),
    )

    add_metric(
        db,
        report,
        "CALCULATED_TURNOVER",
        calculation.turnover_calculated,
        derivation=(
            "SUM(ABS(trade-level "
            "Realized P&L))"
        ),
    )

    if (
        calculation.turnover_reported
        is not None
    ):
        add_metric(
            db,
            report,
            "REPORTED_TURNOVER",
            calculation.turnover_reported,
            source_sheet=(
                parsed
                .reported_turnover
                .sheet
            ),
            source_cell=(
                parsed
                .reported_turnover
                .cell
            ),
            source_label=(
                parsed
                .reported_turnover
                .label
            ),
        )

    pnl_reconciliation = (
        ReportReconciliation(
            report_id=report.id,
            check_name=(
                "Summary P&L vs "
                "Trade-Level P&L"
            ),
            reported_value=(
                calculation.realised_pnl
            ),
            calculated_value=(
                parsed.trade_level_pnl
            ),
            difference=(
                calculation
                .pnl_reconciliation_difference
            ),
            tolerance=tolerance,
            status=(
                calculation.pnl_status
            ),
            message=(
                "Trade-level realised P&L "
                "is compared against the "
                "summary Realised P&L."
            ),
        )
    )

    db.add(
        pnl_reconciliation
    )

    turnover_reconciliation = (
        ReportReconciliation(
            report_id=report.id,
            check_name=(
                "Reported vs "
                "Calculated Turnover"
            ),
            reported_value=(
                calculation
                .turnover_reported
            ),
            calculated_value=(
                calculation
                .turnover_calculated
            ),
            difference=(
                calculation
                .turnover_reconciliation_difference
            ),
            tolerance=tolerance,
            status=(
                calculation.turnover_status
            ),
            message=(
                "Turnover is checked using "
                "trade-level absolute P&L."
            ),
        )
    )

    db.add(
        turnover_reconciliation
    )

    mismatch_statuses = {
        "MISMATCH",
        "REVIEW_REQUIRED",
    }

    if (
        calculation.pnl_status
        in mismatch_statuses
        or calculation.turnover_status
        in mismatch_statuses
    ):
        report.processing_status = (
            "REVIEW_REQUIRED"
        )
    else:
        report.processing_status = (
            "PROCESSED"
        )

    report.validation_message = (
        fy_validation.message
    )

    if tax_case.status == "DRAFT":
        tax_case.status = "IN_PROGRESS"

    db.commit()

    return RedirectResponse(
        url=f"/reports/{report.id}",
        status_code=303,
    )


@router.get(
    "/reports/{report_id}",
    response_class=HTMLResponse,
)
async def report_detail(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    report = (
        db.query(BrokerReport)
        .filter(
            BrokerReport.id
            == report_id
        )
        .first()
    )

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Report not found.",
        )

    metric_map = {
        metric.metric_key: metric
        for metric in report.metrics
    }

    return templates.TemplateResponse(
        request=request,
        name="report_detail.html",
        context={
            "title": (
                f"Groww "
                f"{report.report_type}"
            ),
            "report": report,
            "tax_case": report.tax_case,
            "client": (
                report.tax_case.client
            ),
            "metrics": metric_map,
            "reconciliations": (
                report.reconciliations
            ),
        },
    )