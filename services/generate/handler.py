"""
Generation Service Lambda Handler
Uses Amazon Nova Pro via Bedrock Converse API for all content generation:
Plan, Script, Metadata, Captions, Render Plan.
Uses Amazon Nova Canvas for AI-generated thumbnails.
"""
import json
import os
import base64
from pathlib import Path
import boto3
from datetime import datetime
from botocore.config import Config

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock_canvas = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"), config=Config(read_timeout=300))
s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = dynamodb.Table(os.environ.get("DYNAMODB_JOBS_TABLE", "eyereadeverything-jobs"))
RENDERS_BUCKET = os.environ.get("S3_RENDERS_BUCKET", "eyereadeverything-renders")
MODEL_ID = os.environ.get("NOVA_MODEL_ID", "amazon.nova-pro-v1:0")
CANVAS_MODEL_ID = "amazon.nova-canvas-v1:0"

# Load prompt templates
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


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


def call_nova(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """Call Nova 2 Lite via Bedrock Converse API."""
    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [{"text": user_prompt}],
            }
        ],
        system=[{"text": system_prompt}],
        inferenceConfig={
            "maxTokens": 8192,
            "temperature": temperature,
        },
    )
    return response["output"]["message"]["content"][0]["text"]


def parse_json_response(text: str) -> dict:
    """Extract JSON from Nova's response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(lines)
    return json.loads(text)


def save_to_s3(job_id: str, filename: str, content: str, content_type: str = "application/json"):
    """Save content to S3 under the job's directory."""
    s3_key = f"{job_id}/{filename}"
    s3_client.put_object(
        Bucket=RENDERS_BUCKET,
        Key=s3_key,
        Body=content.encode("utf-8"),
        ContentType=content_type,
    )
    return s3_key


def generate_plan(event: dict) -> dict:
    """Stage 1: Generate video plan with scene beats."""
    system = load_prompt("system")
    template = load_prompt("plan")
    style = event.get("style", {})

    prompt = template.format(
        source_text=event.get("source_text", ""),
        context_exemplars="\n".join(event.get("context_exemplars", ["No prior context available."])),
        target_duration_sec=event.get("target_duration_sec", 180),
        tone=style.get("tone", "professional"),
        audience=style.get("audience", "general"),
    )

    result = call_nova(system, prompt, temperature=0.3)
    plan = parse_json_response(result)
    save_to_s3(event["job_id"], "plan.json", json.dumps(plan, indent=2))
    return plan


def generate_script(event: dict, plan: dict) -> str:
    """Stage 2: Generate full narration script with timestamps."""
    system = load_prompt("system")
    template = load_prompt("script")
    style = event.get("style", {})

    prompt = template.format(
        plan_json=json.dumps(plan, indent=2),
        context_exemplars="\n".join(event.get("context_exemplars", ["No prior context available."])),
        tone=style.get("tone", "professional"),
        audience=style.get("audience", "general"),
    )

    script = call_nova(system, prompt, temperature=0.5)
    save_to_s3(event["job_id"], "script.md", script, "text/markdown")
    return script


def generate_metadata(event: dict, plan: dict, script: str) -> dict:
    """Stage 3: Generate YouTube metadata."""
    template = load_prompt("metadata")
    style = event.get("style", {})

    prompt = template.format(
        script=script[:5000],
        plan_json=json.dumps(plan, indent=2),
        audience=style.get("audience", "general"),
    )

    system = "You are a YouTube SEO expert. Generate optimized metadata."
    result = call_nova(system, prompt, temperature=0.4)
    metadata = parse_json_response(result)
    save_to_s3(event["job_id"], "metadata.json", json.dumps(metadata, indent=2))
    return metadata


def generate_captions(event: dict, script: str) -> str:
    """Stage 4: Generate SRT captions."""
    template = load_prompt("captions")

    prompt = template.format(
        script=script,
        target_duration_sec=event.get("target_duration_sec", 180),
    )

    system = "You are a professional subtitle creator. Generate accurate SRT captions."
    srt = call_nova(system, prompt, temperature=0.2)

    # Clean up any markdown fences
    if srt.startswith("```"):
        lines = srt.split("\n")
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        srt = "\n".join(lines)

    save_to_s3(event["job_id"], "captions.srt", srt, "application/x-subrip")
    return srt


def generate_render_plan(event: dict, plan: dict, script: str) -> dict:
    """Stage 5: Generate visual render plan for FFmpeg."""
    template = load_prompt("render_plan")
    style = event.get("style", {})
    visual_style = style.get("visual_style", "cinematic")

    prompt = template.format(
        plan_json=json.dumps(plan, indent=2),
        script=script[:5000],
        target_duration_sec=event.get("target_duration_sec", 180),
    )

    system = "You are a video compositor. Generate precise render instructions."
    result = call_nova(system, prompt, temperature=0.2)
    render_plan = parse_json_response(result)
    # Carry the chosen visual style forward so the render worker can style Nova Reel clips
    render_plan["visual_style"] = visual_style
    save_to_s3(event["job_id"], "render_plan.json", json.dumps(render_plan, indent=2))
    return render_plan


