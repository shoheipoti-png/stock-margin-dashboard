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
    print("JPX個人信用データ取得（検証済み確実版）を開始します...")
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
    new_rows = []
    
    with pdfplumber.open(pdf_file) as pdf:
        # 1. 1ページ目から正式な「申込み現在日」を正確に抽出
        p0_text = pdf.pages[0].extract_text()
        date_match = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})\s*申込み現在', p0_text)
        if date_match:
            report_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
            print(f"★ 抽出された基準日: {report_date}")
        else:
            report_date = datetime.date.today().strftime("%Y-%m-%d")
            print(f"警告: 基準日が見つからないため当日日付を代用: {report_date}")

        # 2. 全ページの「Shs.」行から座標バケットに基づいて全データを正確に抽出
        for page_idx, page in enumerate(pdf.pages):
            words = page.extract_words()
            if not words:
                continue
            
            # テストで確認できた「Shs.」アンカー
            shs_anchors = [w for w in words if w["text"] == "Shs." and 220 <= w["x0"] <= 255]
            
            for anchor in shs_anchors:
                y = anchor["top"]
                row_words = [w for w in words if abs(w["top"] - y) <= 3]
                
                code = None
                tot_sell = "0"
                tot_buy = "0"
                gen_sell = "0"
                std_sell = "0"
                gen_buy = "0"
                std_buy = "0"
                
                for w in row_words:
                    x = w["x0"]
                    text = w["text"]
                    
                    # 銘柄コード (x0: 170〜195)
                    if 170 <= x < 195 and re.match(r'^\d{4}[0A-Z]?$', text):
                        code = text[:4]
                        continue
                    
                    cleaned = clean_val(text)
                    if not re.match(r'^[\-\+]?\d+$', cleaned):
                        continue
                        
                    # 検証済みのX座標バケットによる項目判定
                    if 260 <= x < 310:
                        tot_sell = cleaned
                    elif 370 <= x < 420:
                        tot_buy = cleaned
                    elif 490 <= x < 540:
                        gen_sell = cleaned
                    elif 570 <= x < 620:
                        std_sell = cleaned
                    elif 650 <= x < 700:
                        gen_buy = cleaned
                    elif 730 <= x < 780:
                        std_buy = cleaned
                
                if code:
                    new_rows.append([
                        report_date, code, tot_sell, gen_sell, std_sell,
                        tot_buy, gen_buy, std_buy
                    ])
                    
    print(f"抽出完了: {len(new_rows)} 銘柄")
    
    # 3. 重複の排除
    unique_rows = {}
    for r in new_rows:
        unique_rows[r[1]] = r
    final_rows = list(unique_rows.values())

    # 4. スプレッドシートの更新（同基準日のデータがある場合は置換し、450日ローリングを適用）
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = []
    
    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "日付" and len(existing_data[0]) == len(headers):
        data_rows = existing_data[1:]
    
    # 今回取得する基準日と一致する既存データがあれば一掃して上書き
    data_rows = [row for row in data_rows if len(row) > 0 and row[0] != report_date]
    
    # 450日ローリング削除
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    
    filtered_rows.extend(final_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print(f"スプレッドシート更新完了（基準日: {report_date} / 書き込み件数: {len(final_rows)} 銘柄）")

if __name__ == "__main__":
    main()
