const { ApiGatewayManagementApiClient, PostToConnectionCommand } = require("@aws-sdk/client-apigatewaymanagementapi");

// WebSocket API のエンドポイントを HTTPS に変換
const apiGateway = new ApiGatewayManagementApiClient({
    endpoint: process.env.WEBSOCKET_ENDPOINT.replace(/^wss:\/\//, "https://"),
});

exports.handler = async (event) => {
    console.log("Received event: ", JSON.stringify(event, null, 2));

    const { requestContext, body } = event;
    const connectionId = requestContext.connectionId;

    try {
        switch (requestContext.routeKey) {
            case '$connect':
                console.log(`New connection: ${connectionId}`);
                return { statusCode: 200, body: 'Connected' };

            case '$disconnect':
                console.log(`Disconnected: ${connectionId}`);
                return { statusCode: 200, body: 'Disconnected' };

            default:
                console.log(`Received message: ${body}`);
                await sendMessageToClient(connectionId, `Echo: ${body}`);
                return { statusCode: 200, body: `Echoed: ${body}` };
        }
    } catch (error) {
        console.error('Error: ', error);
        return { statusCode: 500, body: 'Error processing request' };
    }
};

// メッセージをクライアントに送信する関数（修正済み）
const sendMessageToClient = async (connectionId, message) => {
    try {
        const command = new PostToConnectionCommand({
            ConnectionId: connectionId,
            Data: Buffer.from(message),
        });

        await apiGateway.send(command);
        console.log(`Sent message to ${connectionId}: ${message}`);
    } catch (error) {
        console.error(`Failed to send message to ${connectionId}:`, error);
    }
};