# Deployment Guide

Deploy the eyereadeverything application to AWS using the automated deployment script.

## Architecture Overview

The stack is serverless and pay-per-use. There are no always-on servers, load balancers, or NAT gateways:

| Component | Service | Notes |
|-----------|---------|-------|
| **Web frontend** | S3 + CloudFront | Next.js static export (`apps/web/out`), served globally over HTTPS |
| **API** | Lambda + Function URL | FastAPI via Mangum, bundled from `apps/api` (no container) |
| **Pipeline steps** | 6 Lambdas | validate, ingest, context, generate, tts, package |
| **Render worker** | Fargate (on-demand) | FFmpeg + Nova Reel: runs per job, in public subnets |
| **Nova Act worker** | Fargate (on-demand) | YouTube upload: runs per job, in public subnets |
| **Orchestration** | Step Functions | Drives the pipeline per job |
| **Data** | DynamoDB (on-demand) + S3 | Jobs, voice profiles, uploads, renders |

Only the two worker tasks use the VPC (public subnets, no NAT). The frontend reads the API URL at runtime from `/config.json`, which CDK writes at deploy time — so the static build needs no deploy-time values.

## Prerequisites

| Tool | Minimum Version | Check |
|------|----------------|-------|
| AWS CLI | v2 | `aws --version` |
| Docker | 20+ | `docker --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |

The Docker daemon must be running before you start.

## AWS Credential Configuration

The deploy script needs valid AWS credentials. Configure them using one of these methods:

### Environment Variables

```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_REGION=us-east-1  # optional, defaults to us-east-1
```

### AWS Profile

```bash
# Configure a named profile
aws configure --profile eyeread

# Use it for deployment
export AWS_PROFILE=eyeread
```

### Verify Credentials

```bash
aws sts get-caller-identity
```

This should return your account ID, user ARN, and user ID. If it fails, your credentials are not configured correctly.

## First-Time Deployment

1. Ensure all prerequisites are installed and the Docker daemon is running.

2. Configure AWS credentials (see above).

3. Run the full deployment:

```bash
# macOS / Linux / Git Bash
./scripts/deploy.sh
```

```powershell
# Windows (PowerShell) — use this if your bash is WSL without the AWS CLI/Docker/Node
./scripts/deploy.ps1
```

Both scripts perform the same steps. This will:
- Validate prerequisites (AWS CLI, Docker, Node.js, npm, credentials, Docker daemon)
- Build the **static web frontend** (`npm ci && npm run build` in `apps/web`, producing `apps/web/out`)
- Install CDK dependencies (`npm install` in `infra/`)
- Bootstrap CDK for your AWS account and region
- Deploy the `EyereadStack` via CDK, which:
  - creates the worker ECR repositories
  - bundles the API and pipeline Lambdas from source
  - uploads the static site to S3 and serves it via CloudFront
  - writes `config.json` (with the resolved API Function URL) alongside the site
- Authenticate Docker with ECR and build + push the **2 worker images**:
  - `eyereadeverything-render-worker` (from `services/render-worker`)
  - `eyereadeverything-nova-act-worker` (from `services/nova-act-worker`)
- Print a summary with the CloudFront URL, API Function URL, and resource identifiers

> Note: the CDK stack is deployed **before** the worker images are pushed, so the ECR repositories exist first. The worker task definitions only reference image tags (nothing is pulled at deploy time), so this ordering is safe and avoids first-deploy "repository does not exist" errors.

> Note: the API and web frontend are **not** containers. The API runs on Lambda (bundled from source) and the web app is a static site on S3/CloudFront, so only the two worker images are built and pushed.

Each worker image is tagged with both `latest` and a timestamp (`YYYYMMDD-HHMMSS`).

## Subsequent Deployments

### Full Redeployment

```bash
./scripts/deploy.sh
```

### CDK-Only Deployment (Skip Image Builds)

If you only changed infrastructure and not worker code:

```bash
./scripts/deploy.sh --skip-images
```

Note: `--skip-images` skips only the **worker container** builds/pushes. The static web build still runs, because CDK needs `apps/web/out` to exist at deploy time.

### Skip CDK Bootstrap

If the environment is already bootstrapped (it only needs to happen once per account/region):

```bash
./scripts/deploy.sh --skip-bootstrap
```

### Combine Flags

```bash
./scripts/deploy.sh --skip-images --skip-bootstrap
```

## Script Flags Reference

| Flag | Effect |
|------|--------|
| `--skip-images` | Skip the worker Docker image builds and ECR push. The static web build and CDK deploy still run. |
| `--skip-bootstrap` | Skip the CDK bootstrap step. Use after the first successful deployment. |

For the PowerShell script (`deploy.ps1`), the equivalent flags are `-SkipImages` and `-SkipBootstrap`.

## Troubleshooting

### ECR Authentication Failure

```
ERROR: ECR authentication failed
```

- Verify your AWS credentials are valid: `aws sts get-caller-identity`
- Ensure your IAM user/role has `ecr:GetAuthorizationToken` permission
- The worker ECR repositories (`eyereadeverything-render-worker`, `eyereadeverything-nova-act-worker`) are created by the CDK stack, which deploys before images are pushed — so they should already exist by the time the push runs.

### Web Build Failure

```
ERROR: Failed to build web frontend
ERROR: Web build did not produce apps/web/out
```

- Ensure Node.js 18+ and npm 9+ are installed
- The web app uses a static export (`output: 'export'` in `apps/web/next.config.ts`) built with `next build --webpack`
- Try building manually: `cd apps/web && npm ci && npm run build`, then confirm `apps/web/out` exists
- If the build hangs or crashes, confirm the build script uses `--webpack` (Turbopack builds can be unstable on some platforms)

### CDK Bootstrap Failure

```
ERROR: CDK bootstrap failed
```

- Ensure your IAM user/role has sufficient permissions for CloudFormation and S3
- Check that the target region is correct: `echo $AWS_REGION` (defaults to `us-east-1`)
- Try running bootstrap manually: `cd infra && npx cdk bootstrap aws://ACCOUNT_ID/REGION`

### Docker Daemon Not Running

```
ERROR: Docker daemon is not running
```

- Start Docker Desktop (macOS/Windows) or the Docker service (Linux: `sudo systemctl start docker`)
- Verify with: `docker info`

### Docker Build Failure

```
ERROR: Failed to build image for {service}
```

- Check the Dockerfile in the failing service directory
- Ensure you have enough disk space for Docker builds
- Try building manually: `docker build -t test services/render-worker` (replace with the failing worker path)

### CDK Deployment Failure

```
ERROR: CDK deployment failed
```

- Check the CloudFormation console for detailed error messages
- Ensure your IAM permissions cover all resources in the stack (Lambda, ECS/Fargate, S3, CloudFront, Step Functions, DynamoDB, etc.)
- Run `cd infra && npx cdk diff` to see what changes CDK is trying to apply
- If the deploy fails on bucket creation with "bucket already exists", the global S3 names (`eyereadeverything-uploads`, `eyereadeverything-renders`, `eyereadeverything-web`) are taken — add a unique suffix in `infra/lib/eyeread-stack.ts`

### Missing Prerequisites

```
ERROR: AWS CLI is not installed
ERROR: Docker is not installed
ERROR: Node.js is not installed
ERROR: npm is not installed
```

Install the missing tool and ensure it's on your `PATH`. See the prerequisites table above for minimum versions.
