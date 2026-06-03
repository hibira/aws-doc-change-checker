# AWS Documentation Change Checker

A serverless service that crawls AWS documentation pages (including the full navigation menu), detects content changes, summarizes updates using Bedrock (Claude Sonnet 4.6), and sends notifications via SNS.

## Architecture

```
EventBridge (daily at 9:00 AM JST)
    │
    ▼
Lambda (container-based)
    ├── Crawl: Extract all page URLs from toc-contents.json
    ├── Detect: Compare SHA-256 hashes with DynamoDB records
    ├── Summarize: Generate summary via Bedrock (Claude Sonnet 4.6)
    └── Notify: Publish to SNS topic
    │
    ▼
DynamoDB (page hash & content storage)
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TARGET_URL` | Root URL of the documentation to monitor | `https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html` |
| `DYNAMODB_TABLE` | DynamoDB table name | `aws-doc-change-checker` |
| `SNS_TOPIC_ARN` | SNS topic ARN for notifications | `arn:aws:sns:us-east-1:123456789012:doc-changes` |
| `BEDROCK_MODEL_ID` | Bedrock model ID for summarization | `us.anthropic.claude-sonnet-4-6` |
| `AWS_REGION_NAME` | AWS region | `us-east-1` |

## Deploy

The infrastructure is managed with AWS CDK (TypeScript).

```bash
cd cdk
npm install

# Bootstrap (first time only)
CDK_DOCKER=finch npx cdk bootstrap

# Deploy
CDK_DOCKER=finch npx cdk deploy
```

### Configuration via environment variables

```bash
# Use an existing SNS topic
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:123456789012:my-topic \
  CDK_DOCKER=finch npx cdk deploy

# Override target URL and model
TARGET_URL=https://docs.aws.amazon.com/lambda/latest/dg/welcome.html \
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6 \
  CDK_DOCKER=finch npx cdk deploy
```

## Manual Invocation

```bash
aws lambda invoke --function-name aws-doc-change-checker --region us-east-1 /dev/stdout
```

## Project Structure

```
aws-doc-change-checker/
├── app/
│   ├── Dockerfile              # Lambda container image
│   ├── requirements.txt        # Python dependencies
│   └── src/
│       ├── handler.py          # Lambda entrypoint
│       ├── crawler.py          # Crawl documentation via toc-contents.json
│       ├── change_detector.py  # Detect changes using DynamoDB hash comparison
│       ├── summarizer.py       # Summarize changes via Bedrock Sonnet 4.6
│       └── notifier.py         # Send notifications via SNS
├── cdk/
│   ├── bin/app.ts              # CDK app entry
│   ├── lib/doc-change-checker-stack.ts  # Stack definition
│   ├── package.json
│   ├── tsconfig.json
│   └── cdk.json
├── scripts/
│   └── deploy.sh               # Legacy deploy script (Terraform)
├── .gitignore
└── README.md
```

## How It Works

1. **Crawl** – Fetches `toc-contents.json` from the target documentation to discover all pages in the navigation tree, then retrieves the main content of each page.
2. **Detect** – Computes a SHA-256 hash of each page's content and compares it against the previously stored hash in DynamoDB. Only pages with differing hashes are flagged as changed.
3. **Summarize** – Sends the full previous and current content of changed pages to Bedrock Claude Sonnet 4.6, which generates a Japanese-language summary highlighting the differences.
4. **Notify** – Publishes the summary and list of changed pages to an SNS topic, which delivers email notifications to subscribers.
