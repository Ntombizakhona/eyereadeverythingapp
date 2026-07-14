import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AWS
    aws_region: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    # S3
    s3_uploads_bucket: str = os.getenv("S3_UPLOADS_BUCKET", "eyereadeverything-uploads")
    s3_renders_bucket: str = os.getenv("S3_RENDERS_BUCKET", "eyereadeverything-renders")

    # DynamoDB
    dynamodb_jobs_table: str = os.getenv("DYNAMODB_JOBS_TABLE", "eyereadeverything-jobs")
    dynamodb_voice_profiles_table: str = os.getenv(
        "DYNAMODB_VOICE_PROFILES_TABLE", "eyereadeverything-voice-profiles"
    )

    # Step Functions
    step_functions_arn: str = os.getenv("STEP_FUNCTIONS_ARN", "")

    # Nova
    nova_model_id: str = "amazon.nova-lite-v1:0"
    nova_sonic_model_id: str = "amazon.nova-sonic-v1:0"

    # Polly
    polly_voice_id: str = os.getenv("POLLY_VOICE_ID", "Joanna")

    # Nova Act
    nova_act_api_key: str = os.getenv("NOVA_ACT_API_KEY", "")

    # OpenSearch
    opensearch_endpoint: str = os.getenv("OPENSEARCH_ENDPOINT", "")

    # App
    output_dir: str = os.getenv("OUTPUT_DIR", "./outputs")
    api_url: str = os.getenv("API_URL", "http://localhost:8000")
    local_dev: bool = os.getenv("LOCAL_DEV", "true").lower() in ("true", "1", "yes")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
