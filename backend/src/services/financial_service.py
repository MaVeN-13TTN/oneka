"""
Financial Service - COB BIRR PDF ingestion and absorption gap analysis.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.financial import FinancialRecord

logger = logging.getLogger(__name__)

# Allow importing CoBParser from data/ layer
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FinancialService:
    """
    Handles COB BIRR PDF ingestion and financial progress calculations.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── ingestion ─────────────────────────────────────────────────────────

    def ingest_cob_report(self, pdf_path: str, fiscal_year: str) -> int:
        """
        Parses a COB BIRR PDF and saves FinancialRecord rows.

        Iterates every record returned by CoBParser.extract_financial_records()
        and inserts it (skips duplicates by document_source + fiscal_year +
        programme combination).

        Args:
            pdf_path:    Absolute or relative path to the downloaded PDF.
            fiscal_year: Fiscal year string e.g. "2023/2024".

        Returns:
            Number of new FinancialRecord rows inserted.
        """
        try:
            from data.parsers.cob import CoBParser
        except ImportError:
            logger.error(
                "CoBParser not importable — ensure data/ is on sys.path "
                "and pdfplumber is installed."
            )
            return 0

        parser = CoBParser(pdf_path)
        # extract_financial_records needs a project name for fuzzy match;
        # when called from bulk ingestion we pass an empty string to get all rows.
        raw_records = parser.extract_financial_records(
            project_name="",
            fiscal_year=fiscal_year,
            pdf_url=pdf_path,
        )

        count = 0
        for rec in raw_records:
            # Skip duplicates
            existing = (
                self.db.query(FinancialRecord)
                .filter(
                    FinancialRecord.document_source == rec.get("document_source"),
                    FinancialRecord.fiscal_year == rec.get("fiscal_year"),
                    FinancialRecord.programme == rec.get("programme"),
                )
                .first()
            )
            if existing:
                continue

            financial = FinancialRecord(
                source_system=rec.get("source_system", "COB"),
                fiscal_year=rec.get("fiscal_year"),
                vote_head=rec.get("vote_head"),
                ministry=rec.get("ministry"),
                programme=rec.get("programme"),
                budget_allocated_kes=rec.get("budget_allocated_kes"),
                budget_absorbed_kes=rec.get("budget_absorbed_kes"),
                absorption_rate=rec.get("absorption_rate"),
                reporting_period=rec.get("reporting_period"),
                document_source=rec.get("document_source"),
                match_method=rec.get("match_method"),
                confidence_score=rec.get("confidence_score"),
            )
            self.db.add(financial)
            count += 1

        self.db.commit()
        logger.info(f"FinancialService: inserted {count} records from {pdf_path}")
        return count

    def ingest_cob_report_intelligent(
        self,
        pdf_path: str,
        ctx: Any,
        openai_api_key: str,
        model: str = "gpt-4o",
        max_pages: int = 20,
        dpi: int = 200,
        cost_limit_usd: Optional[float] = None,
    ) -> int:
        """
        Intelligent two-stage COB BIRR ingestion using GPT-4o Vision.

        Stage 1: pdfplumber keyword scan (free, fast).
        Stage 2: GPT-4o Vision extraction on candidate pages (targeted).

        Args:
            pdf_path:       Path to the COB BIRR PDF.
            ctx:            ProjectContext (data.context.ProjectContext or any
                            object with canonical_name, aliases, fiscal_years,
                            procuring_entity, ministry, county, vote_head attrs).
            openai_api_key: OpenAI API key.
            model:          Vision model to use (default: "gpt-4o").
            max_pages:      Maximum number of candidate pages to send to Vision.
            dpi:            Page render DPI (default: 200).
            cost_limit_usd: Cap on OpenAI Vision spend for this call (USD).
                            Defaults to None (uncapped); wire from
                            settings.vision_cost_limit_usd in callers.

        Returns:
            Number of new FinancialRecord rows inserted.
        """
        try:
            from openai import AsyncOpenAI
            from data.parsers.intelligent_cob import IntelligentCoBParser
        except ImportError as exc:
            logger.error(
                f"IntelligentCoBParser not importable: {exc} — "
                "ensure data/ is on sys.path and openai/pdf2image are installed."
            )
            return 0

        client = AsyncOpenAI(api_key=openai_api_key)
        parser = IntelligentCoBParser(
            pdf_path=pdf_path,
            ctx=ctx,
            openai_client=client,
            max_vision_pages=max_pages,
            dpi=dpi,
            cost_limit_usd=cost_limit_usd,
        )
        # Bridge async parser into this synchronous service method.
        raw_records = asyncio.run(parser.extract())

        count = 0
        for rec in raw_records:
            # Skip duplicates by document_source + fiscal_year + programme
            existing = (
                self.db.query(FinancialRecord)
                .filter(
                    FinancialRecord.document_source == rec.get("document_source"),
                    FinancialRecord.fiscal_year == rec.get("fiscal_year"),
                    FinancialRecord.programme == rec.get("programme"),
                )
                .first()
            )
            if existing:
                continue

            financial = FinancialRecord(
                source_system=rec.get("source_system", "COB"),
                fiscal_year=rec.get("fiscal_year"),
                vote_head=rec.get("vote_head"),
                ministry=rec.get("ministry"),
                programme=rec.get("programme"),
                budget_allocated_kes=rec.get("budget_allocated_kes"),
                budget_released_kes=rec.get("budget_released_kes"),
                budget_absorbed_kes=rec.get("budget_absorbed_kes"),
                absorption_rate=rec.get("absorption_rate"),
                reporting_period=rec.get("reporting_period"),
                document_source=rec.get("document_source"),
                match_method=rec.get("match_method"),
                confidence_score=rec.get("confidence_score"),
            )
            self.db.add(financial)
            count += 1

        self.db.commit()
        logger.info(
            f"FinancialService: intelligent ingest inserted {count} records "
            f"from {pdf_path} (vision_cost=${parser.total_cost_usd:.4f})"
        )
        return count

    # ── queries ───────────────────────────────────────────────────────────

    def get_financial_records_for_project(
        self, project_uuid: UUID
    ) -> List[FinancialRecord]:
        """Returns all financial records linked to a project UUID."""
        return (
            self.db.query(FinancialRecord)
            .filter(FinancialRecord.project_uuid == project_uuid)
            .order_by(FinancialRecord.fiscal_year.desc())
            .all()
        )

    def calculate_absorption_gap(self, project_uuid: UUID) -> dict:
        """
        Calculates the financial absorption gap for a project.

        Returns a dict with:
            total_allocated_kes:  Sum of all budget allocations.
            total_absorbed_kes:   Sum of all expenditure.
            absorption_rate:      Weighted average absorption rate (%).
            gap_kes:              Allocated minus absorbed (positive = underspent).
            record_count:         Number of financial records used.
        """
        records = self.get_financial_records_for_project(project_uuid)
        if not records:
            return {
                "total_allocated_kes": 0,
                "total_absorbed_kes": 0,
                "absorption_rate": 0.0,
                "gap_kes": 0,
                "record_count": 0,
            }

        total_alloc = sum(
            float(r.budget_allocated_kes) for r in records if r.budget_allocated_kes
        )
        total_absorbed = sum(
            float(r.budget_absorbed_kes) for r in records if r.budget_absorbed_kes
        )
        rate = (total_absorbed / total_alloc * 100) if total_alloc > 0 else 0.0

        return {
            "total_allocated_kes": round(total_alloc, 2),
            "total_absorbed_kes": round(total_absorbed, 2),
            "absorption_rate": round(rate, 2),
            "gap_kes": round(total_alloc - total_absorbed, 2),
            "record_count": len(records),
        }
