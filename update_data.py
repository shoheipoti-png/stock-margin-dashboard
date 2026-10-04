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
            return href if href.startswith('http') else "https://www.jpx.co.jp" + href
    return None

def main():
    print("JPXからの個人信用データ自動取得（テーブル解析版）を開始します...")
    
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
    if not pdf_url:
        print("エラー: PDFのURLが見つかりませんでした。")
        return
        
    print(f"対象PDF URL: {pdf_url}")
    pdf_res = requests.get(pdf_url)
    pdf_file = io.BytesIO(pdf_res.content)
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    new_rows = []
    
    print("PDFのテーブル解析を開始します...")
    with pdfplumber.open(pdf_file) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            # ページからテーブル（表データ）を直接抽出
            table = page.extract_table()
            if not table:
                continue
            
            for row in table:
                # 行の中にデータが存在するか確認
                if not row or len(row) < 5:
                    continue
                
                # 文字列を結合して、金額行（Val.）やヘッダー行が含まれていないかチェック
                row_str = " ".join([str(cell) for cell in row if cell])
                
                # 金額行（Val.）やヘッダー、株数以外の行はスキップ
                if "Val." in row_str or "銘柄" in row_str or "残高" in row_str:
                    continue
                
                # 銘柄コード（4桁の数字）をセルの中から探す
                code = None
                for cell in row:
                    if cell:
                        # 4桁の数字、または後ろに0や英字が続くパターン（例: 13010, 130A）を検出
                        match = re.search(r'\b(\d{4}[0A-Z])\b', str(cell))
                        if match:
                            code = match.group(1)[:4]
                            break
                
                if not code:
                    continue
                
                # 表のセルから数値を安全にクリーニングして抽出する関数
                def clean_num(val):
                    if not val:
                        return "0"
                    cleaned = str(val).replace(',', '').replace('▲', '-').replace('▲ ', '-').strip()
                    if cleaned in ["-", "*", ""]:
                        return "0"
                    # 数字のみ（マイナスや小数含む）抽出
                    match = re.search(r'[\-\+]?\d+', cleaned)
                    return match.group(0) if match else "0"

                # JPXのテーブル列構造に基づき、各セルからデータを取得
                # （表の列インデックスがページによって若干ずれるのを防ぐため、有効な数値を後ろから順に安全に取得）
                row_nums = [clean_num(c) for c in row if c and re.search(r'[\d\-\▲]', str(c))]
                
                if len(row_nums) >= 6:
                    try:
                        # テーブル構造に基づいた正確な配置：
                        # 売残(合計), 売残(一般), 売残(制度), 買残(合計), 買残(一般), 買残(制度)
                        # ※JPXの表は「売残高に関する列」と「買残高に関する列」が横に並んでいます
                        
                        # 数字列の中から株数データに該当するものをマッピング
                        # 一般的に、行の数値ブロックの後方にある大きめの数値群が残高データになります
                        nums_only = [n for n in row_nums if not n.startswith('0.') and len(n) > 0] # パーセンテージ等を除外
                        
                        if len(nums_only) >= 6:
                            # JPXのテーブル形式における標準的な位置関係から安全に取得
                            tot_sell = nums_only[1] if len(nums_only) > 1 else "0"
                            gen_sell = nums_only[3] if len(nums_only) > 3 else "0"
                            std_sell = nums_only[4] if len(nums_only) > 4 else "0"
                            
                            tot_buy  = nums_only[2] if len(nums_only) > 2 else "0"
                            gen_buy  = nums_only[5] if len(nums_only) > 5 else "0"
                            std_buy  = nums_only[6] if len(nums_only) > 6 else "0"
                            
                            new_rows.append([
                                today_str, code, tot_sell, gen_sell, std_sell, 
                                tot_buy, gen_buy, std_buy
                            ])
                    except Exception:
                        continue

    print(f"{len(new_rows)} 銘柄分のデータを抽出しました。")
    
    # 重複データの排除（同じコードが複数回入らないように最新を優先）
    unique_rows = {}
    for r in new_rows:
        unique_rows[r[1]] = r
    final_new_rows = list(unique_rows.values())
    
    print(f"重複整理後: {len(final_new_rows)} 銘柄分のデータを書き込みます。")

    # スプレッドシートの更新と450日ローリング処理
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = []
    
    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "日付" and len(existing_data[0]) == len(headers):
        data_rows = existing_data[1:]
    
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(final_new_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print("スプレッドシートの更新が完了しました。")

if __name__ == "__main__":
    main()
