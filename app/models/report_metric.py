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


class ReportMetric(Base):
    __tablename__ = "report_metrics"

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

    metric_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    value: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
    )

    source_sheet: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    source_cell: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    source_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    derivation: Mapped[str | None] = mapped_column(
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
        back_populates="metrics",
    )