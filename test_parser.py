import os
import re
import json
import requests
import pdfplumber
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# -------------------------------------------------------------------
# テスト専用設定（本番環境には一切影響しません）
# -------------------------------------------------------------------
TEST_SPREADSHEET_ID = "1jHWbC62ZVRXOcgOaF5Tmn6FQEsERx7LVZUOmOuh-6fM"
BASE_URL = "https://www.jpx.co.jp"
TARGET_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"

def get_latest_pdf_url():
    """JPXサイトから最新の信用取引残高PDFのURLを取得"""
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(TARGET_PAGE_URL, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    
    pdf_link = None
    for a in soup.find_all("a", href=True):
        if "mtall.pdf" in a["href"]:
            pdf_link = urljoin(BASE_URL, a["href"])
            break
            
    if not pdf_link:
        raise ValueError("最新の信用取引残高PDF（mtall.pdf）が見つかりませんでした。")
    return pdf_link

def clean_val(text):
    """カンマや記号を除去して数値に変換"""
    if not text:
        return 0
    clean = re.sub(r"[,\s]", "", text)
    if clean.isdigit():
        return int(clean)
    return 0

def parse_pdf_enhanced(pdf_path):
    """
    大桁銘柄・巨大前日比に対応した全ページ強化型パースロジック
    """
    data = []
    report_date = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            if not words:
                continue

            # 申込現在日の取得
            if not report_date:
                full_text = page.extract_text() or ""
                match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", full_text)
                if match:
                    y, m, d = match.groups()
                    report_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                else:
                    match_slash = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", full_text)
                    if match_slash:
                        y, m, d = match_slash.groups()
                        report_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

            # Y座標ごとにテキストをグループ化（行の再構築）
            rows = {}
            for w in words:
                top_key = round(w["top"], 1)
                matched_key = None
                for k in rows.keys():
                    if abs(k - top_key) <= 3.0:
                        matched_key = k
                        break
                if matched_key is None:
                    matched_key = top_key
                    rows[matched_key] = []
                rows[matched_key].append(w)

            # 各行の解析
            for y_coord, row_words in sorted(rows.items(), key=lambda x: x[0]):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                
                # 銘柄コード（4桁数字または数字3桁+英字1文字）の検出
                # ※表の左端付近（x0 < 130）に存在するコードを確実に捕捉
                code_word = None
                code_idx = -1
                for idx, w in enumerate(row_words):
                    text = w["text"].strip()
                    if w["x0"] < 130 and re.match(r"^(\d{4}|\d{3}[A-Z])$", text):
                        code_word = text
                        code_idx = idx
                        break
                
                if not code_word:
                    continue

                # 銘柄コード以降のトークンを解析
                tokens_after = row_words[code_idx + 1:]
                
                # 前日比の▲記号を事前判定
                num_tokens = []
                for w in tokens_after:
                    t = w["text"].strip()
                    if re.search(r"\d", t) and "%" not in t:
                        is_diff = ("▲" in t) or ("-" in t and not t.isdigit())
                        num_tokens.append({
                            "text": t,
                            "x0": w["x0"],
                            "x1": w["x1"],
                            "is_diff": is_diff,
                            "val": clean_val(t)
                        })

                # 残高列のみを対象（前日比を除外）
                balance_tokens = [tok for tok in num_tokens if not tok["is_diff"]]

                # 各カラムの帯域（JPXレイアウト完全対応）
                # 1. 売残 合計 (x0: 170〜280)
                tot_sell_cands = [tok["val"] for tok in balance_tokens if 170 <= tok["x0"] < 280]
                tot_sell = tot_sell_cands[0] if tot_sell_cands else 0

                # 2. 売残 一般 (x0: 380〜460)
                gen_sell_cands = [tok["val"] for tok in balance_tokens if 380 <= tok["x0"] < 460]
                gen_sell = gen_sell_cands[0] if gen_sell_cands else 0

                # 3. 売残 制度 (x0: 480〜560)
                std_sell_cands = [tok["val"] for tok in balance_tokens if 480 <= tok["x0"] < 560]
                std_sell = std_sell_cands[0] if std_sell_cands else 0

                # 4. 買残 合計 (x0: 270〜390：大桁銘柄のはみ出しにも完全対応)
                tot_buy_cands = [tok["val"] for tok in balance_tokens if 270 <= tok["x0"] < 390]
                tot_buy = tot_buy_cands[0] if tot_buy_cands else 0

                # 5. 買残 一般 (x0: 580〜680)
                gen_buy_cands = [tok["val"] for tok in balance_tokens if 580 <= tok["x0"] < 680]
                gen_buy = gen_buy_cands[0] if gen_buy_cands else 0

                # 6. 買残 制度 (x0: 700〜810)
                std_buy_cands = [tok["val"] for tok in balance_tokens if 700 <= tok["x0"] < 810]
                std_buy = std_buy_cands[0] if std_buy_cands else 0

                # 数学的自己検証・修復
                calc_tot_sell = gen_sell + std_sell
                if (tot_sell == 0 and calc_tot_sell > 0) or (abs(tot_sell - calc_tot_sell) > 100 and calc_tot_sell > 0):
                    tot_sell = calc_tot_sell

                calc_tot_buy = gen_buy + std_buy
                if (tot_buy == 0 and calc_tot_buy > 0) or (abs(tot_buy - calc_tot_buy) > 100 and calc_tot_buy > 0):
                    tot_buy = calc_tot_buy

                data.append({
                    "code": code_word,
                    "sell_total": tot_sell,
                    "sell_general": gen_sell,
                    "sell_standard": std_sell,
                    "buy_total": tot_buy,
                    "buy_general": gen_buy,
                    "buy_standard": std_buy
                })

    return report_date, data

def update_test_sheet(report_date, records):
    """テスト用スプレッドシートへ書き込み"""
    sa_key_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    if not sa_key_json:
        raise ValueError("環境変数 GCP_SERVICE_ACCOUNT_KEY が設定されていません。")

    creds_dict = json.loads(sa_key_json)
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(credentials)

    sheet = client.open_by_key(TEST_SPREADSHEET_ID).sheet1

    header = ["日付", "コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    
    rows = [header]
    for r in records:
        rows.append([
            report_date,
            r["code"],
            r["sell_total"],
            r["sell_general"],
            r["sell_standard"],
            r["buy_total"],
            r["buy_general"],
            r["buy_standard"]
        ])

    print(f"テスト用シートをクリアして全 {len(rows)-1} 件のデータを書き込み中...")
    sheet.clear()
    sheet.update(range_name="A1", values=rows)
    print("テスト用スプレッドシートの更新が完了しました！")

def main():
    print("=== テスト用パーサー実行開始 ===")
    pdf_url = get_latest_pdf_url()
    print(f"PDFダウンロード中: {pdf_url}")
    
    local_pdf = "latest_test.pdf"
    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    with open(local_pdf, "wb") as f:
        f.write(res.content)

    print("PDFパース中（全ページ強化型ロジック適用）...")
    report_date, records = parse_pdf_enhanced(local_pdf)
    print(f"申込日: {report_date}, 抽出件数: {len(records)} 件")

    # 主要銘柄の抽出確認
    for r in records:
        if r["code"] in ["285A", "9432", "7011", "6526"]:
            print(f"検証ログ [{r['code']}]: 売残合計={r['sell_total']:,}, 買残合計={r['buy_total']:,} (一般={r['buy_general']:,}, 制度={r['buy_standard']:,})")

    # テスト用スプレッドシートへ書き込み
    update_test_sheet(report_date, records)
    print("=== テスト完了 ===")

if __name__ == "__main__":
    main()
