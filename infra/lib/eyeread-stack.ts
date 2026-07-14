import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecsPatterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';
import * as path from 'path';

export class EyereadStack extends cdk.Stack {
    constructor(scope: Construct, id: string, props?: cdk.StackProps) {
        super(scope, id, props);

        // ═══════════════════════════════════════════════
        // S3 BUCKETS
        // ═══════════════════════════════════════════════
        const uploadsBucket = new s3.Bucket(this, 'UploadsBucket', {
            bucketName: 'eyereadeverything-uploads',
            encryption: s3.BucketEncryption.S3_MANAGED,
            cors: [{
                allowedMethods: [s3.HttpMethods.PUT, s3.HttpMethods.GET],
                allowedOrigins: ['*'],
                allowedHeaders: ['*'],
                maxAge: 3600,
            }],
            removalPolicy: cdk.RemovalPolicy.RETAIN,
            lifecycleRules: [{
                expiration: cdk.Duration.days(30),
                prefix: 'uploads/',
            }],
        });

        const rendersBucket = new s3.Bucket(this, 'RendersBucket', {
            bucketName: 'eyereadeverything-renders',
            encryption: s3.BucketEncryption.S3_MANAGED,
            removalPolicy: cdk.RemovalPolicy.RETAIN,
            lifecycleRules: [{
                expiration: cdk.Duration.days(90),
            }],
        });

        // ═══════════════════════════════════════════════
        // DYNAMODB TABLES
        // ═══════════════════════════════════════════════
        const jobsTable = new dynamodb.Table(this, 'JobsTable', {
            tableName: 'eyereadeverything-jobs',
            partitionKey: { name: 'job_id', type: dynamodb.AttributeType.STRING },
            billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
            removalPolicy: cdk.RemovalPolicy.RETAIN,
        });

        jobsTable.addGlobalSecondaryIndex({
            indexName: 'userId-createdAt-index',
            partitionKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
            sortKey: { name: 'created_at', type: dynamodb.AttributeType.STRING },
            projectionType: dynamodb.ProjectionType.ALL,
        });

        const voiceProfilesTable = new dynamodb.Table(this, 'VoiceProfilesTable', {
            tableName: 'eyereadeverything-voice-profiles',
            partitionKey: { name: 'voice_profile_id', type: dynamodb.AttributeType.STRING },
            billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
            removalPolicy: cdk.RemovalPolicy.RETAIN,
        });

        voiceProfilesTable.addGlobalSecondaryIndex({
            indexName: 'userId-index',
            partitionKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
            projectionType: dynamodb.ProjectionType.ALL,
        });

        // ═══════════════════════════════════════════════
        // VPC + ECS CLUSTER
        // ═══════════════════════════════════════════════
        const vpc = new ec2.Vpc(this, 'EyereadVpc', {
            maxAzs: 2,
            // No NAT gateway: tasks run in public subnets with public IPs and
            // reach the internet / AWS APIs via the Internet Gateway directly.
            // This removes the ~$33/mo NAT gateway from the always-on cost.
            natGateways: 0,
            subnetConfiguration: [
                {
                    name: 'public',
                    subnetType: ec2.SubnetType.PUBLIC,
                    cidrMask: 24,
                },
            ],
        });

        const cluster = new ecs.Cluster(this, 'EyereadCluster', {
            vpc,
            clusterName: 'eyereadeverything-cluster',
            containerInsights: true,
        });

        // ═══════════════════════════════════════════════
        // ECR REPOSITORIES
        // ═══════════════════════════════════════════════
        // The Web is a static site on S3/CloudFront (no image). The API is built
        // by CDK as a container asset (so it is pushed before the ECS service is
        // created). The two workers use these repositories (pushed by deploy.sh).
        const renderRepo = new ecr.Repository(this, 'RenderRepo', {
            repositoryName: 'eyereadeverything-render-worker',
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        });

        const novaActRepo = new ecr.Repository(this, 'NovaActRepo', {
            repositoryName: 'eyereadeverything-nova-act-worker',
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        });

        // ═══════════════════════════════════════════════
        // SHARED LAMBDA ENVIRONMENT
        // ═══════════════════════════════════════════════
        const lambdaEnv = {
            DYNAMODB_JOBS_TABLE: jobsTable.tableName,
            DYNAMODB_VOICE_PROFILES_TABLE: voiceProfilesTable.tableName,
            S3_UPLOADS_BUCKET: uploadsBucket.bucketName,
            S3_RENDERS_BUCKET: rendersBucket.bucketName,
            NOVA_MODEL_ID: 'amazon.nova-pro-v1:0',
            POLLY_VOICE_ID: 'Joanna',
        };

        // Shared Lambda role
        const lambdaRole = new iam.Role(this, 'LambdaPipelineRole', {
            assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [
                iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
            ],
        });

        // Grant Lambda access to all services
        uploadsBucket.grantReadWrite(lambdaRole);
        rendersBucket.grantReadWrite(lambdaRole);
        jobsTable.grantReadWriteData(lambdaRole);
        voiceProfilesTable.grantReadWriteData(lambdaRole);

        // Bedrock + Polly + Transcribe access
        lambdaRole.addToPolicy(new iam.PolicyStatement({
            actions: [
                'bedrock:InvokeModel',
                'bedrock:Converse',
                'polly:SynthesizeSpeech',
                'polly:StartSpeechSynthesisTask',
                'polly:GetSpeechSynthesisTask',
                'transcribe:StartTranscriptionJob',
                'transcribe:GetTranscriptionJob',
            ],
            resources: ['*'],
        }));

        // ═══════════════════════════════════════════════
        // LAMBDA BUNDLING HELPER
        // ═══════════════════════════════════════════════
        // Bundles Python Lambda functions with their requirements.txt.
        //
        // Uses pip's cross-platform flags to download Linux cp312 wheels
        // (manylinux) regardless of the host OS or local Python version. This
        // is the AWS-documented approach for packaging Lambda deps without
        // Docker, and it fixes the "No module named 'pydantic_core._pydantic_core'"
        // crash that happens when host-platform wheels (Windows, or cp39) get
        // shipped to the Lambda Python 3.12 runtime.
        //
        // Falls back to the Docker Linux build image if the local pip command
        // fails (e.g. a dependency has no manylinux/py3 wheel).
        const bundledPythonCode = (servicePath: string) => {
            const path = require('path');
            const absolutePath = path.resolve(__dirname, '..', servicePath);
            const pipPlatformArgs =
                '--platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all:';
            return lambda.Code.fromAsset(absolutePath, {
                bundling: {
                    image: lambda.Runtime.PYTHON_3_12.bundlingImage,
                    command: [
                        'bash', '-c',
                        [
                            // Inside the Linux build image a plain install already
                            // produces Lambda-compatible packages (incl. building
                            // any sdist-only deps natively).
                            'pip install -r requirements.txt -t /asset-output',
                            'cp -au . /asset-output',
                            'rm -rf /asset-output/__pycache__ /asset-output/requirements.txt',
                        ].join(' && '),
                    ],
                    local: {
                        tryBundle(outputDir: string) {
                            const { execSync } = require('child_process');
                            const os = require('os');
                            const fs = require('fs');
                            // Pick any available pip; --platform makes the output
                            // Linux/cp312 regardless of the host interpreter.
                            const pipCmd = os.platform() === 'win32' ? 'py -m pip' : 'python3 -m pip';
                            // Prefer Linux cp312 wheels; if a dependency has no
                            // wheel (sdist-only, e.g. readability-lxml), fall back
                            // to a plain install so bundling never hard-fails.
                            const installCmd =
                                `${pipCmd} install -r requirements.txt -t "${outputDir}" ${pipPlatformArgs} --quiet` +
                                ` || ${pipCmd} install -r requirements.txt -t "${outputDir}" --quiet`;
                            try {
                                execSync(installCmd, { cwd: absolutePath, stdio: 'inherit' });
                                const entries = fs.readdirSync(absolutePath, { withFileTypes: true });
                                for (const entry of entries) {
                                    if (entry.name === '__pycache__' || entry.name === 'requirements.txt') continue;
                                    const src = path.join(absolutePath, entry.name);
                                    const dest = path.join(outputDir, entry.name);
                                    if (entry.isDirectory()) {
                                        fs.cpSync(src, dest, { recursive: true });
                                    } else {
                                        fs.copyFileSync(src, dest);
                                    }
                                }
                                return true;
                            } catch (e) {
                                console.warn(`Local bundling failed for ${servicePath}, falling back to Docker`);
                                return false;
                            }
                        },
                    },
                },
            });
        };

        // ═══════════════════════════════════════════════
        // LAMBDA FUNCTIONS (Pipeline Steps)
        // ═══════════════════════════════════════════════
        const validateFn = new lambda.Function(this, 'ValidateFn', {
            functionName: 'eyereadeverything-validate',
            runtime: lambda.Runtime.PYTHON_3_12,
            handler: 'handler.handler',
            code: bundledPythonCode('../services/validate'),
            environment: lambdaEnv,
            role: lambdaRole,
            timeout: cdk.Duration.seconds(30),
            memorySize: 256,
        });

        const ingestFn = new lambda.Function(this, 'IngestFn', {
            functionName: 'eyereadeverything-ingest',
            runtime: lambda.Runtime.PYTHON_3_12,
            handler: 'handler.handler',
            code: bundledPythonCode('../services/ingest'),
            environment: lambdaEnv,
            role: lambdaRole,
            timeout: cdk.Duration.minutes(5),
            memorySize: 512,
        });

        const contextFn = new lambda.Function(this, 'ContextFn', {
            functionName: 'eyereadeverything-context',
            runtime: lambda.Runtime.PYTHON_3_12,
            handler: 'handler.handler',
            code: bundledPythonCode('../services/context'),
            environment: lambdaEnv,
            role: lambdaRole,
            timeout: cdk.Duration.minutes(2),
            memorySize: 512,
        });

        const generateFn = new lambda.Function(this, 'GenerateFn', {
            functionName: 'eyereadeverything-generate',
            runtime: lambda.Runtime.PYTHON_3_12,
            handler: 'handler.handler',
            code: bundledPythonCode('../services/generate'),
            environment: lambdaEnv,
            role: lambdaRole,
            timeout: cdk.Duration.minutes(10),
            memorySize: 1024,
        });

        const ttsFn = new lambda.Function(this, 'TtsFn', {
            functionName: 'eyereadeverything-tts',
            runtime: lambda.Runtime.PYTHON_3_12,
            handler: 'handler.handler',
            code: bundledPythonCode('../services/tts'),
            environment: lambdaEnv,
            role: lambdaRole,
            timeout: cdk.Duration.minutes(5),
            memorySize: 512,
        });

        const packageFn = new lambda.Function(this, 'PackageFn', {
            functionName: 'eyereadeverything-package',
            runtime: lambda.Runtime.PYTHON_3_12,
            handler: 'handler.handler',
            code: bundledPythonCode('../services/package'),
            environment: lambdaEnv,
            role: lambdaRole,
            timeout: cdk.Duration.minutes(5),
            memorySize: 1024,
        });

        // ═══════════════════════════════════════════════
        // ECS TASK DEFINITIONS (Fargate)
        // ═══════════════════════════════════════════════

        // Render Worker
        const renderTaskDef = new ecs.FargateTaskDefinition(this, 'RenderTaskDef', {
            cpu: 2048,
            memoryLimitMiB: 4096,
        });

        uploadsBucket.grantRead(renderTaskDef.taskRole);
        rendersBucket.grantReadWrite(renderTaskDef.taskRole);
        jobsTable.grantReadWriteData(renderTaskDef.taskRole);

        (renderTaskDef.taskRole as iam.Role).addToPolicy(new iam.PolicyStatement({
            actions: ['states:SendTaskSuccess', 'states:SendTaskFailure'],
            resources: ['*'],
        }));

        // Bedrock access for Nova Reel video generation
        (renderTaskDef.taskRole as iam.Role).addToPolicy(new iam.PolicyStatement({
            actions: [
                'bedrock:InvokeModel',
                'bedrock:StartAsyncInvoke',
                'bedrock:GetAsyncInvoke',
                'bedrock:ListAsyncInvokes',
            ],
            resources: ['*'],
        }));

        const renderContainer = renderTaskDef.addContainer('render', {
            image: ecs.ContainerImage.fromEcrRepository(renderRepo, 'latest'),
            logging: ecs.LogDrivers.awsLogs({
                streamPrefix: 'render',
                logRetention: logs.RetentionDays.ONE_WEEK,
            }),
            environment: {
                AWS_REGION: this.region,
                DYNAMODB_JOBS_TABLE: jobsTable.tableName,
                S3_RENDERS_BUCKET: rendersBucket.bucketName,
                S3_UPLOADS_BUCKET: uploadsBucket.bucketName,
            },
        });

        // Nova Act Worker
        const novaActTaskDef = new ecs.FargateTaskDefinition(this, 'NovaActTaskDef', {
            cpu: 2048,
            memoryLimitMiB: 4096,
        });

        rendersBucket.grantRead(novaActTaskDef.taskRole);
        jobsTable.grantReadWriteData(novaActTaskDef.taskRole);

        (novaActTaskDef.taskRole as iam.Role).addToPolicy(new iam.PolicyStatement({
            actions: ['states:SendTaskSuccess', 'states:SendTaskFailure'],
            resources: ['*'],
        }));

        const novaActContainer = novaActTaskDef.addContainer('nova-act', {
            image: ecs.ContainerImage.fromEcrRepository(novaActRepo, 'latest'),
            logging: ecs.LogDrivers.awsLogs({
                streamPrefix: 'nova-act',
                logRetention: logs.RetentionDays.ONE_WEEK,
            }),
            environment: {
                AWS_REGION: this.region,
                DYNAMODB_JOBS_TABLE: jobsTable.tableName,
                S3_RENDERS_BUCKET: rendersBucket.bucketName,
            },
        });

        // ═══════════════════════════════════════════════
        // STEP FUNCTIONS STATE MACHINE
        // ═══════════════════════════════════════════════

        // Lambda task helpers
        const validateTask = new tasks.LambdaInvoke(this, 'ValidateJob', {
            lambdaFunction: validateFn,
            outputPath: '$.Payload',
        });

        const ingestTask = new tasks.LambdaInvoke(this, 'Ingest', {
            lambdaFunction: ingestFn,
            outputPath: '$.Payload',
        });

        const contextTask = new tasks.LambdaInvoke(this, 'RetrieveContext', {
            lambdaFunction: contextFn,
            outputPath: '$.Payload',
        });

        const generateTask = new tasks.LambdaInvoke(this, 'Generate', {
            lambdaFunction: generateFn,
            outputPath: '$.Payload',
        });

        const ttsTask = new tasks.LambdaInvoke(this, 'SynthesizeNarration', {
            lambdaFunction: ttsFn,
            outputPath: '$.Payload',
        });

        // ECS Render task (wait for callback)
        const renderTask = new tasks.EcsRunTask(this, 'RenderVideo', {
            integrationPattern: sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
            cluster,
            taskDefinition: renderTaskDef,
            launchTarget: new tasks.EcsFargateLaunchTarget({
                platformVersion: ecs.FargatePlatformVersion.LATEST,
            }),
            containerOverrides: [{
                containerDefinition: renderContainer,
                environment: [
                    { name: 'JOB_ID', value: sfn.JsonPath.stringAt('$.job_id') },
                    { name: 'TASK_TOKEN', value: sfn.JsonPath.taskToken },
                ],
            }],
            subnets: { subnetType: ec2.SubnetType.PUBLIC },
            assignPublicIp: true,
        });

        const packageTask = new tasks.LambdaInvoke(this, 'PackageOutputs', {
            lambdaFunction: packageFn,
            outputPath: '$.Payload',
        });

        // Nova Act upload task (wait for callback)
        const novaActTask = new tasks.EcsRunTask(this, 'UploadYouTube', {
            integrationPattern: sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
            cluster,
            taskDefinition: novaActTaskDef,
            launchTarget: new tasks.EcsFargateLaunchTarget({
                platformVersion: ecs.FargatePlatformVersion.LATEST,
            }),
            containerOverrides: [{
                containerDefinition: novaActContainer,
                environment: [
                    { name: 'JOB_ID', value: sfn.JsonPath.stringAt('$.job_id') },
                    { name: 'TASK_TOKEN', value: sfn.JsonPath.taskToken },
                ],
            }],
            subnets: { subnetType: ec2.SubnetType.PUBLIC },
            assignPublicIp: true,
        });

        // Mark Done
        const markDone = new sfn.Pass(this, 'MarkDone', {
            result: sfn.Result.fromObject({ status: 'DONE' }),
        });

        // Error handler
        const handleError = new sfn.Fail(this, 'HandleError', {
            cause: 'Pipeline step failed',
            error: 'PipelineError',
        });

        // Upload choice
        const shouldUpload = new sfn.Choice(this, 'ShouldUpload')
            .when(
                sfn.Condition.booleanEquals('$.auto_upload_youtube', true),
                novaActTask.next(markDone)
            )
            .otherwise(markDone);

        // Build the pipeline chain
        const definition = validateTask
            .next(ingestTask)
            .next(contextTask)
            .next(generateTask)
            .next(ttsTask)
            .next(renderTask)
            .next(packageTask)
            .next(shouldUpload);

        // Add error handling
        validateTask.addCatch(handleError);
        ingestTask.addCatch(handleError);
        generateTask.addCatch(handleError);
        ttsTask.addCatch(handleError);
        renderTask.addCatch(handleError);
        packageTask.addCatch(handleError);

        const stateMachine = new sfn.StateMachine(this, 'EyereadPipeline', {
            stateMachineName: 'eyereadeverything-pipeline',
            definitionBody: sfn.DefinitionBody.fromChainable(definition),
            timeout: cdk.Duration.hours(1),
            logs: {
                destination: new logs.LogGroup(this, 'SfnLogs', {
                    logGroupName: '/eyereadeverything/stepfunctions',
                    retention: logs.RetentionDays.ONE_WEEK,
                }),
                level: sfn.LogLevel.ALL,
            },
        });

        // ═══════════════════════════════════════════════
        // API SERVICE (ECS Fargate + ALB, fronted by CloudFront)
        // ═══════════════════════════════════════════════
        // The FastAPI app runs as a Fargate container (built on Linux in its
        // Dockerfile, so native deps like pydantic-core are correct — no Lambda
        // cross-platform bundling issues). A small always-on task behind a
        // public ALB. CloudFront routes the API paths to this ALB so the browser
        // calls the API same-origin over HTTPS (no mixed content, no extra cert).
        const apiService = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'ApiService', {
            cluster,
            serviceName: 'eyereadeverything-api',
            cpu: 256,
            memoryLimitMiB: 512,
            desiredCount: 1,
            // Public subnet + public IP since there is no NAT gateway.
            taskSubnets: { subnetType: ec2.SubnetType.PUBLIC },
            assignPublicIp: true,
            taskImageOptions: {
                image: ecs.ContainerImage.fromAsset(path.resolve(__dirname, '..', '../apps/api')),
                containerPort: 8000,
                environment: {
                    AWS_REGION: this.region,
                    DYNAMODB_JOBS_TABLE: jobsTable.tableName,
                    DYNAMODB_VOICE_PROFILES_TABLE: voiceProfilesTable.tableName,
                    S3_UPLOADS_BUCKET: uploadsBucket.bucketName,
                    S3_RENDERS_BUCKET: rendersBucket.bucketName,
                    STEP_FUNCTIONS_ARN: stateMachine.stateMachineArn,
                    POLLY_VOICE_ID: 'Joanna',
                    LOCAL_DEV: 'false',
                },
            },
            publicLoadBalancer: true,
        });

