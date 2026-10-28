import plotly.graph_objects as go
from analytics import SupplyDemandModel

def render_combined_chart(model: SupplyDemandModel, show_price_line: bool = True):
    """
    SupplyDemandModelから信用残・機関空売り・出来高および株価（右軸）を描画
    """
    fig = go.Figure()

    # 時系列データの展開（グラフ用：過去から未来への昇順）
    graph_dates = sorted(model.dates)
    
    vol_list = []
    vol_colors = []
    buy_shares = []
    sell_shares = []
    inst_shares = []
    price_list = []

    for d in graph_dates:
        # 1. 出来高・株価
        p_info = model.price_records.get(d)
        if p_info:
            vol = p_info.get("volume", 0)
            pct = p_info.get("pct", 0)
            close = p_info.get("close")
            vol_list.append(vol)
            price_list.append(close)
            if pct > 0:
                vol_colors.append("rgba(239, 83, 80, 0.45)")
            elif pct < 0:
                vol_colors.append("rgba(66, 165, 245, 0.45)")
            else:
                vol_colors.append("rgba(189, 189, 189, 0.45)")
        else:
            vol_list.append(0)
            vol_colors.append("rgba(189, 189, 189, 0.30)")
            price_list.append(None)

        # 2. 個人信用（買残・売残）
        m_info = model.margin_records.get(d)
        if m_info:
            r = m_info["row"]
            try: b_val = float(str(r.get("買残(合計)", 0)).replace(',', ''))
            except: b_val = None
            try: s_val = float(str(r.get("売残(合計)", 0)).replace(',', ''))
            except: s_val = None
        else:
            b_val, s_val = None, None
        buy_shares.append(b_val)
        sell_shares.append(s_val)

        # 3. 機関空売り合計
        inst_shares.append(model.total_short_by_date.get(d, None))

    # --- トレース追加 ---
    # 出来高（棒グラフ：前日比カラー、左軸）
    fig.add_trace(
        go.Bar(
            x=graph_dates, y=vol_list,
            name='出来高',
            marker=dict(color=vol_colors),
            hovertemplate='出来高: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

    # 個人買残（赤線、左軸）
    fig.add_trace(
        go.Scatter(
            x=graph_dates, y=buy_shares,
            mode='lines+markers', name='個人 買残合計',
            line=dict(color='#d32f2f', width=2),
            hovertemplate='買残: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

    # 個人売残（青線、左軸）
    fig.add_trace(
        go.Scatter(
            x=graph_dates, y=sell_shares,
            mode='lines+markers', name='個人 売残合計',
            line=dict(color='#1976d2', width=2),
            hovertemplate='売残: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

    # 機関空売り合計（オレンジ点線、左軸）
    if any(v is not None and v > 0 for v in inst_shares):
        fig.add_trace(
            go.Scatter(
                x=graph_dates, y=inst_shares,
                mode='lines+markers', name='機関空売り合計',
                line=dict(color='#ff9800', width=2, dash='dot'),
                hovertemplate='機関空売り: %{y:,.0f}株<extra></extra>',
                yaxis='y1'
            )
        )

    # 株価終値（濃グレー実線、右軸）※チェック時のみ描画
    if show_price_line and price_list and any(p is not None for p in price_list):
        fig.add_trace(
            go.Scatter(
                x=graph_dates, y=price_list,
                mode='lines+markers', name='株価 (終値)',
                line=dict(color='#37474f', width=2.5),
                marker=dict(size=5, color='#37474f'),
                hovertemplate='株価: %{y:,.1f}円<extra></extra>',
                yaxis='y2'
            )
        )

    # レイアウト設定
    layout_args = dict(
        title=f"{model.title_label} 信用残・機関空売り・出来高推移",
        dragmode=False,
        hovermode="x unified",
        margin=dict(l=40, r=50 if show_price_line else 40, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
        bargap=0.35,
        xaxis=dict(type='category', title_text="日付", fixedrange=True, hoverformat=""),
        yaxis=dict(title_text="株数（出来高 / 信用残）", fixedrange=True)
    )

    if show_price_line:
        layout_args["yaxis2"] = dict(
            title_text="株価（円）",
            overlaying="y",
            side="right",
            fixedrange=True,
            showgrid=False
        )

    fig.update_layout(**layout_args)
    return fig
