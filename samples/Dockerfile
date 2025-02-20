# Python 3.13 の軽量イメージを使用
FROM python:3.13-slim

# 環境変数の設定（出力をバッファリングしないように設定）
ENV PYTHONUNBUFFERED=1

# 作業ディレクトリを設定
WORKDIR /app

# 必要なパッケージをインストール
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 依存ライブラリをコピーしてインストール（キャッシュ最適化）
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# 環境変数を Docker 経由で設定できるようにする
ENV OPENAI_API_KEY=""

# ポート 3000 を公開
EXPOSE 3000

# アプリケーションの実行
CMD ["python3", "realtime_chat.py"]