        apiService.targetGroup.configureHealthCheck({
            path: '/health',
            healthyThresholdCount: 2,
            unhealthyThresholdCount: 3,
            interval: cdk.Duration.seconds(30),
        });

        // Grant the API task access to the resources it uses.
        uploadsBucket.grantReadWrite(apiService.taskDefinition.taskRole);
        rendersBucket.grantRead(apiService.taskDefinition.taskRole);
        jobsTable.grantReadWriteData(apiService.taskDefinition.taskRole);
        voiceProfilesTable.grantReadWriteData(apiService.taskDefinition.taskRole);
        stateMachine.grantStartExecution(apiService.taskDefinition.taskRole);
        (apiService.taskDefinition.taskRole as iam.Role).addToPolicy(new iam.PolicyStatement({
            actions: ['s3:PutObject', 's3:GetObject'],
            resources: [
                uploadsBucket.arnForObjects('*'),
                rendersBucket.arnForObjects('*'),
            ],
        }));

        // ═══════════════════════════════════════════════
        // WEB FRONTEND (S3 + CloudFront, static export)
        // ═══════════════════════════════════════════════
        // The Next.js app is statically exported (`output: 'export'`) and served
        // from S3 via CloudFront. This replaces the always-on Fargate web service
        // + ALB. The site reads the API URL at runtime from /config.json (written
        // below), so the static build does not need deploy-time values.
        const siteBucket = new s3.Bucket(this, 'WebSiteBucket', {
            bucketName: 'eyereadeverything-web',
            encryption: s3.BucketEncryption.S3_MANAGED,
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
            autoDeleteObjects: true,
        });

