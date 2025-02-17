import os
import json
import boto3

def lambda_handler(event, context):
    print("Received event:", json.dumps(event, indent=2))

    # ルートキーの取得
    route_key = event["requestContext"].get("routeKey", "")
    connection_id = event["requestContext"].get("connectionId", "")
    body = event.get("body", "")

    # WebSocket API のエンドポイントを環境変数から取得して https に変換
    endpoint = os.environ.get("WEBSOCKET_ENDPOINT", "").replace("wss://", "https://")

    # apigatewaymanagementapi クライアントを作成
    apigw_client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint)

    # ルートキーに応じて処理を分岐
    if route_key == "$connect":
        print(f"New connection: {connection_id}")
        return {
            "statusCode": 200,
            "body": "Connected"
        }

    elif route_key == "$disconnect":
        print(f"Disconnected: {connection_id}")
        return {
            "statusCode": 200,
            "body": "Disconnected"
        }

    else:
        # それ以外のルートはメッセージを Echo
        print(f"Received message: {body}")
        message_to_send = f"Echo: {body}"

        # クライアントへメッセージを送信
        try:
            apigw_client.post_to_connection(
                ConnectionId=connection_id,
                Data=message_to_send.encode('utf-8')  # bytes に変換
            )
            print(f"Sent message to {connection_id}: {message_to_send}")
        except Exception as e:
            print(f"Failed to send message to {connection_id}: {e}")
            return {
                "statusCode": 500,
                "body": "Error processing request"
            }

        return {
            "statusCode": 200,
            "body": message_to_send
        }