"""
Unit tests for Pydantic models.
"""
import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from models import (
    Job, JobCreate, StyleSettings, JobOutputs,
    PresignRequest, PresignResponse,
    VoiceProfile, VoiceProfileCreate,
)


class TestStyleSettings:
    """Tests for StyleSettings model."""

    def test_defaults(self):
        s = StyleSettings()
        assert s.duration == "medium"
        assert s.tone == "professional"
        assert s.audience == "general"
        assert s.voice == "polly_default"
        assert s.voice_profile_id is None

    def test_custom_values(self):
        s = StyleSettings(duration="short", tone="energetic", audience="students", voice="byo")
        assert s.duration == "short"
        assert s.tone == "energetic"

    def test_invalid_duration_rejected(self):
        with pytest.raises(Exception):
            StyleSettings(duration="ultra_long")

    def test_invalid_tone_rejected(self):
        with pytest.raises(Exception):
            StyleSettings(tone="angry")


class TestJobCreate:
    """Tests for JobCreate model."""

    def test_blog_mode(self):
        j = JobCreate(mode="BLOG", blog_url="https://example.com", auto_upload_youtube=False)
        assert j.mode == "BLOG"
        assert j.blog_url == "https://example.com"

    def test_talk_mode(self):
        j = JobCreate(mode="TALK", audio_s3_key="uploads/test.webm", auto_upload_youtube=False)
        assert j.mode == "TALK"
        assert j.audio_s3_key == "uploads/test.webm"

    def test_default_style(self):
        j = JobCreate(mode="BLOG", auto_upload_youtube=False)
        assert j.style.duration == "medium"

    def test_invalid_mode_rejected(self):
        with pytest.raises(Exception):
            JobCreate(mode="INVALID", auto_upload_youtube=False)


class TestJob:
    """Tests for Job model."""

    def test_full_job(self):
        j = Job(
            job_id="abc-123",
            mode="BLOG",
            blog_url="https://example.com",
        )
        assert j.job_id == "abc-123"
        assert j.status == "QUEUED"
        assert j.user_id == "anonymous"
        assert j.created_at is not None

    def test_job_serialization(self):
        j = Job(job_id="test-001", mode="TALK")
        data = j.model_dump()
        assert isinstance(data, dict)
        assert data["job_id"] == "test-001"
        assert data["mode"] == "TALK"

    def test_job_with_outputs(self):
        outputs = JobOutputs(video_url="https://s3/video.mp4", package_url="https://s3/pkg.zip")
        j = Job(job_id="test-002", mode="BLOG", outputs=outputs)
        assert j.outputs.video_url == "https://s3/video.mp4"


class TestPresignModels:
    """Tests for presign request/response models."""

    def test_presign_request(self):
        r = PresignRequest(filename="test.webm", content_type="audio/webm")
        assert r.filename == "test.webm"

    def test_presign_response(self):
        r = PresignResponse(upload_url="https://s3.presigned.url", s3_key="uploads/abc.webm")
        assert "presigned" in r.upload_url


class TestVoiceProfile:
    """Tests for voice profile models."""

    def test_create(self):
        v = VoiceProfileCreate(
            reference_audio_s3_key="uploads/voice.mp3",
            consent_text="I consent to use my voice.",
        )
        assert v.provider == "BYO_STYLE_MATCH"

    def test_full_profile(self):
        p = VoiceProfile(
            voice_profile_id="vp-001",
            provider="BYO_STYLE_MATCH",
            reference_audio_s3_key="uploads/voice.mp3",
            consent_timestamp="2026-01-01T00:00:00",
            consent_text="I consent.",
        )
        assert p.deleted_at is None
        assert p.user_id == "anonymous"
