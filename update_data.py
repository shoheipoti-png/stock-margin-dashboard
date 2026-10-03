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
        current_code = None
        tot_sell = None
        tot_buy = None
        
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text: continue
            
            for line in text.split('\n'):
                line = line.replace('▲ ', '-').replace('▲', '-').replace(',', '')
                
                # 1. 銘柄コードと「株数」の行を特定
                match = re.search(r'(?:^|\s)(\d{4})0\s+JP', line)
                if match:
                    current_code = match.group(1)
                    if 'Shs.' in line:
                        parts = line.split('Shs.')[-1].split()
                        nums = [p for p in parts if re.match(r'^[\-\+]?\d+$', p)]
                        if len(nums) >= 2:
                            tot_sell = nums[0]  # 左端が売残合計
                            tot_buy = nums[-2]  # 右から2番目が買残合計（一番右は前日比）
                    continue
                
                # 2. 金額の行は完全に無視
                if 'Val.' in line:
                    continue
                
                # 3. 内訳（一般・制度）の行の抽出
                if current_code and tot_sell and tot_buy:
                    parts = line.split()
                    nums = [p for p in parts if re.match(r'^[\-\+]?\d+$', p)]
                    
                    # 内訳行には0や数値が多数並ぶ
                    if len(nums) >= 6:
                        gen_sell = nums[0]
                        std_sell = nums[2] if len(nums) > 2 else "0"
                        gen_buy = nums[4] if len(nums) > 4 else "0"
                        std_buy = nums[6] if len(nums) > 6 else "0"
                        
                        new_rows.append([today_str, current_code, "-", tot_sell, gen_sell, std_sell, tot_buy, gen_buy, std_buy])
                        
                        # 次の銘柄に向けてリセット
                        current_code = None
                        tot_sell = None
                        tot_buy = None

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    existing_data = worksheet.get_all_values()
    if not existing_data or existing_data[0][0] != "日付":
        headers = ["日付", "銘柄コード", "機関空売り増減", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
        data_rows = []
    else:
        headers = existing_data[0]
        data_rows = existing_data[1:]
    
    # データ保持期間を1年（250営業日/365日）に設定し、容量オーバーを防止
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=365)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(new_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print("スプレッドシートへの書き込みとローリング整理が完了しました。")

if __name__ == "__main__":
    main()
