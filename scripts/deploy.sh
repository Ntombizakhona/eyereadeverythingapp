#!/usr/bin/env bash
set -euo pipefail

# --- Configuration ---
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=""  # resolved at runtime via aws sts get-caller-identity
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SKIP_IMAGES=false
SKIP_BOOTSTRAP=false

# --- Service Definitions ---
# Format: "name:dockerfile_path:ecr_repo_name"
# The Web is a static site (no image) and the API is built by CDK as a
# container asset during deploy. Only the two workers are built/pushed here.
SERVICES=(
  "render-worker:services/render-worker:eyereadeverything-render-worker"
  "nova-act-worker:services/nova-act-worker:eyereadeverything-nova-act-worker"
)

# --- Helper ---
fail() {
  echo "ERROR: $1" >&2
  exit 1
}

# --- Argument Parsing ---
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-images)
        SKIP_IMAGES=true
        shift
        ;;
      --skip-bootstrap)
        SKIP_BOOTSTRAP=true
        shift
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

# --- Prerequisite Validation ---
check_prerequisites() {
  echo "Checking prerequisites..."

  command -v aws &>/dev/null || fail "AWS CLI is not installed"
  command -v node &>/dev/null || fail "Node.js is not installed"
  command -v npm &>/dev/null || fail "npm is not installed"

  # Docker is required: CDK builds the API as a container asset during deploy,
  # and the worker images are built/pushed unless --skip-images is set.
  command -v docker &>/dev/null || fail "Docker is not installed"

  AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
    || fail "AWS credentials not configured"

  docker info &>/dev/null || fail "Docker daemon is not running"

  echo "All prerequisites met (AWS Account: ${AWS_ACCOUNT_ID}, Region: ${AWS_REGION})"
}

# --- ECR Authentication ---
ecr_login() {
  local ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  echo "Authenticating Docker with ECR (${ECR_REGISTRY})..."
  aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${ECR_REGISTRY}" \
    || fail "ECR authentication failed"
}

# --- Image Build & Push ---
build_and_push() {
  local service_tuple="$1"
  local ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

  IFS=: read -r name path repo <<< "${service_tuple}"

  echo "Building image for ${name} from ${path}..."
  docker build -t "${repo}:latest" -t "${repo}:${TIMESTAMP}" "${path}" \
    || fail "Failed to build image for ${name}"

  echo "Tagging image for ECR..."
  docker tag "${repo}:latest" "${ECR_REGISTRY}/${repo}:latest" \
    || fail "Failed to tag image for ${name}"
  docker tag "${repo}:${TIMESTAMP}" "${ECR_REGISTRY}/${repo}:${TIMESTAMP}" \
    || fail "Failed to tag image for ${name}"

  echo "Pushing ${repo}:latest to ECR..."
  docker push "${ECR_REGISTRY}/${repo}:latest" \
    || fail "Failed to push image to ${repo}"

  echo "Pushing ${repo}:${TIMESTAMP} to ECR..."
  docker push "${ECR_REGISTRY}/${repo}:${TIMESTAMP}" \
    || fail "Failed to push image to ${repo}"

  echo "Successfully pushed ${repo} (latest, ${TIMESTAMP})"
}

build_all_images() {
  echo "Building and pushing all service images..."
  for service in "${SERVICES[@]}"; do
    build_and_push "${service}"
  done
  echo "All images built and pushed successfully."
}

# --- Web Static Build ---
# The web app is a static export (apps/web/out) served from S3/CloudFront.
# CDK's BucketDeployment uploads apps/web/out, so it must exist before deploy.
build_web() {
  echo "Building static web frontend (apps/web)..."
  (cd apps/web && npm ci && npm run build) \
    || fail "Failed to build web frontend"
  [[ -d apps/web/out ]] || fail "Web build did not produce apps/web/out"
  echo "Web frontend built (apps/web/out)."
}

# --- CDK Operations ---
CDK_OUTPUTS_FILE=""

