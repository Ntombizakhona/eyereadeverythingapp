"""
Unit tests for the Package Lambda handler.
"""
import sys
import os
import io
import json
import zipfile
import importlib
import pytest


def _load_package_handler():
    """Load package handler via importlib to avoid handler.py name collision."""
    spec = importlib.util.spec_from_file_location(
        "package_handler",
        os.path.join(os.path.dirname(__file__), "..", "services", "package", "handler.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPackageHandler:
    """Tests for the packager Lambda."""

    def _seed_artifacts(self, s3_client, job_id="test-job-001"):
        """Upload mock artifacts to S3 for packaging."""
        artifacts = {
            f"{job_id}/video.mp4": b"fake-video-content",
            f"{job_id}/captions.srt": b"1\n00:00:00,000 --> 00:00:05,000\nHello",
            f"{job_id}/metadata.json": json.dumps({"title": "Test"}).encode(),
            f"{job_id}/script.md": b"# Test Script",
            f"{job_id}/thumbnail.png": b"fake-png",
            f"{job_id}/narration.mp3": b"fake-mp3",
        }
        for key, body in artifacts.items():
            s3_client.put_object(
                Bucket="eyeread-renders-test", Key=key, Body=body
            )

    def test_creates_zip_package(self, mock_aws_services):
        """Should create a ZIP file containing all artifacts."""
        mod = _load_package_handler()
        job_id = "test-job-001"
        self._seed_artifacts(mock_aws_services["s3"], job_id)
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": job_id, "status": "RENDERING"}
        )

        event = {
            "job_id": job_id,
            "auto_upload_youtube": False,
            "narration_s3_key": f"{job_id}/narration.mp3",
        }

        result = mod.handler(event, None)
        assert "package_s3_key" in result
        assert result["package_s3_key"].endswith(".zip")
        assert "outputs" in result

    def test_zip_contains_expected_files(self, mock_aws_services):
        """ZIP should contain video, captions, metadata, script, and thumbnail."""
        mod = _load_package_handler()
        job_id = "test-job-zip"
        self._seed_artifacts(mock_aws_services["s3"], job_id)
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": job_id, "status": "RENDERING"}
        )

        event = {
            "job_id": job_id,
            "auto_upload_youtube": False,
            "narration_s3_key": f"{job_id}/narration.mp3",
        }

        mod.handler(event, None)

        obj = mock_aws_services["s3"].get_object(
            Bucket="eyeread-renders-test", Key=f"{job_id}/package.zip"
        )
        zip_bytes = obj["Body"].read()

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert "video.mp4" in names
            assert "captions.srt" in names
            assert "metadata.json" in names
            assert "script.md" in names
            assert "thumbnail.png" in names

    def test_outputs_have_presigned_urls(self, mock_aws_services):
        """Outputs should contain pre-signed download URLs."""
        mod = _load_package_handler()
        job_id = "test-job-urls"
        self._seed_artifacts(mock_aws_services["s3"], job_id)
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": job_id, "status": "RENDERING"}
        )

        event = {
            "job_id": job_id,
            "auto_upload_youtube": False,
            "narration_s3_key": f"{job_id}/narration.mp3",
        }

        result = mod.handler(event, None)
        outputs = result["outputs"]

        assert "video_url" in outputs
        assert "captions_url" in outputs
        assert "package_url" in outputs
        assert "eyeread-renders-test" in outputs["video_url"]

    def test_status_set_to_done(self, mock_aws_services):
        """Status should be set to DONE when auto_upload is false."""
        mod = _load_package_handler()
        job_id = "test-job-done"
        self._seed_artifacts(mock_aws_services["s3"], job_id)
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": job_id, "status": "RENDERING"}
        )

        event = {
            "job_id": job_id,
            "auto_upload_youtube": False,
            "narration_s3_key": f"{job_id}/narration.mp3",
        }

        mod.handler(event, None)

        item = mock_aws_services["jobs_table"].get_item(
            Key={"job_id": job_id}
        )["Item"]
        assert item["status"] == "DONE"

    def test_status_set_to_uploading_when_auto(self, mock_aws_services):
        """Status should be UPLOADING when auto_upload_youtube is true."""
        mod = _load_package_handler()
        job_id = "test-job-upload"
        self._seed_artifacts(mock_aws_services["s3"], job_id)
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": job_id, "status": "RENDERING"}
        )

        event = {
            "job_id": job_id,
            "auto_upload_youtube": True,
            "narration_s3_key": f"{job_id}/narration.mp3",
        }

        mod.handler(event, None)

        item = mock_aws_services["jobs_table"].get_item(
            Key={"job_id": job_id}
        )["Item"]
        assert item["status"] == "UPLOADING"

    def test_handles_missing_artifacts_gracefully(self, mock_aws_services):
        """Should not crash if some artifacts are missing."""
        mod = _load_package_handler()
        job_id = "test-job-partial"
        mock_aws_services["s3"].put_object(
            Bucket="eyeread-renders-test",
            Key=f"{job_id}/video.mp4",
            Body=b"video",
        )
        mock_aws_services["s3"].put_object(
            Bucket="eyeread-renders-test",
            Key=f"{job_id}/metadata.json",
            Body=b'{"title":"test"}',
        )
        mock_aws_services["jobs_table"].put_item(
            Item={"job_id": job_id, "status": "RENDERING"}
        )

        event = {
            "job_id": job_id,
            "auto_upload_youtube": False,
        }

        result = mod.handler(event, None)
        assert "package_s3_key" in result
