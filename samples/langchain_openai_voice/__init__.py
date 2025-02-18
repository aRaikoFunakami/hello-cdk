import asyncio
import json
import websockets

from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator, Any, Callable, Coroutine
from langchain_openai_voice.utils import amerge

from langchain_core.tools import BaseTool
from langchain_core._api import beta
from langchain_core.utils import secret_from_env

from pydantic import BaseModel, Field, SecretStr, PrivateAttr

DEFAULT_MODEL = "gpt-4o-realtime-preview-2024-10-01"
DEFAULT_URL = "wss://api.openai.com/v1/realtime"

EVENTS_TO_IGNORE = {
    "response.function_call_arguments.delta",
    "rate_limits.updated",
    "response.audio_transcript.delta",
    "response.created",
    "response.content_part.added",
    "response.content_part.done",
    "conversation.item.created",
    "response.audio.done",
    "session.created",
    "session.updated",
    "response.done",
    "response.output_item.done",
}


@asynccontextmanager
async def connect(*, api_key: str, model: str, url: str) -> AsyncGenerator[
    tuple[
        Callable[[dict[str, Any] | str], Coroutine[Any, Any, None]],
        AsyncIterator[dict[str, Any]],
    ],
    None,
]:
    """
    OpenAI Realtime API への websocket 接続を行うコンテキストマネージャ。
    戻り値: (send_event関数, 受信ストリーム)
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    url = url or DEFAULT_URL
    url += f"?model={model}"

    websocket = await websockets.connect(url, extra_headers=headers)

    try:
        async def send_event(event: dict[str, Any] | str) -> None:
            """
            dict あるいは str を送信。dict の場合は json.dumps して送る。
            """
            formatted_event = json.dumps(event) if isinstance(event, dict) else event
            await websocket.send(formatted_event)

        async def event_stream() -> AsyncIterator[dict[str, Any]]:
            """
            受信した JSON をパースして yield する。
            """
            async for raw_event in websocket:
                yield json.loads(raw_event)

        stream: AsyncIterator[dict[str, Any]] = event_stream()

        yield send_event, stream
    finally:
        await websocket.close()


class VoiceToolExecutor(BaseModel):
    """
    OpenAI Realtime API の function_call を受け取り、対応するツールを実行し、その結果をストリームで返す。
    """

    tools_by_name: dict[str, BaseTool]
    _trigger_future: asyncio.Future = PrivateAttr(default_factory=asyncio.Future)
    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    async def _trigger_func(self) -> dict:
        """
        set_result() が呼ばれるまで待機し、その後 tool_call を返す。
        """
        return await self._trigger_future

    async def add_tool_call(self, tool_call: dict) -> None:
        """
        model 側から受け取った function_call_arguments.done イベントをトリガーにツールを実行。
        """
        async with self._lock:
            if self._trigger_future.done():
                # 同時に複数のツールコールが来たときの簡易的な例外処理
                raise ValueError("Tool call adding already in progress")

            self._trigger_future.set_result(tool_call)

    async def _create_tool_call_task(self, tool_call: dict) -> asyncio.Task:
        """
        実際にツールを呼び出すためのタスクを作成し、結果をまとめて返す。
        """
        tool = self.tools_by_name.get(tool_call["name"])
        if tool is None:
            raise ValueError(
                f"tool {tool_call['name']} not found. "
                f"Must be one of {list(self.tools_by_name.keys())}"
            )

        # ツール用の引数を JSON デコード
        try:
            args = json.loads(tool_call["arguments"])
        except json.JSONDecodeError:
            raise ValueError(
                f"failed to parse arguments `{tool_call['arguments']}`. Must be valid JSON."
            )

        async def run_tool() -> dict:
            result = await tool.ainvoke(args)
            try:
                result_str = json.dumps(result)
            except TypeError:
                # JSON 変換できない場合は文字列化
                result_str = str(result)
            return {
                "type": "conversation.item.create",
                "item": {
                    "id": tool_call["call_id"],
                    "call_id": tool_call["call_id"],
                    "type": "function_call_output",
                    "output": result_str,
                },
            }

        task = asyncio.create_task(run_tool())
        return task

    async def output_iterator(self) -> AsyncIterator[dict]:
        """
        ツール実行結果のストリーム。
        """
        trigger_task = asyncio.create_task(self._trigger_func())
        tasks = set([trigger_task])

        while True:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                tasks.remove(task)
                # ツール呼び出しトリガー用タスクだった場合
                if task == trigger_task:
                    # 次のトリガーに備えて Future を再生成
                    async with self._lock:
                        self._trigger_future = asyncio.Future()
                    trigger_task = asyncio.create_task(self._trigger_func())
                    tasks.add(trigger_task)

                    tool_call = task.result()
                    try:
                        new_task = await self._create_tool_call_task(tool_call)
                        tasks.add(new_task)
                    except ValueError as e:
                        # エラーを会話に出す
                        yield {
                            "type": "conversation.item.create",
                            "item": {
                                "id": tool_call["call_id"],
                                "call_id": tool_call["call_id"],
                                "type": "function_call_output",
                                "output": (f"Error: {str(e)}"),
                            },
                        }
                else:
                    # ツール実行結果をそのまま返す
                    yield task.result()


@beta()
class OpenAIVoiceReactAgent(BaseModel):
    """
    OpenAI Realtime API を使った音声+ツール対応エージェント。
    さらにテキスト入力にも対応するように機能追加。
    """

    model: str
    api_key: SecretStr = Field(
        alias="openai_api_key",
        default_factory=secret_from_env("OPENAI_API_KEY", default=""),
    )
    instructions: str | None = None
    tools: list[BaseTool] | None = None
    url: str = Field(default=DEFAULT_URL)

    async def aconnect(
        self,
        input_stream: AsyncIterator[str],
        send_output_chunk: Callable[[str], Coroutine[Any, Any, None]],
    ) -> None:
        """
        Connect to the OpenAI API and send/receive messages (音声とテキストを入力ストリームから受け取り)。
        ツールコールもサポート。
        """
        tools_by_name = {tool.name: tool for tool in self.tools or []}
        tool_executor = VoiceToolExecutor(tools_by_name=tools_by_name)

        async with connect(
            model=self.model, api_key=self.api_key.get_secret_value(), url=self.url
        ) as (
            model_send,
            model_receive_stream,
        ):
            # セッション開始時にツールリストや命令(instructions)などを model に送る
            tool_defs = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {"type": "object", "properties": tool.args},
                }
                for tool in tools_by_name.values()
            ]

            await model_send(
                {
                    "type": "session.update",
                    "session": {
                        "instructions": self.instructions,
                        "input_audio_transcription": {
                            "model": "whisper-1",
                            # "language": "ja"  # 必要に応じて
                        },
                        "tools": tool_defs,
                    },
                }
            )

            # amerge で3つのストリームをまとめる
            # 1. input_mic=input_stream (音声 or テキスト)
            # 2. output_speaker=model_receive_stream (OpenAIからのレスポンス)
            # 3. tool_outputs=tool_executor.output_iterator() (ツール実行結果)
            async for stream_key, data_raw in amerge(
                input_mic=input_stream,
                output_speaker=model_receive_stream,
                tool_outputs=tool_executor.output_iterator(),
            ):
                # まず JSON デコードを試みる。失敗した場合は「生のテキスト入力」として処理する
                try:
                    data = (
                        json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                    )
                except json.JSONDecodeError:
                    # テキスト入力として解釈
                    print("Received raw text input:", data_raw)
                    data = {
                        "type": "conversation.item.create",
                        "item": {
                            "id": "text_input",
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": data_raw
                                }
                            ],
                        },
                    }
                    stream_key = "text"

                if stream_key == "input_mic":
                    # 音声/JSON イベントをそのまま model に転送
                    t = data["type"]
                    if t == "conversation.item.create":
                        print("conversation item create: ", data)
                    await model_send(data)

                elif stream_key == "text":
                    # 生テキスト入力を model 側に送る
                    print("Received text input => sending to model:", data)
                    await model_send(data)
                    await asyncio.sleep(0.1)

                    # テキストの応答を生成するように 'response.create' を送信する
                    event = {
                        "type": "response.create",
                        "response": {
                            "modalities": ["text"],
                            "instructions": "Please respond concisely."
                        }
                    }
                    print("Sending response.create for text input:", event)
                    await model_send(event)

                elif stream_key == "tool_outputs":
                    # ツール実行結果を model + クライアント両方へ返す
                    print("tool output:", data)
                    await model_send(data)

                    # ツール実行後に続きの応答をさせたい場合
                    await model_send({"type": "response.create", "response": {}})

                    # もしツールから "return_direct": True を含む出力があったら、
                    # そのままクライアントへ表示するなどのハンドリングが可能
                    t = data["type"]
                    if t == "conversation.item.create":
                        output_str = data["item"].get("output", "")
                        try:
                            output_json = json.loads(output_str)
                            if isinstance(output_json, dict):
                                return_direct = output_json.get("return_direct", False)
                                if return_direct:
                                    await send_output_chunk(output_str)
                        except Exception:
                            pass

                elif stream_key == "output_speaker":
                    # OpenAI からのレスポンスを処理
                    t = data["type"]
                    if t == "response.audio.delta":
                        # 音声ストリームをクライアントへ送る
                        await send_output_chunk(json.dumps(data))
                    elif t == "response.audio_buffer.speech_started":
                        # 音声の再生開始タイミング
                        await send_output_chunk(json.dumps(data))
                    elif t == "error":
                        print("error:", data)
                    elif t == "response.function_call_arguments.done":
                        # ツール呼び出しの最終引数が届いたらツールを実行
                        print("function_call:", data)
                        await tool_executor.add_tool_call(data)
                    elif t == "response.audio_transcript.done":
                        # Whisper(音声認識)が終わったとき
                        print("model(audio transcript):", data["transcript"])
                    elif t == "conversation.item.input_audio_transcription.completed":
                        # マイク入力が完了した時のトランスクリプト
                        print("user(audio):", data["transcript"])
                    elif t == "response.text.done":
                        # テキスト応答が完了したので、クライアントに送る
                        print("response.text.done:", data)
                        response_text = data.get("text", "")
                        await send_output_chunk(response_text)
                    elif t in EVENTS_TO_IGNORE:
                        # 何もしないイベント
                        pass
                    elif t == "input_audio_buffer.speech_started":
                        print("input_audio_buffer.speech_started",
                              "クライアント側で音声を中断などの処理を考慮可能")
                    else:
                        print("Unhandled event type:", t)

__all__ = ["OpenAIVoiceReactAgent"]