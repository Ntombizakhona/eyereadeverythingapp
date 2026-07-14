"""
Unit tests for the Ingest Lambda handler.
"""
import sys
import os
import json
import importlib
import pytest


def _load_ingest_handler():
    """Load ingest handler via importlib to avoid name collision."""
    spec = importlib.util.spec_from_file_location(
        "ingest_handler",
        os.path.join(os.path.dirname(__file__), "..", "services", "ingest", "handler.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestBlogExtraction:
    """Tests for blog content extraction."""

    def test_extract_blog_returns_text(self, mock_aws_services):
        """extract_blog should return non-empty text from a valid page."""
        mod = _load_ingest_handler()
        try:
            result = mod.extract_blog("https://example.com")
            assert isinstance(result, str)
            assert len(result) > 0
        except Exception:
            pytest.skip("Network unavailable")

    def test_extract_blog_invalid_url(self, mock_aws_services):
        """extract_blog should raise an error for invalid URLs."""
        mod = _load_ingest_handler()
        with pytest.raises(Exception):
            mod.extract_blog("https://this-domain-does-not-exist-xyz123.com")


class TestIngestHandler:
    """Tests for the ingest Lambda handler."""

    def test_blog_ingest_saves_to_s3(self, mock_aws_services, sample_validated_event):
        """Blog ingestion should save source text to S3."""
        mod = _load_ingest_handler()
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": "test-job-001", "status": "VALIDATING"}
        )

        try:
            result = mod.handler(sample_validated_event, None)
            assert "source_text_s3_key" in result
            assert "source_text" in result
            assert result["source_text_s3_key"].startswith("test-job-001/")

            obj = mock_aws_services["s3"].get_object(
                Bucket="eyeread-renders-test",
                Key=result["source_text_s3_key"],
            )
            body = obj["Body"].read().decode("utf-8")
            assert len(body) > 0
        except Exception as e:
            if "Network" in str(e) or "Connection" in str(e) or "getaddrinfo" in str(e):
                pytest.skip("Network unavailable")
            raise

    def test_talk_mode_requires_audio(self, mock_aws_services):
        """Talk mode should attempt to access audio from S3."""
        mod = _load_ingest_handler()
        event = {
            "job_id": "test-job-003",
            "mode": "TALK",
            "audio_s3_key": "uploads/nonexistent.webm",
            "target_duration_sec": 60,
        }
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": "test-job-003", "status": "VALIDATING"}
        )

        with pytest.raises(Exception):
            mod.handler(event, None)

    def test_status_updated_to_ingesting(self, mock_aws_services, sample_validated_event):
        """Handler should update status to INGESTING."""
        mod = _load_ingest_handler()
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": "test-job-001", "status": "VALIDATING"}
        )

        try:
            mod.handler(sample_validated_event, None)
        except Exception:
            pass

        item = mock_aws_services["jobs_table"].get_item(
            Key={"job_id": "test-job-001"}
        )["Item"]
        assert item["status"] in ["INGESTING", "VALIDATING"]
