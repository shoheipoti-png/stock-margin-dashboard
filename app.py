import streamlit as st
import pandas as pd
import datetime
import os
import json
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")
st.title("株価・信用残・機関空売りダッシュボード")

@st.cache_data(ttl=600)
def load_data_from_sheet():
    try:
        creds_json = st.secrets.get("GCP_SERVICE_ACCOUNT_KEY") or os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
        sheet_id = st.secrets.get("SPREADSHEET_ID") or os.environ.get("SPREADSHEET_ID")
        if not creds_json or not sheet_id: return pd.DataFrame()
            
        creds_dict = json.loads(creds_json)
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        worksheet = client.open_by_key(sheet_id).sheet1
        return pd.DataFrame(worksheet.get_all_records())
    except:
        return pd.DataFrame()

def smart_format(val):
    try:
        if val == "" or val == "-": return "-"
        num = float(val)
        if abs(num) >= 1_000_000: return f"{num / 1_000_000:.1f}M"
        elif abs(num) >= 1_000: return f"{num / 1_000:.1f}K"
        else: return f"{int(num)}"
    except:
        return str(val)

ticker = st.text_input("銘柄コード（4桁）を入力してください", value="6323")

if ticker:
    st.subheader(f"{ticker} のデータ分析")
    
    period_option = st.selectbox(
        "表示期間を選択：",
        ["直近1ヶ月", "直近3ヶ月", "直半年", "1年"],
        index=0
    )
    days_map = {"直近1ヶ月": 30, "直近3ヶ月": 90, "直半年": 180, "1年": 365}
    selected_days = days_map[period_option]
    
    df = load_data_from_sheet()
    
# 取得失敗時・空時のダミー
    if df.empty or "銘柄コード" not in df.columns:
        date_list = [datetime.date.today() - datetime.timedelta(days=i) for i in range(selected_days)]
        date_list = [d for d in date_list if d.weekday() < 5]
        
        # すべての要素の配列長さを合わせることでエラーを解消
        df = pd.DataFrame({
            "日付": [d.strftime("%Y-%m-%d") for d in date_list],
            "銘柄コード": [ticker] * len(date_list),
            "機関空売り増減": ["-"] * len(date_list),
            "売残(合計)": ["8800"] * len(date_list),
            "売残(一般)": ["0"] * len(date_list),
            "売残(制度)": ["8800"] * len(date_list),
            "買残(合計)": ["157700"] * len(date_list),
            "買残(一般)": ["37500"] * len(date_list),
            "買残(制度)": ["120200"] * len(date_list),
        })
        
    df_filtered = df[df["銘柄コード"].astype(str) == str(ticker)]
    
    rows_html = []
    for idx, row in df_filtered.head(selected_days).iterrows():
        date_val = str(row.get("日付", ""))
        try:
            dt = datetime.datetime.strptime(date_val.split()[0], "%Y-%m-%d")
            date_str = dt.strftime("%m/%d<br>%a")
        except:
            date_str = date_val
            
        short = smart_format(row.get("機関空売り増減", "-"))
        
        tot_sell = smart_format(row.get("売残(合計)", "-"))
        gen_sell = smart_format(row.get("売残(一般)", "-"))
        std_sell = smart_format(row.get("売残(制度)", "-"))
        
        tot_buy = smart_format(row.get("買残(合計)", "-"))
        gen_buy = smart_format(row.get("買残(一般)", "-"))
        std_buy = smart_format(row.get("買残(制度)", "-"))
        
        diff_bg = "#ffebee" if not str(short).startswith("-") and short != "-" else "#e3f2fd" if str(short).startswith("-") else "#fff"
        diff_color = "#d32f2f" if not str(short).startswith("-") and short != "-" else "#1976d2" if str(short).startswith("-") else "#666"
        
        row_html = f"""
        <tr>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">{date_str}</td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #666;">-</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: {diff_bg};">
                <div style="color: {diff_color}; font-weight: bold;">{short}</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #666;">-</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #666;">-</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: {diff_bg};">
                <div style="color: {diff_color}; font-weight: bold;">{short}</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="font-weight: bold; font-size: 1.1em;">{tot_sell}</div>
                <div style="color: #666; font-size: 0.75em; margin-top: 2px;">般: {gen_sell} / 制: {std_sell}</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="font-weight: bold; font-size: 1.1em;">{tot_buy}</div>
                <div style="color: #666; font-size: 0.75em; margin-top: 2px;">般: {gen_buy} / 制: {std_buy}</div>
            </td>
        </tr>
        """
        rows_html.append(row_html)
        
    html_table = f"""
    <table style="width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <thead>
            <tr style="background-color: #262730; color: white;">
                <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 8%;">Date</th>
                <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 10%;">前日比<br>出来高</th>
                <th colspan="3" style="border: 1px solid #444; padding: 8px; text-align: center;">機関投資家の空売り</th>
                <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 10%;">全増減</th>
                <th colspan="2" style="border: 1px solid #444; padding: 8px; text-align: center;">個人信用 (合計・内訳)</th>
            </tr>
            <tr style="background-color: #3b3c43; color: white;">
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">Barclays</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">JPM</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">モルガン</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center; width: 20%;">売</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center; width: 20%;">買</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows_html)}
        </tbody>
    </table>
    """
    
    components.html(html_table, height=750, scrolling=True)
