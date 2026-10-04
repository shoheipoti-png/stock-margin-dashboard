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
    new_rows = []
    
    print("PDFの解析を開始します...")
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text: continue
            
            for line in text.split('\n'):
                # 金額行は無視し、「株数 Shs.」の行だけをターゲットにする
                if '株数 Shs.' not in line:
                    continue
                    
                # 銘柄コード（4桁＋0）を抽出
                code_match = re.search(r'(?:^|\s)([A-Z0-9]{4})0\s+JP', line)
                if not code_match: continue
                code = code_match.group(1)
                
                # 「株数 Shs.」以降のデータを切り出してクリーニング
                data_part = line.split('株数 Shs.')[1]
                data_part = data_part.replace('▲ ', '-').replace('▲', '-').replace(',', '')
                
                # ハイフンやアスタリスクは 0 に変換
                tokens = [t if t not in ['-', '*'] else '0' for t in data_part.split()]
                # 純粋な数値トークンのみを抽出
                nums = [t for t in tokens if re.match(r'^[\-\+]?\d+$', t)]
                
                # JPXの構造上、株数行には合計・一般・制度の数値が順番に並びます
                # 正常にすべての数値が揃っている行（通常12〜13個の数値ブロック）を対象にします
                if len(nums) >= 12:
                    try:
                        # 並び順の構造定義：
                        # [0]: 売残(合計)
                        # [3]: 売残(一般)
                        # [5]: 売残(制度)
                        # [7]: 買残(合計)
                        # [9]: 買残(一般)
                        # [11]: 買残(制度)
                        tot_sell = nums[0]
                        gen_sell = nums[3]
                        std_sell = nums[5]
                        tot_buy  = nums[7]
                        gen_buy  = nums[9]
                        std_buy  = nums[11]
                        
                        new_rows.append([
                            today_str, code, tot_sell, gen_sell, std_sell, 
                            tot_buy, gen_buy, std_buy
                        ])
                    except IndexError:
                        pass

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = []
    
    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "日付" and len(existing_data[0]) == len(headers):
        data_rows = existing_data[1:]
    
    # 450日ローリング処理
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(new_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print("スプレッドシートの更新が完了しました。")

if __name__ == "__main__":
    main()
