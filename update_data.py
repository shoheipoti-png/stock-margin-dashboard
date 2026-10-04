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

def main():
    print("JPXからの個人信用データ自動取得を開始します...")
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SPREADSHEET_ID")
    
    if not creds_json or not sheet_id:
        print("エラー: 認証情報またはシートIDがありません。")
        return

    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(sheet_id).sheet1
    
    pdf_url = get_latest_pdf_url()
    pdf_res = requests.get(pdf_url)
    pdf_file = io.BytesIO(pdf_res.content)
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    data_dict = {}
    
    print("PDFの解析を開始します...")
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text: continue
            
            is_total_page = "合計 Total" in text
            is_detail_page = "一般信用" in text and "制度信用" in text
            
            for line in text.split('\n'):
                if '株数 Shs.' not in line:
                    continue
                    
                code_match = re.search(r'(?:^|\s)([A-Z0-9]{4})0\s+JP', line)
                if not code_match: continue
                code = code_match.group(1)
                
                data_part = line.split('株数 Shs.')[1]
                data_part = data_part.replace('▲ ', '-').replace('▲', '-').replace(',', '')
                
                tokens = [t if t not in ['-', '*'] else '0' for t in data_part.split()]
                
                if code not in data_dict:
                    data_dict[code] = {"tot_sell": "0", "tot_buy": "0", "gen_sell": "0", "std_sell": "0", "gen_buy": "0", "std_buy": "0"}
                
                if is_total_page and len(tokens) >= 4:
                    try:
                        data_dict[code]["tot_sell"] = tokens[0]
                        data_dict[code]["tot_buy"] = tokens[3]
                    except IndexError:
                        pass
                        
                elif is_detail_page and len(tokens) >= 7:
                    try:
                        data_dict[code]["gen_sell"] = tokens[0]
                        data_dict[code]["std_sell"] = tokens[2]
                        data_dict[code]["gen_buy"]  = tokens[4]
                        data_dict[code]["std_buy"]  = tokens[6]
                    except IndexError:
                        pass

    new_rows = []
    for code, vals in data_dict.items():
        new_rows.append([
            today_str, code, vals["tot_sell"], vals["gen_sell"], vals["std_sell"], 
            vals["tot_buy"], vals["gen_buy"], vals["std_buy"]
        ])

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = []
    
    # 【修正箇所】「完全に空の行」が存在してもエラーで落ちないよう、長さ（len）を厳密にチェック
    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "日付" and len(existing_data[0]) == len(headers):
        data_rows = existing_data[1:]
    
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(new_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print("スプレッドシートの更新が完了しました。")

if __name__ == "__main__":
    main()
