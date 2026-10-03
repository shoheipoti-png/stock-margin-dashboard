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
    print("JPXからのデータ自動取得を開始します...")
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SPREADSHEET_ID")
    
    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(sheet_id).sheet1
    
    pdf_url = get_latest_pdf_url()
    pdf_res = requests.get(pdf_url)
    pdf_file = io.BytesIO(pdf_res.content)
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    new_rows = []
    
    print("PDFの解析を開始します...")
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text: continue
            
            for line in text.split('\n'):
                # 「株数 Shs.」の行だけをピンポイントで抽出
                if '株数 Shs.' in line:
                    # 銘柄コードの抽出
                    code_match = re.search(r'(?:^|\s)([A-Z0-9]{4})0\s', line)
                    if not code_match: continue
                    code = code_match.group(1)
                    
                    # 「株数 Shs.」以降の数値データ部分を切り出し
                    data_part = line.split('株数 Shs.')[1]
                    # ▲表記をマイナスに変換
                    data_part = data_part.replace('▲ ', '-').replace('▲', '-').replace(',', '')
                    tokens = data_part.split()
                    
                    # 正常にデータが並んでいれば13個の数値ブロックになる
                    if len(tokens) >= 12:
                        tot_sell = tokens[0]  # 売残高
                        gen_sell = tokens[3]  # 一般信用売
                        std_sell = tokens[5]  # 制度信用売
                        tot_buy  = tokens[7]  # 買残高
                        gen_buy  = tokens[9]  # 一般信用買
                        std_buy  = tokens[11] # 制度信用買
                        
                        new_rows.append([today_str, code, "-", tot_sell, gen_sell, std_sell, tot_buy, gen_buy, std_buy])

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "機関空売り増減", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = existing_data[1:] if existing_data and existing_data[0][0] == "日付" else []
    
    # 1年（365日）を過ぎたデータを自動削除
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=365)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(new_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print("スプレッドシートの更新が完了しました。")

if __name__ == "__main__":
    main()
