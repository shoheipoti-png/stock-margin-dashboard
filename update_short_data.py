import os
import json
import datetime
import re
import requests
from bs4 import BeautifulSoup
import urllib.parse
import io
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

JPX_SHORT_PAGE = "https://www.jpx.co.jp/markets/public/short-selling/index.html"

def get_latest_short_xls_url():
    """JPXの空売り公表ページから最新のShort_Positions.xlsのURLを取得"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    res = requests.get(JPX_SHORT_PAGE, headers=headers)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, 'html.parser')
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'short_positions.xls' in href.lower():
            return urllib.parse.urljoin(JPX_SHORT_PAGE, href)
    return None

def clean_code(val):
    if pd.isna(val):
        return None
    s = str(val).split('.')[0].strip()
    return s[:4] if len(s) >= 4 else s

def clean_int(val):
    if pd.isna(val):
        return 0
    s = str(val).replace(',', '').strip()
    try:
        return int(float(s))
    except ValueError:
        return 0

def clean_float(val):
    if pd.isna(val):
        return 0.0
    s = str(val).replace(',', '').replace('%', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0

def format_date(val):
    if pd.isna(val):
        return ""
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return s

def main():
    print("機関投資家空売りデータ取得を開始します...")
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SHORT_SPREADSHEET_ID")
    
    if not creds_json or not sheet_id:
        print("エラー: 認証情報 (GCP_SERVICE_ACCOUNT_KEY) または SHORT_SPREADSHEET_ID が設定されていません。")
        return

    # 1. Googleスプレッドシート接続
    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(sheet_id).sheet1
    print(f"接続シート: {client.open_by_key(sheet_id).title} / タブ: {worksheet.title}")

    # 2. 最新ファイルURL取得 & ダウンロード
    xls_url = get_latest_short_xls_url()
    if not xls_url:
        print("エラー: 最新の空売りXLSファイルが見つかりませんでした。")
        return
    print(f"対象XLS URL: {xls_url}")

    res = requests.get(xls_url)
    raw_df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')

    # 3. 公表年月日の取得 (Row 3, Col 2)
    raw_disc_date = raw_df.iloc[3, 2]
    disclosure_date = format_date(raw_disc_date)
    print(f"公表年月日: {disclosure_date}")
    if not disclosure_date:
        disclosure_date = datetime.date.today().strftime("%Y-%m-%d")

    # 4. データ行のパース (Row 7以降)
    # Col 1: 計算日, Col 2: コード, Col 3: 銘柄名, Col 5: 機関名, Col 10: 残高割合, Col 11: 数量(株数), Col 13: 直近計算日, Col 14: 直近割合
    data_df = raw_df.iloc[7:].copy()
    
    parsed_rows = []
    for _, row in data_df.iterrows():
        code = clean_code(row.iloc[2])
        if not code or not re.match(r'^\d{4}$', code):
            continue
            
        calc_date = format_date(row.iloc[1])
        name = str(row.iloc[3]).replace('\n', ' ').strip() if pd.notna(row.iloc[3]) else ""
        institution = str(row.iloc[5]).replace('\n', ' ').strip() if pd.notna(row.iloc[5]) else ""
        ratio = clean_float(row.iloc[10])
        shares = clean_int(row.iloc[11])
        prev_calc_date = format_date(row.iloc[13])
        prev_ratio = clean_float(row.iloc[14])

        parsed_rows.append([
            disclosure_date,
            calc_date,
            code,
            name,
            institution,
            ratio,
            shares,
            prev_calc_date,
            prev_ratio
        ])

    print(f"抽出データ件数: {len(parsed_rows)} 件")
    if not parsed_rows:
        print("抽出可能なデータがありませんでした。")
        return

    # 5. スプレッドシート既存データの取得と公表日ベースの上書きマージ
    headers = ["公表日", "計算年月日", "銘柄コード", "銘柄名", "機関名", "空売り残高割合", "空売り残高数量", "直近計算年月日", "直近空売り残高割合"]
    existing_data = worksheet.get_all_values()
    data_rows = []

    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "公表日":
        data_rows = existing_data[1:]

    # 今回の公表日と同じデータがあれば除外して最新に置換
    data_rows = [row for row in data_rows if len(row) > 0 and row[0] != disclosure_date]

    # 450日ローリング
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]

    filtered_rows.extend(parsed_rows)

    # 6. シートへ書き込み
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print(f"スプレッドシート更新完了: 公表日={disclosure_date}, 総行数={len(filtered_rows)} 件")

if __name__ == "__main__":
    main()
