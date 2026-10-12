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

from app.brokers.groww.parser import GrowwParseError
from app.brokers.groww.processor import process_groww_report
from app.brokers.groww.validator import validate_financial_year

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


# =========================================================
# SUPPORTED REPORT TYPES
# =========================================================

SUPPORTED_REPORT_TYPES = {
    "FNO": "F&O",
    "COMMODITY": "Commodity",
    "SHARES": "Shares",
    "MUTUAL_FUNDS": "Mutual Funds",
}


ACTIVE_REPORT_STATUSES = {
    "PROCESSED",
    "REVIEW_REQUIRED",
}


# =========================================================
# HELPERS
# =========================================================


def get_tax_case_or_404(
    db: Session,
    case_id: int,
) -> TaxCase:

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

    return tax_case


def upload_error_response(
    request: Request,
    tax_case: TaxCase,
    report_type: str,
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

            "client": (
                tax_case.client
            ),

            "report_type": (
                report_type
            ),

            "report_name": (
                SUPPORTED_REPORT_TYPES[
                    report_type
                ]
            ),

            "error": message,
        },
        status_code=status_code,
    )


# =========================================================
# UPLOAD PAGE
# =========================================================


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

    report_type = (
        report_type.upper()
    )

    if (
        report_type
        not in SUPPORTED_REPORT_TYPES
    ):

        raise HTTPException(
            status_code=404,
            detail=(
                "Unsupported Groww "
                "report type."
            ),
        )

    tax_case = (
        get_tax_case_or_404(
            db,
            case_id,
        )
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

            "client": (
                tax_case.client
            ),

            "report_type": (
                report_type
            ),

            "report_name": (
                SUPPORTED_REPORT_TYPES[
                    report_type
                ]
            ),

            "error": None,
        },
    )


