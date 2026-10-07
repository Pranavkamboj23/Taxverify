from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TaxCase(Base):
    __tablename__ = "tax_cases"

    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "financial_year",
            name="uq_client_financial_year",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    financial_year: Mapped[str] = mapped_column(
        String(9),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="DRAFT",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    client = relationship(
        "Client",
        back_populates="tax_cases",
    )

    reports = relationship(
        "BrokerReport",
        back_populates="tax_case",
        cascade="all, delete-orphan",
    )