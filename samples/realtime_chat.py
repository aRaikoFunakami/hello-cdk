import uvicorn
import logging
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from langchain_openai_voice import OpenAIVoiceReactAgent

from typing import AsyncIterator

from realtime_chat_prompt import INSTRUCTIONS

TOOLS = []

async def websocket_stream(websocket: WebSocket) -> AsyncIterator[str]:
    while True:
        data = await websocket.receive_text()
        yield data


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    browser_receive_stream = websocket_stream(websocket)

    logging.info(f"browser_receive_stream: {browser_receive_stream}")
    agent = OpenAIVoiceReactAgent(
        model="gpt-4o-mini-realtime-preview-2024-12-17",
        tools=TOOLS,
        instructions=INSTRUCTIONS,
    )

    await agent.aconnect(browser_receive_stream, websocket.send_text)


async def homepage(request):
    with open("static/index.html") as f:
        html = f.read()
        return HTMLResponse(html)


routes = [Route("/", homepage), WebSocketRoute("/ws", websocket_endpoint)]

app = Starlette(debug=True, routes=routes)

app.mount("/", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    logging.basicConfig(
        format="[%(asctime)s] [%(process)d] [%(levelname)s] [%(filename)s:%(lineno)d %(funcName)s] [%(message)s]",
        level=logging.INFO,
    )
    uvicorn.run(app, host="0.0.0.0", port=3000)