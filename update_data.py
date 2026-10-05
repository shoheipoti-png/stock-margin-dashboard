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
    res = requests.get(JPX_URL)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '_mtall.pdf' in href:
            return href if href.startswith('http') else "https://www.jpx.co.jp" + href
    return None

def clean_value(val):
    if not val:
        return "0"
    v = val.replace(',', '').replace('▲', '-').strip()
    return v if v not in ['-', '*', ''] else "0"

def main():
    print("JPX個人信用データ取得（座標固定バケット方式）を開始します...")
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
    print(f"対象PDF: {pdf_url}")
    
    pdf_res = requests.get(pdf_url)
    pdf_file = io.BytesIO(pdf_res.content)
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    new_rows = []
    
    print("PDF解析開始...")
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            
            # 「Shs.」のアンカー単語を特定（Val.は無視）
            shs_anchors = [w for w in words if w["text"] == "Shs." and 220 < w["x0"] < 255]
            
            for anchor in shs_anchors:
                y = anchor["top"]
                # 同じ行（Y座標の差が±3以内）にある単語群を抽出
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
                    
                    # 銘柄コード (x: 170〜195)
                    if 170 <= x < 195 and re.match(r'^\d{4}[0A-Z]?$', text):
                        code = text[:4]
                    
                    # 数値のみ対象
                    clean_txt = clean_value(text)
                    if not re.match(r'^[\-\+]?\d+$', clean_txt):
                        continue
                        
                    # 売残(合計): 260〜300
                    if 260 <= x < 300:
                        tot_sell = clean_txt
                    # 買残(合計): 370〜415
                    elif 370 <= x < 415:
                        tot_buy = clean_txt
                    # 売残(一般): 485〜530
                    elif 485 <= x < 530:
                        gen_sell = clean_txt
                    # 売残(制度): 565〜610
                    elif 565 <= x < 610:
                        std_sell = clean_txt
                    # 買残(一般): 650〜695
                    elif 650 <= x < 695:
                        gen_buy = clean_txt
                    # 買残(制度): 730〜775
                    elif 730 <= x < 775:
                        std_buy = clean_txt
                
                if code:
                    new_rows.append([
                        today_str, code, tot_sell, gen_sell, std_sell,
                        tot_buy, gen_buy, std_buy
                    ])
                    
    print(f"抽出完了: {len(new_rows)} 銘柄")
    
    # スプレッドシート更新（450日ローリング）
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = []
    
    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "日付" and len(existing_data[0]) == len(headers):
        data_rows = existing_data[1:]
    
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(new_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print("スプレッドシート更新完了。")

if __name__ == "__main__":
    main()
