#!/bin/bash
set -euo pipefail

# AWS Documentation Change Checker - デプロイスクリプト
# Usage: ./scripts/deploy.sh [region]

REGION="${1:-us-east-1}"
PROJECT_NAME="aws-doc-change-checker"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== AWS Doc Change Checker Deploy ==="
echo "Region: $REGION"
echo ""

# 1. Terraform apply
echo ">>> Terraform apply..."
cd "$ROOT_DIR/terraform"
terraform init -input=false
terraform apply -auto-approve -var="aws_region=$REGION"

# Terraform出力値を取得
ECR_REPO_URL=$(terraform output -raw ecr_repository_url)
ACCOUNT_ID=$(echo "$ECR_REPO_URL" | cut -d'.' -f1)

echo ""
echo ">>> ECR Repository: $ECR_REPO_URL"

# 2. Docker build & push
echo ""
echo ">>> Building Docker image..."
cd "$ROOT_DIR/app"

# ECRログイン
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# ビルド & プッシュ
docker build --platform linux/amd64 -t "$PROJECT_NAME" .
docker tag "$PROJECT_NAME:latest" "$ECR_REPO_URL:latest"
docker push "$ECR_REPO_URL:latest"

# 3. Lambda関数を最新イメージで更新
echo ""
echo ">>> Updating Lambda function..."
aws lambda update-function-code \
  --function-name "$PROJECT_NAME" \
  --image-uri "$ECR_REPO_URL:latest" \
  --region "$REGION" \
  --no-cli-pager

echo ""
echo "=== Deploy complete ==="
echo ""
echo "To test manually:"
echo "  aws lambda invoke --function-name $PROJECT_NAME --region $REGION /dev/stdout"
