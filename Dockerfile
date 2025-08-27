# 公式の Python ランタイム（軽量版）を使用
FROM python:3.10-slim

# ログをリアルタイムで出力するように設定
ENV PYTHONUNBUFFERED=1

# 作業ディレクトリを設定
WORKDIR /app

# プロジェクトファイルをコンテナにコピー
COPY . .

# パッケージをインストール（キャッシュを使わず軽量化）
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Cloud Run では 8080 ポートを使用
EXPOSE 8080

# gunicorn を使って Flask アプリを起動（Cloud Run 対応）
CMD ["gunicorn", "--bind", ":8080", "--workers", "1", "--threads", "8", "app:app"]
