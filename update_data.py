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
    
    # 1. 秘密情報の読み込み
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SPREADSHEET_ID")
    if not creds_json or not sheet_id:
        print("エラー: 鍵またはシートIDが設定されていません。")
        return
        
    # 2. スプレッドシート接続
    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1
    
    # 3. 最新PDFのダウンロード
    pdf_url = get_latest_pdf_url()
    if not pdf_url:
        print("エラー: JPXのページからPDFリンクが見つかりませんでした。")
        return
    print(f"対象PDF URL: {pdf_url}")
    
    pdf_res = requests.get(pdf_url)
    pdf_file = io.BytesIO(pdf_res.content)
    
    # 4. PDFからのデータ抽出（pdfplumberによる解析）
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    new_rows = []
    
    print("PDFの解析を開始します...")
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            for line in lines:
                # PDF特有の表記揺れ（▲をマイナスに変換、空白を調整）
                line = line.replace('▲ ', '-').replace('▲', '-')
                parts = line.split()
                
                # 行の先頭が5桁の数字（銘柄コード＋末尾0）か判定
                if len(parts) > 5 and parts[0].isdigit() and len(parts[0]) == 5:
                    code = parts[0][:4] # 先頭4桁を銘柄コードとして取得
                    
                    # 行の後方から連続する数値ブロック（信用残データ）を抽出
                    nums = []
                    for p in reversed(parts):
                        if re.match(r'^[\-\+]?[0-9,]+$', p):
                            nums.append(p.replace(',', ''))
                        else:
                            break
                    nums.reverse()
                    
                    # 数値が8個以上並んでいれば、右から8番目が売残合計、4番目が買残合計
                    if len(nums) >= 8:
                        sell_bal = nums[-8]
                        buy_bal = nums[-4]
                        
                        # [日付, 銘柄コード, 機関空売り(未取得), 個人信用売残, 個人信用買残]
                        new_rows.append([today_str, code, "-", sell_bal, buy_bal])

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    # 5. スプレッドシートのローリング更新（1.5年＝約370日分を維持）
    existing_data = worksheet.get_all_values()
    headers = existing_data[0] if existing_data else ["日付", "銘柄コード", "機関空売り増減", "個人信用売残", "個人信用買残"]
    data_rows = existing_data[1:] if existing_data else []
    
    # 370日以上前の古いデータをフィルタリングして除外
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=370)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    
    # 新しいデータ（今日の分）を追加
    filtered_rows.extend(new_rows)
    
    # スプレッドシートを一度クリアし、最新状態で一括書き込み（処理速度とAPI制限対策）
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    
    print("スプレッドシートへの書き込みとローリング整理が完了しました。")

if __name__ == "__main__":
    main()
