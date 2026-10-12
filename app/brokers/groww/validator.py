from dataclasses import dataclass
from datetime import date

from app.brokers.groww.processor import (
    ProcessedGrowwReport,
)


@dataclass
class ValidationResult:
    valid: bool

    status: str

    message: str

    is_partial: bool = False


def financial_year_dates(
    financial_year: str,
):
    """
    Example:

    2025-26
        ↓
    01 Apr 2025
    31 Mar 2026
    """

    first_year = int(
        financial_year[:4]
    )

    start = date(
        first_year,
        4,
        1,
    )

    end = date(
        first_year + 1,
        3,
        31,
    )

    return (
        start,
        end,
    )


def validate_financial_year(
    result: ProcessedGrowwReport,
    financial_year: str,
) -> ValidationResult:

    (
        expected_start,
        expected_end,
    ) = financial_year_dates(
        financial_year
    )

    # =====================================================
    # COMPLETE FINANCIAL YEAR
    # =====================================================

    if (
        result.period_start
        == expected_start
        and
        result.period_end
        == expected_end
    ):

        return ValidationResult(
            valid=True,

            status="FULL_PERIOD",

            message=(
                "Report covers the full "
                "selected financial year."
            ),

            is_partial=False,
        )

    # =====================================================
    # PARTIAL PERIOD INSIDE SELECTED FY
    # =====================================================

    if (
        result.period_start
        >= expected_start
        and
        result.period_end
        <= expected_end
    ):

        return ValidationResult(
            valid=True,

            status="PARTIAL_PERIOD",

            message=(
                "PARTIAL PERIOD: "
                f"{result.period_start} "
                f"to "
                f"{result.period_end}."
            ),

            is_partial=True,
        )

    # =====================================================
    # WRONG FINANCIAL YEAR
    # =====================================================

    return ValidationResult(
        valid=False,

        status="FY_MISMATCH",

        message=(
            "Report period does not belong "
            "to the selected financial year."
        ),

        is_partial=False,
    )