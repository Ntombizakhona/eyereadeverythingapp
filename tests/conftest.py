"""
Shared fixtures for all tests.
Sets up mocked AWS services via moto.
"""
import os
import json
import pytest
import boto3
from moto import mock_aws


# Force test environment
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["DYNAMODB_JOBS_TABLE"] = "eyeread-jobs"
os.environ["DYNAMODB_VOICE_PROFILES_TABLE"] = "eyeread-voice-profiles"
os.environ["S3_UPLOADS_BUCKET"] = "eyeread-uploads-test"
os.environ["S3_RENDERS_BUCKET"] = "eyeread-renders-test"
os.environ["STEP_FUNCTIONS_ARN"] = ""
os.environ["OPENSEARCH_ENDPOINT"] = ""
os.environ["NOVA_ACT_API_KEY"] = ""


@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials for moto."""
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"


@pytest.fixture
def mock_aws_services(aws_credentials):
    """Set up all mocked AWS services."""
    with mock_aws():
        # Create DynamoDB tables
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        dynamodb.create_table(
            TableName="eyeread-jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "userId-createdAt-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )

        dynamodb.create_table(
            TableName="eyeread-voice-profiles",
            KeySchema=[{"AttributeName": "voice_profile_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "voice_profile_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "userId-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create S3 buckets
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="eyeread-uploads-test")
        s3.create_bucket(Bucket="eyeread-renders-test")

        yield {
            "dynamodb": dynamodb,
            "s3": s3,
            "jobs_table": dynamodb.Table("eyeread-jobs"),
            "profiles_table": dynamodb.Table("eyeread-voice-profiles"),
        }


@pytest.fixture
def sample_blog_event():
    """Sample event for a BLOG mode job."""
    return {
        "job_id": "test-job-001",
        "mode": "BLOG",
        "blog_url": "https://example.com",
        "style": {
            "duration": "medium",
            "tone": "professional",
            "audience": "developers",
            "voice": "polly_default",
        },
        "auto_upload_youtube": False,
    }


@pytest.fixture
def sample_talk_event():
    """Sample event for a TALK mode job."""
    return {
        "job_id": "test-job-002",
        "mode": "TALK",
        "audio_s3_key": "uploads/test-audio.webm",
        "style": {
            "duration": "short",
            "tone": "casual",
            "audience": "general",
            "voice": "polly_default",
        },
        "auto_upload_youtube": False,
    }


@pytest.fixture
def sample_validated_event(sample_blog_event):
    """Event after validation stage."""
    event = sample_blog_event.copy()
    event["target_duration_sec"] = 180
    return event


@pytest.fixture
def sample_ingested_event(sample_validated_event):
    """Event after ingestion stage."""
    event = sample_validated_event.copy()
    event["source_text"] = "# Test Blog Post\n\nThis is a test blog post about Python programming. It covers best practices for writing clean code."
    event["source_text_s3_key"] = "test-job-001/source_text.md"
    return event


@pytest.fixture
def sample_script():
    """Sample generated script with timestamps."""
    return """[00:00] Did you know that Python is the most popular programming language? [pause] Today we're diving into why.

[00:15] Python's simplicity and readability make it perfect for beginners and experts alike. [emphasis] Let's explore the top three reasons.

[00:30] First, Python has an incredibly rich ecosystem of libraries. From data science to web development, there's a package for everything.

[00:45] Second, the community is massive and welcoming. Stack Overflow, Reddit, and countless Discord servers are ready to help.

[01:00] And third, Python jobs are everywhere. [pause] Companies from startups to Fortune 500s are hiring Python developers.

[01:15] If you enjoyed this video, hit subscribe and let me know in the comments which Python library is your favorite."""
