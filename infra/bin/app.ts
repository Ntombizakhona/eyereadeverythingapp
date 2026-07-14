#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { EyereadStack } from '../lib/eyeread-stack';

const app = new cdk.App();

new EyereadStack(app, 'EyereadStack', {
    env: {
        account: process.env.CDK_DEFAULT_ACCOUNT,
        region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
    },
    description: 'eyereadeverything - Blog-to-Video & Talk-to-Video platform powered by Amazon Nova',
});
