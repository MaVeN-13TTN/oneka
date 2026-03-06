"""
S3 Storage Service - Handle PDF document uploads and downloads.

Manages tender document storage in AWS S3 with metadata tracking.
"""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import hashlib
from datetime import datetime

from src.config import settings


logger = logging.getLogger(__name__)


class S3StorageService:
    """
    AWS S3 storage service for tender PDF documents.

    Features:
    - PDF upload with metadata
    - Duplicate detection via content hashing
    - Automatic key generation
    - Error handling and logging
    """

    def __init__(self):
        self.bucket_name = settings.aws_s3_bucket

        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )
            logger.info(f"S3 client initialized for bucket: {self.bucket_name}")
        except NoCredentialsError:
            logger.warning("AWS credentials not found. S3 operations will fail.")
            self.s3_client = None

    def upload_pdf(
        self,
        file_path: str,
        tender_number: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Upload PDF file to S3.

        Args:
            file_path: Local path to PDF file
            tender_number: Tender number for key generation
            metadata: Optional metadata dictionary

        Returns:
            S3 object key if successful, None otherwise
        """
        if not self.s3_client:
            logger.error("S3 client not initialized. Check AWS credentials.")
            return None

        if not self.bucket_name:
            logger.error("S3 bucket name not configured.")
            return None

        try:
            # Generate S3 key
            s3_key = self._generate_s3_key(file_path, tender_number)

            # Calculate file hash for metadata
            file_hash = self._calculate_file_hash(file_path)

            # Prepare metadata
            upload_metadata = {
                "tender_number": tender_number,
                "file_hash": file_hash,
                "upload_timestamp": datetime.utcnow().isoformat(),
                "source": "ppip_scraper",
            }

            if metadata:
                upload_metadata.update(metadata)

            # Upload file
            logger.info(f"Uploading PDF to S3: {s3_key}")

            with open(file_path, "rb") as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={
                        "ContentType": "application/pdf",
                        "Metadata": upload_metadata,
                        "ServerSideEncryption": "AES256",
                    },
                )

            logger.info(f"Successfully uploaded PDF: {s3_key}")
            return s3_key

        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return None

        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error during S3 upload: {e}")
            return None

    def upload_pdf_bytes(
        self,
        pdf_bytes: bytes,
        tender_number: str,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Upload PDF from bytes directly (e.g., from HTTP response).

        Args:
            pdf_bytes: PDF file content as bytes
            tender_number: Tender number for key generation
            filename: Optional filename for key generation
            metadata: Optional metadata dictionary

        Returns:
            S3 object key if successful, None otherwise
        """
        if not self.s3_client:
            logger.error("S3 client not initialized.")
            return None

        try:
            # Generate S3 key
            if not filename:
                filename = f"{tender_number}.pdf"

            s3_key = self._generate_s3_key_from_bytes(
                pdf_bytes, tender_number, filename
            )

            # Calculate content hash
            content_hash = hashlib.sha256(pdf_bytes).hexdigest()

            # Prepare metadata
            upload_metadata = {
                "tender_number": tender_number,
                "content_hash": content_hash,
                "upload_timestamp": datetime.utcnow().isoformat(),
                "source": "ppip_scraper",
                "size_bytes": str(len(pdf_bytes)),
            }

            if metadata:
                upload_metadata.update(metadata)

            logger.info(f"Uploading PDF bytes to S3: {s3_key}")

            # Upload bytes
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
                Metadata=upload_metadata,
                ServerSideEncryption="AES256",
            )

            logger.info(f"Successfully uploaded PDF: {s3_key}")
            return s3_key

        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error during S3 upload: {e}")
            return None

    def download_pdf(self, s3_key: str, local_path: str) -> bool:
        """
        Download PDF from S3 to local file.

        Args:
            s3_key: S3 object key
            local_path: Local file path to save

        Returns:
            True if successful, False otherwise
        """
        if not self.s3_client:
            logger.error("S3 client not initialized.")
            return False

        try:
            logger.info(f"Downloading PDF from S3: {s3_key}")

            # Ensure directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            self.s3_client.download_file(self.bucket_name, s3_key, local_path)

            logger.info(f"Successfully downloaded PDF to: {local_path}")
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.error(f"S3 object not found: {s3_key}")
            else:
                logger.error(f"S3 download failed: {e}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error during S3 download: {e}")
            return False

    def get_pdf_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate presigned URL for PDF access.

        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour, max: 1 hour)

        Returns:
            Presigned URL or None if failed
        """
        # Hard cap: never exceed 60 minutes regardless of caller request
        expiration = min(expiration, 3600)

        if not self.s3_client:
            logger.error("S3 client not initialized.")
            return None

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )

            return url

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None

    def check_exists(self, s3_key: str) -> bool:
        """
        Check if object exists in S3.

        Args:
            s3_key: S3 object key

        Returns:
            True if exists, False otherwise
        """
        if not self.s3_client:
            return False

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False

    def get_metadata(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve object metadata from S3.

        Args:
            s3_key: S3 object key

        Returns:
            Metadata dictionary or None if failed
        """
        if not self.s3_client:
            return None

        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)

            return {
                "size": response.get("ContentLength"),
                "last_modified": response.get("LastModified"),
                "content_type": response.get("ContentType"),
                "metadata": response.get("Metadata", {}),
            }

        except ClientError as e:
            logger.error(f"Failed to retrieve metadata: {e}")
            return None

    def delete_pdf(self, s3_key: str) -> bool:
        """
        Delete PDF from S3.

        Args:
            s3_key: S3 object key

        Returns:
            True if successful, False otherwise
        """
        if not self.s3_client:
            return False

        try:
            logger.info(f"Deleting PDF from S3: {s3_key}")

            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)

            logger.info(f"Successfully deleted PDF: {s3_key}")
            return True

        except ClientError as e:
            logger.error(f"S3 deletion failed: {e}")
            return False

    @staticmethod
    def _generate_s3_key(file_path: str, tender_number: str) -> str:
        """
        Generate S3 object key from file path and tender number.

        Format: tenders/YYYY/MM/tender-number/filename.pdf
        """
        now = datetime.utcnow()
        filename = Path(file_path).name

        # Sanitize tender number for use in path
        safe_tender = tender_number.replace("/", "-").replace("\\", "-")

        key = f"tenders/{now.year}/{now.month:02d}/{safe_tender}/{filename}"
        return key

    @staticmethod
    def _generate_s3_key_from_bytes(
        pdf_bytes: bytes, tender_number: str, filename: str
    ) -> str:
        """Generate S3 object key for bytes upload"""
        now = datetime.utcnow()

        # Sanitize tender number
        safe_tender = tender_number.replace("/", "-").replace("\\", "-")

        # Generate content-based filename if not provided
        if not filename:
            content_hash = hashlib.sha256(pdf_bytes).hexdigest()[:8]
            filename = f"{safe_tender}_{content_hash}.pdf"

        key = f"tenders/{now.year}/{now.month:02d}/{safe_tender}/{filename}"
        return key

    @staticmethod
    def _calculate_file_hash(file_path: str) -> str:
        """Calculate SHA-256 hash of file for duplicate detection"""
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()
