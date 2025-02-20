# 環境変数の設定

**OPENAI_API_KEY** が設定されていること

設定を確認

```bash
echo $OPENAI_API_KEY
```

設定されていない場合には

```bash
export OPENAI_API_KEY="<your_actual_openai_api_key>"
```

# Dockerを起動して動作確認する場合

Dockerコンテナの作成

```bash
docker build -t my-realtime-chat .
```

コンテナを起動する

```bash
docker run --rm -p 3000:3000 --name chat-container --env OPENAI_API_KEY=$OPENAI_API_KEY my-realtime-chat
```

別のターミナルで **wscat** を使ってアプリの動作を確認する

```bash
wscat -c ws://localhost:3000/ws
```

出力例

```bash
Connected (press CTRL+C to quit)
> こんにちはChatGPT
< こんにちは！何かお手伝いできることはありますか？
> 私の名前はrairaiiです。あなたの名前は？
< 私の名前はChatGPTです。何かご質問やお話ししたいことがあれば、どうぞ教えてください。
> 私の名前わかりますか？
< あなたのお名前はrairaiiですね。どうぞよろしくお願いします。
> なぜおぼえているの？
< 会話の流れを理解し、適切に応答するために、先ほど教えていただいた情報を一時的に覚えています。会話が終了すると、情報は保持されませんのでご安心ください。
```

コンテナの終了

**Ctrl-C** で終了する。

Dockerプロセスが残っていないか確認

```
docker ps -a
```

明示的にKILL

```
docker kill chat-container
```


# ローカルで動作確認する場合

Pythonの仮想環境の起動

```bash
python3 -m venv .venv
source .venv/bin/activate 
```

必要なライブラリをインストール

```bash
pip install -r requirements.txt
```

アプリを起動する

```bash
python3 realtime_chat.py
```

別のターミナルで **wscat** を使ってアプリの動作を確認する

```bash
wscat -c ws://localhost:3000/ws
```

出力例

```bash
Connected (press CTRL+C to quit)
> Hello, ChatGPT!
< Hello! How can I help you today?
> I'm Rairaii. 
< Nice to meet you, Rairaii! What can I do for you today?
> Do you know my name?
< Yes, you mentioned that your name is Rairaii. How can I assist you today?
> Why do you remember my name?
< I remember it for our conversation context, to make our chat more personal and engaging. How can I assist you further?
```

Pythonの仮想環境を終了する

```bash
deactivate
```

