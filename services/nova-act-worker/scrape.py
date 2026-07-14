"""
Nova Act Blog Scraper — ECS Fargate
Uses Amazon Nova Act to open a blog URL in a real browser,
extract the article content, and save it to S3.
This bypasses 403/bot-detection issues since Nova Act runs a real Chrome browser.
"""
import json
import os
import sys
import boto3
from datetime import datetime

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
sfn = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
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


def scrape_blog_with_nova_act(url: str) -> str:
    """Use Nova Act to navigate to a blog URL and extract the article content."""
    from nova_act import NovaAct

    print(f"Starting Nova Act blog scrape: {url}")

    with NovaAct(starting_page=url, headless=True) as nova:
        # Wait for page to fully load
        result = nova.act(
            "Wait for the page to fully load. If there are any cookie consent "
            "or popup dialogs, dismiss them by clicking Accept or Close."
        )

        # Extract the article content
        result = nova.act(
            "Extract the main article content from this page. "
            "Return the article title and full body text. "
            "Ignore navigation menus, sidebars, ads, and footers. "
            "Format the output as clean text with the title first, "
            "then the article body."
        )

        # Get the page content via Playwright
        page = nova.page
        content = page.evaluate("""() => {
            // Try to find the article content
            const article = document.querySelector('article') 
                || document.querySelector('[role="main"]')
                || document.querySelector('.post-content')
                || document.querySelector('.article-content')
                || document.querySelector('main');
            
            if (article) {
                return article.innerText;
            }
            
            // Fallback: get body text minus nav/footer
            const body = document.body.cloneNode(true);
            body.querySelectorAll('nav, footer, header, aside, .sidebar, .ad, .advertisement').forEach(el => el.remove());
            return body.innerText;
        }""")

        # Also get the title
        title = page.evaluate("() => document.title || ''")

    return f"# {title}\n\n{content}"


def main():
    """Entry point for the Nova Act scraper ECS Fargate task."""
    job_id = os.environ.get("JOB_ID")
    task_token = os.environ.get("TASK_TOKEN")
    blog_url = os.environ.get("BLOG_URL")

    if not job_id or not blog_url:
        print("ERROR: JOB_ID and BLOG_URL environment variables required")
        sys.exit(1)

    update_status(job_id, "SCRAPING_WITH_NOVA_ACT")

    try:
        source_text = scrape_blog_with_nova_act(blog_url)

        # Save to S3
        s3_key = f"{job_id}/source_text.md"
        s3.put_object(
            Bucket=RENDERS_BUCKET,
            Key=s3_key,
            Body=source_text.encode("utf-8"),
            ContentType="text/markdown",
        )

        print(f"Blog content scraped and saved: {s3_key}")

        if task_token:
            sfn.send_task_success(
                taskToken=task_token,
                output=json.dumps({
                    "job_id": job_id,
                    "source_text_s3_key": s3_key,
                    "source_text": source_text[:15000],
                }),
            )

    except Exception as e:
        error_msg = f"Nova Act scrape failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        update_status(job_id, "FAILED", error_msg)

        if task_token:
            sfn.send_task_failure(
                taskToken=task_token,
                error="ScrapeError",
                cause=error_msg,
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
