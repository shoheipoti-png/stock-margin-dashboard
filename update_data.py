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
            if href.startswith('http'):
                return href
            else:
                return "https://www.jpx.co.jp" + href
    return None

def main():
    print("JPXからのデータ自動取得・更新処理を開始します...")
    
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SPREADSHEET_ID")
    if not creds_json or not sheet_id:
        print("エラー: 鍵またはシートIDが設定されていません。")
        return
        
    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1
    
    pdf_url = get_latest_pdf_url()
    if not pdf_url:
        print("エラー: JPXのページからPDFリンクが見つかりませんでした。")
        return
    print(f"対象PDF URL: {pdf_url}")
    
    pdf_res = requests.get(pdf_url)
    pdf_file = io.BytesIO(pdf_res.content)
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    new_rows = []
    
    print("PDFの解析を開始します...")
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text:
                continue
            
            for line in text.split('\n'):
                # 行の途中からでも「4桁数字+0 + 空白 + JP」の並びを確実に捉える
                match = re.search(r'(?:^|\s)(\d{4})0\s+JP', line)
                if match:
                    code = match.group(1) # 4桁の銘柄コードを取得
                    
                    # 証券コード以降の文字列から数値を抽出
                    after_code = line[match.end():]
                    blocks = after_code.split()
                    
                    nums = []
                    for b in blocks:
                        # カンマ削除、▲やA表記をマイナスに変換
                        clean_b = b.replace(',', '').replace('▲', '-').replace('A', '-')
                        # 整数にマッチするものだけ抽出
                        if re.match(r'^[\-\+]?\d+$', clean_b):
                            nums.append(clean_b)
                    
                    if len(nums) >= 2:
                        # JPXの構造上、最初に出てくる数値が売残合計
                        sell_bal = nums[0]
                        # 買残合計はデータ後半に出現するため、大まかに要素の中央以降から取得
                        buy_bal = nums[len(nums) // 2] if len(nums) >= 4 else nums[-1]
                        
                        new_rows.append([today_str, code, "-", sell_bal, buy_bal])

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    # スプレッドシートのローリング更新と見出し維持
    existing_data = worksheet.get_all_values()
    if not existing_data or existing_data[0][0] != "日付":
        headers = ["日付", "銘柄コード", "機関空売り増減", "個人信用売残", "個人信用買残"]
        data_rows = []
    else:
        headers = existing_data[0]
        data_rows = existing_data[1:]
    
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=370)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(new_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    
    print("スプレッドシートへの書き込みとローリング整理が完了しました。")

if __name__ == "__main__":
    main()
