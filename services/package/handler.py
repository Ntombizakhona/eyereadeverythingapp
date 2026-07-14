"""
Package Service Lambda Handler
Assembles a YouTube-ready ZIP package from all generated artifacts.
"""
import json
import os
import io
import zipfile
import boto3
from datetime import datetime

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = dynamodb.Table(os.environ.get("DYNAMODB_JOBS_TABLE", "eyereadeverything-jobs"))
RENDERS_BUCKET = os.environ.get("S3_RENDERS_BUCKET", "eyereadeverything-renders")


def update_status(job_id: str, status: str, error: str = None):
    update_expr = "SET #s = :s, updated_at = :u"
    expr_values = {":s": status, ":u": datetime.utcnow().isoformat()}
    expr_names = {"#s": "status"}
    if error:
        update_expr += ", #e = :e"
        expr_values[":e"] = error
        expr_names["#e"] = "error"
    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def download_from_s3(s3_key: str) -> bytes:
    """Download a file from S3."""
    response = s3_client.get_object(Bucket=RENDERS_BUCKET, Key=s3_key)
    return response["Body"].read()


def generate_presigned_url(s3_key: str, expiry: int = 86400) -> str:
    """Generate a pre-signed download URL (24h expiry)."""
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": RENDERS_BUCKET, "Key": s3_key},
        ExpiresIn=expiry,
    )


def handler(event, context):
    """
    Input: event with all S3 keys from prior stages
    Output: event + download URLs
    """
    job_id = event["job_id"]

    try:
        update_status(job_id, "PACKAGING")

        # Collect all artifacts
        artifacts = {
            "video.mp4": event.get("video_s3_key", f"{job_id}/video.mp4"),
            "captions.srt": event.get("captions_s3_key", f"{job_id}/captions.srt"),
            "metadata.json": event.get("metadata_s3_key", f"{job_id}/metadata.json"),
            "script.md": event.get("script_s3_key", f"{job_id}/script.md"),
            "thumbnail.png": event.get("thumbnail_s3_key", f"{job_id}/thumbnail.png"),
        }

        # Build ZIP in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, s3_key in artifacts.items():
                try:
                    data = download_from_s3(s3_key)
                    zf.writestr(filename, data)
                except Exception as e:
                    print(f"Warning: Could not include {filename}: {e}")

        zip_buffer.seek(0)

        # Upload ZIP to S3
        zip_key = f"{job_id}/package.zip"
        s3_client.put_object(
            Bucket=RENDERS_BUCKET,
            Key=zip_key,
            Body=zip_buffer.getvalue(),
            ContentType="application/zip",
        )

        # Generate pre-signed URLs for all outputs
        outputs = {
            "video_url": generate_presigned_url(artifacts["video.mp4"]),
            "captions_url": generate_presigned_url(artifacts["captions.srt"]),
            "metadata_url": generate_presigned_url(artifacts["metadata.json"]),
            "script_url": generate_presigned_url(artifacts["script.md"]),
            "thumbnail_url": generate_presigned_url(artifacts["thumbnail.png"]),
            "audio_url": generate_presigned_url(event.get("narration_s3_key", f"{job_id}/narration.mp3")),
            "package_url": generate_presigned_url(zip_key),
        }

        # Update DynamoDB with outputs and DONE status
        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :s, outputs = :o, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "DONE" if not event.get("auto_upload_youtube") else "UPLOADING",
                ":o": json.dumps(outputs),
                ":u": datetime.utcnow().isoformat(),
            },
        )

        event["outputs"] = outputs
        event["package_s3_key"] = zip_key

        return event
    except Exception as e:
        update_status(job_id, "FAILED", str(e))
        raise
