import streamlit as st
import pandas as pd
import yfinance as yf
import datetime

st.set_page_config(page_title="信用残・空売り確認ツール", layout="wide")

st.title("株価・信用残・機関空売り ダッシュボード")

# 銘柄コード入力
ticker = st.text_input("銘柄コード（4桁）を入力してください", value="6323")

# ユーティリティ関数：K/Mフォーマット
def format_km(value):
    if pd.isna(value) or value == "-": return "-"
    try:
        val = float(value)
        if val >= 1_000_000 or val <= -1_000_000:
            return f"{val / 1_000_000:.1f}M"
        elif val >= 1_000 or val <= -1_000:
            return f"{val / 1_000:.1f}K"
        else:
            return str(int(val))
    except:
        return str(value)

# 色付け関数
def color_val(val, prefix=""):
    if pd.isna(val) or val == "-": return "-"
    try:
        v = float(val)
        color = "red" if v > 0 else "blue" if v < 0 else "black"
        sign = "+" if v > 0 else ""
        formatted = format_km(v)
        return f"<span style='color:{color}; font-weight:bold;'>{prefix}{sign}{formatted}</span>"
    except:
        return str(val)

if ticker:
    st.write(f"### 銘柄コード: {ticker} のデータ")
    
    # Yahoo Financeから株価と出来高を取得
    t_code = ticker + ".T"
    stock = yf.Ticker(t_code)
    hist = stock.history(period="1mo").tail(10).sort_index(ascending=False)
    
    if hist.empty:
        st.error("株価データが取得できませんでした。コードを確認してください。")
    else:
        # ご要望の「上下分割セル」「K/M短縮表記」をHTMLで構築
        html = """
        <table style="width:100%; border-collapse: collapse; text-align:center; font-size:14px; font-family:sans-serif;">
            <tr style="background-color:#333; color:white;">
                <th rowspan="2" style="border:1px solid #aaa; padding:8px;">Date</th>
                <th rowspan="2" style="border:1px solid #aaa; padding:8px;">前日比<br><span style="font-size:11px; color:#ddd;">出来高</span></th>
                <th colspan="4" style="border:1px solid #aaa; padding:8px;">機関投資家の空売り</th>
                <th colspan="2" style="border:1px solid #aaa; padding:8px;">個人信用</th>
            </tr>
            <tr style="background-color:#555; color:white; font-size:12px;">
                <th style="border:1px solid #aaa; padding:5px;">Barclays</th>
                <th style="border:1px solid #aaa; padding:5px;">JPM</th>
                <th style="border:1px solid #aaa; padding:5px;">モルガン</th>
                <th style="border:1px solid #aaa; padding:5px; background-color:#444;">全増減</th>
                <th style="border:1px solid #aaa; padding:5px;">売</th>
                <th style="border:1px solid #aaa; padding:5px;">買</th>
            </tr>
        """
        
        # データの行を作成
        prev_close = None
        for idx, row in hist.iterrows():
            date_str = idx.strftime("%m/%d<br>%a")
            close_price = row['Close']
            volume = row['Volume']
            
            # 前日比の計算
            diff_pct = 0.0 # サンプル
            diff_color = "red" # 仮の色
            diff_sign = "+"
            
            # --- ここから下はUI確認用のダミーデータです ---
            # 確認後に実際のJPXデータに連携させます
            inst1 = color_val(50000)
            inst2 = color_val(-120000)
            inst3 = "-"
            total_inst = color_val(-70000)
            
            margin_sell_total = format_km(1500000)
            margin_sell_diff = color_val(20000)
            margin_buy_total = format_km(3200000)
            margin_buy_diff = color_val(-50000)
            
            html += f"""
            <tr>
                <td style="border:1px solid #ccc; padding:8px; font-weight:bold;">{date_str}</td>
                <td style="border:1px solid #ccc; padding:8px; background-color:#f9f9f9;">
                    <span style='color:{diff_color}; font-weight:bold;'>{diff_sign}2.50%</span><br>
                    <span style='font-size:12px; color:#555;'>{format_km(volume)}株</span>
                </td>
                <td style="border:1px solid #ccc; padding:8px;">{inst1}</td>
                <td style="border:1px solid #ccc; padding:8px;">{inst2}</td>
                <td style="border:1px solid #ccc; padding:8px;">{inst3}</td>
                <td style="border:1px solid #ccc; padding:8px; background-color:#f0f0f0;">{total_inst}</td>
                <td style="border:1px solid #ccc; padding:8px;">
                    <span style="font-weight:bold;">{margin_sell_total}</span><br>
                    <span style="font-size:12px;">{margin_sell_diff}</span>
                </td>
                <td style="border:1px solid #ccc; padding:8px;">
                    <span style="font-weight:bold;">{margin_buy_total}</span><br>
                    <span style="font-size:12px;">{margin_buy_diff}</span>
                </td>
            </tr>
            """
        
        html += "</table>"
        
        st.markdown(html, unsafe_allow_html=True)
        
        st.info("💡 **システムからのメッセージ**: 現在は画面レイアウト（上下2段表示やK/M短縮表記）の確認用バージョンです。Yahoo Financeからの株価・出来高は本物ですが、表の右側（機関・信用残）には仮の数値を入れています。スマホやPCで見た目の操作感をご確認いただいた後、JPXのシステムから自動取得する処理を追加します。")
