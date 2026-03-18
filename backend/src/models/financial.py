"""
Financial Record model - Budget allocation and disbursement data.
"""

from sqlalchemy import Column, String, Integer, DECIMAL, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class FinancialRecord(Base, TimestampMixin):
    """
    Financial records from budget and disbursement systems.

    Tracks budget allocation, releases, and absorption from Controller
    of Budget (COB), Treasury, IFMIS, and county systems.
    """

    __tablename__ = "financial_records"

    # Primary Key
    financial_id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key to Project
    project_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Reference to parent project (NULL until entity resolution)",
    )

    # Foreign Key to Investigation (set for targeted-mode ingestion)
    investigation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("investigations.investigation_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Investigation that created this record (NULL for bulk ingestion)",
    )

    # Source Information
    source_system = Column(
        String(50),
        nullable=False,
        comment="Source: 'COB', 'Treasury', 'IFMIS', 'County'",
    )

    # Budget Classification
    fiscal_year = Column(
        String(10), nullable=True, index=True, comment="Fiscal year e.g., '2023/2024'"
    )

    vote_head = Column(
        Integer, nullable=True, index=True, comment="Government vote head number"
    )

    sub_vote = Column(
        Integer, nullable=True, comment="Sub-vote number within vote head"
    )

    ministry = Column(
        String, nullable=True, index=True, comment="Ministry or government entity"
    )

    department = Column(String, nullable=True, comment="Department within ministry")

    programme = Column(String, nullable=True, comment="Budget programme name")

    # Financial Amounts
    budget_allocated_kes = Column(
        DECIMAL(15, 2), nullable=True, comment="Total budget allocated for project"
    )

    budget_released_kes = Column(
        DECIMAL(15, 2), nullable=True, comment="Amount released from Treasury"
    )

    budget_absorbed_kes = Column(
        DECIMAL(15, 2), nullable=True, comment="Amount actually spent/absorbed"
    )

    absorption_rate = Column(
        DECIMAL(5, 2), nullable=True, comment="Absorption rate as percentage (0-100)"
    )

    # Reporting Period
    reporting_period = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Reporting period: 'Q1 2024', 'FY 2023/24', 'First Nine Months FY 2019/20'",
    )

    period_start_date = Column(
        Date, nullable=True, comment="Start date of reporting period"
    )

    period_end_date = Column(
        Date, nullable=True, comment="End date of reporting period"
    )

    # Data Source
    document_source = Column(
        String, nullable=True, comment="URL to source document (COB BIRR PDF)"
    )

    # Data Quality
    match_method = Column(
        String(50),
        nullable=True,
        comment="Matching method: 'direct', 'inference', 'manual'",
    )

    confidence_score = Column(
        Integer,
        nullable=True,
        comment="Confidence in project-to-budget linking (0-100)",
    )

    # Relationship
    project = relationship("Project", back_populates="financial_records")

    def __repr__(self):
        return f"<FinancialRecord(ministry='{self.ministry}', absorbed={self.budget_absorbed_kes})>"

    @property
    def financial_progress_percentage(self) -> float:
        """Calculate financial progress as percentage of allocated budget"""
        if self.budget_allocated_kes and self.budget_absorbed_kes:
            return float((self.budget_absorbed_kes / self.budget_allocated_kes) * 100)
        return 0.0
