import csv
import json
import requests
from pathlib import Path
import time
from google.cloud import storage
from io import StringIO

MODEL = "models/gemini-2.5-flash-lite"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/{MODEL}:generateContent"

CONFIG = Path("config.ini")
PROMPT_FILE = Path("prompt.txt")

BATCH_SIZE = 2000  # バッチサイズ

def load_api_key() -> str:
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        if line.strip().lower().startswith("api_key"):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("config.ini に api_key が見つかりません")

def read_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8").strip()

def clean_to_csv(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("csv\n"):
            s = s[len("csv\n"):]
    lines = [ln.rstrip() for ln in s.splitlines() if ln.strip()]
    return "\n".join(lines)

def call_gemini(api_key: str, prompt_text: str, csv_chunk: str, want_header: bool) -> str:
    rules = f"""
あなたはCSVデータを処理するAIです。
1) 結果は必ずCSV形式で返してください。
2) {"最初のバッチはヘッダーを含める必要があります。" if want_header else "このバッチにはヘッダーを含めないでください。"}
3) 列の順番と数を維持してください。
4) 処理できない行があった場合、その行を返すが、該当する列は空にしてください。
""".strip()

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": rules},
                    {"text": prompt_text},
                    {"text": csv_chunk},
                ],
            }
        ]
    }

    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    resp = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=120)

    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API 呼び出し失敗: {resp.status_code}\n{resp.text}")

    data = resp.json()
    try:
        return clean_to_csv(data["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        raise RuntimeError(f"モデルからの結果解析失敗: {json.dumps(data, ensure_ascii=False)}")

def append_to_csv_text(existing_text: str, new_text: str, include_header: bool) -> str:
    if not new_text.strip():
        return existing_text

    existing_lines = existing_text.splitlines() if existing_text else []
    new_lines = new_text.splitlines()

    if existing_lines and not include_header:
        if new_lines[0].strip() == existing_lines[0].strip():
            new_lines = new_lines[1:]

    combined_lines = existing_lines + new_lines
    return "\n".join(combined_lines)

def process_csv_from_gcs(bucket, input_blob_name: str, output_blob_name: str):
    api_key = load_api_key()
    prompt_text = read_prompt()

    input_blob = bucket.blob(input_blob_name)
    if not input_blob.exists():
        raise FileNotFoundError(f"Input file {input_blob_name} not found in bucket")

    input_data = input_blob.download_as_text(encoding="utf-8")
    lines = input_data.splitlines()
    if not lines:
        raise ValueError("入力CSVファイルが空です")

    header = lines[0]
    data_rows = lines[1:]

    result_text = ""

    for i in range(0, len(data_rows), BATCH_SIZE):
        batch = data_rows[i:i + BATCH_SIZE]
        want_header = (i == 0)
        csv_text = "\n".join([header] + batch)
        try:
            result = call_gemini(api_key, prompt_text, csv_text, want_header)
            result_text = append_to_csv_text(result_text, result, want_header)
        except Exception as e:
            print(f"第 {i} - {i + len(batch)} 行の処理に失敗しました: {e}")
            time.sleep(1)

    output_blob = bucket.blob(output_blob_name)
    utf8_bom = "\ufeff"
    output_blob.upload_from_string(utf8_bom + result_text, content_type="text/csv")
