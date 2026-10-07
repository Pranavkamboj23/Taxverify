from dataclasses import dataclass
from decimal import Decimal

from app.brokers.groww.types import (
    GrowwParseResult,
)


@dataclass
class GrowwCalculation:
    realised_pnl: Decimal
    charges: Decimal

    final_net_pnl: Decimal

    turnover: Decimal

    turnover_reported: Decimal | None
    turnover_calculated: Decimal

    pnl_reconciliation_difference: Decimal
    turnover_reconciliation_difference: (
        Decimal | None
    )

    pnl_status: str
    turnover_status: str


def reconcile_difference(
    difference: Decimal,
    tolerance: Decimal,
):
    absolute_difference = abs(difference)

    if absolute_difference == Decimal("0"):
        return "MATCH"

    if absolute_difference <= tolerance:
        return "MATCH_WITH_ROUNDING"

    return "MISMATCH"


def calculate_groww(
    result: GrowwParseResult,
    tolerance: Decimal = Decimal("1.00"),
):

    final_net_pnl = (
        result.realised_pnl.value
        -
        result.charges.value
    )

    pnl_difference = (
        result.trade_level_pnl
        -
        result.realised_pnl.value
    )

    pnl_status = reconcile_difference(
        pnl_difference,
        tolerance,
    )

    if result.reported_turnover:

        turnover = (
            result.reported_turnover.value
        )

        turnover_difference = (
            result.calculated_turnover
            -
            result.reported_turnover.value
        )

        turnover_status = (
            reconcile_difference(
                turnover_difference,
                tolerance,
            )
        )

    else:

        turnover = (
            result.calculated_turnover
        )

        turnover_difference = None

        turnover_status = "CALCULATED"

    return GrowwCalculation(
        realised_pnl=(
            result.realised_pnl.value
        ),

        charges=result.charges.value,

        final_net_pnl=final_net_pnl,

        turnover=turnover,

        turnover_reported=(
            result.reported_turnover.value
            if result.reported_turnover
            else None
        ),

        turnover_calculated=(
            result.calculated_turnover
        ),

        pnl_reconciliation_difference=(
            pnl_difference
        ),

        turnover_reconciliation_difference=(
            turnover_difference
        ),

        pnl_status=pnl_status,

        turnover_status=turnover_status,
    )