import streamlit as st
import pandas as pd
import datetime
import streamlit.components.v1 as components

from data_loader import (
    clean_ticker_code,
    load_data_from_sheet,
    get_company_name_from_yahoo_japan,
    get_stock_prices
)
from chart_view import render_combined_chart
from table_view import render_institution_summary_html, render_main_table_html
from watchlist_manager import (
    init_watchlist_state,
    is_favorite,
    toggle_favorite,
    save_watchlist,
    render_watchlist_ui
)

st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")

init_watchlist_state()

# ----------------------------------------------------
# 左側サイドバー（TradingView風 ドラッグ＆ドロップ ウォッチリスト）
# ----------------------------------------------------
with st.sidebar:
    st.header("📋 ウォッチリスト")
    st.caption("☰をつかんで並び替え / 銘柄クリックで分析")
    
    # コンポーネントからのイベントを受信
    event_data = render_watchlist_ui()
    
    if event_data and isinstance(event_data, dict):
        action = event_data.get("action")
        
        # 1. 銘柄クリック
        if action == "select":
            selected_code = event_data.get("code")
            if selected_code:
                st.session_state.current_ticker = selected_code
                st.rerun()
                
        # 2. ✕ボタン削除
        elif action == "delete":
            del_code = event_data.get("code")
            if del_code:
                st.session_state.watchlist = [
                    it for it in st.session_state.watchlist
                    if (it.get("code") if isinstance(it, dict) else it) != del_code
                ]
                save_watchlist(st.session_state.watchlist)
                st.rerun()
                
        # 3. ドラッグ＆ドロップ並び替え
        elif action == "reorder":
            new_order = event_data.get("order", [])
            current = st.session_state.watchlist
            item_map = {it.get("code") if isinstance(it, dict) else it: it for it in current}
            st.session_state.watchlist = [item_map[c] for c in new_order if c in item_map]
            save_watchlist(st.session_state.watchlist)
            st.rerun()

    st.divider()

# ----------------------------------------------------
# メイン画面
# ----------------------------------------------------
st.title("株価・信用残・機関空売りダッシュボード")

if "current_ticker" not in st.session_state:
    st.session_state.current_ticker = "6315"

ticker = st.text_input("銘柄コード（4桁）を入力してください", value=st.session_state.current_ticker)

if ticker != st.session_state.current_ticker:
    st.session_state.current_ticker = ticker

