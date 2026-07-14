"""
TTS (Text-to-Speech) Lambda Handler
Synthesizes narration audio using Amazon Polly, with BYO style-match support.
Nova Sonic support is planned as a stretch feature.
"""
import json
import os
import re
import boto3
from datetime import datetime

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
polly = boto3.client("polly", region_name=os.environ.get("AWS_REGION", "us-east-1"))
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


def clean_script_for_tts(script: str) -> str:
    """Remove timestamp markers and delivery cues, keep only narration text."""
    # Remove [HH:MM:SS] or [MM:SS] timestamps
    text = re.sub(r'\[\d{1,2}:\d{2}(?::\d{2})?\]', '', script)
    # Remove delivery cues like [pause], [emphasis], [slower]
    text = re.sub(r'\[(pause|emphasis|slower|faster|beat)\]', '', text, flags=re.IGNORECASE)
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def script_to_ssml(script: str, rate: str = "medium", volume: str = "medium") -> str:
    """Convert script to SSML with prosody controls for BYO style-match."""
    clean = clean_script_for_tts(script)

    # Split into paragraphs for natural breaks
    paragraphs = [p.strip() for p in clean.split('\n\n') if p.strip()]

    ssml_parts = ['<speak>']
    ssml_parts.append(f'<prosody rate="{rate}" volume="{volume}">')

    for para in paragraphs:
        ssml_parts.append(f'<p>{para}</p>')
        ssml_parts.append('<break time="500ms"/>')

    ssml_parts.append('</prosody>')
    ssml_parts.append('</speak>')

    return '\n'.join(ssml_parts)


def synthesize_polly(text: str, voice_id: str = "Joanna", use_ssml: bool = False) -> bytes:
    """Synthesize speech using Amazon Polly."""
    params = {
        "OutputFormat": "mp3",
        "VoiceId": voice_id,
        "Engine": "neural",
    }

    if use_ssml:
        params["TextType"] = "ssml"
        params["Text"] = text
    else:
        params["TextType"] = "text"
        params["Text"] = text

    # For texts > 3000 chars, use start_speech_synthesis_task
    if len(text) > 3000:
        return synthesize_polly_long(text, voice_id, use_ssml)

    response = polly.synthesize_speech(**params)
    return response["AudioStream"].read()


def synthesize_polly_long(text: str, voice_id: str, use_ssml: bool) -> bytes:
    """Handle long text with Polly's async synthesis task."""
    import time

    output_key = f"tts-temp/{os.urandom(8).hex()}.mp3"

    params = {
        "OutputFormat": "mp3",
        "OutputS3BucketName": RENDERS_BUCKET,
        "OutputS3KeyPrefix": output_key.replace(".mp3", ""),
        "VoiceId": voice_id,
        "Engine": "neural",
    }

    if use_ssml:
        params["TextType"] = "ssml"
        params["Text"] = text
    else:
        params["TextType"] = "text"
        params["Text"] = text

    response = polly.start_speech_synthesis_task(**params)
    task_id = response["SynthesisTask"]["TaskId"]

    # Wait for completion
    while True:
        result = polly.get_speech_synthesis_task(TaskId=task_id)
        status = result["SynthesisTask"]["TaskStatus"]
        if status == "completed":
            # Download from S3
            s3_uri = result["SynthesisTask"]["OutputUri"]
            # Parse S3 key from URI
            s3_key = s3_uri.split(f"{RENDERS_BUCKET}/")[-1]
            obj = s3_client.get_object(Bucket=RENDERS_BUCKET, Key=s3_key)
            return obj["Body"].read()
        elif status == "failed":
            reason = result["SynthesisTask"].get("TaskStatusReason", "Unknown")
            raise Exception(f"Polly synthesis failed: {reason}")
        time.sleep(3)


def handler(event, context):
    """
    Input: event with { job_id, script_text, style }
    Output: event + { narration_s3_key }
    """
    job_id = event["job_id"]

    try:
        update_status(job_id, "NARRATING")

        script = event.get("script_text", "")
        style = event.get("style", {})
        voice_option = style.get("voice", "polly_default")
        voice_id = os.environ.get("POLLY_VOICE_ID", "Joanna")

        if voice_option == "byo":
            tone_rates = {
                "professional": "medium",
                "casual": "medium",
                "energetic": "fast",
            }
            rate = tone_rates.get(style.get("tone", "professional"), "medium")
            ssml = script_to_ssml(script, rate=rate)
            audio_data = synthesize_polly(ssml, voice_id=voice_id, use_ssml=True)
        elif voice_option == "nova_sonic":
            clean = clean_script_for_tts(script)
            audio_data = synthesize_polly(clean, voice_id=voice_id)
        else:
            clean = clean_script_for_tts(script)
            audio_data = synthesize_polly(clean, voice_id=voice_id)

        # Upload narration to S3
        s3_key = f"{job_id}/narration.mp3"
        s3_client.put_object(
            Bucket=RENDERS_BUCKET,
            Key=s3_key,
            Body=audio_data,
            ContentType="audio/mpeg",
        )

        event["narration_s3_key"] = s3_key
        return event
    except Exception as e:
        update_status(job_id, "FAILED", str(e))
        raise