        // CloudFront origin + behavior for the API (Fargate ALB, HTTP). All
        // methods allowed and caching disabled so POSTs and live data pass
        // straight through. Host header is not forwarded (ALB routing).
        const apiBehavior: cloudfront.BehaviorOptions = {
            origin: new origins.LoadBalancerV2Origin(apiService.loadBalancer, {
                protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            }),
            viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
            cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
            originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        };

        // CloudFront function: resolve directory/extensionless paths to their
        // static index.html (e.g. /blog -> /blog/index.html, /blog/ ->
        // /blog/index.html). Required for Next.js static export on S3/CloudFront,
        // since OAC origins don't auto-resolve directory indexes. Paths with a
        // file extension (/config.json, /_next/..., /icon.svg) pass through.
        const rewriteFn = new cloudfront.Function(this, 'WebRewriteFn', {
            code: cloudfront.FunctionCode.fromInline([
                'function handler(event) {',
                '  var request = event.request;',
                '  var uri = request.uri;',
                "  if (uri.endsWith('/')) { request.uri += 'index.html'; }",
                "  else if (!uri.includes('.')) { request.uri += '/index.html'; }",
                '  return request;',
                '}',
            ].join('\n')),
        });

        const distribution = new cloudfront.Distribution(this, 'WebDistribution', {
            defaultRootObject: 'index.html',
            defaultBehavior: {
                origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
                viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
                functionAssociations: [{
                    function: rewriteFn,
                    eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,
                }],
            },
            // Route API paths to the Fargate ALB (same-origin HTTPS via CloudFront,
            // so the browser never makes a mixed-content HTTP call).
            additionalBehaviors: {
                '/jobs': apiBehavior,
                '/jobs/*': apiBehavior,
                '/uploads/*': apiBehavior,
                '/voice-profiles/*': apiBehavior,
                '/health': apiBehavior,
            },
        });

