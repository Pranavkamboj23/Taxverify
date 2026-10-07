from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database import Base


class ReportReconciliation(Base):
    __tablename__ = "report_reconciliations"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    report_id: Mapped[int] = mapped_column(
        ForeignKey(
            "broker_reports.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    check_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    reported_value: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2),
        nullable=True,
    )

    calculated_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
    )

    difference: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2),
        nullable=True,
    )

    tolerance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=1,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    report = relationship(
        "BrokerReport",
        back_populates="reconciliations",
    )