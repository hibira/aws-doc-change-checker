# AWSドキュメントの更新を自動検知してAI要約で通知するサーバーレスサービスを作った

## はじめに

AWSのドキュメントは頻繁に更新されますが、気になるサービスのドキュメント変更をタイムリーに把握するのは意外と大変です。RSSフィードがないサービスも多く、What's Newだけではドキュメント本文の細かい修正までは追えません。

そこで、指定したAWSドキュメントを毎日クロールし、変更があればBedrock（Claude Sonnet 4.6）で要約してメール通知するサーバーレスサービスを構築しました。

**リポジトリ**: https://github.com/hibira/aws-doc-change-checker

## アーキテクチャ

```
EventBridge (毎日 9:00 AM JST)
    │
    ▼
Lambda (コンテナベース)
    ├── クロール: toc-contents.json から全ページURL取得
    ├── 変更検知: SHA-256ハッシュをDynamoDBと比較
    ├── 要約生成: Bedrock Claude Sonnet 4.6
    └── 通知: SNSトピックへ配信
    │
    ▼
DynamoDB (ページハッシュ・コンテンツ保存)
```

### 使用サービス

| サービス | 用途 |
|---------|------|
| Lambda (コンテナ) | クローラー & 変更検知 & 要約 |
| DynamoDB | ページコンテンツとハッシュの永続化 |
| Bedrock (Claude Sonnet 4.6) | 変更内容の日本語要約 |
| EventBridge | 定期実行トリガー |
| SNS | メール通知 |
| ECR | Lambdaコンテナイメージの格納 |
| CDK (TypeScript) | IaC |

## 工夫したポイント

### 1. toc-contents.json を使った確実なクロール

AWSドキュメントのナビゲーションはJavaScriptで動的にレンダリングされるため、通常のHTMLパースではサイドメニューのリンクを取得できません。

しかし調査したところ、AWSドキュメントには `toc-contents.json` というエンドポイントが存在しており、ここからナビゲーション構造をJSON形式で取得できます。

```python
def _extract_pages_from_toc(base_url: str) -> list:
    """Recursively extract all page URLs from AWS documentation toc-contents.json."""
    toc_url = base_url + "toc-contents.json"
    response = requests.get(toc_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    toc_data = response.json()

    page_urls = []
    _walk_toc(toc_data.get("contents", []), base_url, page_urls)
    return page_urls
```

これにより、DevOps Agentのドキュメントでは **57ページすべて** を確実に検出できました。TOCが利用できないドキュメントの場合は、ページ内リンクからのフォールバック抽出にも対応しています。

### 2. コンテンツハッシュによる効率的な変更検知

各ページのメインコンテンツをSHA-256でハッシュ化し、DynamoDBに保存した前回のハッシュと比較します。ハッシュが一致すればスキップ、不一致なら変更ありとして処理を続行します。

```python
content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
previous_record = table.get_item(Key={"url": url}).get("Item")

if previous_record.get("content_hash") != content_hash:
    # 変更検知！前回コンテンツと一緒にBedrockへ送る
```

DynamoDBにはハッシュだけでなく **コンテンツ全文** も保存しているため、変更検知時に「前回の内容」と「今回の内容」の両方をBedrockに渡せます。

### 3. 全文比較による高品質な要約

Sonnet 4.6は1Mトークンの入力コンテキストに対応しているため、テキストを切り詰めることなく前回と今回のコンテンツ全文をそのまま渡しています。

```python
response = client.invoke_model(
    modelId="us.anthropic.claude-sonnet-4-6",
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 65536,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }),
)
```

プロンプトでは以下を指示しています:
- 変更の概要（1-2文）
- 各ページの変更点（箇条書き）
- 影響を受ける可能性のあるユーザーや機能

新規ページの場合はコンテンツの要約、更新ページの場合は差分にフォーカスした要約を生成します。

### 4. 環境変数による柔軟な設定

対象URL、モデルID、SNSトピックARNをすべて環境変数で指定できるため、デプロイ後の変更も容易です。

