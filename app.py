import streamlit as st
import pandas as pd
import datetime
import os
import json
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components
import plotly.graph_objects as go
import yfinance as yf

st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")
st.title("株価・信用残・機関空売りダッシュボード")

INSTITUTION_SHORT_NAMES = {
    "barclays": "Barc",
    "goldman": "GOLD",
    "jpm": "JPM",
    "merrill": "MERR",
    "nomura": "Nomu",
    "ubs": "UBS",
    "morgan stanley": "モルガン",
    "モルガン・スタンレー": "モルガン",
    "bnp": "BNP",
    "citigroup": "Citi",
    "citi": "Citi",
    "credit suisse": "CS",
    "societe generale": "SG",
    "integrated core": "Inte",
    "pdt": "PDT",
    "arrowstreet": "Arro",
    "qube": "Qube",
    "jane street": "Jane",
}

def get_short_inst_name(full_name):
    if not full_name:
        return "その他"
    fn_lower = str(full_name).lower()
    for key, val in INSTITUTION_SHORT_NAMES.items():
        if key in fn_lower:
            return val
    return str(full_name)[:6]

def clean_ticker_code(val):
    if pd.isna(val):
        return ""
    s = str(val).split('.')[0].strip()
    return s[:4] if len(s) >= 4 else s

@st.cache_data(ttl=60)
def load_data_from_sheet(sheet_env_key):
    """Googleスプレッドシートからデータを取得"""
    try:
        creds_json = st.secrets.get("GCP_SERVICE_ACCOUNT_KEY") or os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
        sheet_id = st.secrets.get(sheet_env_key) or os.environ.get(sheet_env_key)
        if not creds_json or not sheet_id:
            return pd.DataFrame()
            
        creds_dict = json.loads(creds_json)
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        worksheet = client.open_by_key(sheet_id).sheet1
        records = worksheet.get_all_records()
        return pd.DataFrame(records)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_stock_price_history(ticker_code, days=90):
    """yfinanceから株価の前日比%と出来高を取得"""
    try:
        yf_ticker = f"{ticker_code}.T"
        stock = yf.Ticker(yf_ticker)
        # 指定日数より少し多めに取得して前日比を計算
        hist = stock.history(period="1y")
        if hist.empty:
            return {}
        
        hist = hist.sort_index(ascending=True)
        hist['Pct_Change'] = hist['Close'].pct_change() * 100
        
        price_dict = {}
        for idx_date, row in hist.iterrows():
            d_str = idx_date.strftime("%Y-%m-%d")
            pct = row['Pct_Change']
            vol = row['Volume']
            price_dict[d_str] = {
                "pct": pct if pd.notna(pct) else 0.0,
                "volume": vol if pd.notna(vol) else 0
            }
        return price_dict
    except Exception:
        return {}

def smart_format(val):
    try:
        if val == "" or val is None or val == "-":
            return "-"
        num = float(str(val).replace(',', ''))
        if abs(num) >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif abs(num) >= 1_000:
            return f"{num / 1_000:.1f}K"
        else:
            return f"{int(num)}"
    except Exception:
        return str(val)

def format_change(num):
    """数値から前日比のプラスマイナス・色・背景色を生成"""
    try:
        if num == "" or num is None or num == "-":
            return "-", "#666", "transparent"
        val = float(str(num).replace(',', ''))
        if val == 0:
            return "0", "#666", "#f0f2f6"
        color = "#d32f2f" if val > 0 else "#1976d2"
        bg = "#ffebee" if val > 0 else "#e3f2fd"
        sign = "+" if val > 0 else ""
        if abs(val) >= 1_000_000:
            formatted = f"{sign}{val / 1_000_000:.1f}M"
        elif abs(val) >= 1_000:
            formatted = f"{sign}{val / 1_000:.1f}K"
        else:
            formatted = f"{sign}{int(val)}"
        return formatted, color, bg
    except Exception:
        return str(num), "#666", "#f0f2f6"

def format_pct(num):
    """株価前日比％のフォーマット"""
    try:
        val = float(num)
        if val == 0:
            return "0.0%", "#666"
        color = "#d32f2f" if val > 0 else "#1976d2"
        sign = "+" if val > 0 else ""
        return f"{sign}{val:.1f}%", color
    except Exception:
        return "-", "#666"

ticker = st.text_input("銘柄コード（4桁）を入力してください", value="6315")

