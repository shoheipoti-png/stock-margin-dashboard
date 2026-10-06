import streamlit as st
import pandas as pd
import datetime
import os
import json
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components
import plotly.graph_objects as go

st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")
st.title("株価・信用残・機関空売りダッシュボード")

# 機関名の短縮表示用マップ
INSTITUTION_SHORT_NAMES = {
    "barclays": "Barc",
    "goldman": "GOLD",
    "jpm": "JPM",
    "merrill": "MERR",
    "nomura": "Nomu",
    "ubs": "UBS",
    "morgan stanley": "モルガン",
    "bnp": "BNP",
    "citigroup": "Citi",
    "citi": "Citi",
    "credit suisse": "CS",
    "societe generale": "SG",
    "integrated core": "Inte",
    "pdt": "PDT",
    "arrowstreet": "Arro",
    "qube": "Qube",
}

def get_short_inst_name(full_name):
    if not full_name:
        return "その他"
    fn_lower = full_name.lower()
    for key, val in INSTITUTION_SHORT_NAMES.items():
        if key in fn_lower:
            return val
    # 短縮が見つからない場合は先頭8文字
    return full_name[:8]

@st.cache_data(ttl=300)
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
        return pd.DataFrame(worksheet.get_all_records())
    except Exception:
        return pd.DataFrame()

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

