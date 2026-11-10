import plotly.graph_objects as go
from analytics import SupplyDemandModel

def render_combined_chart(
    model: SupplyDemandModel, 
    show_price_line: bool = True, 
    show_margin_ratio: bool = False
) -> go.Figure:
    """
    SupplyDemandModelを受け取り、信用残・機関空売り・出来高、株価（右軸）、信用倍率を描画
    （X軸の日付は 'MM-DD' 形式に整形）
    """
    raw_dates = sorted(model.dates)
    title_label = model.title_label

    # '2026-11-10' -> '11-10' に整形
    display_dates = [d[5:] if len(d) >= 10 and d[4] == '-' else d for d in raw_dates]

    vol_list = []
    vol_colors = []
    buy_shares = []
    sell_shares = []
    inst_shares = []
    price_list = []
    ratio_list = []

    for d in raw_dates:
        # 株価・出来高情報
        p_info = model.price_records.get(d)
        if p_info:
            vol = p_info.get("volume", 0)
            pct = p_info.get("pct", 0.0)
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

        # 個人信用残高 & 信用倍率
        m_info = model.margin_records.get(d)
        if m_info:
            b_val = m_info.get("cur_buy")
            s_val = m_info.get("cur_sell")
            buy_shares.append(b_val)
            sell_shares.append(s_val)
            if s_val and s_val > 0 and b_val is not None:
                ratio_list.append(round(b_val / s_val, 2))
            else:
                ratio_list.append(None)
        else:
            buy_shares.append(None)
            sell_shares.append(None)
            ratio_list.append(None)

        # 機関空売り合計
        inst_shares.append(model.total_short_by_date.get(d))

    fig = go.Figure()

    # 1. 出来高バー（左軸）
    fig.add_trace(
        go.Bar(
            x=display_dates,
            y=vol_list,
            name='出来高',
            marker=dict(color=vol_colors),
            hovertemplate='出来高: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

    # 2. 個人買残ライン（左軸）
    fig.add_trace(
        go.Scatter(
            x=display_dates,
            y=buy_shares,
            mode='lines+markers',
            name='個人 買残合計',
            line=dict(color='#d32f2f', width=2),
            hovertemplate='買残: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

    # 3. 個人売残ライン（左軸）
    fig.add_trace(
        go.Scatter(
            x=display_dates,
            y=sell_shares,
            mode='lines+markers',
            name='個人 売残合計',
            line=dict(color='#1976d2', width=2),
            hovertemplate='売残: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

    # 4. 機関空売り合計ライン（左軸・点線）
    if any(v is not None and v > 0 for v in inst_shares):
        fig.add_trace(
            go.Scatter(
                x=display_dates,
                y=inst_shares,
                mode='lines+markers',
                name='機関空売り合計',
                line=dict(color='#ff9800', width=2, dash='dot'),
                hovertemplate='機関空売り: %{y:,.0f}株<extra></extra>',
                yaxis='y1'
            )
        )

    # 5. 株価ライン（右軸 y2）
    if show_price_line and any(p is not None for p in price_list):
        fig.add_trace(
            go.Scatter(
                x=display_dates,
                y=price_list,
                mode='lines+markers',
                name='株価 (終値)',
                line=dict(color='#37474f', width=2.5),
                marker=dict(size=5, color='#37474f'),
                hovertemplate='株価: %{y:,.1f}円<extra></extra>',
                yaxis='y2'
            )
        )

    # 6. 信用倍率ライン
    target_ratio_yaxis = 'y3' if show_price_line else 'y2'
    if show_margin_ratio and any(r is not None for r in ratio_list):
        fig.add_trace(
            go.Scatter(
                x=display_dates,
                y=ratio_list,
                mode='lines+markers',
                name='信用倍率',
                line=dict(color='#8e24aa', width=2, dash='dash'),
                marker=dict(size=5, color='#8e24aa'),
                hovertemplate='信用倍率: %{y:.2f}倍<extra></extra>',
                yaxis=target_ratio_yaxis
            )
        )

    layout_args = dict(
        title=f"{title_label} 信用残・機関空売り・出来高推移",
        dragmode=False,
        hovermode="x unified",
        margin=dict(l=40, r=80 if (show_price_line and show_margin_ratio) else (50 if (show_price_line or show_margin_ratio) else 40), t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
        bargap=0.35,
        xaxis=dict(type='category', title_text="日付", fixedrange=True, tickangle=0),
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

    if show_margin_ratio:
        if show_price_line:
            layout_args["yaxis3"] = dict(
                title_text="信用倍率（倍）",
                overlaying="y",
                side="right",
                position=0.96,
                fixedrange=True,
                showgrid=False
            )
        else:
            layout_args["yaxis2"] = dict(
                title_text="信用倍率（倍）",
                overlaying="y",
                side="right",
                fixedrange=True,
                showgrid=False
            )

    fig.update_layout(**layout_args)
    return fig
