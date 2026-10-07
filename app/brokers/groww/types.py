from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class SourceValue:
    value: Decimal
    sheet: str
    cell: str
    label: str


@dataclass
class GrowwParseResult:
    report_type: str

    client_name: str
    client_code: str

    period_start: date
    period_end: date

    realised_pnl: SourceValue
    charges: SourceValue

    reported_turnover: Optional[SourceValue]

    calculated_turnover: Decimal
    turnover_source: str

    trade_level_pnl: Decimal

    final_net_pnl: Decimal