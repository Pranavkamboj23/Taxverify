from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from app.brokers.groww.parser import (
    GrowwParseError,
    SourceValue,
    extract_identity,
    extract_period,
    find_exact,
    normalize_text,
    to_decimal,
)


@dataclass
class GrowwSharesParseResult:
    report_type: str

    client_name: str
    client_code: str

    period_start: object
    period_end: object

    intraday_turnover: SourceValue
    intraday_net_pnl: SourceValue

    stcg: SourceValue
    ltcg: SourceValue
    sale_consideration: SourceValue

    calculated_intraday_turnover: Decimal
    calculated_intraday_net_pnl: Decimal


def source_value_from_label(
    sheet,
    label: str,
) -> SourceValue:

    cell = find_exact(
        sheet,
        label,
    )

    if not cell:
        raise GrowwParseError(
            f"Required field not found: {label}"
        )

    value_cell = sheet.cell(
        row=cell.row,
        column=cell.column + 1,
    )

    return SourceValue(
        value=to_decimal(
            value_cell.value
        ),
        sheet=sheet.title,
        cell=value_cell.coordinate,
        label=label,
    )


def calculate_intraday_from_trades(
    sheet,
):
    heading = find_exact(
        sheet,
        "Intraday Trades",
    )

    if not heading:
        raise GrowwParseError(
            "Intraday trade section not found."
        )

    row = heading.row + 2

    net_pnl = Decimal("0")
    turnover = Decimal("0")

    trade_count = 0

    while row <= sheet.max_row:

        trade_name = normalize_text(
            sheet.cell(
                row=row,
                column=1,
            ).value
        )

        pnl_value = sheet.cell(
            row=row,
            column=2,
        ).value

        if not trade_name:
            break

        if pnl_value is None:
            break

        pnl = to_decimal(
            pnl_value
        )

        net_pnl += pnl
        turnover += abs(pnl)

        trade_count += 1
        row += 1

    if trade_count == 0:
        raise GrowwParseError(
            "No intraday trades found."
        )

    return turnover, net_pnl


def parse_groww_shares(
    filepath: str | Path,
) -> GrowwSharesParseResult:

    workbook = load_workbook(
        filepath,
        data_only=True,
    )

    if "Tax P&L" not in workbook.sheetnames:
        raise GrowwParseError(
            "Expected Groww Shares sheet "
            "'Tax P&L' was not found."
        )

    sheet = workbook["Tax P&L"]

    title = normalize_text(
        sheet["A1"].value
    )

    if "Groww Shares Tax Statement" not in title:
        raise GrowwParseError(
            "This is not a supported Groww "
            "Shares report."
        )

    client_name, client_code = (
        extract_identity(sheet)
    )

    period_start, period_end = (
        extract_period(title)
    )

    intraday_turnover = (
        source_value_from_label(
            sheet,
            "Intraday Turnover",
        )
    )

    intraday_net_pnl = (
        source_value_from_label(
            sheet,
            "Intraday P&L",
        )
    )

    stcg = source_value_from_label(
        sheet,
        "STCG",
    )

    ltcg = source_value_from_label(
        sheet,
        "LTCG",
    )

    sale_consideration = (
        source_value_from_label(
            sheet,
            "Sell Value",
        )
    )

    (
        calculated_turnover,
        calculated_net_pnl,
    ) = calculate_intraday_from_trades(
        sheet
    )

    return GrowwSharesParseResult(
        report_type="SHARES",

        client_name=client_name,
        client_code=client_code,

        period_start=period_start,
        period_end=period_end,

        intraday_turnover=(
            intraday_turnover
        ),

        intraday_net_pnl=(
            intraday_net_pnl
        ),

        stcg=stcg,
        ltcg=ltcg,

        sale_consideration=(
            sale_consideration
        ),

        calculated_intraday_turnover=(
            calculated_turnover
        ),

        calculated_intraday_net_pnl=(
            calculated_net_pnl
        ),
    )