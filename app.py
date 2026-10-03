import streamlit as st
import pandas as pd
import datetime

# ページの設定
st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")

st.title("株価・信用残・機関空売りダッシュボード")

# 銘柄コード入力
ticker = st.text_input("銘柄コード（4桁）を入力してください", value="6323")

if ticker:
    st.subheader(f"{ticker} ローツェ(株)のデータ")
    
    # --- 表示期間の選択UI ---
    period_option = st.selectbox(
        "表示期間を選択：",
        ["直近1ヶ月", "直近3ヶ月", "直近半年", "1年", "1年半（最大）"],
        index=0
    )
    
    # 期間に応じた日数の定義
    days_map = {
        "直近1ヶ月": 30,
        "直近3ヶ月": 90,
        "直近半年": 180,
        "1年": 365,
        "1年半（最大）": 540
    }
    selected_days = days_map[period_option]
    
    # --- 日付リストの生成（選択された期間に応じて行数を変更） ---
    date_list = [datetime.date.today() - datetime.timedelta(days=i) for i in range(selected_days)]
    date_list = [d for d in date_list if d.weekday() < 5] # 土日を除外
    
    # --- 2枚目のデザインを再現するHTMLテーブルの構築 ---
    html_rows = ""
    for d in date_list:
        date_str = d.strftime("%m/%d<br>%a")
        html_rows += f"""
        <tr>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">{date_str}</td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #d32f2f; font-weight: bold;">+2.5%</div>
                <div style="color: #666; font-size: 0.85em;">1.4M株</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #d32f2f; font-weight: bold;">+50.0K</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #1976d2; font-weight: bold;">-120.0K</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #666;">-</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="color: #1976d2; font-weight: bold;">-70.0K</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="font-weight: bold;">1.5M</div>
                <div style="color: #d32f2f; font-size: 0.85em;">+20.0K</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="font-weight: bold;">3.2M</div>
                <div style="color: #1976d2; font-size: 0.85em;">-50.0K</div>
            </td>
        </tr>
        """
        
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
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">モルガン</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">売</th>
                <th style="border: 1px solid #555; padding: 6px; text-align: center;">買</th>
            </tr>
        </thead>
        <tbody>
            {html_rows}
        </tbody>
    </table>
    """
    
    # HTMLの描画
    st.markdown(html_table, unsafe_allow_html=True)
