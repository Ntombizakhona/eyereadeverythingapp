<#
.SYNOPSIS
  Native Windows (PowerShell) deployment for the eyereadeverything stack.
  Mirrors scripts/deploy.sh for environments where bash/WSL lacks the AWS CLI,
  Docker, and Node tooling but Windows has them.

.PARAMETER SkipImages
  Skip the worker Docker image builds and ECR push. The static web build and
  CDK deploy still run.

.PARAMETER SkipBootstrap
  Skip the CDK bootstrap step. Use after the first successful deployment.

.EXAMPLE
  ./scripts/deploy.ps1
  ./scripts/deploy.ps1 -SkipImages
  ./scripts/deploy.ps1 -SkipImages -SkipBootstrap
#>
[CmdletBinding()]
param(
    [switch]$SkipImages,
    [switch]$SkipBootstrap
)

$ErrorActionPreference = 'Stop'

# --- Configuration ---
$AwsRegion = if ($env:AWS_REGION) { $env:AWS_REGION } else { 'us-east-1' }
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'

# Repo root = parent of the directory containing this script.
$RepoRoot = Split-Path -Parent $PSScriptRoot

# The Web is a static site (no image) and the API is built by CDK as a
# container asset during deploy. Only the two workers are built/pushed here.
# Format: @{ Name; Path; Repo }
$Services = @(
    @{ Name = 'render-worker';   Path = 'services/render-worker';   Repo = 'eyereadeverything-render-worker' },
    @{ Name = 'nova-act-worker'; Path = 'services/nova-act-worker'; Repo = 'eyereadeverything-nova-act-worker' }
)

function Fail([string]$Message) {
    Write-Error "ERROR: $Message"
    exit 1
}

function Test-Tool([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Fail "$Name is not installed"
    }
}

# --- Prerequisite Validation ---
function Invoke-CheckPrerequisites {
    Write-Host 'Checking prerequisites...'

    Test-Tool 'aws'
    Test-Tool 'docker'
    Test-Tool 'node'
    Test-Tool 'npm'

    $script:AwsAccountId = (aws sts get-caller-identity --query Account --output text 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($script:AwsAccountId)) {
        Fail 'AWS credentials not configured'
    }

    docker info *> $null
    if ($LASTEXITCODE -ne 0) { Fail 'Docker daemon is not running' }

    Write-Host "All prerequisites met (AWS Account: $($script:AwsAccountId), Region: $AwsRegion)"
}

# --- ECR Authentication ---
function Invoke-EcrLogin {
    $registry = "$($script:AwsAccountId).dkr.ecr.$AwsRegion.amazonaws.com"
    Write-Host "Authenticating Docker with ECR ($registry)..."
    $password = aws ecr get-login-password --region $AwsRegion
    if ($LASTEXITCODE -ne 0) { throw 'ECR authentication failed (get-login-password)' }
    $password | docker login --username AWS --password-stdin $registry
    if ($LASTEXITCODE -ne 0) { throw 'ECR authentication failed (docker login)' }
}

# --- Image Build & Push ---
function Invoke-BuildAndPush($service) {
    $registry = "$($script:AwsAccountId).dkr.ecr.$AwsRegion.amazonaws.com"
    $name = $service.Name
    $path = Join-Path $RepoRoot $service.Path
    $repo = $service.Repo

    Write-Host "Building image for $name from $($service.Path)..."
    docker build -t "$($repo):latest" -t "$($repo):$Timestamp" $path
    if ($LASTEXITCODE -ne 0) { throw "Failed to build image for $name" }

    Write-Host 'Tagging image for ECR...'
    docker tag "$($repo):latest" "$registry/$($repo):latest"
    if ($LASTEXITCODE -ne 0) { throw "Failed to tag image for $name" }
    docker tag "$($repo):$Timestamp" "$registry/$($repo):$Timestamp"
    if ($LASTEXITCODE -ne 0) { throw "Failed to tag image for $name" }

    Write-Host "Pushing $($repo):latest to ECR..."
    docker push "$registry/$($repo):latest"
    if ($LASTEXITCODE -ne 0) { throw "Failed to push image to $repo" }

    Write-Host "Pushing $($repo):$Timestamp to ECR..."
    docker push "$registry/$($repo):$Timestamp"
    if ($LASTEXITCODE -ne 0) { throw "Failed to push image to $repo" }

    Write-Host "Successfully pushed $repo (latest, $Timestamp)"
}

function Invoke-BuildAllImages {
    Write-Host 'Building and pushing all worker images...'
    foreach ($service in $Services) { Invoke-BuildAndPush $service }
    Write-Host 'All images built and pushed successfully.'
}