def generate_thumbnail_with_nova_canvas(event: dict, plan: dict, metadata: dict) -> str:
    """Stage 6: Generate a YouTube thumbnail using Amazon Nova Canvas."""
    title = metadata.get("selected_title", plan.get("title", "Video"))
    topic = plan.get("topic_summary", title)
    style = event.get("style", {})
    visual_style = style.get("visual_style", "cinematic")

    # Style descriptors so the thumbnail matches the video's visual style
    style_descriptors = {
        "cinematic": "photorealistic, cinematic, professional photography",
        "cartoon": "2D flat-design cartoon illustration, bold outlines, vibrant flat colors",
        "anime": "anime illustration style, cel-shaded, vibrant Japanese animation art",
        "claymation": "claymation clay-model style, soft plasticine textures, handcrafted",
        "watercolor": "hand-painted watercolor illustration, soft brush strokes",
    }
    style_hint = style_descriptors.get(visual_style, style_descriptors["cinematic"])

    # Use Nova Pro to create an optimal thumbnail prompt
    thumb_prompt_response = call_nova(
        "You are a YouTube thumbnail design expert. Create a concise image generation prompt.",
        f"""Create a vivid, eye-catching image prompt for a YouTube video thumbnail.
The video is about: {topic}
Title: {title}

Requirements:
- The image should be visually striking and professional
- Use bold colors and clear visual elements
- Do NOT include any text in the image (text will be overlaid separately)
- Describe a single compelling scene or visual metaphor
- Keep the prompt under 100 words

Return ONLY the image generation prompt, nothing else.""",
        temperature=0.7,
    )

    # Append the visual style so the thumbnail matches the rendered video
    thumb_prompt = f"{thumb_prompt_response.strip()}. Art style: {style_hint}."[:512]

    try:
        body = json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": thumb_prompt,
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 720,
                "width": 1280,
                "cfgScale": 8.0,
            },
        })

        response = bedrock_canvas.invoke_model(
            body=body,
            modelId=CANVAS_MODEL_ID,
            accept="application/json",
            contentType="application/json",
        )
        response_body = json.loads(response["body"].read())
        base64_image = response_body["images"][0]
        image_bytes = base64.b64decode(base64_image)

        # Upload thumbnail to S3
        s3_key = f"{event['job_id']}/thumbnail.png"
        s3_client.put_object(
            Bucket=RENDERS_BUCKET,
            Key=s3_key,
            Body=image_bytes,
            ContentType="image/png",
        )
        return s3_key
    except Exception as e:
        print(f"Nova Canvas thumbnail generation failed (non-fatal): {e}")
        return None


def handler(event, context):
    """
    Runs all 5 generation stages sequentially.
    Input: event with { job_id, source_text, style, target_duration_sec, context_exemplars }
    Output: event + { plan, script, metadata, captions, render_plan } (S3 keys)
    """
    job_id = event["job_id"]

    try:
        # Stage 1: Plan
        update_status(job_id, "PLANNING")
        plan = generate_plan(event)

        # Stage 2: Script
        update_status(job_id, "SCRIPTING")
        script = generate_script(event, plan)

        # Stage 3: Metadata
        update_status(job_id, "GENERATING_METADATA")
        metadata = generate_metadata(event, plan, script)

        # Stage 4: Captions
        update_status(job_id, "GENERATING_CAPTIONS")
        captions = generate_captions(event, script)

        # Stage 5: Render Plan
        render_plan = generate_render_plan(event, plan, script)

        # Stage 6: AI Thumbnail via Nova Canvas
        update_status(job_id, "GENERATING_THUMBNAIL")
        thumbnail_key = generate_thumbnail_with_nova_canvas(event, plan, metadata)

        # Pass S3 keys forward
        event["plan_s3_key"] = f"{job_id}/plan.json"
        event["script_s3_key"] = f"{job_id}/script.md"
        event["metadata_s3_key"] = f"{job_id}/metadata.json"
        event["captions_s3_key"] = f"{job_id}/captions.srt"
        event["render_plan_s3_key"] = f"{job_id}/render_plan.json"
        if thumbnail_key:
            event["thumbnail_s3_key"] = thumbnail_key

        # Pass raw content for TTS
        event["script_text"] = script

        return event
    except Exception as e:
        update_status(job_id, "FAILED", str(e))
        raise
