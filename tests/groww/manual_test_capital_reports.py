from pathlib import Path

from app.brokers.groww.mf_parser import (
    parse_groww_mutual_funds,
)
from app.brokers.groww.shares_parser import (
    parse_groww_shares,
)


BASE = Path(
    "local_test_files"
)


shares = parse_groww_shares(
    BASE
    / "dummy_groww_shares.xlsx"
)


print()
print("=" * 60)
print("GROWW SHARES")
print("=" * 60)

print(
    "Client:",
    shares.client_name,
)

print(
    "Client Code:",
    shares.client_code,
)

print()

print(
    "Intraday Turnover:",
    shares.intraday_turnover.value,
)

print(
    "Calculated Turnover:",
    shares.calculated_intraday_turnover,
)

print(
    "Intraday Net P&L:",
    shares.intraday_net_pnl.value,
)

print(
    "Calculated Net P&L:",
    shares.calculated_intraday_net_pnl,
)

print(
    "Sale Consideration:",
    shares.sale_consideration.value,
)

print(
    "STCG:",
    shares.stcg.value,
)

print(
    "LTCG:",
    shares.ltcg.value,
)


mf = parse_groww_mutual_funds(
    BASE
    / "dummy_groww_mutual_funds.xlsx"
)


print()
print("=" * 60)
print("GROWW MUTUAL FUNDS")
print("=" * 60)

print(
    "Client:",
    mf.client_name,
)

print(
    "Client Code:",
    mf.client_code,
)

print()

print(
    "Sale Consideration:",
    mf.sale_consideration,
)

print(
    "STCG:",
    mf.stcg.value,
)

print(
    "LTCG:",
    mf.ltcg.value,
)

print(
    "Redemptions:",
    mf.redemption_count,
)