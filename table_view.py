import datetime

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
    if not full_name: return "その他"
    fn_lower = str(full_name).lower()
    for key, val in INSTITUTION_SHORT_NAMES.items():
        if key in fn_lower: return val
    return str(full_name)[:6]

def smart_format(val):
    try:
        if val == "" or val is None or val == "-": return "-"
        num = float(str(val).replace(',', ''))
        if abs(num) >= 1_000_000: return f"{num / 1_000_000:.1f}M"
        elif abs(num) >= 1_000: return f"{num / 1_000:.1f}K"
        else: return f"{int(num)}"
    except:
        return str(val)

def format_change(num):
    try:
        if num == "" or num is None or num == "-": return "-", "#666", "transparent"
        val = float(str(num).replace(',', ''))
        if val == 0: return "0", "#666", "#f0f2f6"
        color = "#d32f2f" if val > 0 else "#1976d2"
        bg = "#ffebee" if val > 0 else "#e3f2fd"
        sign = "+" if val > 0 else ""
        if abs(val) >= 1_000_000: formatted = f"{sign}{val / 1_000_000:.1f}M"
        elif abs(val) >= 1_000: formatted = f"{sign}{val / 1_000:.1f}K"
        else: formatted = f"{sign}{int(val)}"
        return formatted, color, bg
    except:
        return str(num), "#666", "#f0f2f6"

def format_pct(num):
    try:
        val = float(num)
        if val == 0: return "0.0%", "#666"
        color = "#d32f2f" if val > 0 else "#1976d2"
        sign = "+" if val > 0 else ""
        return f"{sign}{val:.1f}%", color
    except:
        return "-", "#666"

