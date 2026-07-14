"""
Integration tests for FastAPI API routes.
Tests the API endpoints with mocked AWS backends.
"""
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_200(self, mock_aws_services):
        """Health endpoint should return 200."""
        from main import app
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "eyereadeverything-api"


class TestJobsEndpoints:
    """Tests for the /jobs endpoints."""

    def test_create_blog_job(self, mock_aws_services):
        """POST /jobs should create a new BLOG job."""
        from main import app
        client = TestClient(app)

        payload = {
            "mode": "BLOG",
            "blog_url": "https://example.com/test-post",
            "style": {
                "duration": "medium",
                "tone": "professional",
                "audience": "developers",
                "voice": "polly_default",
            },
            "auto_upload_youtube": False,
        }

        response = client.post("/jobs", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "BLOG"
        assert data["status"] == "QUEUED"
        assert data["blog_url"] == "https://example.com/test-post"
        assert "job_id" in data

    def test_create_talk_job(self, mock_aws_services):
        """POST /jobs should create a new TALK job."""
        from main import app
        client = TestClient(app)

        payload = {
            "mode": "TALK",
            "audio_s3_key": "uploads/test.webm",
            "style": {
                "duration": "short",
                "tone": "casual",
                "audience": "general",
                "voice": "polly_default",
            },
            "auto_upload_youtube": False,
        }

        response = client.post("/jobs", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "TALK"
        assert data["audio_s3_key"] == "uploads/test.webm"

    def test_get_job_by_id(self, mock_aws_services):
        """GET /jobs/{id} should return the job."""
        from main import app
        client = TestClient(app)

        # Create a job first
        payload = {
            "mode": "BLOG",
            "blog_url": "https://example.com",
            "auto_upload_youtube": False,
        }
        create_resp = client.post("/jobs", json=payload)
        job_id = create_resp.json()["job_id"]

        # Fetch it
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["job_id"] == job_id

    def test_get_nonexistent_job_returns_404(self, mock_aws_services):
        """GET /jobs/{id} should return 404 for unknown IDs."""
        from main import app
        client = TestClient(app)

        response = client.get("/jobs/nonexistent-id-999")
        assert response.status_code == 404

    def test_list_jobs_empty(self, mock_aws_services):
        """GET /jobs should return empty list when no jobs exist."""
        from main import app
        client = TestClient(app)

        response = client.get("/jobs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_jobs_after_creation(self, mock_aws_services):
        """GET /jobs should include created jobs."""
        from main import app
        client = TestClient(app)

        # Create two jobs
        for url in ["https://example.com/a", "https://example.com/b"]:
            client.post("/jobs", json={
                "mode": "BLOG", "blog_url": url, "auto_upload_youtube": False,
            })

        response = client.get("/jobs")
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) >= 2


class TestUploadsEndpoints:
    """Tests for the /uploads endpoints."""

    def test_presign_returns_url_and_key(self, mock_aws_services):
        """POST /uploads/presign should return an upload URL and S3 key."""
        from main import app
        client = TestClient(app)

        response = client.post("/uploads/presign", json={
            "filename": "recording.webm",
            "content_type": "audio/webm",
        })

        assert response.status_code == 200
        data = response.json()
        assert "upload_url" in data
        assert "s3_key" in data
        assert data["s3_key"].startswith("uploads/")
        assert data["s3_key"].endswith(".webm")


class TestVoiceProfileEndpoints:
    """Tests for the /voice-profiles endpoints."""

    def test_create_voice_profile(self, mock_aws_services):
        """POST /voice-profiles should create a profile."""
        from main import app
        client = TestClient(app)

        response = client.post("/voice-profiles", json={
            "reference_audio_s3_key": "uploads/voice-sample.mp3",
            "consent_text": "I consent to use my voice for TTS.",
        })

        assert response.status_code == 200
        data = response.json()
        assert "voice_profile_id" in data
        assert data["provider"] == "BYO_STYLE_MATCH"
        assert data["consent_text"] == "I consent to use my voice for TTS."

    def test_list_voice_profiles_empty(self, mock_aws_services):
        """GET /voice-profiles should return empty list initially."""
        from main import app
        client = TestClient(app)

        response = client.get("/voice-profiles")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_delete_voice_profile(self, mock_aws_services):
        """DELETE /voice-profiles/{id} should soft-delete."""
        from main import app
        client = TestClient(app)

        # Create first
        create_resp = client.post("/voice-profiles", json={
            "reference_audio_s3_key": "uploads/voice.mp3",
            "consent_text": "I consent.",
        })
        profile_id = create_resp.json()["voice_profile_id"]

        # Delete
        response = client.delete(f"/voice-profiles/{profile_id}")
        assert response.status_code == 200
        assert response.json()["profile_id"] == profile_id