        // Deploy the statically exported site (apps/web/out) to the bucket.
        // deploy.sh runs `npm run build` for the web app, producing apps/web/out.
        new s3deploy.BucketDeployment(this, 'WebSiteDeployment', {
            sources: [
                s3deploy.Source.asset('../apps/web/out'),
                // apiUrl is empty: the frontend calls the API same-origin
                // (e.g. fetch('/jobs')), and CloudFront routes it to the ALB.
                s3deploy.Source.jsonData('config.json', { apiUrl: '' }),
            ],
            destinationBucket: siteBucket,
            distribution,
            distributionPaths: ['/*'],
        });

        // ═══════════════════════════════════════════════
        // OUTPUTS
        // ═══════════════════════════════════════════════
        new cdk.CfnOutput(this, 'ApiUrl', {
            value: `https://${distribution.distributionDomainName}`,
            description: 'API is served same-origin via the CloudFront URL (e.g. /jobs)',
        });

        new cdk.CfnOutput(this, 'ApiAlbUrl', {
            value: `http://${apiService.loadBalancer.loadBalancerDnsName}`,
            description: 'Direct API ALB URL (origin behind CloudFront; for debugging)',
        });

        new cdk.CfnOutput(this, 'WebUrl', {
            value: `https://${distribution.distributionDomainName}`,
            description: 'Web Frontend CloudFront URL',
        });

        new cdk.CfnOutput(this, 'UploadsBucketName', {
            value: uploadsBucket.bucketName,
        });

        new cdk.CfnOutput(this, 'RendersBucketName', {
            value: rendersBucket.bucketName,
        });

        new cdk.CfnOutput(this, 'StateMachineArn', {
            value: stateMachine.stateMachineArn,
        });

        new cdk.CfnOutput(this, 'ClusterName', {
            value: cluster.clusterName,
        });
    }
}
