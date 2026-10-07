import re

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.brokers.groww.types import (
    GrowwParseResult,
    SourceValue,
)


FNO_TITLE = "Futures & Options"
COMMODITY_TITLE = "Commodities"


class GrowwParseError(Exception):
    pass


def to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise GrowwParseError(
            f"Could not convert value to Decimal: {value}"
        )


def normalize_text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def find_exact(
    sheet: Worksheet,
    text: str,
):
    target = text.casefold()

    for row in sheet.iter_rows():
        for cell in row:

            value = normalize_text(cell.value)

            if value.casefold() == target:
                return cell

    return None


def find_title_sheet(
    workbook,
    report_type: str,
):
    report_type = report_type.upper()

    for sheet in workbook.worksheets:

        for row in sheet.iter_rows(
            min_row=1,
            max_row=min(sheet.max_row, 15),
        ):
            for cell in row:

                value = normalize_text(cell.value)

                if report_type == "FNO":
                    if (
                        "P&L Statement for Futures & Options"
                        in value
                    ):
                        return sheet, value

                elif report_type == "COMMODITY":
                    if (
                        "Tax Statement for Commodities"
                        in value
                    ):
                        return sheet, value

    raise GrowwParseError(
        f"Could not locate Groww {report_type} "
        f"statement title."
    )


def extract_period(title: str):

    match = re.search(
        r"from\s+"
        r"(\d{2}\s+[A-Za-z]{3}\s+\d{4})"
        r"\s+to\s+"
        r"(\d{2}\s+[A-Za-z]{3}\s+\d{4})",
        title,
        re.IGNORECASE,
    )

    if not match:
        raise GrowwParseError(
            "Could not determine report period."
        )

    start = datetime.strptime(
        match.group(1),
        "%d %b %Y",
    ).date()

    end = datetime.strptime(
        match.group(2),
        "%d %b %Y",
    ).date()

    return start, end


def extract_identity(sheet: Worksheet):

    client_name = None
    client_code = None

    for row in range(
        1,
        min(sheet.max_row, 15) + 1,
    ):

        label = normalize_text(
            sheet.cell(row=row, column=1).value
        )

        value = normalize_text(
            sheet.cell(row=row, column=2).value
        )

        if label.casefold() == "name":
            client_name = value

        elif (
            label.casefold()
            == "unique client code"
        ):
            client_code = value

    if not client_name:
        raise GrowwParseError(
            "Groww client name was not found."
        )

    if not client_code:
        raise GrowwParseError(
            "Groww Unique Client Code was not found."
        )

    return client_name, client_code


def find_section_total(
    sheet: Worksheet,
    section_name: str,
) -> SourceValue:

    section_cell = find_exact(
        sheet,
        section_name,
    )

    if not section_cell:
        raise GrowwParseError(
            f"Section not found: {section_name}"
        )

    start_row = section_cell.row + 1

    for row in range(
        start_row,
        min(start_row + 20, sheet.max_row) + 1,
    ):

        label_cell = sheet.cell(
            row=row,
            column=section_cell.column,
        )

        label = normalize_text(
            label_cell.value
        )

        if label.casefold() == "total":

            value_cell = sheet.cell(
                row=row,
                column=section_cell.column + 1,
            )

            return SourceValue(
                value=to_decimal(
                    value_cell.value
                ),
                sheet=sheet.title,
                cell=value_cell.coordinate,
                label=f"{section_name} Total",
            )

    raise GrowwParseError(
        f"Total not found for section: "
        f"{section_name}"
    )


def find_optional_turnover(
    sheet: Worksheet,
):

    turnover_cell = find_exact(
        sheet,
        "Turnover",
    )

    if not turnover_cell:
        return None

    start_row = turnover_cell.row + 1

    total = Decimal("0")
    found = False

    for row in range(
        start_row,
        min(start_row + 10, sheet.max_row) + 1,
    ):

        label = normalize_text(
            sheet.cell(
                row=row,
                column=turnover_cell.column,
            ).value
        )

        value = sheet.cell(
            row=row,
            column=turnover_cell.column + 1,
        ).value

        if label in {
            "Futures",
            "Options",
        }:
            total += to_decimal(value)
            found = True

        elif found:
            break

    if not found:
        return None

    return SourceValue(
        value=total,
        sheet=sheet.title,
        cell=turnover_cell.coordinate,
        label="Turnover",
    )


def calculate_trade_level_turnover(
    sheet: Worksheet,
):
    """
    Groww turnover observed in the supplied
    reports equals the aggregate absolute
    Realized P&L of trade-level rows.
    """

    trade_heading = find_exact(
        sheet,
        "Realised trades (trade level)",
    )

    if not trade_heading:
        raise GrowwParseError(
            "Trade-level section was not found."
        )

    start_row = trade_heading.row + 1

    turnover = Decimal("0")
    signed_pnl = Decimal("0")
    trade_count = 0

    for row in range(
        start_row,
        sheet.max_row + 1,
    ):

        first_value = normalize_text(
            sheet.cell(
                row=row,
                column=1,
            ).value
        )

        if first_value.casefold() == "disclaimer:":
            break

        pnl_value = sheet.cell(
            row=row,
            column=9,
        ).value

        if (
            first_value
            and isinstance(
                pnl_value,
                (int, float, Decimal),
            )
        ):
            pnl = to_decimal(pnl_value)

            signed_pnl += pnl
            turnover += abs(pnl)

            trade_count += 1

    if trade_count == 0:
        raise GrowwParseError(
            "No trade-level rows were found."
        )

    return turnover, signed_pnl


def parse_groww_report(
    filepath: str | Path,
    report_type: str,
) -> GrowwParseResult:

    report_type = report_type.upper()

    if report_type not in {
        "FNO",
        "COMMODITY",
    }:
        raise GrowwParseError(
            "Groww parser currently supports "
            "FNO and COMMODITY only."
        )

    workbook = load_workbook(
        filename=filepath,
        data_only=True,
        read_only=False,
    )

    sheet, title = find_title_sheet(
        workbook,
        report_type,
    )

    client_name, client_code = (
        extract_identity(sheet)
    )

    period_start, period_end = (
        extract_period(title)
    )

    realised_pnl = find_section_total(
        sheet,
        "Realised P&L",
    )

    charges = find_section_total(
        sheet,
        "Charges",
    )

    reported_turnover = (
        find_optional_turnover(sheet)
    )

    (
        calculated_turnover,
        trade_level_pnl,
    ) = calculate_trade_level_turnover(
        sheet
    )

    final_net_pnl = (
        realised_pnl.value
        -
        charges.value
    )

    if reported_turnover:
        turnover_source = "BROKER_REPORTED"
    else:
        turnover_source = (
            "CALCULATED_FROM_TRADE_LEVEL"
        )

    return GrowwParseResult(
        report_type=report_type,

        client_name=client_name,
        client_code=client_code,

        period_start=period_start,
        period_end=period_end,

        realised_pnl=realised_pnl,
        charges=charges,

        reported_turnover=reported_turnover,

        calculated_turnover=(
            calculated_turnover
        ),

        turnover_source=turnover_source,

        trade_level_pnl=trade_level_pnl,

        final_net_pnl=final_net_pnl,
    )