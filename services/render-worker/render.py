"""
Video Render Worker — ECS Fargate
Uses Amazon Nova Reel to generate AI video clips for each scene,
then composites with FFmpeg: text overlays + narration audio.
Falls back to solid-color backgrounds if Nova Reel fails.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import boto3
from datetime import datetime

# AWS Clients
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
sfn = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = dynamodb.Table(os.environ.get("DYNAMODB_JOBS_TABLE", "eyereadeverything-jobs"))

RENDERS_BUCKET = os.environ.get("S3_RENDERS_BUCKET", "eyereadeverything-renders")
NOVA_REEL_MODEL = "amazon.nova-reel-v1:1"

# Visual style descriptors injected into every Nova Reel scene prompt.
# Controlled by the job's style.visual_style setting (chosen in the UI).
VISUAL_STYLES = {
    "cinematic": "Professional cinematic live-action footage, 4K, photorealistic, shallow depth of field, professional lighting",
    "cartoon": "2D flat-design cartoon animation, bold clean outlines, vibrant flat colors, smooth motion, playful Saturday-morning cartoon aesthetic",
    "anime": "Anime style animation, cel-shaded, expressive, dynamic, vibrant Japanese animation aesthetic, detailed backgrounds",
    "claymation": "Claymation stop-motion animation, soft plasticine clay textures, handcrafted tactile look, warm studio lighting",
    "watercolor": "Hand-painted watercolor animation, soft flowing brush strokes, gentle color bleeds, artistic illustrated storybook look",
}
DEFAULT_VISUAL_STYLE = "cinematic"


def update_status(job_id: str, status: str):
    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, updated_at = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":u": datetime.utcnow().isoformat()},
    )


def download_s3(s3_key: str, local_path: str):
    s3.download_file(RENDERS_BUCKET, s3_key, local_path)


def upload_s3(local_path: str, s3_key: str, content_type: str = "application/octet-stream"):
    s3.upload_file(local_path, RENDERS_BUCKET, s3_key, ExtraArgs={"ContentType": content_type})


def build_scene_prompt(scene: dict, visual_style: str = DEFAULT_VISUAL_STYLE) -> str:
    """Build a visual prompt for Nova Reel from scene data."""
    keywords = scene.get("broll_keywords", [])
    overlays = scene.get("text_overlays", [])
    scene_type = scene.get("type", "main")

    # Combine keywords into a visual description
    keyword_str = ", ".join(keywords) if keywords else "abstract background"
    overlay_texts = [o.get("text", "") for o in overlays]
    context = ". ".join(overlay_texts) if overlay_texts else ""

    # Base aesthetic from the user-selected visual style
    base_style = VISUAL_STYLES.get(visual_style, VISUAL_STYLES[DEFAULT_VISUAL_STYLE])

    # Scene-type modifiers (camera/energy) layered on top of the base style
    if scene_type == "hook":
        motion = "Dramatic opening shot, dynamic camera movement"
    elif scene_type == "cta":
        motion = "Clean modern composition, subtle animation"
    else:
        motion = "Smooth camera pan, engaging composition"

    prompt = f"{base_style}. {motion}. Visual theme: {keyword_str}. Context: {context}. High quality, consistent style."
    return prompt[:512]  # Nova Reel prompt limit


def generate_nova_reel_clips(job_id: str, scenes: list, work_dir: str, visual_style: str = DEFAULT_VISUAL_STYLE) -> list:
    """
    Generate video clips for each scene using Nova Reel multi-shot.
    Returns list of local file paths for each scene clip.
    """
    # Build shots for multi-shot manual mode
    shots = []
    for scene in scenes:
        prompt = build_scene_prompt(scene, visual_style)
        shots.append({"text": prompt})
        print(f"  Scene {scene.get('scene_number', '?')}: {prompt[:80]}...")

    # Cap at 20 shots (2 min max = 20 x 6sec)
    shots = shots[:20]
    total_duration = len(shots) * 6

    print(f"Starting Nova Reel generation: {len(shots)} shots, {total_duration}s total")

    output_s3_uri = f"s3://{RENDERS_BUCKET}/{job_id}/nova-reel"

    model_input = {
        "taskType": "MULTI_SHOT_MANUAL",
        "multiShotManualParams": {
            "shots": shots,
        },
        "videoGenerationConfig": {
            "durationSeconds": total_duration,
            "fps": 24,
            "dimension": "1280x720",
            "seed": 42,
        },
    }

    # Start async video generation
    invocation = bedrock.start_async_invoke(
        modelId=NOVA_REEL_MODEL,
        modelInput=model_input,
        outputDataConfig={
            "s3OutputDataConfig": {
                "s3Uri": output_s3_uri,
            }
        },
    )

    invocation_arn = invocation["invocationArn"]
    print(f"Nova Reel job started: {invocation_arn}")

    # Poll for completion (Nova Reel takes ~90s per 6s clip, ~14-17min for 2min)
    max_wait = 1200  # 20 minutes max
    poll_interval = 15
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        status_resp = bedrock.get_async_invoke(invocationArn=invocation_arn)
        status = status_resp["status"]

        if status == "Completed":
            print(f"Nova Reel generation completed in {elapsed}s")
            break
        elif status == "Failed":
            failure = status_resp.get("failureMessage", "Unknown error")
            raise Exception(f"Nova Reel generation failed: {failure}")
        else:
            print(f"  Nova Reel status: {status} ({elapsed}s elapsed)")

    if elapsed >= max_wait:
        raise Exception("Nova Reel generation timed out")

    # Download the generated video from S3
    # Nova Reel outputs to: {output_s3_uri}/{invocation_id}/output.mp4
    invocation_id = invocation_arn.split("/")[-1]
    reel_s3_key = f"{job_id}/nova-reel/{invocation_id}/output.mp4"

    reel_video_path = os.path.join(work_dir, "nova_reel_full.mp4")
    try:
        s3.download_file(RENDERS_BUCKET, reel_s3_key, reel_video_path)
    except Exception:
        # Try alternate path structure
        # List objects to find the video
        resp = s3.list_objects_v2(
            Bucket=RENDERS_BUCKET,
            Prefix=f"{job_id}/nova-reel/{invocation_id}/",
        )
        for obj in resp.get("Contents", []):
            if obj["Key"].endswith(".mp4"):
                s3.download_file(RENDERS_BUCKET, obj["Key"], reel_video_path)
                break

    if not os.path.exists(reel_video_path):
        raise Exception("Could not find Nova Reel output video in S3")

    # Split the full video into per-scene clips (6 seconds each)
    scene_clips = []
    for i, scene in enumerate(scenes[:len(shots)]):
        clip_path = os.path.join(work_dir, f"reel_scene_{i}.mp4")
        start_time = i * 6
        cmd = [
            "ffmpeg", "-y",
            "-i", reel_video_path,
            "-ss", str(start_time),
            "-t", "6",
            "-c:v", "libx264", "-c:a", "copy",
            clip_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        scene_clips.append(clip_path)

    return scene_clips


def render_fallback_background(scene: dict, width: int, height: int, duration: float, output_path: str):
    """Fallback: render a solid/gradient background when Nova Reel is unavailable."""
    bg = scene.get("background", {})
    bg_type = bg.get("type", "solid")
    color = bg.get("color", "#0a0a0a")

    if bg_type == "gradient":
        colors = bg.get("colors", ["#0a0a0a", "#1a1a2e"])
        color = colors[0]

    hex_color = color.lstrip("#")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x{hex_color}:s={width}x{height}:d={duration}:r=24",
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def scale_clip_to_scene(clip_path: str, scene: dict, width: int, height: int, output_path: str):
    """Scale a Nova Reel clip (1280x720) to the target resolution and duration."""
    duration = scene["end_sec"] - scene["start_sec"]

    # Scale up to target resolution and adjust duration
    cmd = [
        "ffmpeg", "-y",
        "-i", clip_path,
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",  # Remove audio from clip
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # If the clip is shorter than the scene, loop it
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", output_path],
        capture_output=True, text=True,
    )
    clip_duration = float(probe.stdout.strip()) if probe.stdout.strip() else 6.0

    if clip_duration < duration - 0.5:
        looped_path = output_path.replace(".mp4", "_looped.mp4")
        loops = int(duration / clip_duration) + 1
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", str(loops),
            "-i", output_path,
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            looped_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        os.replace(looped_path, output_path)


def add_text_overlays(input_path: str, scene: dict, output_path: str):
    """Add text overlays to a scene video using FFmpeg drawtext filter."""
    overlays = scene.get("text_overlays", [])
    if not overlays:
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path],
                       check=True, capture_output=True)
        return

    scene_start = scene["start_sec"]
    filter_parts = []

    for overlay in overlays:
        text = overlay.get("text", "").replace("'", "\\'").replace(":", "\\:")
        position = overlay.get("position", "center")
        font_size = overlay.get("font_size", 48)

        if position == "center":
            x, y = "(w-text_w)/2", "(h-text_h)/2"
        elif position == "top":
            x, y = "(w-text_w)/2", "h*0.12"
        elif position == "bottom":
            x, y = "(w-text_w)/2", "h*0.82"
        elif position == "left":
            x, y = "w*0.05", "(h-text_h)/2"
        elif position == "right":
            x, y = "w*0.55", "(h-text_h)/2"
        else:
            x, y = "(w-text_w)/2", "(h-text_h)/2"

        enable_start = overlay.get("start_sec", scene_start) - scene_start
        enable_end = overlay.get("end_sec", scene["end_sec"]) - scene_start

        filter_parts.append(
            f"drawtext=text='{text}':"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"x={x}:y={y}:"
            f"enable='between(t,{enable_start},{enable_end})':"
            f"shadowcolor=black@0.7:shadowx=3:shadowy=3:"
            f"borderw=2:bordercolor=black@0.4"
        )

    vf = ",".join(filter_parts)
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", vf,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path]
    subprocess.run(cmd, check=True, capture_output=True)


def render_video(job_id: str, work_dir: str, render_plan: dict, narration_path: str, captions_path: str) -> str:
    """Full video render pipeline with Nova Reel AI clips."""
    width = 1920
    height = 1080
    scenes = render_plan.get("scenes", [])
    visual_style = render_plan.get("visual_style", DEFAULT_VISUAL_STYLE)

    # Try Nova Reel for AI-generated scene clips
    reel_clips = None
    try:
        update_status(job_id, "GENERATING_VIDEO_CLIPS")
        reel_clips = generate_nova_reel_clips(job_id, scenes, work_dir, visual_style)
        print(f"Nova Reel generated {len(reel_clips)} clips (style: {visual_style})")
    except Exception as e:
        print(f"Nova Reel failed, falling back to static backgrounds: {e}")
        reel_clips = None

    update_status(job_id, "COMPOSITING")

    scene_files = []
    for i, scene in enumerate(scenes):
        bg_path = os.path.join(work_dir, f"scene_{i}_bg.mp4")
        overlay_path = os.path.join(work_dir, f"scene_{i}_final.mp4")
        duration = scene["end_sec"] - scene["start_sec"]

        if reel_clips and i < len(reel_clips) and os.path.exists(reel_clips[i]):
            # Use Nova Reel clip as background
            scale_clip_to_scene(reel_clips[i], scene, width, height, bg_path)
        else:
            # Fallback to solid color
            render_fallback_background(scene, width, height, duration, bg_path)

        # Add text overlays on top
        add_text_overlays(bg_path, scene, overlay_path)
        scene_files.append(overlay_path)

    # Concatenate all scenes
    concat_list = os.path.join(work_dir, "concat.txt")
    with open(concat_list, "w") as f:
        for sf in scene_files:
            f.write(f"file '{sf}'\n")

    concat_path = os.path.join(work_dir, "concat.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", concat_list, "-c", "copy", concat_path]
    subprocess.run(cmd, check=True, capture_output=True)

    # Add narration audio
    output_path = os.path.join(work_dir, "video.mp4")
    if os.path.exists(narration_path):
        cmd = [
            "ffmpeg", "-y",
            "-i", concat_path,
            "-i", narration_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]
    else:
        cmd = ["ffmpeg", "-y", "-i", concat_path, "-c", "copy", output_path]

    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def generate_thumbnail(video_path: str, work_dir: str) -> str:
    """Extract a frame from the video as thumbnail."""
    thumb_path = os.path.join(work_dir, "thumbnail.png")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ss", "00:00:02",
        "-vframes", "1",
        "-vf", "scale=1280:720",
        thumb_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return thumb_path


def main():
    """Entry point for the ECS Fargate task."""
    job_id = os.environ.get("JOB_ID")
    task_token = os.environ.get("TASK_TOKEN")

    if not job_id:
        print("ERROR: JOB_ID environment variable required")
        sys.exit(1)

    update_status(job_id, "RENDERING")

    try:
        with tempfile.TemporaryDirectory() as work_dir:
            render_plan_path = os.path.join(work_dir, "render_plan.json")
            narration_path = os.path.join(work_dir, "narration.mp3")
            captions_path = os.path.join(work_dir, "captions.srt")

            download_s3(f"{job_id}/render_plan.json", render_plan_path)

            try:
                download_s3(f"{job_id}/narration.mp3", narration_path)
            except Exception:
                print("Warning: No narration audio found")

            try:
                download_s3(f"{job_id}/captions.srt", captions_path)
            except Exception:
                print("Warning: No captions found")

            with open(render_plan_path) as f:
                render_plan = json.load(f)

            video_path = render_video(job_id, work_dir, render_plan, narration_path, captions_path)

            # Only generate FFmpeg thumbnail if Nova Canvas didn't already create one
            try:
                s3.head_object(Bucket=RENDERS_BUCKET, Key=f"{job_id}/thumbnail.png")
                print("Thumbnail already exists (Nova Canvas), skipping FFmpeg extraction")
            except Exception:
                thumb_path = generate_thumbnail(video_path, work_dir)
                upload_s3(thumb_path, f"{job_id}/thumbnail.png", "image/png")

            upload_s3(video_path, f"{job_id}/video.mp4", "video/mp4")
            print(f"Video rendered and uploaded: {job_id}/video.mp4")

            if task_token:
                sfn.send_task_success(
                    taskToken=task_token,
                    output=json.dumps({
                        "job_id": job_id,
                        "video_s3_key": f"{job_id}/video.mp4",
                        "thumbnail_s3_key": f"{job_id}/thumbnail.png",
                    }),
                )

    except Exception as e:
        error_msg = f"Render failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        update_status(job_id, "FAILED")

        if task_token:
            sfn.send_task_failure(
                taskToken=task_token,
                error="RenderError",
                cause=error_msg,
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
