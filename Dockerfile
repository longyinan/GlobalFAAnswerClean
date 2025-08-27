# 公式のPythonランタイム（スリム版）を使用
FROM python:3.10-slim

# 作業ディレクトリを設定
WORKDIR /app

# プロジェクトファイルをコンテナにコピー
COPY . .

# 依存関係をインストール
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Cloud Runはポート8080での待ち受けを要求
EXPOSE 8080

# gunicornをWSGIサーバーとして使用（Cloud Runに最適）
CMD ["gunicorn", "--bind", ":8080", "--workers", "1", "--threads", "8", "app:app"]