def format_change(val):
    """前日比のプラスマイナスに色と符号を付ける"""
    try:
        if val == "" or val is None or val == "-" or str(val).strip() == "0":
            return "0", "#666", "#f0f2f6"
        num = float(str(val).replace(',', ''))
        if num == 0:
            return "0", "#666", "#f0f2f6"
        color = "#d32f2f" if num > 0 else "#1976d2"
        bg = "#ffebee" if num > 0 else "#e3f2fd"
        sign = "+" if num > 0 else ""
        if abs(num) >= 1_000_000:
            formatted = f"{sign}{num / 1_000_000:.1f}M"
        elif abs(num) >= 1_000:
            formatted = f"{sign}{num / 1_000:.1f}K"
        else:
            formatted = f"{sign}{int(num)}"
        return formatted, color, bg
    except Exception:
        return str(val), "#666", "#f0f2f6"

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

    cutoff_date = datetime.date.today() - datetime.timedelta(days=selected_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    # 1. データ読み込み
    df_margin = load_data_from_sheet("SPREADSHEET_ID")
    df_short = load_data_from_sheet("SHORT_SPREADSHEET_ID")

    # 2. 個人信用データの抽出
    if not df_margin.empty and "銘柄コード" in df_margin.columns:
        m_filtered = df_margin[df_margin["銘柄コード"].astype(str) == str(ticker)].copy()
        if "日付" in m_filtered.columns:
            m_filtered = m_filtered[m_filtered["日付"] >= cutoff_str]
    else:
        m_filtered = pd.DataFrame()

    # 3. 機関空売りデータの抽出
    if not df_short.empty and "銘柄コード" in df_short.columns:
        s_filtered = df_short[df_short["銘柄コード"].astype(str) == str(ticker)].copy()
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        if date_col in s_filtered.columns:
            s_filtered = s_filtered[s_filtered[date_col] >= cutoff_str]
    else:
        s_filtered = pd.DataFrame()

    # 日付軸の決定（個人信用または機関空売りのユニーク日付、降順）
    all_dates = set()
    if not m_filtered.empty and "日付" in m_filtered.columns:
        all_dates.update(m_filtered["日付"].dropna().astype(str).tolist())
    if not s_filtered.empty:
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        all_dates.update(s_filtered[date_col].dropna().astype(str).tolist())

    if not all_dates:
        # データがまだない場合のダミー日付軸
        base_dates = [datetime.date.today() - datetime.timedelta(days=i) for i in range(min(selected_days, 15))]
        sorted_dates = [d.strftime("%Y-%m-%d") for d in base_dates if d.weekday() < 5]
    else:
        sorted_dates = sorted(list(all_dates), reverse=True)

    # 機関リストの特定（期間内に登場するユニーク機関名）
    institutions = []
    if not s_filtered.empty and "機関名" in s_filtered.columns:
        institutions = s_filtered["機関名"].dropna().unique().tolist()

    # 機関ごとの残高マップ構築 (date, inst) -> (shares, diff)
    short_map = {}
    total_short_by_date = {}
    if not s_filtered.empty:
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        # 昇順ソートして前日差を計算
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

    # 個人信用マップの構築
    margin_map = {}
    if not m_filtered.empty:
        for _, r in m_filtered.iterrows():
            d_str = str(r.get("日付", ""))
            margin_map[d_str] = r

    # ----------------------------------------------------
    # グラフ描画 (Plotly)
    # ----------------------------------------------------
    graph_dates = sorted(sorted_dates)  # グラフは時系列順（左から右へ過去→現在）
    buy_shares_list = []
    sell_shares_list = []
    inst_shares_list = []

    for d in graph_dates:
        # 買残
        m_row = margin_map.get(d)
        if m_row is not None:
            try:
                b_val = float(str(m_row.get("買残(合計)", 0)).replace(',', ''))
            except Exception:
                b_val = None
            try:
                s_val = float(str(m_row.get("売残(合計)", 0)).replace(',', ''))
            except Exception:
                s_val = None
        else:
            b_val = None
            s_val = None
        buy_shares_list.append(b_val)
        sell_shares_list.append(s_val)

        # 機関空売り合計
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
        title=f"{ticker} 信用残・機関空売り推移",
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
    
    # テーブルヘッダー生成
    header_tr1 = f"""
    <tr style="background-color: #262730; color: white;">
        <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 8%;">Date</th>
        <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 8%;">前日比<br>出来高</th>
    """
    if inst_count > 0:
        header_tr1 += f'<th colspan="{inst_count}" style="border: 1px solid #444; padding: 8px; text-align: center;">機関投資家の空売り</th>'
    header_tr1 += """
        <th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 8%;">全増減</th>
        <th colspan="2" style="border: 1px solid #444; padding: 8px; text-align: center;">個人信用 (合計・前日差・内訳)</th>
    </tr>
    """

    header_tr2 = '<tr style="background-color: #3b3c43; color: white;">'
    for idx, inst in enumerate(institutions, 1):
        short_label = get_short_inst_name(inst)
        header_tr2 += f'<th style="border: 1px solid #555; padding: 6px; text-align: center;" title="{inst}">{idx}<br>{short_label}</th>'
    header_tr2 += """
        <th style="border: 1px solid #555; padding: 6px; text-align: center; width: 18%;">売</th>
        <th style="border: 1px solid #555; padding: 6px; text-align: center; width: 18%;">買</th>
    </tr>
    """

    rows_html = []
    prev_total_short = 0

    for d in sorted_dates:
        try:
            dt = datetime.datetime.strptime(d, "%Y-%m-%d")
            date_str = dt.strftime("%m/%d<br>%a")
        except Exception:
            date_str = d

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
                inst_tds += f"""
                <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 6px; background-color: #fff;">
                    <div style="font-weight: bold; font-size: 0.95em;">{sh_str}</div>
                    <div style="color: {d_col}; background-color: {d_bg}; font-size: 0.8em; padding: 1px; border-radius: 2px;">{d_str}</div>
                </td>
                """
            else:
                inst_tds += '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 6px; background-color: #fff; color: #888;">-</td>'

        # 全増減
        if daily_short_sum > 0:
            all_diff = daily_short_sum - prev_total_short if prev_total_short > 0 else 0
            all_diff_str, all_diff_col, all_diff_bg = format_change(all_diff)
            all_change_html = f'<div style="color: {all_diff_col}; background-color: {all_diff_bg}; font-size: 0.85em; padding: 2px; border-radius: 2px;">{all_diff_str}</div>'
            prev_total_short = daily_short_sum
        else:
            all_change_html = '<div style="color: #666;">-</div>'

        # 個人信用の取得
        m_row = margin_map.get(d)
        if m_row is not None:
            tot_sell = smart_format(m_row.get("売残(合計)", "-"))
            sell_chg_str, sell_chg_color, sell_chg_bg = format_change(m_row.get("売残(前日比)", "-"))
            gen_sell = smart_format(m_row.get("売残(一般)", "-"))
            std_sell = smart_format(m_row.get("売残(制度)", "-"))

            tot_buy = smart_format(m_row.get("買残(合計)", "-"))
            buy_chg_str, buy_chg_color, buy_chg_bg = format_change(m_row.get("買残(前日比)", "-"))
            gen_buy = smart_format(m_row.get("買残(一般)", "-"))
            std_buy = smart_format(m_row.get("買残(制度)", "-"))
        else:
            tot_sell, sell_chg_str, sell_chg_color, sell_chg_bg, gen_sell, std_sell = "-", "0", "#666", "#f0f2f6", "-", "-"
            tot_buy, buy_chg_str, buy_chg_color, buy_chg_bg, gen_buy, std_buy = "-", "0", "#666", "#f0f2f6", "-", "-"

        row_html = f"""
        <tr>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">{date_str}</td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff; color: #666;">-</td>
            {inst_tds}
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">{all_change_html}</td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="font-weight: bold; font-size: 1.05em;">{tot_sell}</div>
                <div style="color: {sell_chg_color}; background-color: {sell_chg_bg}; font-size: 0.85em; padding: 2px; margin: 3px 0; border-radius: 2px;">{sell_chg_str}</div>
                <div style="color: #666; font-size: 0.75em;">般: {gen_sell} / 制: {std_sell}</div>
            </td>
            <td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #fff;">
                <div style="font-weight: bold; font-size: 1.05em;">{tot_buy}</div>
                <div style="color: {buy_chg_color}; background-color: {buy_chg_bg}; font-size: 0.85em; padding: 2px; margin: 3px 0; border-radius: 2px;">{buy_chg_str}</div>
                <div style="color: #666; font-size: 0.75em;">般: {gen_buy} / 制: {std_buy}</div>
            </td>
        </tr>
        """
        rows_html.append(row_html)

    # 機関一覧リスト（参考サイトの上部集計テーブル風）の表示
    if inst_count > 0:
        inst_summary_html = f"""
        <div style="margin-bottom: 12px; font-family: sans-serif;">
            <div style="background-color: #000; color: #fff; padding: 6px 12px; font-weight: bold; font-size: 13px;">
                {ticker} 空売り参加機関一覧 ({len(institutions)}社)
            </div>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px; border: 1px solid #ddd;">
                <tr style="background-color: #f5f5f5;">
                    <th style="padding: 4px 8px; border: 1px solid #ddd; width: 60px; text-align: center;">Number</th>
                    <th style="padding: 4px 8px; border: 1px solid #ddd; text-align: left;">空売り機関名</th>
                </tr>
        """
        for idx, inst in enumerate(institutions, 1):
            inst_summary_html += f"""
                <tr>
                    <td style="padding: 4px 8px; border: 1px solid #ddd; text-align: center;">{idx}</td>
                    <td style="padding: 4px 8px; border: 1px solid #ddd;">{inst}</td>
                </tr>
            """
        inst_summary_html += "</table></div>"
        components.html(inst_summary_html, height=min(180, 40 + inst_count * 28), scrolling=True)

    html_table = f"""
    <table style="width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 13px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <thead>
            {header_tr1}
            {header_tr2}
        </thead>
        <tbody>
            {"".join(rows_html)}
        </tbody>
    </table>
    """
    
    components.html(html_table, height=750, scrolling=True)