# --- Web Static Build ---
# The web app is a static export (apps/web/out) served from S3/CloudFront.
# CDK's BucketDeployment uploads apps/web/out, so it must exist before deploy.
function Invoke-BuildWeb {
    Write-Host 'Building static web frontend (apps/web)...'
    Push-Location (Join-Path $RepoRoot 'apps/web')
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { Fail 'Failed to install web dependencies' }
        npm run build
        if ($LASTEXITCODE -ne 0) { Fail 'Failed to build web frontend' }
    }
    finally { Pop-Location }
    if (-not (Test-Path (Join-Path $RepoRoot 'apps/web/out'))) {
        Fail 'Web build did not produce apps/web/out'
    }
    Write-Host 'Web frontend built (apps/web/out).'
}

# --- CDK Operations ---
$script:CdkOutputsFile = ''

function Invoke-CdkInstall {
    Write-Host 'Installing CDK dependencies...'
    Push-Location (Join-Path $RepoRoot 'infra')
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { Fail 'Failed to install CDK dependencies' }
    }
    finally { Pop-Location }
    Write-Host 'CDK dependencies installed.'
}

function Invoke-CdkBootstrap {
    Write-Host "Bootstrapping CDK for aws://$($script:AwsAccountId)/$AwsRegion..."
    Push-Location (Join-Path $RepoRoot 'infra')
    try {
        npx.cmd cdk bootstrap "aws://$($script:AwsAccountId)/$AwsRegion"
        if ($LASTEXITCODE -ne 0) { Fail 'CDK bootstrap failed' }
    }
    finally { Pop-Location }
    Write-Host 'CDK bootstrap complete.'
}

function Invoke-CdkDeploy {
    $script:CdkOutputsFile = Join-Path ([System.IO.Path]::GetTempPath()) "cdk-outputs-$([System.Guid]::NewGuid().ToString('N')).json"
    Write-Host 'Deploying CDK stack...'
    Push-Location (Join-Path $RepoRoot 'infra')
    try {
        npx.cmd cdk deploy --require-approval never --outputs-file $script:CdkOutputsFile
        if ($LASTEXITCODE -ne 0) { Fail 'CDK deployment failed' }
    }
    finally { Pop-Location }
    Write-Host 'CDK deployment complete.'
}

function Write-Summary {
    Write-Host ''
    Write-Host '=========================================='
    Write-Host '  Deployment Summary'
    Write-Host '=========================================='

    if ($script:CdkOutputsFile -and (Test-Path $script:CdkOutputsFile)) {
        try {
            $data = Get-Content $script:CdkOutputsFile -Raw | ConvertFrom-Json
            $stackKey = ($data.PSObject.Properties | Select-Object -First 1).Name
            if ($stackKey) {
                $o = $data.$stackKey
                Write-Host "  API URL:              $($o.ApiUrl)"
                Write-Host "  Web URL:              $($o.WebUrl)"
                Write-Host "  Uploads Bucket:       $($o.UploadsBucketName)"
                Write-Host "  Renders Bucket:       $($o.RendersBucketName)"
                Write-Host "  State Machine ARN:    $($o.StateMachineArn)"
            }
            else {
                Write-Host '  (Could not parse CDK outputs)'
            }
        }
        catch {
            Write-Host '  (Could not parse CDK outputs)'
        }
        Remove-Item -Force $script:CdkOutputsFile -ErrorAction SilentlyContinue
    }
    else {
        Write-Host '  (No CDK outputs file available)'
    }

    Write-Host '=========================================='
    Write-Host '  Deployment complete!'
    Write-Host '=========================================='
}

# --- Main Execution ---
# Order matters: deploy the CDK stack first so the ECR repositories exist
# before images are pushed. The worker task definitions only reference image
# tags (nothing is pulled at deploy time), so deploying before the images
# exist is safe and avoids the first-deploy "repository does not exist" error.
Invoke-CheckPrerequisites

# Build the static web app — CDK needs apps/web/out at deploy time.
Invoke-BuildWeb

Invoke-CdkInstall

if (-not $SkipBootstrap) {
    Invoke-CdkBootstrap
}
else {
    Write-Host 'Skipping CDK bootstrap (-SkipBootstrap)'
}

Invoke-CdkDeploy

# Print the stack outputs (URLs) now — before the image push — so they are not
# lost if the Docker/ECR step fails (workers can be pushed separately later).
Write-Summary

if (-not $SkipImages) {
    try {
        Invoke-EcrLogin
        Invoke-BuildAllImages
    }
    catch {
        Write-Warning "Worker image build/push failed: $($_.Exception.Message)"
        Write-Warning "The stack is deployed and the web/API are live. The render and"
        Write-Warning "nova-act workers will not run jobs until their images are pushed."
        Write-Warning "Retry just the images later with: ./scripts/deploy.ps1 -SkipBootstrap"
    }
}
else {
    Write-Host 'Skipping image build and push (-SkipImages)'
}
