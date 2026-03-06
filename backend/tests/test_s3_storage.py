"""
Phase 7 — S3StorageService unit tests.

Covers all methods of src/services/s3_storage.py with mocked boto3 client.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from botocore.exceptions import ClientError, NoCredentialsError


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_client_error(code: str = "NoSuchKey", message: str = "Not found"):
    """Create a botocore ClientError with the given error code."""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "HeadObject",
    )


# =============================================================================
# Init
# =============================================================================


class TestS3StorageServiceInit:
    """Tests for __init__ and client creation."""

    @patch("src.services.s3_storage.boto3.client")
    def test_init_creates_s3_client(self, mock_boto):
        mock_boto.return_value = MagicMock()
        from src.services.s3_storage import S3StorageService
        svc = S3StorageService()
        mock_boto.assert_called_once()
        assert svc.s3_client is not None

    @patch("src.services.s3_storage.boto3.client", side_effect=NoCredentialsError())
    def test_init_no_credentials_sets_client_none(self, mock_boto):
        from src.services.s3_storage import S3StorageService
        svc = S3StorageService()
        assert svc.s3_client is None


# =============================================================================
# Upload PDF (file-based)
# =============================================================================


class TestUploadPdf:
    """Tests for upload_pdf()."""

    def test_upload_pdf_success(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 content")

        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
            key = svc.upload_pdf(str(pdf), "T-001")

        assert key is not None
        assert "T-001" in key
        mock_s3.upload_fileobj.assert_called_once()

    def test_upload_pdf_no_client_returns_none(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client", side_effect=NoCredentialsError()):
            svc = S3StorageService()
        result = svc.upload_pdf(str(tmp_path / "x.pdf"), "T-001")
        assert result is None

    def test_upload_pdf_no_bucket_returns_none(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF")
        with patch("src.services.s3_storage.boto3.client"):
            svc = S3StorageService()
            svc.bucket_name = None
        result = svc.upload_pdf(str(pdf), "T-001")
        assert result is None

    def test_upload_pdf_file_not_found(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client"):
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        result = svc.upload_pdf("/nonexistent/path.pdf", "T-001")
        assert result is None

    def test_upload_pdf_client_error(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF")
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.upload_fileobj.side_effect = _make_client_error("AccessDenied")
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        result = svc.upload_pdf(str(pdf), "T-001")
        assert result is None

    def test_upload_pdf_includes_sse_metadata(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF")
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
            svc.upload_pdf(str(pdf), "T-001")
        call_args = mock_s3.upload_fileobj.call_args
        extra_args = call_args[1].get("ExtraArgs") or call_args[0][3] if len(call_args[0]) > 3 else call_args[1]["ExtraArgs"]
        assert extra_args["ServerSideEncryption"] == "AES256"


# =============================================================================
# Upload PDF bytes
# =============================================================================


class TestUploadPdfBytes:
    """Tests for upload_pdf_bytes()."""

    def test_upload_bytes_success(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        key = svc.upload_pdf_bytes(b"%PDF-1.4", "T-002", filename="cert.pdf")
        assert key is not None
        mock_s3.put_object.assert_called_once()

    def test_upload_bytes_no_client(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client", side_effect=NoCredentialsError()):
            svc = S3StorageService()
        result = svc.upload_pdf_bytes(b"%PDF", "T-002")
        assert result is None

    def test_upload_bytes_default_filename(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        key = svc.upload_pdf_bytes(b"%PDF", "T-003")
        assert "T-003" in key

    def test_upload_bytes_client_error(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.put_object.side_effect = _make_client_error("AccessDenied")
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        result = svc.upload_pdf_bytes(b"%PDF", "T-003")
        assert result is None


# =============================================================================
# Download PDF
# =============================================================================


class TestDownloadPdf:
    """Tests for download_pdf()."""

    def test_download_success(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        result = svc.download_pdf("some/key.pdf", str(tmp_path / "out.pdf"))
        assert result is True
        mock_s3.download_file.assert_called_once()

    def test_download_no_client(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client", side_effect=NoCredentialsError()):
            svc = S3StorageService()
        result = svc.download_pdf("key.pdf", str(tmp_path / "out.pdf"))
        assert result is False

    def test_download_no_such_key(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.download_file.side_effect = _make_client_error("NoSuchKey")
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        result = svc.download_pdf("missing/key.pdf", str(tmp_path / "out.pdf"))
        assert result is False


# =============================================================================
# Presigned URL
# =============================================================================


class TestGetPdfUrl:
    """Tests for get_pdf_url()."""

    def test_presigned_url_success(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.return_value = "https://s3.example.com/key?sig=abc"
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        url = svc.get_pdf_url("key.pdf")
        assert url is not None
        assert "s3.example.com" in url

    def test_presigned_url_no_client(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client", side_effect=NoCredentialsError()):
            svc = S3StorageService()
        result = svc.get_pdf_url("key.pdf")
        assert result is None

    def test_presigned_url_client_error(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.side_effect = _make_client_error("AccessDenied")
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        result = svc.get_pdf_url("key.pdf")
        assert result is None

    def test_presigned_url_capped_at_3600(self):
        """Expiration is hard-capped at 3600 seconds."""
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.return_value = "https://url"
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        svc.get_pdf_url("key.pdf", expiration=7200)
        call_args = mock_s3.generate_presigned_url.call_args
        assert call_args[1].get("ExpiresIn", call_args[0][2] if len(call_args[0]) > 2 else None) <= 3600


# =============================================================================
# Check exists
# =============================================================================


class TestCheckExists:
    """Tests for check_exists()."""

    def test_exists_true(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        assert svc.check_exists("key.pdf") is True

    def test_exists_false(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.head_object.side_effect = _make_client_error("404")
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        assert svc.check_exists("missing.pdf") is False


# =============================================================================
# Get metadata
# =============================================================================


class TestGetMetadata:
    """Tests for get_metadata()."""

    def test_metadata_success(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.head_object.return_value = {
                "ContentLength": 1024,
                "LastModified": "2024-01-01T00:00:00Z",
                "ContentType": "application/pdf",
                "Metadata": {"file_hash": "abc123"},
            }
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        meta = svc.get_metadata("some/key.pdf")
        assert meta is not None
        assert meta["size"] == 1024
        assert meta["metadata"]["file_hash"] == "abc123"

    def test_metadata_no_client(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client", side_effect=NoCredentialsError()):
            svc = S3StorageService()
        assert svc.get_metadata("key.pdf") is None


# =============================================================================
# Delete
# =============================================================================


class TestDeletePdf:
    """Tests for delete_pdf()."""

    def test_delete_success(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        assert svc.delete_pdf("key.pdf") is True
        mock_s3.delete_object.assert_called_once()

    def test_delete_client_error(self):
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.delete_object.side_effect = _make_client_error("AccessDenied")
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"
        assert svc.delete_pdf("key.pdf") is False


# =============================================================================
# Static helpers
# =============================================================================


class TestStaticHelpers:
    """Tests for static utility methods."""

    def test_generate_s3_key_format(self):
        from src.services.s3_storage import S3StorageService
        key = S3StorageService._generate_s3_key("/tmp/doc.pdf", "TENDER-001")
        assert key.startswith("tenders/")
        assert "TENDER-001" in key
        assert key.endswith("doc.pdf")

    def test_generate_s3_key_sanitizes_slashes(self):
        from src.services.s3_storage import S3StorageService
        key = S3StorageService._generate_s3_key("/tmp/doc.pdf", "T/2024/001")
        assert "T-2024-001" in key

    def test_calculate_file_hash(self, tmp_path):
        from src.services.s3_storage import S3StorageService
        f = tmp_path / "test.bin"
        content = b"hello world"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert S3StorageService._calculate_file_hash(str(f)) == expected

    def test_generate_s3_key_from_bytes(self):
        from src.services.s3_storage import S3StorageService
        key = S3StorageService._generate_s3_key_from_bytes(
            b"%PDF", "T-001", "cert.pdf"
        )
        assert key.startswith("tenders/")
        assert "T-001" in key
        assert key.endswith("cert.pdf")
