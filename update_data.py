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

def get_latest_pdf_url():
    """JPXのページから最新の銘柄別信用取引残高PDFのURLを取得"""
    res = requests.get(JPX_URL)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '_mtall.pdf' in href:
            return href if href.startswith('http') else "https://www.jpx.co.jp" + href
    return None

def clean_val(text):
    if not text:
        return "0"
    v = str(text).replace(',', '').replace('▲', '-').strip()
    return v if v not in ['-', '*', ''] else "0"

def main():
    print("JPX個人信用データ取得（軽量8列・ETF除外・英字コード対応版）を開始します...")
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SPREADSHEET_ID")
    
    if not creds_json or not sheet_id:
        print("エラー: 認証情報またはシートIDが設定されていません。")
        return

    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(sheet_id).sheet1
    
    pdf_url = get_latest_pdf_url()
    if not pdf_url:
        print("エラー: PDF URLが取得できませんでした。")
        return
    print(f"対象PDF URL: {pdf_url}")
    
    pdf_res = requests.get(pdf_url)
    pdf_file = io.BytesIO(pdf_res.content)
    
    report_date = None
    
    # 1. 1ページ目から基準日を取得
    with pdfplumber.open(pdf_file) as pdf:
        p0_text = pdf.pages[0].extract_text()
        date_match = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})\s*申込み現在', p0_text)
        if date_match:
            report_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
            print(f"★ 基準日: {report_date}")
        else:
            report_date = datetime.date.today().strftime("%Y-%m-%d")

    # 2. 既存データ（8列形式）の取得
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = []
    
    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "日付":
        # 過去データから同日を除外して読み込み
        for r in existing_data[1:]:
            if len(r) >= 8:
                # 銘柄名列が入ってしまっている9列データがある場合はスキップ/補正
                if len(r) >= 9 and not str(r[2]).replace('-', '').isdigit():
                    row_8 = [r[0], r[1], r[3], r[4], r[5], r[6], r[7], r[8]]
                else:
                    row_8 = r[:8]
                if row_8[0] != report_date:
                    data_rows.append(row_8)

    print("PDF解析を開始...")
    new_rows = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            
            shs_anchors = [w for w in words if w["text"] == "Shs." and 220 <= w["x0"] <= 255]
            
            for anchor in shs_anchors:
                y = anchor["top"]
                row_words = [w for w in words if abs(w["top"] - y) <= 3]
                
                code = None
                raw_name = ""
                tot_sell, gen_sell, std_sell = "0", "0", "0"
                tot_buy, gen_buy, std_buy = "0", "0", "0"
                
                for w in row_words:
                    x = w["x0"]
                    text = w["text"]
                    
                    if x < 170:
                        raw_name += text
                        continue
                    
                    # 英数字4文字（285A含む）に対応
                    if 170 <= x < 210 and re.match(r'^[0-9A-Za-z]{4}[0A-Za-z]?$', text):
                        code = text[:4].upper()
                        continue
                    
                    cleaned = clean_val(text)
                    if not re.match(r'^[\-\+]?\d+$', cleaned):
                        continue
                        
                    if 260 <= x < 310: tot_sell = cleaned
                    elif 370 <= x < 420: tot_buy = cleaned
                    elif 490 <= x < 540: gen_sell = cleaned
                    elif 570 <= x < 620: std_sell = cleaned
                    elif 650 <= x < 700: gen_buy = cleaned
                    elif 730 <= x < 780: std_buy = cleaned
                
                if code:
                    # 【ETF・投信完全除外】1570以外はスキップ
                    if code != "1570" and any(k in raw_name for k in ["投信", "ETF", "受益証券", "連動型", "上場投信"]):
                        continue
                        
                    new_rows.append([
                        report_date, code, tot_sell, gen_sell, std_sell,
                        tot_buy, gen_buy, std_buy
                    ])
                    
    print(f"抽出完了（ETF除外後）: {len(new_rows)} 銘柄")
    
    unique_rows = {}
    for r in new_rows:
        unique_rows[r[1]] = r
    final_rows = list(unique_rows.values())

    # 3. 450日ローリング
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(final_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print(f"スプレッドシート更新完了（基準日: {report_date} / 行数: {len(final_rows)}）")

if __name__ == "__main__":
    main()
