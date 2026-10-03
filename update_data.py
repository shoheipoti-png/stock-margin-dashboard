import os
import json
import datetime
import gspread
from google.oauth2.service_account import Credentials

def main():
    print("Googleスプレッドシートへの接続テストを開始します...")
    
    # GitHubの秘密鍵を読み込む
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SPREADSHEET_ID")
    
    if not creds_json or not sheet_id:
        print("エラー: 鍵またはシートIDが設定されていません。")
        return
        
    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    
    # スプレッドシートに接続
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1
    
    # 1行目（ヘッダー）が空なら見出しを追加
    if not worksheet.get_all_values():
        worksheet.append_row(["日付", "銘柄コード", "機関空売り全増減", "個人信用売残", "個人信用買残"])
    
    # 今日の日付とテストデータを書き込む
    today_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    test_data = [today_str, "6323", "-70000", "1500000", "3200000"]
    worksheet.append_row(test_data)
    
    print(f"成功！ スプレッドシートにテストデータを書き込みました: {test_data}")

if __name__ == "__main__":
    main()
