"""
Context Retrieval Lambda Handler
Queries Nova Multimodal Embeddings + OpenSearch Serverless
for channel consistency exemplars.
"""
import json
import os
import boto3
from datetime import datetime

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = dynamodb.Table(os.environ.get("DYNAMODB_JOBS_TABLE", "eyereadeverything-jobs"))
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")


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


def get_embedding(text: str) -> list:
    """Generate text embedding using Nova Multimodal Embeddings."""
    body = json.dumps({
        "inputText": text[:8000],
        "embeddingConfig": {
            "outputEmbeddingLength": 1024
        }
    })

    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())
    return result["embedding"]


def search_opensearch(embedding: list, top_k: int = 5) -> list:
    """Search OpenSearch Serverless for similar content."""
    if not OPENSEARCH_ENDPOINT:
        return []

    # OpenSearch k-NN query
    from opensearchpy import OpenSearch, RequestsHttpConnection
    from requests_aws4auth import AWS4Auth
    import boto3 as b3

    credentials = b3.Session().get_credentials()
    region = os.environ.get("AWS_REGION", "us-east-1")
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        "aoss",
        session_token=credentials.token,
    )

    client = OpenSearch(
        hosts=[{"host": OPENSEARCH_ENDPOINT, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )

    query = {
        "size": top_k,
        "query": {
            "knn": {
                "embedding": {
                    "vector": embedding,
                    "k": top_k,
                }
            }
        },
    }

    response = client.search(index="channel-brain", body=query)
    hits = response.get("hits", {}).get("hits", [])
    return [hit["_source"].get("content", "") for hit in hits]


def handler(event, context):
    """
    Input: event with source_text
    Output: event + { context_exemplars }
    """
    job_id = event["job_id"]

    try:
        update_status(job_id, "RETRIEVING_CONTEXT")

        source_text = event.get("source_text", "")

        # Generate embedding for the source text summary
        try:
            embedding = get_embedding(source_text[:2000])
            context_exemplars = search_opensearch(embedding)
        except Exception as e:
            # Context retrieval is optional; don't fail the pipeline
            print(f"Context retrieval failed (non-fatal): {e}")
            context_exemplars = []

        event["context_exemplars"] = context_exemplars
        return event
    except Exception as e:
        update_status(job_id, "FAILED", str(e))
        raise
