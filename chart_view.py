import plotly.graph_objects as go

def render_combined_chart(*args, **kwargs):
    """
    信用残・機関空売り・出来高および株価（右軸）を描画
    """
    # 引数の安全な取得
    if "model" in kwargs:
        model = kwargs["model"]
        show_price_line = kwargs.get("show_price_line", True)
    elif len(args) > 0 and hasattr(args[0], "dates"):
        model = args[0]
        show_price_line = args[1] if len(args) > 1 else kwargs.get("show_price_line", True)
    else:
        # 旧形式の引数フォールバック
        graph_dates = args[0] if len(args) > 0 else kwargs.get("graph_dates", [])
        buy_shares = args[1] if len(args) > 1 else kwargs.get("buy_shares", [])
        sell_shares = args[2] if len(args) > 2 else kwargs.get("sell_shares", [])
        inst_shares = args[3] if len(args) > 3 else kwargs.get("inst_shares", [])
        vol_list = args[4] if len(args) > 4 else kwargs.get("vol_list", [])
        vol_colors = args[5] if len(args) > 5 else kwargs.get("vol_colors", [])
        title_label = args[6] if len(args) > 6 else kwargs.get("title_label", "")
        price_list = kwargs.get("price_list", args[7] if len(args) > 7 else None)
        show_price_line = kwargs.get("show_price_line", args[8] if len(args) > 8 else True)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=graph_dates, y=vol_list, name='出来高', marker=dict(color=vol_colors), hovertemplate='出来高: %{y:,.0f}株<extra></extra>', yaxis='y1'))
        fig.add_trace(go.Scatter(x=graph_dates, y=buy_shares, mode='lines+markers', name='個人 買残合計', line=dict(color='#d32f2f', width=2), hovertemplate='買残: %{y:,.0f}株<extra></extra>', yaxis='y1'))
        fig.add_trace(go.Scatter(x=graph_dates, y=sell_shares, mode='lines+markers', name='個人 売残合計', line=dict(color='#1976d2', width=2), hovertemplate='売残: %{y:,.0f}株<extra></extra>', yaxis='y1'))
        if any(v is not None and v > 0 for v in inst_shares):
            fig.add_trace(go.Scatter(x=graph_dates, y=inst_shares, mode='lines+markers', name='機関空売り合計', line=dict(color='#ff9800', width=2, dash='dot'), hovertemplate='機関空売り: %{y:,.0f}株<extra></extra>', yaxis='y1'))
        if show_price_line and price_list and any(p is not None for p in price_list):
            fig.add_trace(go.Scatter(x=graph_dates, y=price_list, mode='lines+markers', name='株価 (終値)', line=dict(color='#37474f', width=2.5), marker=dict(size=5, color='#37474f'), hovertemplate='株価: %{y:,.1f}円<extra></extra>', yaxis='y2'))

        layout_args = dict(
            title=f"{title_label} 信用残・機関空売り・出来高推移",
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
            layout_args["yaxis2"] = dict(title_text="株価（円）", overlaying="y", side="right", fixedrange=True, showgrid=False)
        fig.update_layout(**layout_args)
        return fig

    # Modelオブジェクトからの描画
    graph_dates = sorted(model.dates)
    title_label = model.title_label
    
    vol_list = []
    vol_colors = []
    buy_shares = []
    sell_shares = []
    inst_shares = []
    price_list = []

    for d in graph_dates:
        p_info = model.price_records.get(d)
        if p_info:
            vol = p_info.get("volume", 0)
            pct = p_info.get("pct", 0)
            close = p_info.get("close")
            vol_list.append(vol)
            price_list.append(close)
            if pct > 0: vol_colors.append("rgba(239, 83, 80, 0.45)")
            elif pct < 0: vol_colors.append("rgba(66, 165, 245, 0.45)")
            else: vol_colors.append("rgba(189, 189, 189, 0.45)")
        else:
            vol_list.append(0)
            vol_colors.append("rgba(189, 189, 189, 0.30)")
            price_list.append(None)

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

        inst_shares.append(model.total_short_by_date.get(d, None))

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=graph_dates, y=vol_list,
            name='出来高',
            marker=dict(color=vol_colors),
            hovertemplate='出来高: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

    fig.add_trace(
        go.Scatter(
            x=graph_dates, y=buy_shares,
            mode='lines+markers', name='個人 買残合計',
            line=dict(color='#d32f2f', width=2),
            hovertemplate='買残: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

    fig.add_trace(
        go.Scatter(
            x=graph_dates, y=sell_shares,
            mode='lines+markers', name='個人 売残合計',
            line=dict(color='#1976d2', width=2),
            hovertemplate='売残: %{y:,.0f}株<extra></extra>',
            yaxis='y1'
        )
    )

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

    layout_args = dict(
        title=f"{title_label} 信用残・機関空売り・出来高推移",
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
