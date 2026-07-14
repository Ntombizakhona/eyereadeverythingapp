"""
Validate Job Lambda Handler
Validates job input, checks limits, and updates DynamoDB status.
"""
import json
import os
import boto3
from datetime import datetime

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = dynamodb.Table(os.environ.get("DYNAMODB_JOBS_TABLE", "eyereadeverything-jobs"))


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
        ExpressionAttributeValues=expr_values,
        ExpressionAttributeNames=expr_names,
    )


def handler(event, context):
    """
    Input: { job_id, mode, blog_url?, audio_s3_key?, style, auto_upload_youtube }
    Output: passes through event if valid
    """
    job_id = event["job_id"]
    mode = event["mode"]

    update_status(job_id, "VALIDATING")

    # Validate required fields
    if mode == "BLOG" and not event.get("blog_url"):
        error = "Blog mode requires a blog_url"
        update_status(job_id, "FAILED", error)
        raise ValueError(error)

    if mode == "TALK" and not event.get("audio_s3_key"):
        error = "Talk mode requires an audio_s3_key"
        update_status(job_id, "FAILED", error)
        raise ValueError(error)

    if mode == "TEXT" and not event.get("source_text"):
        error = "Text mode requires source_text"
        update_status(job_id, "FAILED", error)
        raise ValueError(error)

    # Duration limits
    style = event.get("style", {})
    duration = style.get("duration", "medium")
    max_durations = {"short": 60, "medium": 180, "long": 300}
    event["target_duration_sec"] = max_durations.get(duration, 180)

    return event
