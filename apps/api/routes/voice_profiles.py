import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from config import settings

from models import VoiceProfile, VoiceProfileCreate

router = APIRouter()

# ── In-memory store for local development ──
_local_profiles: dict[str, VoiceProfile] = {}

# ── AWS clients (only when not in local dev mode) ──
if not settings.local_dev:
    import boto3
    from botocore.exceptions import ClientError

    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    profiles_table = dynamodb.Table(settings.dynamodb_voice_profiles_table)


@router.post("", response_model=VoiceProfile)
async def create_profile(req: VoiceProfileCreate):
    """Create a new BYO voice profile with consent."""
    profile = VoiceProfile(
        voice_profile_id=str(uuid.uuid4()),
        user_id="anonymous",
        provider=req.provider,
        reference_audio_s3_key=req.reference_audio_s3_key,
        consent_timestamp=datetime.utcnow().isoformat(),
        consent_text=req.consent_text,
        custom_endpoint_url=req.custom_endpoint_url,
    )

    if settings.local_dev:
        _local_profiles[profile.voice_profile_id] = profile
        return profile

    from botocore.exceptions import ClientError

    try:
        profiles_table.put_item(Item=profile.model_dump())
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return profile


@router.get("")
async def list_profiles(user_id: str = "anonymous"):
    """List voice profiles for a user."""
    if settings.local_dev:
        return [
            p for p in _local_profiles.values()
            if p.user_id == user_id and p.deleted_at is None
        ]

    from botocore.exceptions import ClientError

    try:
        response = profiles_table.scan(
            FilterExpression="user_id = :uid AND attribute_not_exists(deleted_at)",
            ExpressionAttributeValues={":uid": user_id},
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return response.get("Items", [])


@router.delete("/{profile_id}")
async def delete_profile(profile_id: str):
    """Soft-delete a voice profile."""
    now = datetime.utcnow().isoformat()

    if settings.local_dev:
        profile = _local_profiles.get(profile_id)
        if profile:
            profile.deleted_at = now
        return {"message": "Voice profile deleted", "profile_id": profile_id}

    from botocore.exceptions import ClientError

    try:
        profiles_table.update_item(
            Key={"voice_profile_id": profile_id},
            UpdateExpression="SET deleted_at = :d",
            ExpressionAttributeValues={":d": now},
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Voice profile deleted", "profile_id": profile_id}
