import os
import json
import datetime
import re
import requests
from bs4 import BeautifulSoup
import pdfplumber
import io
import gspread
from google.oauth2.service_account import Credentials

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"

# 定点監視用アンカー銘柄（これらの買残・売残が0になった場合は異常と判定）
ANCHOR_CODES = ["1570", "7011", "9432"]

def get_latest_pdf_url():
    """JPXのページから最新の銘柄別信用取引残高PDFのURLを取得"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(JPX_URL, headers=headers)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '_mtall.pdf' in href:
            return href if href.startswith('http') else "https://www.jpx.co.jp" + href
    return None

def clean_val(text):
    if not text:
        return 0
    v = str(text).replace(',', '').replace('▲', '').replace('-', '').replace('%', '').strip()
    try:
        return int(float(v))
    except Exception:
        return 0

def parse_row_numbers_grid(row_words):
    """
    特定された物理グリッド（X境界線）に基づき、各カラムを厳格に抽出
    """
    code = None
    raw_name = ""
    for w in sorted(row_words, key=lambda x: x["x0"]):
        t = w["text"].strip()
        if w["x0"] < 130:
            raw_name += t
        elif w["x0"] < 185 and not code:
            m = re.match(r'^([0-9A-Za-z]{4})[0A-Za-z]?$', t)
            if m:
                code = m.group(1).upper()

    if not code:
        return None, None, None

    def get_cell_val(x_start, x_end):
        for w in row_words:
            cx = (w["x0"] + w["x1"]) / 2.0
            if x_start <= cx < x_end:
                t = w["text"].strip()
                if "%" not in t and "▲" not in t and "-" not in t:
                    v = clean_val(t)
                    if v > 0:
                        return v
        return 0

    # 物理境界座標
    tot_sell = get_cell_val(185.0, 250.0)
    tot_buy  = get_cell_val(291.0, 363.6)
    gen_sell = get_cell_val(405.0, 477.2)
    std_sell = get_cell_val(477.2, 560.0)
    gen_buy  = get_cell_val(560.0, 684.2)
    std_buy  = get_cell_val(684.2, 808.4)

    # 数学的整合性チェック＆自動補正（合計 ＝ 一般 ＋ 制度）
    calc_tot_sell = gen_sell + std_sell
    calc_tot_buy  = gen_buy + std_buy

    if (tot_sell == 0 and calc_tot_sell > 0) or (abs(tot_sell - calc_tot_sell) > 100 and calc_tot_sell > 0):
        tot_sell = calc_tot_sell

    if (tot_buy == 0 and calc_tot_buy > 0) or (abs(tot_buy - calc_tot_buy) > 100 and calc_tot_buy > 0):
        tot_buy = calc_tot_buy

    return code, raw_name, (str(tot_sell), str(gen_sell), str(std_sell), str(tot_buy), str(gen_buy), str(std_buy))

def validate_extracted_data(rows_dict):
    """
    不測の事態・レイアウト変更を検知する多層バリデーション
    """
    total_count = len(rows_dict)
    print(f"=== バリデーション実行（抽出銘柄数: {total_count} 件）===")

    # 1. 抽出件数のしきい値チェック（通常3,800件前後）
    if total_count < 3500:
        raise ValueError(f"【重大アラート】抽出件数が異常に少なすぎます（{total_count} 件 < 3,500件）。PDFレイアウト変更の可能性があるため更新を中断します。")

    # 2. 定点監視アンカー銘柄の検証
    for acode in ANCHOR_CODES:
        if acode not in rows_dict:
            raise ValueError(f"【重大アラート】必須アンカー銘柄 [{acode}] が抽出データ内に存在しません。更新を中断します。")
        r = rows_dict[acode]
        buy_tot = int(r[5])
        if buy_tot == 0:
            raise ValueError(f"【重大アラート】主要アンカー銘柄 [{acode}] の買残合計が 0 です（大桁・レイアウトズレの疑い）。更新を中断します。")
        print(f"定点観測 [{acode}]: 売残合計={int(r[2]):,}株, 買残合計={buy_tot:,}株 (一般={int(r[6]):,}, 制度={int(r[7]):,}) -> 正常")

    # 3. 数学的整合性（合計＝一般＋制度）の違反率チェック
    mismatch_count = 0
    for r in rows_dict.values():
        if int(r[2]) != (int(r[3]) + int(r[4])) or int(r[5]) != (int(r[6]) + int(r[7])):
            mismatch_count += 1

    mismatch_rate = (mismatch_count / total_count) * 100
    print(f"整合性チェック不一致率: {mismatch_rate:.2f}% ({mismatch_count}/{total_count})")
    if mismatch_rate > 3.0:
        raise ValueError(f"【重大アラート】内訳整合性エラー率が許容値（3%）を超えています（{mismatch_rate:.2f}%）。カラム境界ズレの可能性があるため中断します。")

    print("=== 全バリデーション通過: データは極めて正常です ===")

def main():
    print("JPX個人信用データ取得（物理グリッド＆多層バリデーション版）を開始します...")
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SPREADSHEET_ID")
    
    if not creds_json or not sheet_id:
        raise ValueError("エラー: 認証情報またはシートIDが設定されていません。")

    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(sheet_id).sheet1
    
    pdf_url = get_latest_pdf_url()
    if not pdf_url:
        raise ValueError("エラー: PDF URLが取得できませんでした。")
    print(f"対象PDF URL: {pdf_url}")
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    pdf_res = requests.get(pdf_url, headers=headers)
    pdf_file = io.BytesIO(pdf_res.content)
    
    report_date = None
    
    # 1. 1ページ目から基準日を取得
    with pdfplumber.open(pdf_file) as pdf:
        p0_text = pdf.pages[0].extract_text() or ""
        date_match = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})\s*申込み現在', p0_text)
        if date_match:
            report_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
        else:
            match_kanji = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', p0_text)
            if match_kanji:
                report_date = f"{int(match_kanji.group(1)):04d}-{int(match_kanji.group(2)):02d}-{int(match_kanji.group(3)):02d}"
            else:
                report_date = datetime.date.today().strftime("%Y-%m-%d")
        print(f"★ 基準日: {report_date}")

    # 2. 既存データ（8列形式）の取得
    existing_data = worksheet.get_all_values()
    headers_row = ["日付", "銘柄コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = []
    
    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "日付":
        for r in existing_data[1:]:
            if len(r) >= 8:
                row_8 = [r[0], r[1], r[3], r[4], r[5], r[6], r[7], r[8]] if (len(r) >= 9 and not str(r[2]).replace('-', '').isdigit()) else r[:8]
                if row_8[0] != report_date:
                    data_rows.append(row_8)

    print("PDF解析を開始...")
    extracted_rows = {}
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            if not words:
                continue
            
            # 各銘柄行のアンカーとなる「株数」または「Shs.」を検出
            shs_anchors = [w for w in words if ("株数" in w["text"] or "Shs" in w["text"]) and 180 <= w["x0"] <= 260]
            
            for anchor in shs_anchors:
                y = (anchor["top"] + anchor["bottom"]) / 2.0
                row_words = [w for w in words if abs(((w["top"] + w["bottom"]) / 2.0) - y) <= 4.0]
                
                code, raw_name, values = parse_row_numbers_grid(row_words)
                if not code or not values:
                    continue
                
                # 【ETF・投信完全除外】1570（日経レバ）以外のETF・投信はスキップ
                if code != "1570":
                    if any(k in raw_name for k in ["投信", "ETF", "受益証券", "連動型", "上場投信"]):
                        continue
                
                tot_sell, gen_sell, std_sell, tot_buy, gen_buy, std_buy = values
                extracted_rows[code] = [
                    report_date, code, tot_sell, gen_sell, std_sell,
                    tot_buy, gen_buy, std_buy
                ]

    # 3. 異常検知バリデーション（異常があれば例外を投げて更新処理を完全停止）
    validate_extracted_data(extracted_rows)

    final_rows = list(extracted_rows.values())

    # 4. 450日ローリング更新
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(final_rows)
    
    print(f"スプレッドシート書き込み中（全 {len(filtered_rows)} レコード）...")
    worksheet.clear()
    worksheet.update('A1', [headers_row] + filtered_rows)
    print(f"スプレッドシート更新完了（基準日: {report_date} / 当日追加銘柄数: {len(final_rows)}）")

if __name__ == "__main__":
    main()
