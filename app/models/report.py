from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database import Base


class BrokerReport(Base):
    __tablename__ = "broker_reports"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    tax_case_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tax_cases.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    broker: Mapped[str] = mapped_column(
        String(50),
        default="GROWW",
        nullable=False,
    )

    report_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    format_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    broker_client_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    broker_client_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    period_start: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    period_end: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    processing_status: Mapped[str] = mapped_column(
        String(30),
        default="UPLOADED",
        nullable=False,
    )

    validation_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    tax_case = relationship(
        "TaxCase",
        back_populates="reports",
    )

    metrics = relationship(
        "ReportMetric",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    reconciliations = relationship(
        "ReportReconciliation",
        back_populates="report",
        cascade="all, delete-orphan",
    )