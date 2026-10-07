from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    BrokerReport,
    ReportMetric,
)


@dataclass
class TaxSummaryValue:
    value: Optional[Decimal]
    status: str
    message: str


@dataclass
class GrowwCaseSummary:
    intraday_turnover: TaxSummaryValue
    intraday_net_pnl: TaxSummaryValue

    non_spec_turnover: TaxSummaryValue
    non_spec_net_pnl: TaxSummaryValue

    sale_consideration: TaxSummaryValue

    ltcg: TaxSummaryValue
    stcg: TaxSummaryValue

    processed_report_count: int
    review_required_count: int


def get_metric(
    db: Session,
    report_id: int,
    metric_key: str,
) -> Optional[Decimal]:

    metric = (
        db.query(ReportMetric)
        .filter(
            ReportMetric.report_id
            == report_id,
            ReportMetric.metric_key
            == metric_key,
        )
        .first()
    )

    if not metric:
        return None

    return metric.value


def latest_report_by_type(
    reports: list[BrokerReport],
) -> dict[str, BrokerReport]:

    result = {}

    for report in reports:

        if report.report_type not in result:
            result[report.report_type] = report

    return result


def build_groww_case_summary(
    db: Session,
    case_id: int,
) -> GrowwCaseSummary:

    reports = (
        db.query(BrokerReport)
        .filter(
            BrokerReport.tax_case_id
            == case_id,
            BrokerReport.broker
            == "GROWW",
        )
        .order_by(
            BrokerReport.id.desc()
        )
        .all()
    )

    processed_reports = [
        report
        for report in reports
        if report.processing_status
        == "PROCESSED"
    ]

    review_required_count = sum(
        1
        for report in reports
        if report.processing_status
        == "REVIEW_REQUIRED"
    )

    report_map = latest_report_by_type(
        processed_reports
    )

    # =====================================================
    # NON-SPECULATIVE BUSINESS
    # F&O + COMMODITY
    # =====================================================

    non_spec_turnover = Decimal("0")
    non_spec_net_pnl = Decimal("0")

    non_spec_sources = []

    for report_type in [
        "FNO",
        "COMMODITY",
    ]:

        report = report_map.get(
            report_type
        )

        if not report:
            continue

        turnover = get_metric(
            db,
            report.id,
            "TURNOVER",
        )

        net_pnl = get_metric(
            db,
            report.id,
            "FINAL_NET_PNL",
        )

        if turnover is not None:
            non_spec_turnover += turnover

        if net_pnl is not None:
            non_spec_net_pnl += net_pnl

        non_spec_sources.append(
            report_type
        )

    if non_spec_sources:

        non_spec_turnover_result = (
            TaxSummaryValue(
                value=non_spec_turnover,
                status="CALCULATED",
                message=(
                    "Calculated from: "
                    + ", ".join(
                        non_spec_sources
                    )
                ),
            )
        )

        non_spec_pnl_result = (
            TaxSummaryValue(
                value=non_spec_net_pnl,
                status="CALCULATED",
                message=(
                    "Calculated from: "
                    + ", ".join(
                        non_spec_sources
                    )
                ),
            )
        )

    else:

        non_spec_turnover_result = (
            TaxSummaryValue(
                value=None,
                status="WAITING",
                message=(
                    "Upload Groww F&O "
                    "or Commodity report."
                ),
            )
        )

        non_spec_pnl_result = (
            TaxSummaryValue(
                value=None,
                status="WAITING",
                message=(
                    "Upload Groww F&O "
                    "or Commodity report."
                ),
            )
        )

    # =====================================================
    # SHARES
    # =====================================================

    shares_report = report_map.get(
        "SHARES"
    )

    if shares_report:

        intraday_turnover = get_metric(
            db,
            shares_report.id,
            "INTRADAY_TURNOVER",
        )

        intraday_pnl = get_metric(
            db,
            shares_report.id,
            "INTRADAY_NET_PNL",
        )

        equity_sale = get_metric(
            db,
            shares_report.id,
            "SALE_CONSIDERATION",
        )

        equity_stcg = get_metric(
            db,
            shares_report.id,
            "STCG",
        )

        equity_ltcg = get_metric(
            db,
            shares_report.id,
            "LTCG",
        )

    else:

        intraday_turnover = None
        intraday_pnl = None
        equity_sale = None
        equity_stcg = None
        equity_ltcg = None

    # =====================================================
    # MUTUAL FUNDS
    # =====================================================

    mf_report = report_map.get(
        "MUTUAL_FUNDS"
    )

    if mf_report:

        mf_sale = get_metric(
            db,
            mf_report.id,
            "SALE_CONSIDERATION",
        )

        mf_stcg = get_metric(
            db,
            mf_report.id,
            "STCG",
        )

        mf_ltcg = get_metric(
            db,
            mf_report.id,
            "LTCG",
        )

    else:

        mf_sale = None
        mf_stcg = None
        mf_ltcg = None

    # =====================================================
    # CAPITAL GAIN AGGREGATION
    # =====================================================

    sale_components = [
        value
        for value in [
            equity_sale,
            mf_sale,
        ]
        if value is not None
    ]

    stcg_components = [
        value
        for value in [
            equity_stcg,
            mf_stcg,
        ]
        if value is not None
    ]

    ltcg_components = [
        value
        for value in [
            equity_ltcg,
            mf_ltcg,
        ]
        if value is not None
    ]

    sale_consideration = (
        sum(
            sale_components,
            Decimal("0"),
        )
        if sale_components
        else None
    )

    total_stcg = (
        sum(
            stcg_components,
            Decimal("0"),
        )
        if stcg_components
        else None
    )

    total_ltcg = (
        sum(
            ltcg_components,
            Decimal("0"),
        )
        if ltcg_components
        else None
    )

    return GrowwCaseSummary(

        intraday_turnover=TaxSummaryValue(
            value=intraday_turnover,
            status=(
                "CALCULATED"
                if intraday_turnover
                is not None
                else "WAITING"
            ),
            message=(
                "Groww Shares report"
                if intraday_turnover
                is not None
                else "Groww Shares report required."
            ),
        ),

        intraday_net_pnl=TaxSummaryValue(
            value=intraday_pnl,
            status=(
                "CALCULATED"
                if intraday_pnl
                is not None
                else "WAITING"
            ),
            message=(
                "Groww Shares report"
                if intraday_pnl
                is not None
                else "Groww Shares report required."
            ),
        ),

        non_spec_turnover=(
            non_spec_turnover_result
        ),

        non_spec_net_pnl=(
            non_spec_pnl_result
        ),

        sale_consideration=TaxSummaryValue(
            value=sale_consideration,
            status=(
                "CALCULATED"
                if sale_consideration
                is not None
                else "WAITING"
            ),
            message=(
                "Shares + Mutual Funds"
                if sale_consideration
                is not None
                else (
                    "Shares or Mutual Funds "
                    "report required."
                )
            ),
        ),

        ltcg=TaxSummaryValue(
            value=total_ltcg,
            status=(
                "CALCULATED"
                if total_ltcg
                is not None
                else "WAITING"
            ),
            message=(
                "Equity LTCG + MF LTCG"
                if total_ltcg
                is not None
                else (
                    "Shares or Mutual Funds "
                    "report required."
                )
            ),
        ),

        stcg=TaxSummaryValue(
            value=total_stcg,
            status=(
                "CALCULATED"
                if total_stcg
                is not None
                else "WAITING"
            ),
            message=(
                "Equity STCG + MF STCG"
                if total_stcg
                is not None
                else (
                    "Shares or Mutual Funds "
                    "report required."
                )
            ),
        ),

        processed_report_count=len(
            processed_reports
        ),

        review_required_count=(
            review_required_count
        ),
    )