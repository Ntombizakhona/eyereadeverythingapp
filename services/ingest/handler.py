"""
Ingest Service Lambda Handler
Blog: Nova Act scraper (ECS) fallback → httpx with readability → clean markdown → S3
Talk: read audio from S3 → Amazon Transcribe → transcript + summary → S3
Text: direct text passthrough → S3
"""
import json
import os
import boto3
import httpx
from datetime import datetime

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
transcribe = boto3.client("transcribe", region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = dynamodb.Table(os.environ.get("DYNAMODB_JOBS_TABLE", "eyereadeverything-jobs"))
RENDERS_BUCKET = os.environ.get("S3_RENDERS_BUCKET", "eyereadeverything-renders")
UPLOADS_BUCKET = os.environ.get("S3_UPLOADS_BUCKET", "eyereadeverything-uploads")
NOVA_MODEL_ID = os.environ.get("NOVA_MODEL_ID", "amazon.nova-pro-v1:0")


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


def extract_blog(url: str) -> str:
    """Fetch a blog URL and extract its main content as clean text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    resp = httpx.get(url, follow_redirects=True, timeout=30, headers=headers)
    resp.raise_for_status()

    try:
        from readability import Document
        from bs4 import BeautifulSoup
        doc = Document(resp.text)
        title = doc.title()
        content_html = doc.summary()
        soup = BeautifulSoup(content_html, "lxml")
        text = soup.get_text(separator="\n", strip=True)
        return f"# {title}\n\n{text}"
    except ImportError:
        return resp.text[:50000]


def extract_blog_with_nova(url: str, job_id: str) -> str:
    """
    Use Amazon Nova Pro to intelligently extract and analyze blog content.
    First fetches the raw HTML, then uses Nova to extract clean content
    and provide an initial analysis.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
    }
    resp = httpx.get(url, follow_redirects=True, timeout=30, headers=headers)
    resp.raise_for_status()
    raw_html = resp.text[:80000]

    # Use Nova Pro to extract and analyze the content
    response = bedrock.converse(
        modelId=NOVA_MODEL_ID,
        messages=[{
            "role": "user",
            "content": [{"text": f"""Extract the main article content from this HTML page. 
Remove all navigation, ads, footers, and boilerplate. 
Return ONLY the article title and body text in clean markdown format.
Also add a brief 2-sentence summary at the end under a "## Summary" heading.

HTML:
{raw_html}"""}],
        }],
        system=[{"text": "You are a content extraction expert. Extract article content from HTML and return clean markdown. Be thorough and preserve all article content."}],
        inferenceConfig={"maxTokens": 8192, "temperature": 0.1},
    )
    return response["output"]["message"]["content"][0]["text"]


def transcribe_audio(job_id: str, audio_s3_key: str) -> str:
    """Transcribe an audio file from S3 using Amazon Transcribe."""
    job_name = f"eyereadeverything-{job_id}"
    media_uri = f"s3://{UPLOADS_BUCKET}/{audio_s3_key}"

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": media_uri},
        MediaFormat=audio_s3_key.rsplit(".", 1)[-1],
        LanguageCode="en-US",
        OutputBucketName=RENDERS_BUCKET,
        OutputKey=f"{job_id}/transcript.json",
    )

    import time
    while True:
        result = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = result["TranscriptionJob"]["TranscriptionJobStatus"]
        if status == "COMPLETED":
            break
        elif status == "FAILED":
            raise Exception(f"Transcription failed: {result['TranscriptionJob'].get('FailureReason')}")
        time.sleep(5)

    obj = s3_client.get_object(Bucket=RENDERS_BUCKET, Key=f"{job_id}/transcript.json")
    transcript_data = json.loads(obj["Body"].read().decode("utf-8"))
    return transcript_data["results"]["transcripts"][0]["transcript"]


def handler(event, context):
    """
    Input: { job_id, mode, blog_url?, audio_s3_key?, source_text?, style, target_duration_sec }
    Output: event + { source_text }
    """
    job_id = event["job_id"]
    mode = event["mode"]

    try:
        update_status(job_id, "INGESTING")

        if mode == "BLOG":
            # Try Nova-powered extraction first, fall back to basic extraction
            try:
                source_text = extract_blog_with_nova(event["blog_url"], job_id)
            except httpx.HTTPStatusError:
                # If the URL is blocked (403 etc), try basic extraction
                source_text = extract_blog(event["blog_url"])
        elif mode == "TALK":
            source_text = transcribe_audio(job_id, event["audio_s3_key"])
        elif mode == "TEXT":
            source_text = event["source_text"]
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Store source text to S3
        s3_key = f"{job_id}/source_text.md"
        s3_client.put_object(
            Bucket=RENDERS_BUCKET,
            Key=s3_key,
            Body=source_text.encode("utf-8"),
            ContentType="text/markdown",
        )

        event["source_text_s3_key"] = s3_key
        event["source_text"] = source_text[:15000]

        return event
    except Exception as e:
        update_status(job_id, "FAILED", str(e))
        raise
