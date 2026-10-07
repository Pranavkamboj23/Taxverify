from dataclasses import dataclass
from datetime import date

from app.brokers.groww.parser import (
    GrowwParseResult,
)


@dataclass
class ValidationResult:
    valid: bool
    message: str


def financial_year_dates(
    financial_year: str,
):
    """
    Example:
    2025-26
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

    return start, end


def validate_financial_year(
    result: GrowwParseResult,
    financial_year: str,
) -> ValidationResult:

    expected_start, expected_end = (
        financial_year_dates(
            financial_year
        )
    )

    if (
        result.period_start
        == expected_start
        and result.period_end
        == expected_end
    ):
        return ValidationResult(
            valid=True,
            message=(
                "Report covers the full "
                "selected financial year."
            ),
        )

    if (
        result.period_start >= expected_start
        and result.period_end <= expected_end
    ):
        return ValidationResult(
            valid=False,
            message=(
                "PARTIAL PERIOD: "
                f"{result.period_start} to "
                f"{result.period_end}."
            ),
        )

    return ValidationResult(
        valid=False,
        message=(
            "Report period does not match "
            "the selected financial year."
        ),
    )