if ticker:
    period_option = st.selectbox(
        "表示期間を選択：",
        ["直近1ヶ月", "直近3ヶ月", "直半年", "1年"],
        index=0
    )
    days_map = {"直近1ヶ月": 30, "直近3ヶ月": 90, "直半年": 180, "1年": 365}
    selected_days = days_map[period_option]

    cutoff_date = datetime.date.today() - datetime.timedelta(days=selected_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    # 1. データ読み込み
    df_margin = load_data_from_sheet("SPREADSHEET_ID")
    df_short = load_data_from_sheet("SHORT_SPREADSHEET_ID")

    # 2. 個人信用データの抽出
    company_name = ""
    if not df_margin.empty and "銘柄コード" in df_margin.columns:
        df_margin['clean_code'] = df_margin['銘柄コード'].apply(clean_ticker_code)
        m_filtered = df_margin[df_margin['clean_code'] == str(ticker)].copy()
        if not m_filtered.empty and "銘柄名" in m_filtered.columns:
            company_name = str(m_filtered["銘柄名"].iloc[0]).split()[0]
        if "日付" in m_filtered.columns:
            m_filtered = m_filtered[m_filtered["日付"] >= cutoff_str]
    else:
        m_filtered = pd.DataFrame()

    # 3. 機関空売りデータの抽出
    if not df_short.empty and "銘柄コード" in df_short.columns:
        df_short['clean_code'] = df_short['銘柄コード'].apply(clean_ticker_code)
        s_filtered = df_short[df_short['clean_code'] == str(ticker)].copy()
        if not company_name and not s_filtered.empty and "銘柄名" in s_filtered.columns:
            company_name = str(s_filtered["銘柄名"].iloc[0]).split()[0]
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        if date_col in s_filtered.columns:
            s_filtered = s_filtered[s_filtered[date_col] >= cutoff_str]
    else:
        s_filtered = pd.DataFrame()

    title_label = f"{ticker}（{company_name}）" if company_name else f"{ticker}"
    st.subheader(f"{title_label} のデータ分析")

    # 株価・出来高データの取得 (yfinance)
    stock_prices = get_stock_price_history(ticker, selected_days)

    # 日付軸の決定（降順）
    all_dates = set()
    if not m_filtered.empty and "日付" in m_filtered.columns:
        all_dates.update(m_filtered["日付"].dropna().astype(str).tolist())
    if not s_filtered.empty:
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        all_dates.update(s_filtered[date_col].dropna().astype(str).tolist())

    if not all_dates:
        base_dates = [datetime.date.today() - datetime.timedelta(days=i) for i in range(min(selected_days, 15))]
        sorted_dates = [d.strftime("%Y-%m-%d") for d in base_dates if d.weekday() < 5]
    else:
        sorted_dates = sorted(list(all_dates), reverse=True)

    # 機関リストの特定
    institutions = []
    if not s_filtered.empty and "機関名" in s_filtered.columns:
        institutions = s_filtered["機関名"].dropna().unique().tolist()

    # 機関ごとの残高マップ構築
    short_map = {}
    total_short_by_date = {}
    if not s_filtered.empty:
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        s_sorted = s_filtered.sort_values(by=date_col, ascending=True)
        prev_shares_by_inst = {}
        for d, group in s_sorted.groupby(date_col):
            d_str = str(d)
            daily_total = 0
            for _, r in group.iterrows():
                inst = r.get("機関名", "")
                try:
                    shares = float(str(r.get("空売り残高数量", 0)).replace(',', ''))
                except Exception:
                    shares = 0
                prev = prev_shares_by_inst.get(inst, 0)
                diff = shares - prev if prev != 0 else 0
                prev_shares_by_inst[inst] = shares
                short_map[(d_str, inst)] = (shares, diff)
                daily_total += shares
            total_short_by_date[d_str] = daily_total

    # 個人信用マップの構築（日付順ソートして前日差を自動計算）
    margin_map = {}
    if not m_filtered.empty and "日付" in m_filtered.columns:
        m_sorted = m_filtered.sort_values(by="日付", ascending=True)
        prev_sell = None
        prev_buy = None
        for _, r in m_sorted.iterrows():
            d_str = str(r.get("日付", ""))
            try:
                cur_sell = float(str(r.get("売残(合計)", 0)).replace(',', ''))
            except Exception:
                cur_sell = 0
            try:
                cur_buy = float(str(r.get("買残(合計)", 0)).replace(',', ''))
            except Exception:
                cur_buy = 0
                
            sell_diff = cur_sell - prev_sell if prev_sell is not None else 0
            buy_diff = cur_buy - prev_buy if prev_buy is not None else 0
            prev_sell = cur_sell
            prev_buy = cur_buy
            
            margin_map[d_str] = {
                "row": r,
                "sell_diff": sell_diff,
                "buy_diff": buy_diff
            }

    # ----------------------------------------------------
    # グラフ描画 (Plotly)
    # ----------------------------------------------------
    graph_dates = sorted(sorted_dates)
    buy_shares_list = []
    sell_shares_list = []
    inst_shares_list = []

    for d in graph_dates:
        m_info = margin_map.get(d)
        if m_info:
            r = m_info["row"]
            try:
                b_val = float(str(r.get("買残(合計)", 0)).replace(',', ''))
            except Exception:
                b_val = None
            try:
                s_val = float(str(r.get("売残(合計)", 0)).replace(',', ''))
            except Exception:
                s_val = None
        else:
            b_val = None
            s_val = None
        buy_shares_list.append(b_val)
        sell_shares_list.append(s_val)

        tot_inst = total_short_by_date.get(d, None)
        inst_shares_list.append(tot_inst)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=graph_dates, y=buy_shares_list,
        mode='lines+markers', name='個人 買残合計',
        line=dict(color='#d32f2f', width=2),
        hovertemplate='日付: %{x}<br>買残: %{y:,.0f}株<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=graph_dates, y=sell_shares_list,
        mode='lines+markers', name='個人 売残合計',
        line=dict(color='#1976d2', width=2),
        hovertemplate='日付: %{x}<br>売残: %{y:,.0f}株<extra></extra>'
    ))
    if any(v is not None and v > 0 for v in inst_shares_list):
        fig.add_trace(go.Scatter(
            x=graph_dates, y=inst_shares_list,
            mode='lines+markers', name='機関空売り合計',
            line=dict(color='#ff9800', width=2, dash='dot'),
            hovertemplate='日付: %{x}<br>機関空売り: %{y:,.0f}株<extra></extra>'
        ))

    fig.update_layout(
        title=f"{title_label} 信用残・機関空売り推移",
        xaxis_title="日付",
        yaxis_title="株数",
        hovermode="x unified",
        margin=dict(l=40, r=40, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white"
    )
    st.plotly_chart(fig, use_container_width=True)

    # ----------------------------------------------------
    # テーブルHTML生成
    # ----------------------------------------------------
    inst_count = len(institutions)
    
    header_tr1 = (
        '<tr style="background-color: #262730; color: white;">'
        '<th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 8%;">Date</th>'
        '<th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 10%;">前日比<br>出来高</th>'
    )
    if inst_count > 0:
        header_tr1 += f'<th colspan="{inst_count}" style="border: 1px solid #444; padding: 8px; text-align: center;">機関投資家の空売り</th>'
    header_tr1 += (
        '<th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 8%;">全増減</th>'
        '<th colspan="2" style="border: 1px solid #444; padding: 8px; text-align: center;">個人信用 (合計・前日差・内訳)</th>'
        '</tr>'
    )

    header_tr2 = '<tr style="background-color: #3b3c43; color: white;">'
    for idx, inst in enumerate(institutions, 1):
        short_label = get_short_inst_name(inst)
        header_tr2 += f'<th style="border: 1px solid #555; padding: 6px; text-align: center;" title="{inst}">{idx}<br>{short_label}</th>'
    header_tr2 += (
        '<th style="border: 1px solid #555; padding: 6px; text-align: center; width: 18%;">売</th>'
        '<th style="border: 1px solid #555; padding: 6px; text-align: center; width: 18%;">買</th>'
        '</tr>'
    )

    rows_html = []
    # 日付降順でループし、前日差は次の日（過去）との比較で計算
    for i, d in enumerate(sorted_dates):
        try:
            dt = datetime.datetime.strptime(d, "%Y-%m-%d")
            date_str = dt.strftime("%m/%d<br>%a")
        except Exception:
            date_str = d

        # 株価前日比・出来高 (yfinance)
        price_info = stock_prices.get(d)
        if price_info:
            pct_str, pct_color = format_pct(price_info["pct"])
            vol_str = smart_format(price_info["volume"])
            price_cell_html = (
                f'<div style="font-weight: bold; color: {pct_color}; font-size: 0.95em;">{pct_str}</div>'
                f'<div style="color: #666; font-size: 0.8em; margin-top: 2px;">{vol_str}</div>'
            )
        else:
            price_cell_html = '<div style="color: #666;">-</div>'

        # 機関列のセル生成
        inst_tds = ""
        daily_short_sum = 0
        for inst in institutions:
            item = short_map.get((d, inst))
            if item:
                shares, diff = item
                sh_str = smart_format(shares)
                d_str, d_col, d_bg = format_change(diff)
                daily_short_sum += shares
                inst_tds += (
                    '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 6px; background-color: #fff;">'
                    f'<div style="font-weight: bold; font-size: 0.95em;">{sh_str}</div>'
                    f'<div style="color: {d_col}; background-color: {d_bg}; font-size: 0.8em; padding: 1px; border-radius: 2px;">{d_str}</div>'
                    '</td>'
                )
            else:
                inst_tds += '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 6px; background-color: #fff; color: #888;">-</td>'

        # 全増減
        # 過去日（i+1）の合計との差分
        prev_d = sorted_dates[i+1] if i + 1 < len(sorted_dates) else None
        prev_sum = total_short_by_date.get(prev_d, 0) if prev_d else 0
        cur_sum = total_short_by_date.get(d, 0)
        
        if cur_sum > 0:
            all_diff = cur_sum - prev_sum if prev_sum > 0 else 0
            all_diff_str, all_diff_col, all_diff_bg = format_change(all_diff)
            all_change_html = f'<div style="color: {all_diff_col}; background-color: {all_diff_bg}; font-size: 0.85em; padding: 2px; border-radius: 2px;">{all_diff_str}</div>'
        else:
            all_change_html = '<div style="color: #666;">-</div>'

        # 個人信用の取得（自動計算された差分を表示）
        m_info = margin_map.get(d)
        if m_info is not None:
            r = m_info["row"]
            tot_sell = smart_format(r.get("売残(合計)", "-"))
            sell_chg_str, sell_chg_color, sell_chg_bg = format_change(m_info["sell_diff"])
            gen_sell = smart_format(r.get("売残(一般)", "-"))
            std_sell = smart_format(r.get("売残(制度)", "-"))

            tot_buy = smart_format(r.get("買残(合計)", "-"))
            buy_chg_str, buy_chg_color, buy_chg_bg = format_change(m_info["buy_diff"])
            gen_buy = smart_format(r.get("買残(一般)", "-"))
            std_buy = smart_format(r.get("買残(制度)", "-"))
        else:
            tot_sell, sell_chg_str, sell_chg_color, sell_chg_bg, gen_sell, std_sell = "-", "0", "#666", "#f0f2f6", "-", "-"
            tot_buy, buy_chg_str, buy_chg_color, buy_chg_bg, gen_buy, std_buy = "-", "0", "#666", "#f0f2f6", "-", "-"

        row_html = (
            '<tr>'
            f'<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">{date_str}</td>'
            f'<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">{price_cell_html}</td>'
            f'{inst_tds}'
            f'<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">{all_change_html}</td>'
            '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">'
            f'<div style="font-weight: bold; font-size: 1.05em;">{tot_sell}</div>'
            f'<div style="color: {sell_chg_color}; background-color: {sell_chg_bg}; font-size: 0.85em; padding: 2px; margin: 3px 0; border-radius: 2px;">{sell_chg_str}</div>'
            f'<div style="color: #666; font-size: 0.75em;">般: {gen_sell} / 制: {std_sell}</div>'
            '</td>'
            '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">'
            f'<div style="font-weight: bold; font-size: 1.05em;">{tot_buy}</div>'
            f'<div style="color: {buy_chg_color}; background-color: {buy_chg_bg}; font-size: 0.85em; padding: 2px; margin: 3px 0; border-radius: 2px;">{buy_chg_str}</div>'
            f'<div style="color: #666; font-size: 0.75em;">般: {gen_buy} / 制: {std_buy}</div>'
            '</td>'
            '</tr>'
        )
        rows_html.append(row_html)

    # 機関一覧リスト（上部サマリー）
    if inst_count > 0:
        inst_summary_html = (
            '<div style="margin-bottom: 12px; font-family: sans-serif;">'
            f'<div style="background-color: #000; color: #fff; padding: 6px 12px; font-weight: bold; font-size: 13px;">{title_label} 空売り参加機関一覧 ({len(institutions)}社)</div>'
            '<table style="width: 100%; border-collapse: collapse; font-size: 12px; border: 1px solid #ddd;">'
            '<tr style="background-color: #f5f5f5;">'
            '<th style="padding: 4px 8px; border: 1px solid #ddd; width: 60px; text-align: center;">Number</th>'
            '<th style="padding: 4px 8px; border: 1px solid #ddd; text-align: left;">空売り機関名</th>'
            '</tr>'
        )
        for idx, inst in enumerate(institutions, 1):
            inst_summary_html += (
                '<tr>'
                f'<td style="padding: 4px 8px; border: 1px solid #ddd; text-align: center;">{idx}</td>'
                f'<td style="padding: 4px 8px; border: 1px solid #ddd;">{inst}</td>'
                '</tr>'
            )
        inst_summary_html += '</table></div>'
        components.html(inst_summary_html, height=min(180, 40 + inst_count * 28), scrolling=True)

    body_content = "".join(rows_html)
    html_table = (
        '<table style="width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 13px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">'
        f'<thead>{header_tr1}{header_tr2}</thead>'
        f'<tbody>{body_content}</tbody>'
        '</table>'
    )
    
    components.html(html_table, height=750, scrolling=True)
