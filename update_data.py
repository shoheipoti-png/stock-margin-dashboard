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
        if '_mtall.pdf' in a['href']:
            return a['href'] if a['href'].startswith('http') else "https://www.jpx.co.jp" + a['href']
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
        saved_line1 = {}
        
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text: continue
            
            for line in text.split('\n'):
                line = line.replace('▲ ', '-').replace('▲', '-').replace(',', '')
                
                # 1. 銘柄コードと株数(Shs.)の行を特定
                match = re.search(r'(?:^|\s)(\d{4})0\s+JP', line)
                if match:
                    if 'Shs.' in line:
                        current_code = match.group(1)
                        data_part = line.split('Shs.')[-1]
                        tokens = data_part.split()
                        # 数値またはハイフンのみを抽出 (比率の%を除外)
                        nums = [p for p in tokens if re.match(r'^[\-\+]?[0-9\.]+$', p) or p == '-']
                        if len(nums) >= 4:
                            saved_line1 = {
                                'tot_sell': nums[0],
                                'tot_sell_chg': nums[1],
                                'tot_buy': nums[-2],
                                'tot_buy_chg': nums[-1]
                            }
                    # 2. 金額(Val.)の行は完全に無視
                    continue
                
                # 3. 内訳（一般・制度）の行の抽出（コード取得の直後に出現）
                if current_code and saved_line1:
                    tokens = line.split()
                    nums = [p for p in tokens if re.match(r'^[\-\+]?[0-9\.]+$', p) or p == '-']
                    
                    if len(nums) >= 8:
                        gen_sell = nums[0]
                        std_sell = nums[2]
                        gen_buy = nums[4]
                        std_buy = nums[6]
                        
                        new_rows.append([
                            today_str, current_code, "-", 
                            saved_line1['tot_sell'], saved_line1['tot_sell_chg'], gen_sell, std_sell, 
                            saved_line1['tot_buy'], saved_line1['tot_buy_chg'], gen_buy, std_buy
                        ])
                        
                        # 次の銘柄のためにリセット
                        current_code = None
                        saved_line1 = {}

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    # スプレッドシートの更新（全11列）
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "機関空売り増減", "売残(合計)", "売残(前日比)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(前日比)", "買残(一般)", "買残(制度)"]
    data_rows = existing_data[1:] if existing_data and existing_data[0][0] == "日付" else []
    
    # 250営業日（約1年分）をローリング維持
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=250)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(new_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print("スプレッドシートの更新が完了しました。")

if __name__ == "__main__":
    main()
