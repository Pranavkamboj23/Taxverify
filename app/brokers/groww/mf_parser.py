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
class GrowwMutualFundParseResult:
    report_type: str

    client_name: str
    client_code: str

    period_start: object
    period_end: object

    stcg: SourceValue
    ltcg: SourceValue

    sale_consideration: Decimal

    redemption_count: int


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


def calculate_sale_consideration(
    sheet,
):
    heading = find_exact(
        sheet,
        "Redemption Transactions",
    )

    if not heading:
        raise GrowwParseError(
            "Redemption transaction "
            "section not found."
        )

    header_row = heading.row + 1

    redeem_price_column = None
    quantity_column = None

    for column in range(
        1,
        sheet.max_column + 1,
    ):

        header = normalize_text(
            sheet.cell(
                row=header_row,
                column=column,
            ).value
        )

        if (
            header.casefold()
            == "redeem price"
        ):
            redeem_price_column = column

        elif (
            header.casefold()
            == "matched quantity"
        ):
            quantity_column = column

    if redeem_price_column is None:
        raise GrowwParseError(
            "Redeem Price column not found."
        )

    if quantity_column is None:
        raise GrowwParseError(
            "Matched Quantity column not found."
        )

    total = Decimal("0")

    row = header_row + 1
    count = 0

    while row <= sheet.max_row:

        scheme = normalize_text(
            sheet.cell(
                row=row,
                column=1,
            ).value
        )

        if not scheme:
            break

        redeem_price = to_decimal(
            sheet.cell(
                row=row,
                column=redeem_price_column,
            ).value
        )

        quantity = to_decimal(
            sheet.cell(
                row=row,
                column=quantity_column,
            ).value
        )

        transaction_sale_value = (
            redeem_price
            *
            quantity
        )

        total += transaction_sale_value

        count += 1
        row += 1

    if count == 0:
        raise GrowwParseError(
            "No mutual fund redemption "
            "transactions were found."
        )

    return total, count


def parse_groww_mutual_funds(
    filepath: str | Path,
) -> GrowwMutualFundParseResult:

    workbook = load_workbook(
        filepath,
        data_only=True,
    )

    if "Mutual Funds" not in workbook.sheetnames:
        raise GrowwParseError(
            "Expected Groww Mutual Funds sheet "
            "'Mutual Funds' was not found."
        )

    sheet = workbook["Mutual Funds"]

    title = normalize_text(
        sheet["A1"].value
    )

    if (
        "Groww Mutual Funds Tax Statement"
        not in title
    ):
        raise GrowwParseError(
            "This is not a supported Groww "
            "Mutual Funds report."
        )

    client_name, client_code = (
        extract_identity(sheet)
    )

    period_start, period_end = (
        extract_period(title)
    )

    stcg = source_value_from_label(
        sheet,
        "Taxable STCG",
    )

    ltcg = source_value_from_label(
        sheet,
        "Taxable LTCG",
    )

    (
        sale_consideration,
        redemption_count,
    ) = calculate_sale_consideration(
        sheet
    )

    return GrowwMutualFundParseResult(
        report_type="MUTUAL_FUNDS",

        client_name=client_name,
        client_code=client_code,

        period_start=period_start,
        period_end=period_end,

        stcg=stcg,
        ltcg=ltcg,

        sale_consideration=(
            sale_consideration
        ),

        redemption_count=(
            redemption_count
        ),
    )