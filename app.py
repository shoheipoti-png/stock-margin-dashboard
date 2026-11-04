import streamlit as st
import datetime
import streamlit.components.v1 as components

import data_loader
from analytics import build_supply_demand_model
from chart_view import render_combined_chart
from table_view import render_institution_summary_html, render_main_table_html
from watchlist_manager import (
    init_watchlist_state,
    is_favorite,
    toggle_favorite,
    render_watchlist_ui
)

clean_ticker_code = getattr(data_loader, "clean_ticker_code", lambda x: str(x)[:4])
load_data_from_sheet = getattr(data_loader, "load_data_from_sheet")
get_company_name_from_yahoo_japan = getattr(data_loader, "get_company_name_from_yahoo_japan")
get_stock_prices = getattr(data_loader, "get_stock_prices")
get_yahoo_realtime_and_pts = getattr(data_loader, "get_yahoo_realtime_and_pts")
get_fundamentals_summary = getattr(
    data_loader, 
    "get_fundamentals_summary", 
    lambda x: {
        "market": "-", "margin_type": "貸借", "market_cap": "-", 
        "industry": "-", "per": "-", "pbr": "-", "dividend_yield": "-", 
        "settlement_date": "-", "settlement_bg": "transparent", "settlement_color": "#333"
    }
)

st.set_page_config(page_title="株価・信用残・機関空売りダッシュボード", layout="wide")

init_watchlist_state()

# 画面表示モードの管理（需給ビュー / 詳細ビュー）
if "active_view" not in st.session_state:
    st.session_state.active_view = "supply_demand"

# 1. 左側サイドバー（ウォッチリスト）
with st.sidebar:
    st.header("📋 ウォッチリスト")
    st.caption("クリックで即時分析 / ✕で削除")
    render_watchlist_ui()
    st.divider()

# 2. メイン画面入力
st.title("株価・信用残・機関空売りダッシュボード")

if "current_ticker" not in st.session_state:
    st.session_state.current_ticker = "6315"

ticker = st.text_input("銘柄コード（4桁）を入力してください", value=st.session_state.current_ticker)

if ticker != st.session_state.current_ticker:
    st.session_state.current_ticker = ticker

if ticker:
    clean_target = clean_ticker_code(ticker)

    # 共通データ取得
    company_name = get_company_name_from_yahoo_japan(clean_target)
    title_label = f"{clean_target}（{company_name}）" if company_name else clean_target
    fav_status = is_favorite(clean_target)
    btn_label = "★ 削除" if fav_status else "★ 追加"

    # A. 銘柄詳細ビュー
    if st.session_state.active_view == "detail":
        col_back, col_d_title = st.columns([0.15, 0.85])
        with col_back:
            if st.button("⬅ 需給画面へ戻る", use_container_width=True):
                st.session_state.active_view = "supply_demand"
                st.rerun()
        with col_d_title:
            st.subheader(f"📑 {title_label} の詳細データ分析")

        st.info("💡 詳細データ分析画面（日証金速報・信用倍率推移など）は現在設計・準備中です。")

    # B. 通常画面（需給メインビュー）
    else:
        period_option = st.selectbox(
            "表示期間を選択：",
            ["直近1ヶ月", "直近3ヶ月", "直半年", "1年"],
            index=0
        )
        days_map = {"直近1ヶ月": 30, "直近3ヶ月": 90, "直半年": 180, "1年": 365}
        selected_days = days_map[period_option]

        cutoff_date = datetime.date.today() - datetime.timedelta(days=selected_days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        # 生データ取得
        df_margin = load_data_from_sheet("margin")
        df_short = load_data_from_sheet("short")
        stock_prices = get_stock_prices(clean_target)
        quote_info = get_yahoo_realtime_and_pts(clean_target)
        fund_info = get_fundamentals_summary(clean_target)

        # ヘッダーとお気に入りボタン ＋ 詳細画面切り替えボタン
        col_title, col_fav, col_detail, col_empty = st.columns([0.45, 0.12, 0.18, 0.25])
        with col_title:
            st.subheader(f"{title_label} のデータ分析")
        with col_fav:
            st.write("")
            if st.button(btn_label, use_container_width=True):
                toggle_favorite(clean_target, company_name)
                st.rerun()
        with col_detail:
            st.write("")
            if st.button("🔍 詳細データ ➔", use_container_width=True):
                st.session_state.active_view = "detail"
                st.rerun()

        # ファンダメンタルズ概要カード（決算アラート色バッジ対応）
        s_bg = fund_info.get("settlement_bg", "transparent")
        s_col = fund_info.get("settlement_color", "#333333")
        s_date = fund_info.get("settlement_date", "-")

        fund_html = f"""
        <div style="background-color: #f8f9fa; border: 1px solid #e1e4e8; border-radius: 6px; padding: 7px 12px; margin-bottom: 12px; font-size: 13px; color: #333; display: flex; flex-wrap: wrap; gap: 16px; align-items: center;">
            <div><span style="color: #666;">市場/貸借:</span> <b>{fund_info.get('market', '-')} / {fund_info.get('margin_type', '貸借')}</b></div>
            <div><span style="color: #666;">業種:</span> <b>{fund_info.get('industry', '-')}</b></div>
            <div><span style="color: #666;">時価総額:</span> <b>{fund_info.get('market_cap', '-')}</b></div>
            <div><span style="color: #666;">予想PER:</span> <b>{fund_info.get('per', '-')}</b></div>
            <div><span style="color: #666;">実績PBR:</span> <b>{fund_info.get('pbr', '-')}</b></div>
            <div><span style="color: #666;">配当利回り:</span> <b>{fund_info.get('dividend_yield', '-')}</b></div>
            <div>
                <span style="color: #666;">決算予定:</span> 
                <span style="background-color: {s_bg}; color: {s_col}; padding: 2px 6px; border-radius: 4px; font-weight: bold; display: inline-block;">
                    {s_date}
                </span>
            </div>
        </div>
        """
        st.markdown(fund_html, unsafe_allow_html=True)

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

        # 需給データモデル構築
        model = build_supply_demand_model(
            ticker=clean_target,
            company_name=company_name,
            df_margin=df_margin,
            df_short=df_short,
            stock_prices=stock_prices,
            cutoff_str=cutoff_str,
            clean_ticker_func=clean_ticker_code
        )

        # グラフ描画
        c_check, c_space = st.columns([0.4, 0.6])
        with c_check:
            show_price = st.checkbox("📈 株価推移（右軸）を表示", value=True)

        fig = render_combined_chart(model=model, show_price_line=show_price)
        st.plotly_chart(
            fig, 
            use_container_width=True, 
            config={'scrollZoom': False, 'displayModeBar': False, 'doubleClick': False}
        )

        # 機関一覧とメインテーブル描画
        if model.institutions:
            inst_summary_html = render_institution_summary_html(model.institutions, model.title_label)
            components.html(inst_summary_html, height=min(180, 40 + len(model.institutions) * 28), scrolling=True)

        html_table = render_main_table_html(model=model)
        components.html(html_table, height=750, scrolling=True)
