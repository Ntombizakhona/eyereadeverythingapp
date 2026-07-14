import uuid
from fastapi import APIRouter

from models import PresignRequest, PresignResponse
from config import settings

router = APIRouter()

# AWS clients (only when not in local dev mode)
if not settings.local_dev:
    import boto3

    s3_client = boto3.client("s3", region_name=settings.aws_region)


@router.post("/presign", response_model=PresignResponse)
async def get_presigned_url(req: PresignRequest):
    """Generate a pre-signed S3 PUT URL for direct browser upload."""
    ext = req.filename.rsplit(".", 1)[-1] if "." in req.filename else "bin"
    s3_key = f"uploads/{uuid.uuid4()}.{ext}"

    if settings.local_dev:
        # Return a mock presigned URL for local development
        return PresignResponse(
            upload_url=f"http://localhost:8000/uploads/mock/{s3_key}",
            s3_key=s3_key,
        )

    url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_uploads_bucket,
            "Key": s3_key,
            "ContentType": req.content_type,
        },
        ExpiresIn=3600,
    )

    return PresignResponse(upload_url=url, s3_key=s3_key)
