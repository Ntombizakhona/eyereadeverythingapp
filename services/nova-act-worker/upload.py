"""
Nova Act Worker — ECS Fargate
Automates YouTube Studio upload using Amazon Nova Act.
Downloads video + metadata from S3, opens YouTube Studio in a browser,
and automates the upload workflow.
"""
import json
import os
import sys
import tempfile
import boto3
from datetime import datetime

# AWS clients
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
sfn = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = dynamodb.Table(os.environ.get("DYNAMODB_JOBS_TABLE", "eyereadeverything-jobs"))
RENDERS_BUCKET = os.environ.get("S3_RENDERS_BUCKET", "eyereadeverything-renders")


def update_status(job_id: str, status: str):
    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, updated_at = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":u": datetime.utcnow().isoformat()},
    )


def upload_to_youtube(video_path: str, thumbnail_path: str, metadata: dict):
    """
    Automate YouTube Studio upload using Nova Act.

    Nova Act uses natural language instructions to drive a browser.
    It wraps Playwright under the hood and provides the `NovaAct` context manager.
    """
    from nova_act import NovaAct

    title = metadata.get("selected_title", "Untitled Video")
    description = metadata.get("description", "")
    tags = metadata.get("tags", [])
    tags_str = ", ".join(tags[:15])

    print(f"Starting Nova Act YouTube upload: {title}")

    with NovaAct(
        starting_page="https://studio.youtube.com",
        headless=True,
    ) as nova:

        # Step 1: Click the upload button
        result = nova.act("Click the 'Upload Videos' or 'CREATE' button to start uploading a new video")
        if not result.matches:
            raise Exception("Could not find the upload button on YouTube Studio")

        # Step 2: Select file for upload
        result = nova.act(
            f"Upload the video file. Use the file input to select: {video_path}",
        )

        # Step 3: Wait for upload to start processing
        result = nova.act("Wait for the video upload to begin processing, then proceed to fill in details")

        # Step 4: Set title
        result = nova.act(f"Set the video title to: {title}")

        # Step 5: Set description
        description_short = description[:4500]  # YouTube limit
        result = nova.act(f"Set the video description to: {description_short}")

        # Step 6: Add tags (if the tags section is visible)
        if tags:
            result = nova.act(f"If there is a tags section, add these tags: {tags_str}")

        # Step 7: Upload thumbnail
        if thumbnail_path and os.path.exists(thumbnail_path):
            result = nova.act(f"Upload a custom thumbnail from file: {thumbnail_path}")

        # Step 8: Set visibility to Private (safe default)
        result = nova.act("Go to the Visibility step and set the video visibility to 'Private'")

        # Step 9: Publish
        result = nova.act("Click 'Save' or 'Publish' to finalize the video upload")

        print("Nova Act YouTube upload completed successfully")

    return True


def main():
    """Entry point for the Nova Act ECS Fargate task."""
    job_id = os.environ.get("JOB_ID")
    task_token = os.environ.get("TASK_TOKEN")

    if not job_id:
        print("ERROR: JOB_ID environment variable required")
        sys.exit(1)

    update_status(job_id, "UPLOADING")

    try:
        with tempfile.TemporaryDirectory() as work_dir:
            # Download video, thumbnail, and metadata from S3
            video_path = os.path.join(work_dir, "video.mp4")
            thumb_path = os.path.join(work_dir, "thumbnail.png")
            metadata_path = os.path.join(work_dir, "metadata.json")

            s3.download_file(RENDERS_BUCKET, f"{job_id}/video.mp4", video_path)

            try:
                s3.download_file(RENDERS_BUCKET, f"{job_id}/thumbnail.png", thumb_path)
            except Exception:
                thumb_path = None

            s3.download_file(RENDERS_BUCKET, f"{job_id}/metadata.json", metadata_path)

            with open(metadata_path) as f:
                metadata = json.load(f)

            # Run Nova Act upload
            upload_to_youtube(video_path, thumb_path, metadata)

            # Signal success to Step Functions
            if task_token:
                sfn.send_task_success(
                    taskToken=task_token,
                    output=json.dumps({
                        "job_id": job_id,
                        "youtube_uploaded": True,
                    }),
                )

            # Update job status to DONE
            update_status(job_id, "DONE")

    except Exception as e:
        error_msg = f"YouTube upload failed: {str(e)}"
        print(f"ERROR: {error_msg}")

        # Don't mark the job as FAILED — the video was still generated
        # Just log the upload failure
        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :s, upload_error = :e, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "DONE",
                ":e": error_msg,
                ":u": datetime.utcnow().isoformat(),
            },
        )

        if task_token:
            sfn.send_task_failure(
                taskToken=task_token,
                error="UploadError",
                cause=error_msg,
            )


if __name__ == "__main__":
    main()
