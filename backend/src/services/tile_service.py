"""
Tile Service - Orchestrate satellite tile generation and S3 upload.

Coordinates tile generation workflow:
  1. Queue Celery task for tile generation
  2. Track tile generation status
  3. Generate presigned S3 URLs for frontend consumption
  4. Update database with tile URLs
"""

from __future__ import annotations

import logging
from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from celery.result import AsyncResult

from src.celery_app import celery_app
from src.models.satellite import SatelliteAnalysis
from src.models.project import Project
from src.services.s3_storage import S3StorageService

logger = logging.getLogger(__name__)


class TileService:
    """
    Orchestrate tile generation, S3 upload, and URL management.

    Provides interface for:
      - Queueing tile generation tasks
      - Tracking generation status
      - Generating presigned S3 URLs
    """

    def __init__(self, db: Session):
        """
        Initialize TileService with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.s3_service = S3StorageService()
        self.s3_bucket = self.s3_service.bucket_name

    def queue_tile_generation(
        self, project_uuid: UUID, layer_type: str = "ndvi"
    ) -> str:
        """
        Enqueue tile generation task.

        Validates that project has satellite analysis with GeoTIFF before
        queueing Celery task.

        Args:
            project_uuid: Project UUID
            layer_type: 'ndvi' or 'sar' (default: 'ndvi')

        Returns:
            Celery task ID string

        Raises:
            ValueError: If project/analysis not found or GeoTIFF missing
        """
        # Fetch latest satellite analysis
        analysis = (
            self.db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == project_uuid)
            .order_by(SatelliteAnalysis.acquisition_date.desc())
            .first()
        )

        if not analysis:
            raise ValueError(f"No satellite analysis found for {project_uuid}")

        if not analysis.image_url:
            raise ValueError(
                f"Satellite analysis has no GeoTIFF image_url for {project_uuid}"
            )

        logger.info(
            f"Queueing tile generation for {project_uuid} ({layer_type}), "
            f"GeoTIFF: {analysis.image_url}"
        )

        # Enqueue Celery task
        try:
            task = celery_app.send_task(
                "src.tasks.tile_tasks.generate_project_tiles_task",
                args=[str(project_uuid), layer_type],
            )
            logger.info(f"Enqueued tile task {task.id} for {project_uuid}")
            return str(task.id)
        except Exception as e:
            logger.exception(f"Failed to enqueue tile task for {project_uuid}: {e}")
            raise

    def get_tile_status(self, project_uuid: UUID) -> dict:
        """
        Get tile generation status for a project.

        Checks if tiles have been generated (tile_url_template set) or
        polls Celery for task status if generation in progress.

        Args:
            project_uuid: Project UUID

        Returns:
            dict with keys:
                - status: 'complete'|'pending'|'generating'|'failed'
                - task_id: Celery task ID or None
                - tile_url_template: S3 template URL or None
                - error: Error message or None
        """
        # Get latest satellite analysis
        analysis = (
            self.db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == project_uuid)
            .order_by(SatelliteAnalysis.acquisition_date.desc())
            .first()
        )

        if not analysis:
            return {
                "status": "failed",
                "task_id": None,
                "tile_url_template": None,
                "error": "No satellite analysis found",
            }

        # Check if tiles already generated
        if analysis.tile_url_template:
            return {
                "status": "complete",
                "task_id": None,
                "tile_url_template": analysis.tile_url_template,
                "error": None,
            }

        # Tiles not yet generated; no way to track task status without storing it
        # (would require DB field for task_id or using Celery result backend only)
        # For now, return pending status
        return {
            "status": "pending",
            "task_id": None,
            "tile_url_template": None,
            "error": None,
        }

    def get_tile_presigned_urls(
        self,
        project_uuid: UUID,
        layer: str = "ndvi",
        z_range: tuple = (8, 14),
        expiration: int = 3600,
    ) -> list:
        """
        Generate presigned S3 URLs for tile set.

        Creates a list of presigned URLs for all tiles in the specified
        zoom range. URLs expire in 1 hour by default.

        Args:
            project_uuid: Project UUID
            layer: Layer type ('ndvi', 'sar', etc.)
            z_range: (min_zoom, max_zoom) tuple, default (8, 14)
            expiration: URL expiration time in seconds (default: 3600 = 1 hour, max: 3600)

        Returns:
            List of presigned S3 URLs

        Raises:
            ValueError: If tiles not found for project
        """
        # Hard cap: never exceed 60 minutes
        expiration = min(expiration, 3600)

        # Fetch latest satellite analysis
        analysis = (
            self.db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == project_uuid)
            .order_by(SatelliteAnalysis.acquisition_date.desc())
            .first()
        )

        if not analysis or not analysis.tile_url_template:
            raise ValueError(
                f"Tiles not (yet) generated for project {project_uuid}"
            )

        urls = []
        z_min, z_max = z_range

        for z in range(z_min, z_max + 1):
            # For each zoom level, generate a sample of tiles
            # (in practice, generate URLs on-demand as frontend requests them)
            n_tiles = 2 ** z  # 2^z tiles per dimension

            # Generate ~10 sample tile URLs per zoom level for frontend preview
            step = max(1, n_tiles // 10)

            for x in range(0, n_tiles, step):
                for y in range(0, n_tiles, step):
                    # Build S3 key
                    s3_key = f"tiles/{project_uuid}/{layer}/{z}/{x}/{y}.png"

                    try:
                        # Generate presigned URL
                        url = self.s3_service.get_pdf_url(
                            s3_key, expiration=expiration
                        )
                        if url:
                            urls.append(url)
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate presigned URL for {s3_key}: {e}"
                        )

        logger.info(
            f"Generated {len(urls)} presigned tile URLs for {project_uuid}"
        )
        return urls

    def update_tile_url(
        self, project_uuid: UUID, tile_url_template: str
    ) -> bool:
        """
        Update SatelliteAnalysis with generated tile URL.

        Called by tile generation task after successful tile upload.

        Args:
            project_uuid: Project UUID
            tile_url_template: S3 tile URL template with {z}, {x}, {y} placeholders

        Returns:
            True if update successful

        Raises:
            ValueError: If analysis not found
        """
        analysis = (
            self.db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == project_uuid)
            .order_by(SatelliteAnalysis.acquisition_date.desc())
            .first()
        )

        if not analysis:
            raise ValueError(f"No satellite analysis found for {project_uuid}")

        try:
            analysis.tile_url_template = tile_url_template
            self.db.commit()
            logger.info(
                f"Updated tile URL for {project_uuid}: {tile_url_template}"
            )
            return True
        except Exception as e:
            logger.exception(f"Failed to update tile URL for {project_uuid}: {e}")
            self.db.rollback()
            raise

    def mark_tiles_generated(self, project_uuid: UUID) -> bool:
        """
        Mark project as having tiles generated.

        Updates Project.tiles_generated flag (if field exists in model).

        Args:
            project_uuid: Project UUID

        Returns:
            True if successful
        """
        try:
            project = (
                self.db.query(Project)
                .filter(Project.project_uuid == project_uuid)
                .first()
            )

            if not project:
                logger.warning(f"Project not found: {project_uuid}")
                return False

            # Check if field exists (optional in Phase 5)
            if hasattr(project, "tiles_generated"):
                project.tiles_generated = True
                self.db.commit()
                logger.info(f"Marked project {project_uuid} as tiles generated")

            return True
        except Exception as e:
            logger.exception(f"Failed to mark tiles generated for {project_uuid}: {e}")
            self.db.rollback()
            return False
