import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
// Import the Lambda module
import * as lambda from 'aws-cdk-lib/aws-lambda';

// Import API Gateway WebSocket module
import * as apigatewayv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';

// Import IAM module
import * as iam from 'aws-cdk-lib/aws-iam';

export class HelloCdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // 1. WebSocket APIを先に作成 (ルートは後で addRoute)
    const webSocketApi = new apigatewayv2.WebSocketApi(this, 'HelloWebSocketApi');

    cdk.Tags.of(webSocketApi).add('WPS', 'cdktest_rairaii');

    // 2. WebSocketステージの作成 (任意で 'prod' や '$default' を指定)
    const webSocketStage = new apigatewayv2.WebSocketStage(this, 'HelloWebSocketStage', {
      webSocketApi,
      stageName: 'prod', // 例: 'prod' にした場合の接続URL → wss://{apiId}.execute-api.{region}.amazonaws.com/prod
      autoDeploy: true,
    });
    cdk.Tags.of(webSocketStage).add('WPS', 'cdktest_rairaii');

    // 3. WebSocketから呼びだされるLambda関数の定義
    const helloWorldFunction = new lambda.Function(this, 'HelloWorldFunction', {
      runtime: lambda.Runtime.NODEJS_20_X,
      code: lambda.Code.fromAsset('lambda'),
      handler: 'hello.handler',
      // もしLambdaで endpoint を使うなら、ここでwebSocketApi.apiIdを参照可能
      // 例: stageName が 'prod' の場合
      environment: {
        WEBSOCKET_ENDPOINT: `https://${webSocketApi.apiId}.execute-api.${this.region}.amazonaws.com/prod`,
      },
    });
    
    cdk.Tags.of(helloWorldFunction).add('WPS', 'cdktest_rairaii');

    // 4. すでに作成済みの Lambda 関数 (helloWorldFunction) に対してポリシーを追加
    helloWorldFunction.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['execute-api:ManageConnections'],
      resources: [
        // WebSocket API の ARN を指定
        // stageName: 'prod' → "prod/POST/@connections/*"
        `arn:aws:execute-api:${this.region}:${this.account}:${webSocketApi.apiId}/${webSocketStage.stageName}/POST/@connections/*`,
      ],
    }));

    // 5. WebSocket APIの各ルート ($connect, $disconnect, $default) を addRoute で定義
    webSocketApi.addRoute('$connect', {
      integration: new integrations.WebSocketLambdaIntegration('ConnectIntegration', helloWorldFunction),
    });

    webSocketApi.addRoute('$disconnect', {
      integration: new integrations.WebSocketLambdaIntegration('DisconnectIntegration', helloWorldFunction),
    });

    webSocketApi.addRoute('$default', {
      integration: new integrations.WebSocketLambdaIntegration('DefaultIntegration', helloWorldFunction),
    });
  }
}