if ticker:
    clean_target = clean_ticker_code(ticker)
    
    period_option = st.selectbox(
        "表示期間を選択：",
        ["直近1ヶ月", "直近3ヶ月", "直半年", "1年"],
        index=0
    )
    days_map = {"直近1ヶ月": 30, "直近3ヶ月": 90, "直半年": 180, "1年": 365}
    selected_days = days_map[period_option]

    cutoff_date = datetime.date.today() - datetime.timedelta(days=selected_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    # 1. データ取得
    df_margin = load_data_from_sheet("margin")
    df_short = load_data_from_sheet("short")
    company_name = get_company_name_from_yahoo_japan(clean_target)
    stock_prices = get_stock_prices(clean_target)

    # 2. 銘柄ヘッダーとお気に入りボタン（見出しのすぐ右隣に配置）
    title_label = f"{clean_target}（{company_name}）" if company_name else clean_target
    fav_status = is_favorite(clean_target)
    btn_label = "★ 削除" if fav_status else "★ 追加"

    col_title, col_fav, col_empty = st.columns([0.45, 0.12, 0.43])
    with col_title:
        st.subheader(f"{title_label} のデータ分析")
    with col_fav:
        st.write("")
        if st.button(btn_label, use_container_width=True):
            toggle_favorite(clean_target, company_name)
            st.rerun()

    # 3. 銘柄コード・期間によるフィルタリング
    if not df_margin.empty and "銘柄コード" in df_margin.columns:
        df_margin['clean_code'] = df_margin['銘柄コード'].apply(clean_ticker_code)
        m_filtered = df_margin[df_margin['clean_code'] == clean_target].copy()
        if "日付" in m_filtered.columns:
            m_filtered = m_filtered[m_filtered["日付"] >= cutoff_str]
    else:
        m_filtered = pd.DataFrame()

    if not df_short.empty and "銘柄コード" in df_short.columns:
        df_short['clean_code'] = df_short['銘柄コード'].apply(clean_ticker_code)
        s_filtered = df_short[df_short['clean_code'] == clean_target].copy()
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        if date_col in s_filtered.columns:
            s_filtered = s_filtered[s_filtered[date_col] >= cutoff_str]
    else:
        s_filtered = pd.DataFrame()

    # 4. 日付軸とマッピングの構築
    all_dates = set()
    if not m_filtered.empty and "日付" in m_filtered.columns:
        all_dates.update(m_filtered["日付"].dropna().astype(str).tolist())
    if not s_filtered.empty:
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        all_dates.update(s_filtered[date_col].dropna().astype(str).tolist())

    sorted_dates = sorted(list(all_dates), reverse=True) if all_dates else [
        (datetime.date.today() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(15) if (datetime.date.today() - datetime.timedelta(days=i)).weekday() < 5
    ][:10]

    institutions = s_filtered["機関名"].dropna().unique().tolist() if not s_filtered.empty and "機関名" in s_filtered.columns else []

    # 機関データ辞書の構築
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
                try: shares = float(str(r.get("空売り残高数量", 0)).replace(',', ''))
                except: shares = 0
                prev = prev_shares_by_inst.get(inst, 0)
                diff = shares - prev if prev != 0 else 0
                prev_shares_by_inst[inst] = shares
                short_map[(d_str, inst)] = (shares, diff)
                daily_total += shares
            total_short_by_date[d_str] = daily_total

    # 個人信用辞書の構築（前日差自動計算）
    margin_map = {}
    if not m_filtered.empty and "日付" in m_filtered.columns:
        m_sorted = m_filtered.sort_values(by="日付", ascending=True)
        prev_sell = None
        prev_buy = None
        for _, r in m_sorted.iterrows():
            d_str = str(r.get("日付", ""))
            try: cur_sell = float(str(r.get("売残(合計)", 0)).replace(',', ''))
            except: cur_sell = 0
            try: cur_buy = float(str(r.get("買残(合計)", 0)).replace(',', ''))
            except: cur_buy = 0
            sell_diff = cur_sell - prev_sell if prev_sell is not None else 0
            buy_diff = cur_buy - prev_buy if prev_buy is not None else 0
            prev_sell, prev_buy = cur_sell, cur_buy
            margin_map[d_str] = {"row": r, "sell_diff": sell_diff, "buy_diff": buy_diff}

    # 5. グラフ用データの整形と描画（同一株数軸）
    graph_dates = sorted(sorted_dates)
    buy_shares_list = []
    sell_shares_list = []
    inst_shares_list = []
    vol_list = []
    vol_colors = []

    for d in graph_dates:
        m_info = margin_map.get(d)
        if m_info:
            r = m_info["row"]
            try: b_val = float(str(r.get("買残(合計)", 0)).replace(',', ''))
            except: b_val = None
            try: s_val = float(str(r.get("売残(合計)", 0)).replace(',', ''))
            except: s_val = None
        else:
            b_val, s_val = None, None
        buy_shares_list.append(b_val)
        sell_shares_list.append(s_val)
        inst_shares_list.append(total_short_by_date.get(d, None))

        p_info = stock_prices.get(d)
        if p_info:
            vol = p_info["volume"]
            pct = p_info["pct"]
            vol_list.append(vol)
            if pct > 0: vol_colors.append("rgba(239, 83, 80, 0.45)")     # 赤（プラス）
            elif pct < 0: vol_colors.append("rgba(66, 165, 245, 0.45)")  # 青（マイナス）
            else: vol_colors.append("rgba(189, 189, 189, 0.45)")
        else:
            vol_list.append(0)
            vol_colors.append("rgba(189, 189, 189, 0.30)")

    fig = render_combined_chart(graph_dates, buy_shares_list, sell_shares_list, inst_shares_list, vol_list, vol_colors, title_label)
    st.plotly_chart(fig, use_container_width=True)

    # 6. 機関一覧とHTMLテーブルの表示
    if institutions:
        inst_summary_html = render_institution_summary_html(institutions, title_label)
        components.html(inst_summary_html, height=min(180, 40 + len(institutions) * 28), scrolling=True)

    html_table = render_main_table_html(sorted_dates, institutions, short_map, total_short_by_date, margin_map, stock_prices)
    components.html(html_table, height=750, scrolling=True)
