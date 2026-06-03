import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import * as events from "aws-cdk-lib/aws-events";
import * as events_targets from "aws-cdk-lib/aws-events-targets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as sns from "aws-cdk-lib/aws-sns";
import * as sns_subscriptions from "aws-cdk-lib/aws-sns-subscriptions";
import { Construct } from "constructs";
import * as path from "path";

export interface DocChangeCheckerStackProps extends cdk.StackProps {
  targetUrl: string;
  bedrockModelId: string;
  snsTopicArn?: string;
  notificationEmail?: string;
}

export class DocChangeCheckerStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: DocChangeCheckerStackProps) {
    super(scope, id, props);

    const projectName = "aws-doc-change-checker";

    // DynamoDB Table
    const table = new dynamodb.Table(this, "DocPagesTable", {
      tableName: projectName,
      partitionKey: { name: "url", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // SNS Topic: Import existing ARN if specified, otherwise create a new one
    let topic: sns.ITopic;
    if (props.snsTopicArn) {
      topic = sns.Topic.fromTopicArn(this, "ImportedTopic", props.snsTopicArn);
    } else {
      const newTopic = new sns.Topic(this, "DocChangesTopic", {
        topicName: `${projectName}-notifications`,
      });

      if (props.notificationEmail) {
        newTopic.addSubscription(
          new sns_subscriptions.EmailSubscription(props.notificationEmail)
        );
      }

      topic = newTopic;
    }

    // Docker Image (from app/ directory)
    const dockerImage = new ecr_assets.DockerImageAsset(this, "LambdaImage", {
      directory: path.join(__dirname, "../../app"),
      platform: ecr_assets.Platform.LINUX_AMD64,
    });

    // Lambda Function
    const fn = new lambda.DockerImageFunction(this, "CheckerFunction", {
      functionName: projectName,
      code: lambda.DockerImageCode.fromEcr(dockerImage.repository, {
        tagOrDigest: dockerImage.imageTag,
      }),
      memorySize: 512,
      timeout: cdk.Duration.minutes(5),
      environment: {
        TARGET_URL: props.targetUrl,
        DYNAMODB_TABLE: table.tableName,
        SNS_TOPIC_ARN: topic.topicArn,
        BEDROCK_MODEL_ID: props.bedrockModelId,
        AWS_REGION_NAME: this.region,
      },
      logRetention: logs.RetentionDays.TWO_WEEKS,
    });

    // Permissions
    table.grantReadWriteData(fn);
    topic.grantPublish(fn);

    // Bedrock permissions
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:InvokeModel"],
        resources: ["*"],
      })
    );

    // EventBridge Rule: Daily at 9:00 AM JST (= 0:00 UTC)
    const rule = new events.Rule(this, "DailySchedule", {
      ruleName: `${projectName}-daily-9am`,
      schedule: events.Schedule.cron({
        minute: "0",
        hour: "0",
        day: "*",
        month: "*",
        year: "*",
      }),
      description: "Run AWS doc change checker daily at 9:00 AM JST",
    });

    rule.addTarget(new events_targets.LambdaFunction(fn));

    // Outputs
    new cdk.CfnOutput(this, "FunctionName", {
      value: fn.functionName,
    });
    new cdk.CfnOutput(this, "TableName", {
      value: table.tableName,
    });
    new cdk.CfnOutput(this, "TopicArn", {
      value: topic.topicArn,
    });
  }
}
