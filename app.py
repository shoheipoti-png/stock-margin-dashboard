import streamlit as st
import datetime
import streamlit.components.v1 as components

from data_loader import (
    clean_ticker_code,
    load_data_from_sheet,
    get_company_name_from_yahoo_japan,
    get_stock_prices,
    get_yahoo_realtime_and_pts
)
from analytics import build_supply_demand_model
from chart_view import render_combined_chart
from table_view import render_institution_summary_html, render_main_table_html
from watchlist_manager import (
    init_watchlist_state,
    is_favorite,
    toggle_favorite,
    render_watchlist_ui
)

st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")

init_watchlist_state()

# ----------------------------------------------------
# 1. 左側サイドバー（ウォッチリスト）
# ----------------------------------------------------
with st.sidebar:
    st.header("📋 ウォッチリスト")
    st.caption("クリックで即時分析 / ✕で削除")
    render_watchlist_ui()
    st.divider()

# ----------------------------------------------------
# 2. メイン画面入力
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

    # ----------------------------------------------------
    # 3. 生データ取得
    # ----------------------------------------------------
    df_margin = load_data_from_sheet("margin")
    df_short = load_data_from_sheet("short")
    company_name = get_company_name_from_yahoo_japan(clean_target)
    stock_prices = get_stock_prices(clean_target)
    quote_info = get_yahoo_realtime_and_pts(clean_target)

    # 銘柄ヘッダーとお気に入りボタン
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

    # リアルタイム株価 / 夜間PTSカード
    tse_price = f"{quote_info['price']} 円" if quote_info['price'] else "-"
    if quote_info['change_val'] and quote_info['change_pct']:
        tse_delta = f"{quote_info['change_val']} ({quote_info['change_pct']})"
    elif quote_info['change_val']:
        tse_delta = quote_info['change_val']
    elif quote_info['change_pct']:
        tse_delta = quote_info['change_pct']
    else:
        tse_delta = None

    pts_price = f"{quote_info['pts_price']} 円" if quote_info['pts_price'] else "-"
    if quote_info['pts_diff_val'] and quote_info['pts_diff_pct']:
        pts_delta = f"{quote_info['pts_diff_val']} ({quote_info['pts_diff_pct']})"
    elif quote_info['pts_diff_val']:
        pts_delta = quote_info['pts_diff_val']
    elif quote_info['pts_diff_pct']:
        pts_delta = quote_info['pts_diff_pct']
    else:
        pts_delta = None

    q_col1, q_col2, q_empty = st.columns([0.30, 0.30, 0.40])
    with q_col1:
        st.metric(label="リアルタイム株価 / 前日比・騰落率", value=tse_price, delta=tse_delta)
    with q_col2:
        st.metric(label="夜間PTS株価 / 東証終値比", value=pts_price, delta=pts_delta)

    # ----------------------------------------------------
    # 4. 需給データモデルの構築（集計ロジックを1行で集約）
    # ----------------------------------------------------
    model = build_supply_demand_model(
        ticker=clean_target,
        company_name=company_name,
        df_margin=df_margin,
        df_short=df_short,
        stock_prices=stock_prices,
        cutoff_str=cutoff_str,
        clean_ticker_func=clean_ticker_code
    )

    # ----------------------------------------------------
    # 5. グラフ描画
    # ----------------------------------------------------
    c_check, c_space = st.columns([0.4, 0.6])
    with c_check:
        show_price = st.checkbox("📈 株価推移（右軸）を表示", value=True)

    fig = render_combined_chart(model=model, show_price_line=show_price)
    st.plotly_chart(
        fig, 
        use_container_width=True, 
        config={'scrollZoom': False, 'displayModeBar': False, 'doubleClick': False}
    )

    # ----------------------------------------------------
    # 6. 機関一覧とメインテーブル描画
    # ----------------------------------------------------
    if model.institutions:
        inst_summary_html = render_institution_summary_html(model.institutions, model.title_label)
        components.html(inst_summary_html, height=min(180, 40 + len(model.institutions) * 28), scrolling=True)

    html_table = render_main_table_html(model=model)
    components.html(html_table, height=750, scrolling=True)
