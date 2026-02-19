"""
Procurement Service - Business logic for procurement record management.

Handles CRUD operations, scraping integration, and data validation.
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from src.models.procurement import ProcurementRecord
from src.schemas.procurement import (
    ProcurementRecordCreate,
    ProcurementRecordUpdate,
    ScraperStats,
)
from src.services.ppip_scraper import PPIPScraper
from src.services.s3_storage import S3StorageService


logger = logging.getLogger(__name__)


class ProcurementService:
    """
    Service layer for procurement record operations.

    Handles:
    - CRUD operations
    - Scraping and data ingestion
    - PDF storage management
    - Data validation and deduplication
    """

    def __init__(self, db: Session):
        self.db = db
        self.scraper = PPIPScraper()
        self.s3_service = S3StorageService()

    def create_procurement_record(
        self, procurement_data: ProcurementRecordCreate
    ) -> ProcurementRecord:
        """
        Create a new procurement record.

        Args:
            procurement_data: Pydantic schema with procurement data

        Returns:
            Created procurement record
        """
        # Check for duplicate tender_number
        existing = self.get_by_tender_number(procurement_data.tender_number)
        if existing:
            logger.warning(f"Duplicate tender number: {procurement_data.tender_number}")
            raise ValueError(
                f"Tender number already exists: {procurement_data.tender_number}"
            )

        # Create database record
        db_record = ProcurementRecord(**procurement_data.model_dump())

        self.db.add(db_record)
        self.db.commit()
        self.db.refresh(db_record)

        logger.info(f"Created procurement record: {db_record.tender_number}")
        return db_record

    def get_procurement_record(
        self, procurement_id: int
    ) -> Optional[ProcurementRecord]:
        """Get procurement record by ID"""
        return (
            self.db.query(ProcurementRecord)
            .filter(ProcurementRecord.procurement_id == procurement_id)
            .first()
        )

    def get_by_tender_number(self, tender_number: str) -> Optional[ProcurementRecord]:
        """Get procurement record by tender number"""
        return (
            self.db.query(ProcurementRecord)
            .filter(ProcurementRecord.tender_number == tender_number)
            .first()
        )

    def get_procurement_records(
        self,
        skip: int = 0,
        limit: int = 100,
        source_system: Optional[str] = None,
        procuring_entity: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[ProcurementRecord], int]:
        """
        Get paginated list of procurement records with filtering.

        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            source_system: Filter by source system
            procuring_entity: Filter by procuring entity
            search: Search in tender_number, tender_title, contractor_name
            sort_by: Field to sort by
            sort_order: Sort order (asc/desc)

        Returns:
            Tuple of (records, total_count)
        """
        query = self.db.query(ProcurementRecord)

        # Apply filters
        if source_system:
            query = query.filter(ProcurementRecord.source_system == source_system)

        if procuring_entity:
            query = query.filter(
                ProcurementRecord.procuring_entity.ilike(f"%{procuring_entity}%")
            )

        if search:
            search_filter = or_(
                ProcurementRecord.tender_number.ilike(f"%{search}%"),
                ProcurementRecord.tender_title.ilike(f"%{search}%"),
                ProcurementRecord.contractor_name.ilike(f"%{search}%"),
            )
            query = query.filter(search_filter)

        # Get total count before pagination
        total = query.count()

        # Apply sorting
        order_func = desc if sort_order == "desc" else asc
        if hasattr(ProcurementRecord, sort_by):
            query = query.order_by(order_func(getattr(ProcurementRecord, sort_by)))

        # Apply pagination
        records = query.offset(skip).limit(limit).all()

        return records, total

    def update_procurement_record(
        self, procurement_id: int, update_data: ProcurementRecordUpdate
    ) -> Optional[ProcurementRecord]:
        """
        Update procurement record.

        Args:
            procurement_id: ID of record to update
            update_data: Pydantic schema with update data

        Returns:
            Updated record or None if not found
        """
        db_record = self.get_procurement_record(procurement_id)
        if not db_record:
            return None

        # Update only provided fields
        update_dict = update_data.model_dump(exclude_unset=True)

        for field, value in update_dict.items():
            setattr(db_record, field, value)

        self.db.commit()
        self.db.refresh(db_record)

        logger.info(f"Updated procurement record: {db_record.tender_number}")
        return db_record

    def delete_procurement_record(self, procurement_id: int) -> bool:
        """
        Delete procurement record.

        Args:
            procurement_id: ID of record to delete

        Returns:
            True if deleted, False if not found
        """
        db_record = self.get_procurement_record(procurement_id)
        if not db_record:
            return False

        # Delete associated S3 file if exists
        if db_record.document_s3_key is not None:
            self.s3_service.delete_pdf(str(db_record.document_s3_key))

        self.db.delete(db_record)
        self.db.commit()

        logger.info(f"Deleted procurement record: {db_record.tender_number}")
        return True

    def scrape_and_store_tenders(
        self, max_pages: int = 5, download_pdfs: bool = True
    ) -> ScraperStats:
        """
        Scrape tenders from PPIP and store in database.

        Args:
            max_pages: Maximum number of pages to scrape
            download_pdfs: Whether to download and upload PDFs to S3

        Returns:
            ScraperStats with scraping statistics
        """
        logger.info(f"Starting PPIP scrape (max {max_pages} pages)")

        # Reset scraper stats
        self.scraper.reset_stats()

        # Scrape tenders
        tenders = self.scraper.scrape_tenders_list(max_pages=max_pages)

        successful_stores = 0
        duplicates = 0
        failed_stores = 0

        for tender_data in tenders:
            try:
                # Check for duplicate
                existing = self.get_by_tender_number(tender_data["tender_number"])
                if existing:
                    logger.debug(f"Skipping duplicate: {tender_data['tender_number']}")
                    duplicates += 1
                    continue

                # Download and upload PDF if available and requested
                if download_pdfs and tender_data.get("document_url"):
                    s3_key = self._process_pdf(
                        tender_data["document_url"], tender_data["tender_number"]
                    )
                    if s3_key:
                        tender_data["document_s3_key"] = s3_key

                # Create procurement record
                procurement_create = ProcurementRecordCreate(**tender_data)
                self.create_procurement_record(procurement_create)

                successful_stores += 1

            except Exception as e:
                logger.error(
                    f"Failed to store tender {tender_data.get('tender_number')}: {e}"
                )
                failed_stores += 1

        # Prepare statistics
        stats = ScraperStats(
            total_tenders_scraped=len(tenders),
            successful_downloads=successful_stores,
            failed_downloads=failed_stores,
            duplicates_skipped=duplicates,
            processing_time_seconds=0.0,  # Would need timing logic
            last_scrape_timestamp=datetime.utcnow(),
            errors=self.scraper.get_stats().get("errors", []),
        )

        logger.info(
            f"Scraping complete: {successful_stores} stored, {duplicates} duplicates, {failed_stores} failed"
        )
        return stats

    def _process_pdf(self, pdf_url: str, tender_number: str) -> Optional[str]:
        """
        Download PDF and upload to S3.

        Args:
            pdf_url: URL of PDF to download
            tender_number: Tender number for S3 key generation

        Returns:
            S3 key if successful, None otherwise
        """
        try:
            # Download PDF (scraper handles this)
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                temp_path = tmp_file.name

            # Download using scraper
            success = self.scraper.download_pdf(pdf_url, temp_path)

            if not success:
                return None

            # Upload to S3
            s3_key = self.s3_service.upload_pdf(
                file_path=temp_path,
                tender_number=tender_number,
                metadata={
                    "source_url": pdf_url,
                    "download_timestamp": datetime.utcnow().isoformat(),
                },
            )

            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass

            return s3_key

        except Exception as e:
            logger.error(f"Failed to process PDF for {tender_number}: {e}")
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get procurement records statistics"""
        total_records = self.db.query(ProcurementRecord).count()

        # Count by source system
        source_counts = {}
        sources = self.db.query(ProcurementRecord.source_system).distinct().all()
        for (source,) in sources:
            count = (
                self.db.query(ProcurementRecord)
                .filter(ProcurementRecord.source_system == source)
                .count()
            )
            source_counts[source] = count

        # Count records with PDFs
        with_pdfs = (
            self.db.query(ProcurementRecord)
            .filter(ProcurementRecord.document_s3_key.isnot(None))
            .count()
        )

        # Count records linked to projects
        with_projects = (
            self.db.query(ProcurementRecord)
            .filter(ProcurementRecord.project_uuid.isnot(None))
            .count()
        )

        return {
            "total_records": total_records,
            "by_source_system": source_counts,
            "with_pdf_documents": with_pdfs,
            "linked_to_projects": with_projects,
        }
