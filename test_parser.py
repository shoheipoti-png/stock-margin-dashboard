import os
import re
import json
import requests
import pdfplumber
import gspread
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# -------------------------------------------------------------------
# テスト専用設定
# -------------------------------------------------------------------
TEST_SPREADSHEET_ID = "1jHWbC62ZVRXOcgOaF5Tmn6FQEsERx7LVZUOmOuh-6fM"
BASE_URL = "https://www.jpx.co.jp"
TARGET_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"

def get_latest_pdf_url():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(TARGET_PAGE_URL, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    
    for a in soup.find_all("a", href=True):
        if "mtall.pdf" in a["href"]:
            return urljoin(BASE_URL, a["href"])
    raise ValueError("PDFリンクが見つかりませんでした。")

def clean_val(text):
    if not text:
        return 0
    clean = re.sub(r"[,\s]", "", text)
    if clean.isdigit():
        return int(clean)
    return 0

def parse_pdf_grid(pdf_path):
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

            # 1. 銘柄コード（x0が110〜180の間にある4桁英数字）を検出して行アンカーとする
            # ヘッダー領域（top < 70）は除外して誤認を防止
            code_words = []
            for w in words:
                if w["top"] >= 70 and 110 <= w["x0"] < 185:
                    t = w["text"].strip()
                    m = re.match(r"^(\d{4}|\d{3}[A-Z])$", t)
                    if m:
                        code_words.append({
                            "code": m.group(1),
                            "top": w["top"],
                            "bottom": w["bottom"]
                        })

            if not code_words:
                continue

            # Y座標（上から下）へソート
            code_words = sorted(code_words, key=lambda x: x["top"])

            # 2. 各銘柄行のY範囲を決定して、特定された物理グリッド枠から数値を抽出
            for i, c_info in enumerate(code_words):
                code = c_info["code"]
                y_top = c_info["top"] - 3.0
                if i + 1 < len(code_words):
                    y_bottom = code_words[i+1]["top"] - 3.0
                else:
                    y_bottom = c_info["bottom"] + 15.0

                # 行内の単語を取得
                row_words = [w for w in words if y_top <= w["top"] < y_bottom and w["x0"] >= 185]

                # 物理境界に基づくカラム別仕分け
                # 各単語の中心X座標 (x0 + x1)/2 を用いて所属セルを厳密判定
                def get_cell_val(x_start, x_end):
                    tokens = []
                    for w in row_words:
                        cx = (w["x0"] + w["x1"]) / 2.0
                        if x_start <= cx < x_end:
                            t = w["text"].strip()
                            if "%" not in t and "▲" not in t and "-" not in t:
                                v = clean_val(t)
                                if v > 0:
                                    tokens.append(v)
                    return tokens[0] if tokens else 0

                # 物理境界座標:
                # 193.3〜250.0: 売残合計
                # 291.4〜363.6: 買残合計
                # 405.0〜477.2: 売残一般
                # 477.2〜560.0: 売残制度
                # 560.0〜684.2: 買残一般
                # 684.2〜808.4: 買残制度
                tot_sell = get_cell_val(185.0, 250.0)
                tot_buy  = get_cell_val(290.0, 363.6)
                gen_sell = get_cell_val(405.0, 477.2)
                std_sell = get_cell_val(477.2, 560.0)
                gen_buy  = get_cell_val(560.0, 684.2)
                std_buy  = get_cell_val(684.2, 808.4)

                # 数学的自己修復（内訳合計との整合性担保）
                calc_tot_sell = gen_sell + std_sell
                if (tot_sell == 0 and calc_tot_sell > 0) or (abs(tot_sell - calc_tot_sell) > 100 and calc_tot_sell > 0):
                    tot_sell = calc_tot_sell

                calc_tot_buy = gen_buy + std_buy
                if (tot_buy == 0 and calc_tot_buy > 0) or (abs(tot_buy - calc_tot_buy) > 100 and calc_tot_buy > 0):
                    tot_buy = calc_tot_buy

                data.append({
                    "code": code,
                    "sell_total": tot_sell,
                    "sell_general": gen_sell,
                    "sell_standard": std_sell,
                    "buy_total": tot_buy,
                    "buy_general": gen_buy,
                    "buy_standard": std_buy
                })

    return report_date, data

def update_test_sheet(report_date, records):
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

    print(f"テスト用シートへ全 {len(rows)-1} 件のデータを書き込み中...")
    sheet.clear()
    sheet.update(range_name="A1", values=rows)
    print("テスト用スプレッドシートの更新が完了しました！")

def main():
    print("=== 物理グリッド方式パーサー実行開始 ===")
    pdf_url = get_latest_pdf_url()
    print(f"PDFダウンロード中: {pdf_url}")
    
    local_pdf = "latest_test.pdf"
    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with open(local_pdf, "wb") as f:
        f.write(res.content)

    print("PDFパース中（物理境界セル抽出）...")
    report_date, records = parse_pdf_grid(local_pdf)
    print(f"申込日: {report_date}, 抽出件数: {len(records)} 件")

    # 主要銘柄の抽出確認ログ
    for r in records:
        if r["code"] in ["285A", "9432", "7011", "6526", "1301", "7203"]:
            print(f"検証ログ [{r['code']}]: 売残合計={r['sell_total']:,}, 買残合計={r['buy_total']:,} (一般={r['buy_general']:,}, 制度={r['buy_standard']:,})")

    update_test_sheet(report_date, records)
    print("=== テスト完了 ===")

if __name__ == "__main__":
    main()
