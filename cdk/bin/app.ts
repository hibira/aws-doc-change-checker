#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { DocChangeCheckerStack } from "../lib/doc-change-checker-stack";

const app = new cdk.App();

new DocChangeCheckerStack(app, "AwsDocChangeCheckerStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || "us-east-1",
  },
  targetUrl:
    process.env.TARGET_URL ||
    "https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html",
  bedrockModelId: process.env.BEDROCK_MODEL_ID || "us.anthropic.claude-sonnet-4-6",
  // Specify an existing SNS topic ARN (a new topic is created if omitted)
  snsTopicArn: process.env.SNS_TOPIC_ARN,
  // Email address for notifications (only used when creating a new topic)
  // notificationEmail: "your-email@example.com",
});