```bash
# 別のドキュメントを監視対象に変更
TARGET_URL=https://docs.aws.amazon.com/lambda/latest/dg/welcome.html \
  CDK_DOCKER=finch npx cdk deploy
```

## CDKによるインフラ定義

インフラはCDK（TypeScript）で管理しています。主要な部分を抜粋します。

```typescript
// EventBridge: 毎日 9:00 AM JST (= UTC 0:00)
const rule = new events.Rule(this, "DailySchedule", {
  schedule: events.Schedule.cron({
    minute: "0",
    hour: "0",
    day: "*",
    month: "*",
    year: "*",
  }),
});
rule.addTarget(new events_targets.LambdaFunction(fn));

// SNS: 既存トピックの利用 or 新規作成
let topic: sns.ITopic;
if (props.snsTopicArn) {
  topic = sns.Topic.fromTopicArn(this, "ImportedTopic", props.snsTopicArn);
} else {
  topic = new sns.Topic(this, "DocChangesTopic", {
    topicName: `${projectName}-notifications`,
  });
}
```

## 実行結果

実際にAWS DevOps Agentのドキュメント（57ページ）で動作確認しました。

```
$ aws lambda invoke --function-name aws-doc-change-checker /dev/stdout
{"statusCode": 200, "body": "{\"message\": \"Changes detected and notified\", \"pages_checked\": 57, \"pages_changed\": 1}"}
```

変更を検知するとこのようなメールが届きます:

```
============================================================
AWS Documentation Change Notification
============================================================

Pages changed: 1

Changed pages:
  [UPDATED] About AWS DevOps Agent
           https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html

------------------------------------------------------------
AI Summary:
------------------------------------------------------------

## 変更の概要
AWS DevOps Agentの「About」ページにChat機能の説明が追加されました。

## 各ページの変更点
- **About AWS DevOps Agent**: 「AWS DevOps Agent Chat」の説明が新たに追加。
  自然言語でインフラへの問い合わせ、システムヘルスの分析、調査のガイドが
  可能になったことが記載されています。

## 影響を受ける可能性のあるユーザーや機能
- DevOps Agent Spaceを利用中のオペレーションチーム
- 既存の調査ワークフローに自然言語インターフェースが追加されたことで、
  操作方法に新しい選択肢が増えます

============================================================
```

## コスト見積もり

月間コストはほぼ無視できるレベルです:

| リソース | 月額見積もり |
|---------|-------------|
| Lambda (1日1回, 約20秒) | ~$0.01 |
| DynamoDB (57レコード, PAY_PER_REQUEST) | ~$0.01 |
| Bedrock (変更がある場合のみ) | 変更頻度による（1回約$0.01-0.05） |
| EventBridge | 無料 |
| SNS (メール) | 無料枠内 |

## デプロイ手順

```bash
git clone https://github.com/hibira/aws-doc-change-checker.git
cd aws-doc-change-checker/cdk
npm install

# 初回のみ
CDK_DOCKER=finch npx cdk bootstrap

# デプロイ
CDK_DOCKER=finch npx cdk deploy

# SNSメール通知を追加
aws sns subscribe \
  --topic-arn <出力されたTopicArn> \
  --protocol email \
  --notification-endpoint your-email@example.com
```

※ Dockerの代わりに `finch` を使っている場合は `CDK_DOCKER=finch` を指定してください。通常のDocker環境であれば不要です。

## まとめ

- AWSドキュメントの `toc-contents.json` を使うことで、ナビゲーションメニュー内の全ページを確実にクロール可能
- SHA-256ハッシュによる変更検知で、テキストレベルの差分を正確に検出
- Bedrock Claude Sonnet 4.6の1Mトークンコンテキストを活用し、全文比較による高品質な要約を生成
- サーバーレス構成のため運用コストはほぼゼロ
- CDKで管理しているため、対象ドキュメントの追加も環境変数の変更だけで対応可能

気になるAWSサービスのドキュメント更新を見逃したくない方は、ぜひ試してみてください。
