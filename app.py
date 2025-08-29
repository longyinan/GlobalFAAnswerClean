from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from google.cloud import storage
from io import BytesIO
import os
import tempfile
from process import process_csv_from_gcs
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "secret"

# GCS設定
GCS_BUCKET_NAME = "global-fa-answer-clean"  # バケット名
UPLOAD_FOLDER = "uploads"                   # アップロード先のフォルダ
OUTPUT_FOLDER = "outputs"                   # 処理結果の保存先フォルダ
DELETE_OLDER_THAN_DAYS = 1                  # 削除対象のファイルの経過日数

# GCSクライアント初期化
storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET_NAME)

# 削除対象のフォルダ一覧
FOLDERS = [UPLOAD_FOLDER, OUTPUT_FOLDER]


# 処理済みファイル一覧を取得
def list_processed_files():
    blobs = list(bucket.list_blobs(prefix=f"{OUTPUT_FOLDER}/"))
    result_files = [b for b in blobs if b.name.endswith("_result.csv")]

    results = []
    for result_blob in result_files:
        # アップロード元ファイル名を復元
        original_filename = result_blob.name.replace(f"{OUTPUT_FOLDER}/", "").replace("_result.csv", ".csv")
        input_blob_path = f"{UPLOAD_FOLDER}/{original_filename}"

        if bucket.blob(input_blob_path).exists():
            results.append({
                "filename": original_filename,
                "result_filename": result_blob.name,
                "updated": result_blob.updated
            })

    # 更新日時で降順ソート
    results.sort(key=lambda x: x["updated"], reverse=True)
    return results


# 古いファイルを削除するエンドポイント
@app.route("/clean", methods=["GET", "POST"])
def delete_old_files():
    if request.method == "GET":
        # GETアクセスには説明を返す
        return "このエンドポイントは POST メソッドでのみ使用してください。", 405

    # POST の場合、削除処理を実行
    cutoff = datetime.now(timezone.utc) - timedelta(days=DELETE_OLDER_THAN_DAYS)
    deleted_files = []

    for folder in FOLDERS:
        blobs = bucket.list_blobs(prefix=f"{folder}/")
        for blob in blobs:
            if blob.updated < cutoff:
                print(f"Deleting {blob.name} (updated: {blob.updated})")
                blob.delete()
                deleted_files.append(blob.name)

    return {
        "status": "success",
        "deleted_files": deleted_files
    }, 200


# メインページ（アップロード・結果表示）
@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded_file = request.files.get("file")
        if not uploaded_file:
            flash("ファイルが選択されていません。", "error")
            return redirect(url_for("index"))

        if not uploaded_file.filename.endswith(".csv"):
            flash("CSVファイルのみアップロード可能です。", "error")
            return redirect(url_for("index"))

        original_filename = uploaded_file.filename
        gcs_input_path = f"{UPLOAD_FOLDER}/{original_filename}"
        gcs_output_path = f"{OUTPUT_FOLDER}/{original_filename.replace('.csv', '_result.csv')}"

        # 一時ファイルとして保存し、GCSにアップロード
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            uploaded_file.save(tmp.name)
            blob = bucket.blob(gcs_input_path)
            blob.upload_from_filename(tmp.name, content_type="text/csv")

        try:
            # CSV処理関数の呼び出し
            process_csv_from_gcs(bucket, gcs_input_path, gcs_output_path)
            flash("回答データの処理が完了しました。", "success")
        except Exception as e:
            flash(f"処理中にエラーが発生しました: {e}", "error")

        return redirect(url_for("index"))

    # 処理済みファイルの一覧を表示
    results = list_processed_files()
    return render_template("index.html", results=results)


# ファイルダウンロード用エンドポイント
@app.route("/download/<path:filename>")
def download(filename):
    blob = bucket.blob(filename)
    if not blob.exists():
        return "ファイルが存在しません。", 404

    file_data = blob.download_as_bytes()
    return send_file(
        BytesIO(file_data),
        as_attachment=True,
        download_name=os.path.basename(filename),
        mimetype="text/csv"
    )


# Flaskアプリケーションの起動
if __name__ == "__main__":
    app.run(debug=True)
