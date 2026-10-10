import plotly.graph_objects as go

def render_combined_chart(graph_dates, buy_shares, sell_shares, inst_shares, vol_list, vol_colors, title_label):
    """信用残・機関空売り・出来高を同一株数スケールで描画（ホバーから日付を排除）"""
    fig = go.Figure()

    # 1. 出来高（棒グラフ：前日比カラー）
    fig.add_trace(
        go.Bar(
            x=graph_dates, y=vol_list,
            name='出来高',
            marker=dict(color=vol_colors),
            hovertemplate='出来高: %{y:,.0f}株<extra></extra>'
        )
    )

    # 2. 個人買残（赤線）
    fig.add_trace(
        go.Scatter(
            x=graph_dates, y=buy_shares,
            mode='lines+markers', name='個人 買残合計',
            line=dict(color='#d32f2f', width=2),
            hovertemplate='買残: %{y:,.0f}株<extra></extra>'
        )
    )

    # 3. 個人売残（青線）
    fig.add_trace(
        go.Scatter(
            x=graph_dates, y=sell_shares,
            mode='lines+markers', name='個人 売残合計',
            line=dict(color='#1976d2', width=2),
            hovertemplate='売残: %{y:,.0f}株<extra></extra>'
        )
    )

    # 4. 機関空売り合計（オレンジ点線）
    if any(v is not None and v > 0 for v in inst_shares):
        fig.add_trace(
            go.Scatter(
                x=graph_dates, y=inst_shares,
                mode='lines+markers', name='機関空売り合計',
                line=dict(color='#ff9800', width=2, dash='dot'),
                hovertemplate='機関空売り: %{y:,.0f}株<extra></extra>'
            )
        )

    fig.update_layout(
        title=f"{title_label} 信用残・機関空売り・出来高推移（同一株数軸）",
        dragmode=False,  # ドラッグ操作（四角いズーム枠）を完全に無効化
        hovermode="closest",  # 各要素単体でスマートに表示（日付ヘッダーを非表示化）
        margin=dict(l=40, r=40, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
        bargap=0.35
    )
    # 軸のズーム・移動固定
    fig.update_xaxes(type='category', title_text="日付", fixedrange=True)
    fig.update_yaxes(title_text="株数（出来高 / 信用残）", fixedrange=True)
    return fig