def render_institution_summary_html(institutions, title_label):
    """上部の機関参加一覧ボックス（スマホのダークモード強制反転をブロック）"""
    if not institutions:
        return ""
    
    rows_html = ""
    for idx, inst in enumerate(institutions, 1):
        rows_html += f"""
            <tr style="background-color: #ffffff !important; color: #1a1a1a !important;">
                <td style="padding: 6px 8px; border: 1px solid #ddd; text-align: center; font-weight: bold; color: #333333 !important; background-color: #f7f9fa !important; width: 50px;">{idx}</td>
                <td style="padding: 6px 12px; border: 1px solid #ddd; text-align: left; font-size: 13px; font-weight: 500; color: #1a1a1a !important; background-color: #ffffff !important;">{inst}</td>
            </tr>
        """
        
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <meta name="color-scheme" content="light">
    <style>
      :root {{ color-scheme: light; }}
      body {{ margin: 0; padding: 0; background-color: #ffffff !important; color: #1a1a1a !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
      table {{ width: 100%; border-collapse: collapse; background-color: #ffffff !important; }}
      th, td {{ color: #1a1a1a !important; }}
    </style>
    </head>
    <body>
    <div style="margin-bottom: 8px; border: 1px solid #d0d7de; border-radius: 6px; overflow: hidden; background-color: #ffffff !important;">
        <div style="background-color: #262730 !important; color: #ffffff !important; padding: 7px 12px; font-weight: bold; font-size: 13px;">
            🏢 {title_label} 空売り参加機関一覧 ({len(institutions)}社)
        </div>
        <table>
            <thead>
                <tr style="background-color: #f0f2f6 !important; color: #333333 !important;">
                    <th style="padding: 5px 8px; border: 1px solid #ddd; width: 50px; text-align: center; font-size: 12px; color: #333333 !important;">No.</th>
                    <th style="padding: 5px 12px; border: 1px solid #ddd; text-align: left; font-size: 12px; color: #333333 !important;">空売り機関名</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    </body>
    </html>
    """
    return html

def render_main_table_html(sorted_dates, institutions, short_map, total_short_by_date, margin_map, stock_prices):
    """メインHTMLテーブル（スマホのダークモード強制反転をブロック）"""
    inst_count = len(institutions)
    
    header_tr1 = (
        '<tr style="background-color: #262730 !important; color: #ffffff !important;">'
        '<th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 8%; color: #ffffff !important;">Date</th>'
        '<th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 10%; color: #ffffff !important;">前日比<br>出来高</th>'
    )
    if inst_count > 0:
        header_tr1 += f'<th colspan="{inst_count}" style="border: 1px solid #444; padding: 8px; text-align: center; color: #ffffff !important;">機関投資家の空売り</th>'
    header_tr1 += (
        '<th rowspan="2" style="border: 1px solid #444; padding: 10px; text-align: center; width: 8%; color: #ffffff !important;">全増減</th>'
        '<th colspan="2" style="border: 1px solid #444; padding: 8px; text-align: center; color: #ffffff !important;">個人信用 (合計・前日差・内訳)</th>'
        '</tr>'
    )

    header_tr2 = '<tr style="background-color: #3b3c43 !important; color: #ffffff !important;">'
    for idx, inst in enumerate(institutions, 1):
        short_label = get_short_inst_name(inst)
        header_tr2 += f'<th style="border: 1px solid #555; padding: 6px; text-align: center; color: #ffffff !important;" title="{inst}">{idx}<br>{short_label}</th>'
    header_tr2 += (
        '<th style="border: 1px solid #555; padding: 6px; text-align: center; width: 18%; color: #ffffff !important;">売</th>'
        '<th style="border: 1px solid #555; padding: 6px; text-align: center; width: 18%; color: #ffffff !important;">買</th>'
        '</tr>'
    )

    rows_html = []
    for i, d in enumerate(sorted_dates):
        try:
            dt = datetime.datetime.strptime(d, "%Y-%m-%d")
            date_str = dt.strftime("%m/%d<br>%a")
        except:
            date_str = d

        # 株価・出来高
        price_info = stock_prices.get(d)
        if price_info:
            pct_str, pct_color = format_pct(price_info["pct"])
            vol_str = smart_format(price_info["volume"])
            price_cell_html = (
                f'<div style="font-weight: bold; color: {pct_color} !important; font-size: 0.95em;">{pct_str}</div>'
                f'<div style="color: #666666 !important; font-size: 0.8em; margin-top: 2px;">{vol_str}</div>'
            )
        else:
            price_cell_html = '<div style="color: #666666 !important;">-</div>'

        # 機関列
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
                    '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 6px; background-color: #ffffff !important; color: #1a1a1a !important;">'
                    f'<div style="font-weight: bold; font-size: 0.95em; color: #1a1a1a !important;">{sh_str}</div>'
                    f'<div style="color: {d_col} !important; background-color: {d_bg} !important; font-size: 0.8em; padding: 1px; border-radius: 2px;">{d_str}</div>'
                    '</td>'
                )
            else:
                inst_tds += '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 6px; background-color: #ffffff !important; color: #888888 !important;">-</td>'

        # 全増減
        prev_d = sorted_dates[i+1] if i + 1 < len(sorted_dates) else None
        prev_sum = total_short_by_date.get(prev_d, 0) if prev_d else 0
        cur_sum = total_short_by_date.get(d, 0)
        
        if cur_sum > 0:
            all_diff = cur_sum - prev_sum if prev_sum > 0 else 0
            all_diff_str, all_diff_col, all_diff_bg = format_change(all_diff)
            all_change_html = f'<div style="color: {all_diff_col} !important; background-color: {all_diff_bg} !important; font-size: 0.85em; padding: 2px; border-radius: 2px;">{all_diff_str}</div>'
        else:
            all_change_html = '<div style="color: #666666 !important;">-</div>'

        # 個人信用
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
            '<tr style="background-color: #ffffff !important;">'
            f'<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #ffffff !important; color: #1a1a1a !important;">{date_str}</td>'
            f'<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #ffffff !important; color: #1a1a1a !important;">{price_cell_html}</td>'
            f'{inst_tds}'
            f'<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #ffffff !important; color: #1a1a1a !important;">{all_change_html}</td>'
            '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #ffffff !important; color: #1a1a1a !important;">'
            f'<div style="font-weight: bold; font-size: 1.05em; color: #1a1a1a !important;">{tot_sell}</div>'
            f'<div style="color: {sell_chg_color} !important; background-color: {sell_chg_bg} !important; font-size: 0.85em; padding: 2px; margin: 3px 0; border-radius: 2px;">{sell_chg_str}</div>'
            f'<div style="color: #666666 !important; font-size: 0.75em;">般: {gen_sell} / 制: {std_sell}</div>'
            '</td>'
            '<td style="text-align: center; vertical-align: middle; border: 1px solid #ddd; padding: 8px; background-color: #ffffff !important; color: #1a1a1a !important;">'
            f'<div style="font-weight: bold; font-size: 1.05em; color: #1a1a1a !important;">{tot_buy}</div>'
            f'<div style="color: {buy_chg_color} !important; background-color: {buy_chg_bg} !important; font-size: 0.85em; padding: 2px; margin: 3px 0; border-radius: 2px;">{buy_chg_str}</div>'
            f'<div style="color: #666666 !important; font-size: 0.75em;">般: {gen_buy} / 制: {std_buy}</div>'
            '</td>'
            '</tr>'
        )
        rows_html.append(row_html)

    body_content = "".join(rows_html)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light">'
        '<style>:root { color-scheme: light; } body { margin:0; background:#fff !important; color:#1a1a1a !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }</style>'
        '</head><body>'
        '<table style="width:100%; border-collapse: collapse; font-size: 13px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); background-color: #ffffff !important;">'
        f'<thead>{header_tr1}{header_tr2}</thead>'
        f'<tbody>{body_content}</tbody>'
        '</table></body></html>'
    )
