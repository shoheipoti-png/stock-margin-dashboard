import streamlit as st
import streamlit.components.v1 as components
from chart_view import render_combined_chart
from table_view import render_main_table_html


def render_tv_panel(clean_target: str, prepare_data_func):
    """
    アプローチ2：TradingView 下部パネル専用のコンパクト描画モジュール
    （初期高さ360pxのパネル内にスクロールなしでグラフ全体が収まるよう最適化）
    """
    st.markdown("""
        <style>
            [data-testid="stSidebar"], [data-testid="collapsedControl"], header, footer {
                display: none !important;
            }
            .block-container {
                padding-top: 0.15rem !important;
                padding-bottom: 0rem !important;
                padding-left: 0.6rem !important;
                padding-right: 0.6rem !important;
            }
            /* コントロールバーとグラフの間の余白を詰める */
            [data-testid="stVerticalBlock"] {
                gap: 0.2rem !important;
            }
            /* セレクトボックス・チェックボックス周りの余白を最小化 */
            .stSelectbox, .stCheckbox {
                margin-bottom: 0 !important;
            }
        </style>
    """, unsafe_allow_html=True)

    if not clean_target:
        st.info("TradingViewで日本株の銘柄（4桁コード）を選択すると、ここに信用残・機関空売りグラフが表示されます。")
        return

    # 上部コンパクトコントロールバー
    c1, c2, c3, c4 = st.columns([0.22, 0.24, 0.22, 0.32])
    with c1:
        period_option = st.selectbox(
            "期間", ["直近1ヶ月", "直近3ヶ月", "直半年", "1年"], index=0, label_visibility="collapsed"
        )
    with c2:
        show_price = st.checkbox("📈 株価（右軸）", value=True)
    with c3:
        show_ratio = st.checkbox("⚖️ 信用倍率", value=False)
    with c4:
        show_table = st.checkbox("📋 需給テーブルも表示", value=False)

    # 共通関数でデータ取得・補完・モデル構築を一括実行
    _, _, model = prepare_data_func(clean_target, period_option)

    fig = render_combined_chart(
        model=model,
        show_price_line=show_price,
        show_margin_ratio=show_ratio
    )
    # パネル内にスクロールなしで収まるよう高さ・余白・タイトル位置を最適化
    fig.update_layout(
        height=225,
        margin=dict(l=35, r=45, t=28, b=18),
        title=dict(font=dict(size=13), y=0.97),
        xaxis=dict(title_text="")
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={'scrollZoom': False, 'displayModeBar': False, 'doubleClick': False}
    )

    if show_table:
        html_table = render_main_table_html(model=model)
        components.html(html_table, height=450, scrolling=True)
