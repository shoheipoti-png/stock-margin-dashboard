"""
analytics.py
需給データ（個人信用、機関空売り、株価・出来高）の統合集計モデル
"""
import datetime
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any

class SupplyDemandModel:
    """銘柄の需給統合データモデル"""
    def __init__(
        self,
        ticker: str,
        company_name: str,
        dates: List[str],
        institutions: List[str],
        margin_records: Dict[str, Dict[str, Any]],
        short_records: Dict[Tuple[str, str], Tuple[float, float]],
        total_short_by_date: Dict[str, Optional[float]],
        daily_inst_display: Dict[Tuple[str, str], Tuple[str, str, str, str, bool, str]],
        daily_total_estimated: Dict[str, Optional[float]],
        price_records: Dict[str, Dict[str, Any]]
    ):
        self.ticker = ticker
        self.company_name = company_name
        self.dates = dates  # 最新日付順 (降順)
        self.institutions = institutions
        self.margin_records = margin_records
        self.short_records = short_records
        self.total_short_by_date = total_short_by_date
        self.daily_inst_display = daily_inst_display
        self.daily_total_estimated = daily_total_estimated
        self.price_records = price_records

    @property
    def title_label(self) -> str:
        return f"{self.ticker}（{self.company_name}）" if self.company_name else self.ticker


def build_supply_demand_model(
    ticker: str,
    company_name: str,
    df_margin: pd.DataFrame,
    df_short: pd.DataFrame,
    stock_prices: Dict[str, Dict[str, Any]],
    cutoff_str: str,
    clean_ticker_func
) -> SupplyDemandModel:
    """
    生データ群から需給集計を行い、SupplyDemandModel を生成するファクトリ関数
    """
    clean_target = clean_ticker_func(ticker)

    # 1. フィルタリング
    if not df_margin.empty and "銘柄コード" in df_margin.columns:
        df_margin['clean_code'] = df_margin['銘柄コード'].apply(clean_ticker_func)
        m_filtered = df_margin[df_margin['clean_code'] == clean_target].copy()
        if "日付" in m_filtered.columns:
            m_filtered = m_filtered[m_filtered["日付"] >= cutoff_str]
    else:
        m_filtered = pd.DataFrame()

    if not df_short.empty and "銘柄コード" in df_short.columns:
        df_short['clean_code'] = df_short['銘柄コード'].apply(clean_ticker_func)
        s_filtered = df_short[df_short['clean_code'] == clean_target].copy()
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        if date_col in s_filtered.columns:
            s_filtered = s_filtered[s_filtered[date_col] >= cutoff_str]
    else:
        s_filtered = pd.DataFrame()

    # 2. 日付軸の統合
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

    # 3. 個人信用辞書の構築（前日差自動計算）
    margin_records = {}
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
            margin_records[d_str] = {"row": r, "sell_diff": sell_diff, "buy_diff": buy_diff}

    # 4. 機関空売り辞書と時系列差分の構築
    short_records = {}
    if not s_filtered.empty:
        date_col = "計算年月日" if "計算年月日" in s_filtered.columns else "公表日"
        s_sorted = s_filtered.sort_values(by=date_col, ascending=True)
        prev_shares_by_inst = {}
        for d, group in s_sorted.groupby(date_col):
            d_str = str(d)
            for _, r in group.iterrows():
                inst = r.get("機関名", "")
                try: shares = float(str(r.get("空売り残高数量", 0)).replace(',', ''))
                except: shares = 0
                prev = prev_shares_by_inst.get(inst, 0)
                diff = shares - prev if prev != 0 else 0
                prev_shares_by_inst[inst] = shares
                short_records[(d_str, inst)] = (shares, diff)

    # 5. 全営業日キャリーオーバー＆合計残高の算出
    chronological_dates = list(reversed(sorted_dates))
    tracking_state = {inst: {"shares": 0.0, "status": "none"} for inst in institutions}
    running_inst_shares = {inst: 0.0 for inst in institutions}

    daily_inst_display = {}
    daily_total_estimated = {}
    total_short_by_date = {}

    has_started = False
    latest_date = sorted_dates[0] if sorted_dates else None

    # ヘルパー関数: 表示フォーマット
    def fmt_smart(num):
        if abs(num) >= 1_000_000: return f"{num / 1_000_000:.2f}M"
        elif abs(num) >= 1_000: return f"{num / 1_000:.1f}K"
        return f"{int(num)}"

    def fmt_chg(num):
        if num == 0: return "0", "#666", "#f0f2f6"
        c = "#d32f2f" if num > 0 else "#1976d2"
        bg = "#ffebee" if num > 0 else "#e3f2fd"
        sign = "+" if num > 0 else ""
        if abs(num) >= 1_000_000: f_str = f"{sign}{num / 1_000_000:.2f}M"
        elif abs(num) >= 1_000: f_str = f"{sign}{num / 1_000:.1f}K"
        else: f_str = f"{sign}{int(num)}"
        return f_str, c, bg

    for d in chronological_dates:
        day_has_report = any((d, inst) in short_records for inst in institutions)
        if day_has_report:
            has_started = True

        day_sum = 0.0
        is_pending_day = (d == latest_date and not day_has_report)

        for inst in institutions:
            item = short_records.get((d, inst))
            if item:
                shares, diff = item
                if shares > 0:
                    tracking_state[inst] = {"shares": shares, "status": "active"}
                    running_inst_shares[inst] = shares
                    d_str, d_col, d_bg = fmt_chg(diff)
                    daily_inst_display[(d, inst)] = (fmt_smart(shares), d_str, d_col, d_bg, True, "active")
                    day_sum += shares
                else:
                    tracking_state[inst] = {"shares": 0.0, "status": "released"}
                    running_inst_shares[inst] = 0.0
                    daily_inst_display[(d, inst)] = ("<0.5%", "消失", "#888", "#f0f2f6", True, "released")
            else:
                prev_status = tracking_state[inst]["status"]
                prev_shares = tracking_state[inst]["shares"]

                if is_pending_day:
                    daily_inst_display[(d, inst)] = ("-", "-", "#888", "transparent", False, "none")
                elif has_started and prev_status == "active" and prev_shares > 0:
                    daily_inst_display[(d, inst)] = (f"({fmt_smart(prev_shares)})", "-", "#666", "transparent", False, "active")
                    day_sum += prev_shares
                elif prev_status == "released":
                    daily_inst_display[(d, inst)] = ("-", "-", "#888", "transparent", False, "released")
                else:
                    daily_inst_display[(d, inst)] = ("-", "-", "#888", "transparent", False, "none")

        if has_started and not is_pending_day:
            daily_total_estimated[d] = day_sum
            total_short_by_date[d] = sum(running_inst_shares.values())
        else:
            daily_total_estimated[d] = None
            total_short_by_date[d] = None

    return SupplyDemandModel(
        ticker=clean_target,
        company_name=company_name,
        dates=sorted_dates,
        institutions=institutions,
        margin_records=margin_records,
        short_records=short_records,
        total_short_by_date=total_short_by_date,
        daily_inst_display=daily_inst_display,
        daily_total_estimated=daily_total_estimated,
        price_records=stock_prices
    )
