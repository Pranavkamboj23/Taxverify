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
)
from app.brokers.groww.processor import (
    process_groww_report,
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
    "SHARES": "Shares",
    "MUTUAL_FUNDS": "Mutual Funds",
}


def upload_error_response(
    request,
    tax_case,
    report_type,
    message,
    status_code=400,
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
            detail="Unsupported Groww report type.",
        )

    tax_case = (
        db.query(TaxCase)
        .filter(
            TaxCase.id == case_id
        )
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
            detail="Unsupported Groww report type.",
        )

    tax_case = (
        db.query(TaxCase)
        .filter(
            TaxCase.id == case_id
        )
        .first()
    )

    if not tax_case:
        raise HTTPException(
            status_code=404,
            detail="Tax case not found.",
        )

    existing_report = (
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

    if existing_report:
        return upload_error_response(
            request,
            tax_case,
            report_type,
            (
                "A processed Groww report "
                "of this type already exists "
                "for this tax case."
            ),
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
        return upload_error_response(
            request,
            tax_case,
            report_type,
            str(exc),
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
        return upload_error_response(
            request,
            tax_case,
            report_type,
            (
                "This exact file has already "
                "been uploaded to this tax case."
            ),
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

    tolerance = Decimal(
        str(
            settings
            .reconciliation_tolerance
        )
    )

    try:
        processed = process_groww_report(
            filepath=stored_path,
            report_type=report_type,
            tolerance=tolerance,
        )

    except GrowwParseError as exc:

        report.processing_status = (
            "VALIDATION_FAILED"
        )

        report.validation_message = str(
            exc
        )

        db.commit()

        return upload_error_response(
            request,
            tax_case,
            report_type,
            (
                f"Groww validation failed: "
                f"{exc}"
            ),
        )

    report.broker_client_name = (
        processed.client_name
    )

    report.broker_client_code = (
        processed.client_code
    )

    report.period_start = (
        processed.period_start
    )

    report.period_end = (
        processed.period_end
    )

    # --------------------------------------------
    # Financial year validation
    # --------------------------------------------

    fy_validation = (
        validate_financial_year(
            processed,
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

        return upload_error_response(
            request,
            tax_case,
            report_type,
            fy_validation.message,
        )

    # --------------------------------------------
    # Groww account consistency
    # --------------------------------------------

    existing_groww_report = (
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
        existing_groww_report
        and
        existing_groww_report
        .broker_client_code
        != processed.client_code
    ):

        report.processing_status = (
            "VALIDATION_FAILED"
        )

        report.validation_message = (
            "Groww client code does not "
            "match the existing Groww "
            "reports in this tax case."
        )

        db.commit()

        return upload_error_response(
            request,
            tax_case,
            report_type,
            report.validation_message,
            409,
        )

    # --------------------------------------------
    # Save metrics
    # --------------------------------------------

    for metric in processed.metrics:

        db.add(
            ReportMetric(
                report_id=report.id,
                metric_key=metric.key,
                value=metric.value,
                source_sheet=(
                    metric.source_sheet
                ),
                source_cell=(
                    metric.source_cell
                ),
                source_label=(
                    metric.source_label
                ),
                derivation=(
                    metric.derivation
                ),
            )
        )

    # --------------------------------------------
    # Save reconciliations
    # --------------------------------------------

    for check in processed.reconciliations:

        db.add(
            ReportReconciliation(
                report_id=report.id,

                check_name=(
                    check.check_name
                ),

                reported_value=(
                    check.reported_value
                ),

                calculated_value=(
                    check.calculated_value
                ),

                difference=(
                    check.difference
                ),

                tolerance=tolerance,

                status=check.status,

                message=check.message,
            )
        )

    # --------------------------------------------
    # Determine final report status
    # --------------------------------------------

    review_statuses = {
        "MISMATCH",
        "REVIEW_REQUIRED",
    }

    requires_review = any(
        check.status in review_statuses
        for check
        in processed.reconciliations
    )

    if requires_review:
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