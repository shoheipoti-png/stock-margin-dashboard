import streamlit as st
import pandas as pd
import datetime
import os
import json
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

# ページの設定
st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")

st.title("株価・信用残・機関空売りダッシュボード")

# --- スプレッドシートからデータを取得する関数 ---
@st.cache_data(ttl=600) # 10分間キャッシュ
def load_data_from_sheet():
    try:
        creds_json = st.secrets.get("GCP_SERVICE_ACCOUNT_KEY") or os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
        sheet_id = st.secrets.get("SPREADSHEET_ID") or os.environ.get("SPREADSHEET_ID")
        
        if not creds_json or not sheet_id:
            return pd.DataFrame()
            
        creds_dict = json.loads(creds_json)
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1
        
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        return pd.DataFrame()

# 数値をスマートに単位変換する関数（小型株の数千株〜NTT等の数億株に対応）
def smart_format(val):
    try:
        num = float(val)
        if abs(num) >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif abs(num) >= 1_000:
            return f"{num / 1_000:.1f}K"
        else:
            return f"{int(num)}"
    except:
        return str(val)

# 銘柄コード入力
ticker = st.text_input("銘柄コード（4桁）を入力してください", value="6323")

if ticker:
    st.subheader(f"{ticker} のデータ分析")
    
    # --- 表示期間の選択UI ---
    period_option = st.selectbox(
        "表示期間を選択：",
        ["直近1ヶ月", "直近3ヶ月", "直半年", "1年", "1年半（最大）"],
        index=0
    )
    
    days_map = {
        "直近1ヶ月": 30,
        "直近3ヶ月": 90,
        "直半年": 180,
        "1年": 365,
        "1年半（最大）": 540
    }
    selected_days = days_map[period_option]
    
    # スプレッドシートからのデータ読み込み
    df = load_data_from_sheet()
    
    # データが存在しない場合のフォールバック（初期テスト用ダミー生成）
    if df.empty or "銘柄コード" not in df.columns:
        date_list = [datetime.date.today() - datetime.timedelta(days=i) for i in range(selected_days)]
        date_list = [d for d in date_list if d.weekday() < 5]
        df = pd.DataFrame({
            "日付": [d.strftime("%Y-%m-%d") for d in date_list],
            "銘柄コード": [ticker] * len(date_list),
            "機関空売り増減": ["-70000"] * len(date_list),
            "個人信用売残": ["1500000"] * len(date_list),
            "個人信用買残": ["3200000"] * len(date_list),
        })
    
    # 選択された銘柄コードでフィルター
    df_filtered = df[df["銘柄コード"].astype(str) == str(ticker)]
    
    # --- HTMLテーブルの構築（自動単位変換＆色分け対応） ---
    rows_html = []
    for idx, row in df_filtered.head(selected_days).iterrows():
        # 日付の整形
        date_val = str(row.get("日付", "2026-10-03"))
        try:
            dt = datetime.datetime.strptime(date_val.split()[0], "%Y-%m-%d")
            date_str = dt.strftime("%m/%d<br>%a")
        except:
            date_str = date_val
            
        # 数値の取得とスマートフォーマット適用
        raw_short = row.get("機関空売り増減", "-70000")
        formatted_short = smart_format(raw_short)
        
        raw_sell = row.get("個人信用売残", "1500000")
        formatted_sell = smart_format(raw_sell)
        
        raw_buy = row.get("個人信用買残", "3200000")
        formatted_buy = smart_format(raw_buy)
        
        # プラス・マイナスに応じた背景色・文字色
        diff_bg = "#ffebee" if not str(raw_short).startswith("-") else "#e3f2fd"
        diff_color = "#d32f2f" if not str(raw_short).startswith("-") else "#1976d2"
        
        row_html = f"""
        <tr>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">{date_str}</td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #d32f2f; font-weight: bold;">+2.5%</div>
                <div style="color: #666; font-size: 0.85em;">1.4M株</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: {diff_bg};">
                <div style="color: {diff_color}; font-weight: bold;">{formatted_short}</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: {diff_color}; font-weight: bold;">-</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #666;">-</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: {diff_bg};">
                <div style="color: {diff_color}; font-weight: bold;">{formatted_short}</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="font-weight: bold;">{formatted_sell}</div>
                <div style="color: #d32f2f; background-color: #ffebee; font-size: 0.85em; padding: 2px;">+20.0K</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="font-weight: bold;">{formatted_buy}</div>
                <div style="color: #1976d2; background-color: #e3f2fd; font-size: 0.85em; padding: 2px;">-50.0K</div>
            </td>
        </tr>
        """
        rows_html.append(row_html)
        
    joined_rows = "".join(rows_html)
    
    html_table = f"""
    <table style="width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <thead>
            <tr style="background-color: #262730; color: white;">
                <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 12%;">Date</th>
                <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 14%;">前日比<br>出来高</th>
                <th colspan="3" style="border: 1px solid #444; padding: 8px; text-align: center;">機関投資家の空売り</th>
                <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 12%;">全増減</th>
                <th colspan="2" style="border: 1px solid #444; padding: 8px; text-align: center;">個人信用</th>
            </tr>
            <tr style="background-color: #3b3c43; color: white;">
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">Barclays</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">JPM</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">モルガン株</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">売</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">買</th>
            </tr>
        </thead>
        <tbody>
            {joined_rows}
        </tbody>
    </table>
    """
    
    components.html(html_table, height=750, scrolling=True)
