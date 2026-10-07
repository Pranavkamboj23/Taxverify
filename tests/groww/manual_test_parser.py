from decimal import Decimal
from pathlib import Path

from app.brokers.groww.parser import (
    parse_groww_report,
)
from app.brokers.groww.rules import (
    calculate_groww,
)


BASE = Path("local_test_files")


def print_result(
    filename: str,
    report_type: str,
):

    result = parse_groww_report(
        BASE / filename,
        report_type,
    )

    calculation = calculate_groww(
        result,
        Decimal("1.00"),
    )

    print()
    print("=" * 60)

    print(
        f"REPORT TYPE: "
        f"{result.report_type}"
    )

    print(
        f"CLIENT: "
        f"{result.client_name}"
    )

    print(
        f"CLIENT CODE: "
        f"{result.client_code}"
    )

    print(
        f"PERIOD: "
        f"{result.period_start} "
        f"to "
        f"{result.period_end}"
    )

    print()

    print(
        "Realised P&L:",
        calculation.realised_pnl,
    )

    print(
        "Charges:",
        calculation.charges,
    )

    print(
        "Net P&L:",
        calculation.final_net_pnl,
    )

    print()

    print(
        "Turnover:",
        calculation.turnover,
    )

    print(
        "Calculated Turnover:",
        calculation.turnover_calculated,
    )

    print(
        "Reported Turnover:",
        calculation.turnover_reported,
    )

    print()

    print(
        "P&L Reconciliation:",
        calculation.pnl_status,
    )

    print(
        "Turnover Reconciliation:",
        calculation.turnover_status,
    )


print_result(
    "FnO groww.xlsx",
    "FNO",
)

print_result(
    "Commodity Groww.xlsx",
    "COMMODITY",
)