# =========================================================
# UPLOAD + PROCESS
# =========================================================


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

    report_type = (
        report_type.upper()
    )

    # -----------------------------------------------------
    # Validate report type
    # -----------------------------------------------------

    if (
        report_type
        not in SUPPORTED_REPORT_TYPES
    ):

        raise HTTPException(
            status_code=404,
            detail=(
                "Unsupported Groww "
                "report type."
            ),
        )

    # -----------------------------------------------------
    # Tax Case
    # -----------------------------------------------------

    tax_case = (
        get_tax_case_or_404(
            db,
            case_id,
        )
    )

    # -----------------------------------------------------
    # Prevent second ACTIVE report of same type
    # -----------------------------------------------------

    existing_active_report = (
        db.query(BrokerReport)
        .filter(
            BrokerReport.tax_case_id
            == tax_case.id,

            BrokerReport.broker
            == "GROWW",

            BrokerReport.report_type
            == report_type,

            BrokerReport.processing_status.in_(
                list(
                    ACTIVE_REPORT_STATUSES
                )
            ),
        )
        .order_by(
            BrokerReport.id.desc()
        )
        .first()
    )

    if existing_active_report:

        return upload_error_response(
            request=request,
            tax_case=tax_case,
            report_type=report_type,
            message=(
                "A processed Groww report "
                "of this type already exists "
                "for this tax case."
            ),
            status_code=409,
        )

    # -----------------------------------------------------
    # Validate physical upload
    # -----------------------------------------------------

    filename = (
        file.filename
        or ""
    )

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
            request=request,
            tax_case=tax_case,
            report_type=report_type,
            message=str(exc),
        )

    # -----------------------------------------------------
    # SHA-256
    # -----------------------------------------------------

    file_hash = (
        calculate_sha256(
            content
        )
    )

    # -----------------------------------------------------
    # Duplicate active file check
    #
    # VALIDATION_FAILED is intentionally excluded.
    #
    # This means the same file can be retried after
    # parser improvements.
    # -----------------------------------------------------

    duplicate_active_report = (
        db.query(BrokerReport)
        .filter(
            BrokerReport.tax_case_id
            == tax_case.id,

            BrokerReport.file_hash
            == file_hash,

            BrokerReport.processing_status.in_(
                [
                    "PROCESSING",
                    "PROCESSED",
                    "REVIEW_REQUIRED",
                ]
            ),
        )
        .first()
    )

    if duplicate_active_report:

        return upload_error_response(
            request=request,
            tax_case=tax_case,
            report_type=report_type,
            message=(
                "This exact file has already "
                "been uploaded to this tax case."
            ),
            status_code=409,
        )

    # -----------------------------------------------------
    # Save uploaded file
    # -----------------------------------------------------

    stored_path = (
        save_report_file(
            content=content,
            original_filename=filename,
            case_id=tax_case.id,
            report_type=report_type,
        )
    )

    # -----------------------------------------------------
    # Create BrokerReport
    # -----------------------------------------------------

    report = BrokerReport(
        tax_case_id=(
            tax_case.id
        ),

        broker="GROWW",

        report_type=(
            report_type
        ),

        original_filename=(
            filename
        ),

        stored_filename=(
            stored_path
        ),

        file_hash=(
            file_hash
        ),

        format_version=(
            "GROWW_V1"
        ),

        processing_status=(
            "PROCESSING"
        ),
    )

    db.add(
        report
    )

    db.commit()

    db.refresh(
        report
    )

    # -----------------------------------------------------
    # Tolerance
    # -----------------------------------------------------

    tolerance = Decimal(
        str(
            settings
            .reconciliation_tolerance
        )
    )

    # -----------------------------------------------------
    # Parse and calculate
    # -----------------------------------------------------

    try:

        processed = (
            process_groww_report(
                filepath=stored_path,
                report_type=report_type,
                tolerance=tolerance,
            )
        )

    except GrowwParseError as exc:

        report.processing_status = (
            "VALIDATION_FAILED"
        )

        report.validation_message = (
            str(exc)
        )

        db.commit()

        return upload_error_response(
            request=request,
            tax_case=tax_case,
            report_type=report_type,
            message=(
                "Groww validation failed: "
                f"{exc}"
            ),
        )

    # -----------------------------------------------------
    # Pull optional identity fields safely
    # -----------------------------------------------------

    processed_client_code = (
        getattr(
            processed,
            "client_code",
            None,
        )
    )

    processed_pan = (
        getattr(
            processed,
            "pan",
            None,
        )
    )

    # -----------------------------------------------------
    # Save extracted report metadata
    # -----------------------------------------------------

    report.broker_client_name = (
        processed.client_name
    )

    report.broker_client_code = (
        processed_client_code
    )

    report.period_start = (
        processed.period_start
    )

    report.period_end = (
        processed.period_end
    )

    # -----------------------------------------------------
    # Financial year validation
    # -----------------------------------------------------

    fy_validation = (
        validate_financial_year(
            processed,
            tax_case.financial_year,
        )
    )

    # Genuine FY mismatch must be rejected.
    #
    # PARTIAL_PERIOD returns valid=True,
    # so it is allowed to continue processing.

    if not fy_validation.valid:

        report.processing_status = (
            "VALIDATION_FAILED"
        )

        report.validation_message = (
            fy_validation.message
        )

        db.commit()

        return upload_error_response(
            request=request,
            tax_case=tax_case,
            report_type=report_type,
            message=(
                fy_validation.message
            ),
        )

    # -----------------------------------------------------
    # PAN validation
    #
    # Real Groww MF reports may expose PAN.
    # When PAN exists, it must match TaxVerify client PAN.
    # -----------------------------------------------------

    if (
        processed_pan is not None
    ):

        workbook_pan = (
            str(
                processed_pan
            )
            .strip()
            .upper()
        )

        client_pan = (
            tax_case
            .client
            .pan
            .strip()
            .upper()
        )

        if (
            workbook_pan
            != client_pan
        ):

            report.processing_status = (
                "VALIDATION_FAILED"
            )

            report.validation_message = (
                "PAN in the Groww report "
                "does not match the PAN "
                "of this TaxVerify client."
            )

            db.commit()

            return upload_error_response(
                request=request,
                tax_case=tax_case,
                report_type=report_type,
                message=(
                    report
                    .validation_message
                ),
                status_code=409,
            )

    # -----------------------------------------------------
    # Groww UCC validation
    #
    # Compare only if the current report contains a UCC.
    # Mutual Fund reports may not.
    # -----------------------------------------------------

    if (
        processed_client_code
        is not None
    ):

        existing_ucc_report = (
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
                    list(
                        ACTIVE_REPORT_STATUSES
                    )
                ),
            )
            .order_by(
                BrokerReport.id.desc()
            )
            .first()
        )

        if existing_ucc_report:

            old_ucc = (
                str(
                    existing_ucc_report
                    .broker_client_code
                )
                .strip()
            )

            new_ucc = (
                str(
                    processed_client_code
                )
                .strip()
            )

            if (
                old_ucc
                != new_ucc
            ):

                report.processing_status = (
                    "VALIDATION_FAILED"
                )

                report.validation_message = (
                    "Groww Unique Client Code "
                    "does not match the existing "
                    "Groww reports in this "
                    "TaxVerify case."
                )

                db.commit()

                return upload_error_response(
                    request=request,
                    tax_case=tax_case,
                    report_type=report_type,
                    message=(
                        report
                        .validation_message
                    ),
                    status_code=409,
                )

    # -----------------------------------------------------
    # Save metrics
    # -----------------------------------------------------

    for metric in (
        processed.metrics
    ):

        db.add(
            ReportMetric(
                report_id=(
                    report.id
                ),

                metric_key=(
                    metric.key
                ),

                value=(
                    metric.value
                ),

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

    # -----------------------------------------------------
    # Save reconciliation checks
    # -----------------------------------------------------

    for check in (
        processed.reconciliations
    ):

        db.add(
            ReportReconciliation(
                report_id=(
                    report.id
                ),

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

                tolerance=(
                    tolerance
                ),

                status=(
                    check.status
                ),

                message=(
                    check.message
                ),
            )
        )

    # -----------------------------------------------------
    # Determine whether reconciliation itself
    # requires review
    # -----------------------------------------------------

    review_statuses = {
        "MISMATCH",
        "REVIEW_REQUIRED",
    }

    reconciliation_requires_review = (
        any(
            check.status
            in review_statuses

            for check
            in processed.reconciliations
        )
    )

    # -----------------------------------------------------
    # Final report status
    #
    # IMPORTANT:
    #
    # PARTIAL PERIOD:
    #     REVIEW_REQUIRED
    #
    # Reconciliation mismatch:
    #     REVIEW_REQUIRED
    #
    # Otherwise:
    #     PROCESSED
    # -----------------------------------------------------

    if (
        fy_validation.is_partial
        or
        reconciliation_requires_review
    ):

        report.processing_status = (
            "REVIEW_REQUIRED"
        )

    else:

        report.processing_status = (
            "PROCESSED"
        )

    # Preserve FY information for audit/review UI.

    report.validation_message = (
        fy_validation.message
    )

    # -----------------------------------------------------
    # Tax case state
    # -----------------------------------------------------

    if (
        tax_case.status
        == "DRAFT"
    ):

        tax_case.status = (
            "IN_PROGRESS"
        )

    # -----------------------------------------------------
    # Commit everything atomically at end
    # -----------------------------------------------------

    db.commit()

    # -----------------------------------------------------
    # Redirect to report
    # -----------------------------------------------------

    return RedirectResponse(
        url=(
            f"/reports/"
            f"{report.id}"
        ),
        status_code=303,
    )


# =========================================================
# REPORT DETAIL
# =========================================================


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

        for metric
        in report.metrics
    }

    return templates.TemplateResponse(
        request=request,
        name="report_detail.html",
        context={
            "title": (
                f"Groww "
                f"{report.report_type}"
            ),

            "report": (
                report
            ),

            "tax_case": (
                report.tax_case
            ),

            "client": (
                report
                .tax_case
                .client
            ),

            "metrics": (
                metric_map
            ),

            "reconciliations": (
                report
                .reconciliations
            ),
        },
    )