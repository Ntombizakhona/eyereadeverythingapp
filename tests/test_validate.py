"""
Unit tests for the Validate Lambda handler.
"""
import sys
import os
import importlib
import pytest


def _load_validate_handler():
    """Load validate handler explicitly."""
    spec = importlib.util.spec_from_file_location(
        "validate_handler",
        os.path.join(os.path.dirname(__file__), "..", "services", "validate", "handler.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestValidateHandler:
    """Tests for the validate Lambda handler."""

    def test_blog_mode_valid(self, mock_aws_services, sample_blog_event):
        """Blog mode with valid URL should pass validation."""
        mod = _load_validate_handler()
        result = mod.handler(sample_blog_event, None)
        assert result["job_id"] == "test-job-001"
        assert result["mode"] == "BLOG"
        assert result["target_duration_sec"] == 180

    def test_blog_mode_missing_url(self, mock_aws_services):
        """Blog mode without URL should raise ValueError."""
        mod = _load_validate_handler()
        event = {
            "job_id": "test-fail-001",
            "mode": "BLOG",
            "blog_url": None,
            "style": {"duration": "medium"},
        }
        with pytest.raises(ValueError, match="blog_url"):
            mod.handler(event, None)

    def test_talk_mode_valid(self, mock_aws_services, sample_talk_event):
        """Talk mode with valid audio key should pass validation."""
        mod = _load_validate_handler()
        result = mod.handler(sample_talk_event, None)
        assert result["job_id"] == "test-job-002"
        assert result["mode"] == "TALK"
        assert result["target_duration_sec"] == 60

    def test_talk_mode_missing_audio(self, mock_aws_services):
        """Talk mode without audio key should raise ValueError."""
        mod = _load_validate_handler()
        event = {
            "job_id": "test-fail-002",
            "mode": "TALK",
            "audio_s3_key": None,
            "style": {"duration": "short"},
        }
        with pytest.raises(ValueError, match="audio_s3_key"):
            mod.handler(event, None)

    def test_duration_mapping_short(self, mock_aws_services, sample_blog_event):
        """Short duration should map to 60 seconds."""
        mod = _load_validate_handler()
        sample_blog_event["style"]["duration"] = "short"
        result = mod.handler(sample_blog_event, None)
        assert result["target_duration_sec"] == 60

    def test_duration_mapping_long(self, mock_aws_services, sample_blog_event):
        """Long duration should map to 300 seconds."""
        mod = _load_validate_handler()
        sample_blog_event["style"]["duration"] = "long"
        result = mod.handler(sample_blog_event, None)
        assert result["target_duration_sec"] == 300

    def test_status_updated_to_validating(self, mock_aws_services, sample_blog_event):
        """Handler should update job status to VALIDATING in DynamoDB."""
        mod = _load_validate_handler()
        table = mock_aws_services["jobs_table"]
        table.put_item(Item={"job_id": "test-job-001", "status": "QUEUED"})

        mod.handler(sample_blog_event, None)

        item = table.get_item(Key={"job_id": "test-job-001"})["Item"]
        assert item["status"] == "VALIDATING"
