from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from google.cloud import storage
from io import BytesIO
import os
import tempfile
from process import process_csv_from_gcs

app = Flask(__name__)
app.secret_key = "secret"

# GCSの設定
GCS_BUCKET_NAME = "your-gcs-bucket-name"  # ←ここを実際のバケット名に置き換えてください

# GCSクライアント作成
storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET_NAME)


def list_processed_files():
    """
    GCSバケットから処理済みの result ファイル一覧を取得し、
    元ファイル名と結果ファイル名のペアをリストで返す。
    例：data.csv → data_result.csv
    """
    blobs = bucket.list_blobs()
    results = []
    result_files = [blob.name for blob in blobs if blob.name.endswith("_result.csv")]

    for result_file in result_files:
        # 元のファイル名を復元
        if result_file.endswith("_result.csv"):
            original_filename = result_file[:-len("_result.csv")] + ".csv"
            # 確認用に元ファイルが存在するかチェック（あれば表示する）
            if bucket.blob(original_filename).exists():
                results.append({
                    "filename": original_filename,
                    "result_filename": result_file
                })
    # ソートして見やすく
    results.sort(key=lambda x: x["filename"])
    return results


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded_file = request.files.get("file")
        if not uploaded_file:
            flash("ファイルが選択されていません。", "error")
            return redirect(url_for("index"))

        if not uploaded_file.filename.endswith(".csv"):
            flash("CSVファイルのみアップロード可能です。", "error")
            return redirect(url_for("index"))

        # 一時ファイルとしてサーバに保存（GCSにアップロードのため）
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            uploaded_file.save(tmp.name)

            # GCSにアップロード
            blob = bucket.blob(uploaded_file.filename)
            blob.upload_from_filename(tmp.name, content_type="text/csv")

        flash("アップロード成功。処理を開始します。", "success")

        # 処理結果ファイル名
        result_filename = uploaded_file.filename.replace(".csv", "_result.csv")

        try:
            # GCS上のファイルを処理し、結果を同じバケットにアップロード
            process_csv_from_gcs(bucket, uploaded_file.filename, result_filename)
            flash("回答データを処理完了しました。", "success")
        except Exception as e:
            flash(f"処理中にエラーが発生しました: {e}", "error")

        return redirect(url_for("index"))

    # GET時は処理済みファイル一覧を取得して表示
    results = list_processed_files()

    return render_template("index.html", results=results)


@app.route("/download/<filename>")
def download(filename):
    blob = bucket.blob(filename)
    if not blob.exists():
        return "ファイルが存在しません。", 404

    # GCSからファイル内容をダウンロードし、Flaskのレスポンスで返す
    file_data = blob.download_as_bytes()
    return send_file(
        BytesIO(file_data),
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv"
    )


if __name__ == "__main__":
    # 環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されていることを確認してください
    app.run(debug=True)