cdk_install() {
  echo "Installing CDK dependencies..."
  (cd infra && npm install) \
    || fail "Failed to install CDK dependencies"
  echo "CDK dependencies installed."
}

cdk_bootstrap() {
  echo "Bootstrapping CDK for aws://${AWS_ACCOUNT_ID}/${AWS_REGION}..."
  (cd infra && npx cdk bootstrap "aws://${AWS_ACCOUNT_ID}/${AWS_REGION}") \
    || fail "CDK bootstrap failed"
  echo "CDK bootstrap complete."
}

cdk_deploy() {
  CDK_OUTPUTS_FILE=$(mktemp /tmp/cdk-outputs-XXXXXX.json)
  echo "Deploying CDK stack..."
  (cd infra && npx cdk deploy --require-approval never --outputs-file "${CDK_OUTPUTS_FILE}") \
    || fail "CDK deployment failed"
  echo "CDK deployment complete."
}

print_summary() {
  echo ""
  echo "=========================================="
  echo "  Deployment Summary"
  echo "=========================================="

  if [[ -n "${CDK_OUTPUTS_FILE}" && -f "${CDK_OUTPUTS_FILE}" ]]; then
    local stack_key
    stack_key=$(python3 -c "import json,sys; data=json.load(open('${CDK_OUTPUTS_FILE}')); print(list(data.keys())[0])" 2>/dev/null || echo "")

    if [[ -n "${stack_key}" ]]; then
      local api_url web_url uploads_bucket renders_bucket state_machine_arn
      api_url=$(python3 -c "import json; data=json.load(open('${CDK_OUTPUTS_FILE}')); print(data['${stack_key}'].get('ApiUrl','N/A'))" 2>/dev/null || echo "N/A")
      web_url=$(python3 -c "import json; data=json.load(open('${CDK_OUTPUTS_FILE}')); print(data['${stack_key}'].get('WebUrl','N/A'))" 2>/dev/null || echo "N/A")
      uploads_bucket=$(python3 -c "import json; data=json.load(open('${CDK_OUTPUTS_FILE}')); print(data['${stack_key}'].get('UploadsBucketName','N/A'))" 2>/dev/null || echo "N/A")
      renders_bucket=$(python3 -c "import json; data=json.load(open('${CDK_OUTPUTS_FILE}')); print(data['${stack_key}'].get('RendersBucketName','N/A'))" 2>/dev/null || echo "N/A")
      state_machine_arn=$(python3 -c "import json; data=json.load(open('${CDK_OUTPUTS_FILE}')); print(data['${stack_key}'].get('StateMachineArn','N/A'))" 2>/dev/null || echo "N/A")

      echo "  API URL:              ${api_url}"
      echo "  Web URL:              ${web_url}"
      echo "  Uploads Bucket:       ${uploads_bucket}"
      echo "  Renders Bucket:       ${renders_bucket}"
      echo "  State Machine ARN:    ${state_machine_arn}"
    else
      echo "  (Could not parse CDK outputs)"
    fi

    rm -f "${CDK_OUTPUTS_FILE}"
  else
    echo "  (No CDK outputs file available)"
  fi

  echo "=========================================="
  echo "  Deployment complete!"
  echo "=========================================="
}

# --- Main Execution ---
main() {
  parse_args "$@"
  check_prerequisites

  # Order matters: deploy the CDK stack first so the ECR repositories exist
  # before images are pushed. The worker task definitions only reference image
  # tags (nothing is pulled at deploy time), so deploying before the images
  # exist is safe and avoids the first-deploy "repository does not exist" error.

  # Build the static web app — CDK needs apps/web/out at deploy time.
  build_web

  cdk_install

  if [[ "${SKIP_BOOTSTRAP}" == "false" ]]; then
    cdk_bootstrap
  else
    echo "Skipping CDK bootstrap (--skip-bootstrap)"
  fi

  cdk_deploy

  if [[ "${SKIP_IMAGES}" == "false" ]]; then
    ecr_login
    build_all_images
  else
    echo "Skipping image build and push (--skip-images)"
  fi

  print_summary
}

main "$@"
