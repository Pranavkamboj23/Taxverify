from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from app.brokers.groww.mf_parser import (
    parse_groww_mutual_funds,
)
from app.brokers.groww.parser import (
    GrowwParseError,
    parse_groww_report,
)
from app.brokers.groww.rules import (
    calculate_groww,
    reconcile_difference,
)
from app.brokers.groww.shares_parser import (
    parse_groww_shares,
)


@dataclass
class MetricRecord:
    key: str
    value: Decimal

    source_sheet: Optional[str] = None
    source_cell: Optional[str] = None
    source_label: Optional[str] = None

    derivation: Optional[str] = None


@dataclass
class ReconciliationRecord:
    check_name: str

    reported_value: Optional[Decimal]
    calculated_value: Decimal

    difference: Optional[Decimal]

    status: str
    message: str


@dataclass
class ProcessedGrowwReport:
    report_type: str

    client_name: str

    client_code: Optional[str]
    pan: Optional[str]

    period_start: date
    period_end: date

    metrics: list[MetricRecord]
    reconciliations: list[ReconciliationRecord]


# =========================================================
# F&O / COMMODITY
# =========================================================

def process_fno_or_commodity(
    filepath: str | Path,
    report_type: str,
    tolerance: Decimal,
) -> ProcessedGrowwReport:

    parsed = parse_groww_report(
        filepath,
        report_type,
    )

    calculation = calculate_groww(
        parsed,
        tolerance,
    )

    metrics = [
        MetricRecord(
            key="REALISED_PNL",
            value=(
                calculation.realised_pnl
            ),
            source_sheet=(
                parsed.realised_pnl.sheet
            ),
            source_cell=(
                parsed.realised_pnl.cell
            ),
            source_label=(
                parsed.realised_pnl.label
            ),
        ),

        MetricRecord(
            key="CHARGES",
            value=calculation.charges,
            source_sheet=(
                parsed.charges.sheet
            ),
            source_cell=(
                parsed.charges.cell
            ),
            source_label=(
                parsed.charges.label
            ),
        ),

        MetricRecord(
            key="FINAL_NET_PNL",
            value=(
                calculation.final_net_pnl
            ),
            derivation=(
                "Groww rule: "
                "Realised P&L - Charges"
            ),
        ),

        MetricRecord(
            key="TURNOVER",
            value=calculation.turnover,
            derivation=(
                "Broker-reported turnover "
                "when available; otherwise "
                "calculated from trade-level "
                "absolute P&L."
            ),
        ),

        MetricRecord(
            key="CALCULATED_TURNOVER",
            value=(
                calculation
                .turnover_calculated
            ),
            derivation=(
                "SUM(ABS(trade-level "
                "Realized P&L))"
            ),
        ),
    ]

    if (
        calculation.turnover_reported
        is not None
    ):

        metrics.append(
            MetricRecord(
                key="REPORTED_TURNOVER",
                value=(
                    calculation
                    .turnover_reported
                ),
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
        )

    reconciliations = [
        ReconciliationRecord(
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
            status=(
                calculation.pnl_status
            ),
            message=(
                "Trade-level realised P&L "
                "compared with summary "
                "Realised P&L."
            ),
        ),

        ReconciliationRecord(
            check_name=(
                "Reported vs "
                "Calculated Turnover"
            ),
            reported_value=(
                calculation.turnover_reported
            ),
            calculated_value=(
                calculation
                .turnover_calculated
            ),
            difference=(
                calculation
                .turnover_reconciliation_difference
            ),
            status=(
                calculation.turnover_status
            ),
            message=(
                "Turnover checked against "
                "trade-level absolute P&L."
            ),
        ),
    ]

    return ProcessedGrowwReport(
        report_type=report_type,

        client_name=(
            parsed.client_name
        ),

        client_code=(
            parsed.client_code
        ),

        pan=None,

        period_start=(
            parsed.period_start
        ),

        period_end=(
            parsed.period_end
        ),

        metrics=metrics,

        reconciliations=(
            reconciliations
        ),
    )


# =========================================================
# SHARES
# =========================================================

def process_shares(
    filepath: str | Path,
    tolerance: Decimal,
) -> ProcessedGrowwReport:

    parsed = parse_groww_shares(
        filepath
    )

    turnover_difference = (
        parsed
        .calculated_intraday_turnover
        -
        parsed
        .intraday_turnover
        .value
    )

    pnl_difference = (
        parsed
        .calculated_intraday_net_pnl
        -
        parsed
        .intraday_net_pnl
        .value
    )

    stcg_difference = (
        parsed.calculated_stcg
        -
        parsed.stcg.value
    )

    ltcg_difference = (
        parsed.calculated_ltcg
        -
        parsed.ltcg.value
    )

    metrics = [
        MetricRecord(
            key="INTRADAY_TURNOVER",
            value=(
                parsed
                .intraday_turnover
                .value
            ),
            source_sheet=(
                parsed
                .intraday_turnover
                .sheet
            ),
            source_cell=(
                parsed
                .intraday_turnover
                .cell
            ),
            source_label=(
                parsed
                .intraday_turnover
                .label
            ),
        ),

        MetricRecord(
            key="INTRADAY_NET_PNL",
            value=(
                parsed
                .intraday_net_pnl
                .value
            ),
            source_sheet=(
                parsed
                .intraday_net_pnl
                .sheet
            ),
            source_cell=(
                parsed
                .intraday_net_pnl
                .cell
            ),
            source_label=(
                parsed
                .intraday_net_pnl
                .label
            ),
        ),

        MetricRecord(
            key="SALE_CONSIDERATION",
            value=(
                parsed.sale_consideration
            ),
            derivation=(
                "SUM(Sell Value) for "
                "Short Term + Long Term "
                "investment trades."
            ),
        ),

        MetricRecord(
            key="STCG",
            value=parsed.stcg.value,
            source_sheet=(
                parsed.stcg.sheet
            ),
            source_cell=(
                parsed.stcg.cell
            ),
            source_label=(
                parsed.stcg.label
            ),
        ),

        MetricRecord(
            key="LTCG",
            value=parsed.ltcg.value,
            source_sheet=(
                parsed.ltcg.sheet
            ),
            source_cell=(
                parsed.ltcg.cell
            ),
            source_label=(
                parsed.ltcg.label
            ),
        ),
    ]

    reconciliations = [
        ReconciliationRecord(
            check_name=(
                "Intraday Turnover"
            ),
            reported_value=(
                parsed
                .intraday_turnover
                .value
            ),
            calculated_value=(
                parsed
                .calculated_intraday_turnover
            ),
            difference=(
                turnover_difference
            ),
            status=(
                reconcile_difference(
                    turnover_difference,
                    tolerance,
                )
            ),
            message=(
                "Summary Intraday Turnover "
                "checked against absolute "
                "trade-level P&L."
            ),
        ),

        ReconciliationRecord(
            check_name=(
                "Intraday P&L"
            ),
            reported_value=(
                parsed
                .intraday_net_pnl
                .value
            ),
            calculated_value=(
                parsed
                .calculated_intraday_net_pnl
            ),
            difference=(
                pnl_difference
            ),
            status=(
                reconcile_difference(
                    pnl_difference,
                    tolerance,
                )
            ),
            message=(
                "Summary Intraday P&L "
                "checked against trade-level "
                "P&L."
            ),
        ),

        ReconciliationRecord(
            check_name="STCG",
            reported_value=(
                parsed.stcg.value
            ),
            calculated_value=(
                parsed.calculated_stcg
            ),
            difference=(
                stcg_difference
            ),
            status=(
                reconcile_difference(
                    stcg_difference,
                    tolerance,
                )
            ),
            message=(
                "Summary Short Term P&L "
                "checked against Short Term "
                "trade-level P&L."
            ),
        ),

        ReconciliationRecord(
            check_name="LTCG",
            reported_value=(
                parsed.ltcg.value
            ),
            calculated_value=(
                parsed.calculated_ltcg
            ),
            difference=(
                ltcg_difference
            ),
            status=(
                reconcile_difference(
                    ltcg_difference,
                    tolerance,
                )
            ),
            message=(
                "Summary Long Term P&L "
                "checked against Long Term "
                "trade-level P&L."
            ),
        ),
    ]

    return ProcessedGrowwReport(
        report_type="SHARES",

        client_name=(
            parsed.client_name
        ),

        client_code=(
            parsed.client_code
        ),

        pan=None,

        period_start=(
            parsed.period_start
        ),

        period_end=(
            parsed.period_end
        ),

        metrics=metrics,

        reconciliations=(
            reconciliations
        ),
    )


# =========================================================
# MUTUAL FUNDS
# =========================================================

def process_mutual_funds(
    filepath: str | Path,
    tolerance: Decimal,
) -> ProcessedGrowwReport:

    parsed = (
        parse_groww_mutual_funds(
            filepath
        )
    )

    stcg_difference = (
        parsed.transaction_stcg
        -
        parsed.stcg.value
    )

    ltcg_difference = (
        parsed.transaction_ltcg
        -
        parsed.ltcg.value
    )

    metrics = [
        MetricRecord(
            key="SALE_CONSIDERATION",
            value=(
                parsed.sale_consideration
            ),
            derivation=(
                "SUM(Redeem Price × "
                "Matched Quantity), "
                "transaction by transaction."
            ),
        ),

        MetricRecord(
            key="STCG",
            value=parsed.stcg.value,
            source_sheet=(
                parsed.stcg.sheet
            ),
            source_cell=(
                parsed.stcg.cell
            ),
            source_label=(
                parsed.stcg.label
            ),
        ),

        MetricRecord(
            key="LTCG",
            value=parsed.ltcg.value,
            source_sheet=(
                parsed.ltcg.sheet
            ),
            source_cell=(
                parsed.ltcg.cell
            ),
            source_label=(
                parsed.ltcg.label
            ),
        ),
    ]

    reconciliations = [
        ReconciliationRecord(
            check_name=(
                "MF Sale Consideration"
            ),
            reported_value=None,
            calculated_value=(
                parsed.sale_consideration
            ),
            difference=None,
            status="CALCULATED",
            message=(
                f"Calculated from "
                f"{parsed.redemption_count} "
                f"matched redemption rows."
            ),
        ),

        ReconciliationRecord(
            check_name="MF STCG",
            reported_value=(
                parsed.stcg.value
            ),
            calculated_value=(
                parsed.transaction_stcg
            ),
            difference=(
                stcg_difference
            ),
            status=(
                reconcile_difference(
                    stcg_difference,
                    tolerance,
                )
            ),
            message=(
                "Taxable Short Term summary "
                "checked against transaction "
                "capital gains."
            ),
        ),

        ReconciliationRecord(
            check_name="MF LTCG",
            reported_value=(
                parsed.ltcg.value
            ),
            calculated_value=(
                parsed.transaction_ltcg
            ),
            difference=(
                ltcg_difference
            ),
            status=(
                reconcile_difference(
                    ltcg_difference,
                    tolerance,
                )
            ),
            message=(
                "Taxable Long Term summary "
                "checked against transaction "
                "capital gains."
            ),
        ),
    ]

    return ProcessedGrowwReport(
        report_type="MUTUAL_FUNDS",

        client_name=(
            parsed.client_name
        ),

        client_code=None,

        pan=parsed.pan,

        period_start=(
            parsed.period_start
        ),

        period_end=(
            parsed.period_end
        ),

        metrics=metrics,

        reconciliations=(
            reconciliations
        ),
    )


# =========================================================
# ROUTER
# =========================================================

def process_groww_report(
    filepath: str | Path,
    report_type: str,
    tolerance: Decimal,
) -> ProcessedGrowwReport:

    report_type = (
        report_type.upper()
    )

    if report_type in {
        "FNO",
        "COMMODITY",
    }:

        return (
            process_fno_or_commodity(
                filepath,
                report_type,
                tolerance,
            )
        )

    if report_type == "SHARES":

        return process_shares(
            filepath,
            tolerance,
        )

    if (
        report_type
        == "MUTUAL_FUNDS"
    ):

        return process_mutual_funds(
            filepath,
            tolerance,
        )

    raise GrowwParseError(
        f"Unsupported Groww "
        f"report type: "
        f"{report_type}"
    )