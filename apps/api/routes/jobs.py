import uuid
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from config import settings

from models import Job, JobCreate, JobOutputs

router = APIRouter()

# ── In-memory store for local development ──
_local_jobs: dict[str, Job] = {}

# ── AWS clients (only when not in local dev mode) ──
if not settings.local_dev:
    import boto3
    from botocore.exceptions import ClientError

    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    sfn_client = boto3.client("stepfunctions", region_name=settings.aws_region)
    jobs_table = dynamodb.Table(settings.dynamodb_jobs_table)


def _job_to_dict(job: Job) -> dict:
    """Convert job model to DynamoDB item."""
    data = job.model_dump()
    # Convert nested models to JSON strings for DynamoDB
    if data.get("outputs"):
        data["outputs"] = json.dumps(data["outputs"])
    if data.get("style"):
        data["style"] = json.dumps(data["style"])
    return data


def _dict_to_job(item: dict) -> Job:
    """Convert DynamoDB item to Job model."""
    if isinstance(item.get("outputs"), str):
        item["outputs"] = json.loads(item["outputs"])
    if isinstance(item.get("style"), str):
        item["style"] = json.loads(item["style"])
    return Job(**item)


@router.post("", response_model=Job)
async def create_job(job_create: JobCreate):
    """Create a new video generation job and start the pipeline."""
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    job = Job(
        job_id=job_id,
        user_id="anonymous",  # Cognito integration later
        mode=job_create.mode,
        status="QUEUED",
        style=job_create.style,
        blog_url=job_create.blog_url,
        audio_s3_key=job_create.audio_s3_key,
        source_text=job_create.source_text,
        auto_upload_youtube=job_create.auto_upload_youtube,
        created_at=now,
        updated_at=now,
    )

    if settings.local_dev:
        # Store in memory for local development
        _local_jobs[job_id] = job
        return job

    # Save to DynamoDB
    from botocore.exceptions import ClientError

    try:
        jobs_table.put_item(Item=_job_to_dict(job))
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")

    # Start Step Functions execution
    if settings.step_functions_arn:
        try:
            sfn_client.start_execution(
                stateMachineArn=settings.step_functions_arn,
                name=f"job-{job_id}",
                input=json.dumps({
                    "job_id": job_id,
                    "mode": job_create.mode,
                    "blog_url": job_create.blog_url,
                    "audio_s3_key": job_create.audio_s3_key,
                    "source_text": job_create.source_text,
                    "style": job_create.style.model_dump(),
                    "auto_upload_youtube": job_create.auto_upload_youtube,
                }),
            )
        except ClientError as e:
            # Update job status to FAILED
            jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #s = :s, #e = :e, updated_at = :u",
                ExpressionAttributeNames={"#s": "status", "#e": "error"},
                ExpressionAttributeValues={
                    ":s": "FAILED",
                    ":e": f"Failed to start pipeline: {str(e)}",
                    ":u": now,
                },
            )
            raise HTTPException(status_code=500, detail=f"Failed to start pipeline: {str(e)}")

    return job


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str):
    """Get job status and outputs."""
    if settings.local_dev:
        job = _local_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    from botocore.exceptions import ClientError

    try:
        response = jobs_table.get_item(Key={"job_id": job_id})
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Job not found")

    return _dict_to_job(item)


@router.get("")
async def list_jobs(user_id: str = "anonymous", limit: int = 20):
    """List jobs for a user."""
    if settings.local_dev:
        jobs = [j for j in _local_jobs.values() if j.user_id == user_id]
        return jobs[:limit]

    from botocore.exceptions import ClientError

    try:
        # For now just scan; will use GSI with Cognito userId later
        response = jobs_table.scan(
            FilterExpression="user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
            Limit=limit,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

    items = response.get("Items", [])
    return [_dict_to_job(item) for item in items]


def _find_execution_arn(job_id: str) -> str | None:
    """Find the Step Functions execution ARN for a job."""
    if not settings.step_functions_arn:
        return None
    try:
        response = sfn_client.list_executions(
            stateMachineArn=settings.step_functions_arn,
            statusFilter="RUNNING",
            maxResults=100,
        )
        for execution in response.get("executions", []):
            if execution["name"] == f"job-{job_id}":
                return execution["executionArn"]
    except Exception:
        pass
    return None


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job by stopping its Step Functions execution."""
    if settings.local_dev:
        job = _local_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.status = "FAILED"
        job.error = "Cancelled by user"
        return {"status": "cancelled"}

    from botocore.exceptions import ClientError

    # Update DynamoDB status
    now = datetime.utcnow().isoformat()
    try:
        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :s, #e = :e, updated_at = :u",
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={
                ":s": "CANCELLED",
                ":e": "Cancelled by user",
                ":u": now,
            },
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Stop the Step Functions execution
    execution_arn = _find_execution_arn(job_id)
    if execution_arn:
        try:
            sfn_client.stop_execution(
                executionArn=execution_arn,
                cause="Cancelled by user",
            )
        except ClientError:
            pass  # Execution may have already finished

    return {"status": "cancelled"}


@router.post("/{job_id}/pause")
async def pause_job(job_id: str):
    """Pause a running job (marks as PAUSED; pipeline checks this flag)."""
    if settings.local_dev:
        job = _local_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.status = "PAUSED"
        return {"status": "paused"}

    from botocore.exceptions import ClientError

    now = datetime.utcnow().isoformat()
    try:
        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :s, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "PAUSED", ":u": now},
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Stop the execution so it doesn't continue to the next step
    execution_arn = _find_execution_arn(job_id)
    if execution_arn:
        try:
            sfn_client.stop_execution(
                executionArn=execution_arn,
                cause="Paused by user",
            )
        except ClientError:
            pass

    return {"status": "paused"}
