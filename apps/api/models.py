from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class StyleSettings(BaseModel):
    duration: Literal["short", "medium", "long"] = "medium"
    tone: Literal["professional", "casual", "energetic"] = "professional"
    audience: str = "general"
    voice: Literal["polly_default", "nova_sonic", "byo"] = "polly_default"
    voice_profile_id: Optional[str] = None
    visual_style: Literal[
        "cinematic", "cartoon", "anime", "claymation", "watercolor"
    ] = "cinematic"


class JobCreate(BaseModel):
    mode: Literal["BLOG", "TALK", "TEXT"]
    blog_url: Optional[str] = None
    audio_s3_key: Optional[str] = None
    source_text: Optional[str] = None
    style: StyleSettings = Field(default_factory=StyleSettings)
    auto_upload_youtube: bool = False


class JobOutputs(BaseModel):
    script_url: Optional[str] = None
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    captions_url: Optional[str] = None
    metadata_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    package_url: Optional[str] = None


JOB_STATUSES = [
    "QUEUED", "VALIDATING", "INGESTING", "RETRIEVING_CONTEXT",
    "PLANNING", "SCRIPTING", "GENERATING_METADATA",
    "GENERATING_CAPTIONS", "NARRATING", "RENDERING",
    "PACKAGING", "UPLOADING", "DONE", "FAILED", "PAUSED", "CANCELLED"
]

JobStatus = Literal[
    "QUEUED", "VALIDATING", "INGESTING", "RETRIEVING_CONTEXT",
    "PLANNING", "SCRIPTING", "GENERATING_METADATA",
    "GENERATING_CAPTIONS", "NARRATING", "RENDERING",
    "PACKAGING", "UPLOADING", "DONE", "FAILED", "PAUSED", "CANCELLED"
]


class Job(BaseModel):
    job_id: str
    user_id: str = "anonymous"
    mode: Literal["BLOG", "TALK", "TEXT"]
    status: JobStatus = "QUEUED"
    style: StyleSettings = Field(default_factory=StyleSettings)
    blog_url: Optional[str] = None
    audio_s3_key: Optional[str] = None
    source_text: Optional[str] = None
    auto_upload_youtube: bool = False
    outputs: Optional[JobOutputs] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PresignRequest(BaseModel):
    filename: str
    content_type: str


class PresignResponse(BaseModel):
    upload_url: str
    s3_key: str


class VoiceProfileCreate(BaseModel):
    reference_audio_s3_key: str
    provider: Literal["BYO_STYLE_MATCH", "BYO_CUSTOM_ENDPOINT"] = "BYO_STYLE_MATCH"
    consent_text: str
    custom_endpoint_url: Optional[str] = None


class VoiceProfile(BaseModel):
    voice_profile_id: str
    user_id: str = "anonymous"
    provider: Literal["BYO_STYLE_MATCH", "BYO_CUSTOM_ENDPOINT"]
    reference_audio_s3_key: str
    consent_timestamp: str
    consent_text: str
    custom_endpoint_url: Optional[str] = None
    deleted_at: Optional[str] = None
