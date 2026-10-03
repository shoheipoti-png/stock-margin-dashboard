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
            # layout=True を指定し、PDFの見た目通りに空白（スペース）を維持してズレを防ぐ
            text = page.extract_text(layout=True)
            if not text:
                continue
            
            for line in text.split('\n'):
                # 先頭が5桁の数字（銘柄コード＋末尾0）で始まる行を対象
                match = re.match(r'^\s*(\d{5})\s', line)
                if match:
                    code = match.group(1)[:4] # 先頭4桁を銘柄コードとして取得
                    
                    # スペース2個以上を区切り文字として、列のブロックを正確に分割
                    blocks = re.split(r'\s{2,}', line.strip())
                    
                    # カンマ付きの数値をリスト化（▲表記はマイナスに変換）
                    nums = []
                    for b in blocks:
                        clean_b = b.replace(',', '').replace('▲', '-')
                        if re.match(r'^[\-\+]?\d+$', clean_b):
                            nums.append(clean_b)
                    
                    # JPXのフォーマットに合わせ、右側に配置される信用残データを取得
                    if len(nums) >= 2:
                        try:
                            # ※前日比（プラスマイナス）の有無で要素数が変わるため、後方から安全に取得
                            buy_bal = nums[-1] if len(nums) <= 2 else nums[-2]
                            sell_bal = nums[-2] if len(nums) <= 2 else nums[-4]
                            
                            new_rows.append([today_str, code, "-", sell_bal, buy_bal])
                        except Exception:
                            continue

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    # 5. スプレッドシートのローリング更新と見出しの自動修復
    existing_data = worksheet.get_all_values()
    
    # 1行目が見出し（"日付"）でない場合、手動テストデータで上書きされていると判断し強制リセット
    if not existing_data or existing_data[0][0] != "日付":
        headers = ["日付", "銘柄コード", "機関空売り増減", "個人信用売残", "個人信用買残"]
        data_rows = []
    else:
        headers = existing_data[0]
        data_rows = existing_data[1:]
    
    # 370日以上前の古いデータをフィルタリングして除外（ローリング処理）
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=370)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    
    # 新しいデータ（今日の分）を追加
    filtered_rows.extend(new_rows)
    
    # スプレッドシートを一度クリアし、最新状態で一括書き込み
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    
    print("スプレッドシートへの書き込みとローリング整理が完了しました。")

if __name__ == "__main__":
    main()
