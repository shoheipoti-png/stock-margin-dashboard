import streamlit as st
import pandas as pd
import datetime

# ページの設定
st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")

st.title("株価・信用残・機関空売りダッシュボード")

# 銘柄コード入力
ticker = st.text_input("銘柄コード（4桁）を入力してください", value="6323")

if ticker:
    st.subheader(f"{ticker} のデータ")
    
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
    
    # --- デモ用データフレームの生成（※後ほどスプレッドシートからの実データ取得に完全連動させます） ---
    # ここでは選択された期間に合わせてダミー行数を変化させています
    date_list = [datetime.date.today() - datetime.timedelta(days=i) for i in range(selected_days)]
    # 土日を除外する簡易フィルター
    date_list = [d for d in date_list if d.weekday() < 5]
    
    df = pd.DataFrame({
        "Date": [d.strftime("%m/%d\n%a") for d in date_list],
        "前日比・出来高": ["+2.5%\n1.4M株"] * len(date_list),
        "Barclays": ["+50.0K"] * len(date_list),
        "JPM": ["-120.0K"] * len(date_list),
        "モルガン": ["-"] * len(date_list),
        "全増減": ["-70.0K"] * len(date_list),
        "売残": ["1.5M\n+20.0K"] * len(date_list),
        "買残": ["3.2M\n-50.0K"] * len(date_list),
    })
    
    # --- テーブルの描画 ---
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )
