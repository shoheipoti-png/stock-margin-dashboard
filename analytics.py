"""
analytics.py
需給データ（個人信用、機関空売り、株価・出来高）の統合集計モデル
"""
import datetime
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any

class SupplyDemandModel:
    """銘柄の需給統合データモデル（純粋な数値・ステータスを保持）"""
    def __init__(
        self,
        ticker: str,
        company_name: str,
        dates: List[str],
        institutions: List[str],
        margin_records: Dict[str, Dict[str, Any]],
        short_records: Dict[Tuple[str, str], Tuple[float, float]],
        total_short_by_date: Dict[str, Optional[float]],
        daily_inst_data: Dict[Tuple[str, str], Dict[str, Any]],
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
        self.daily_inst_data = daily_inst_data
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

    # 1. フィルタリング（文字列高速マッチング）
    if not df_margin.empty and "銘柄コード" in df_margin.columns:
        m_code_series = df_margin['銘柄コード'].astype(str).str.split('.').str[0].str.strip()
        m_mask = (m_code_series == clean_target)
        if "日付" in df_margin.columns:
            m_mask &= (df_margin["日付"].astype(str) >= cutoff_str)
        m_filtered = df_margin[m_mask].copy()
    else:
        m_filtered = pd.DataFrame()

    if not df_short.empty and "銘柄コード" in df_short.columns:
        s_code_series = df_short['銘柄コード'].astype(str).str.split('.').str[0].str.strip()
        s_mask = (s_code_series == clean_target)
        date_col = "計算年月日" if "計算年月日" in df_short.columns else "公表日"
        if date_col in df_short.columns:
            s_mask &= (df_short[date_col].astype(str) >= cutoff_str)
        s_filtered = df_short[s_mask].copy()
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

    # 3. 個人信用辞書の構築（前日差計算）
    margin_records = {}
    if not m_filtered.empty and "日付" in m_filtered.columns:
        m_sorted = m_filtered.sort_values(by="日付", ascending=True)
        prev_sell = None
        prev_buy = None
        for _, r in m_sorted.iterrows():
            d_str = str(r.get("日付", ""))
            try: cur_sell = float(str(r.get("売残(合計)", 0)).replace(',', ''))
            except: cur_sell = 0.0
            try: cur_buy = float(str(r.get("買残(合計)", 0)).replace(',', ''))
            except: cur_buy = 0.0
            sell_diff = (cur_sell - prev_sell) if prev_sell is not None else 0.0
            buy_diff = (cur_buy - prev_buy) if prev_buy is not None else 0.0
            prev_sell, prev_buy = cur_sell, cur_buy
            margin_records[d_str] = {
                "row": r,
                "cur_sell": cur_sell,
                "cur_buy": cur_buy,
                "sell_diff": sell_diff,
                "buy_diff": buy_diff
            }

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
                except: shares = 0.0
                prev = prev_shares_by_inst.get(inst, 0.0)
                diff = (shares - prev) if prev != 0.0 else 0.0
                prev_shares_by_inst[inst] = shares
                short_records[(d_str, inst)] = (shares, diff)

    # 5. 全営業日キャリーオーバー＆合計残高の算出
    chronological_dates = list(reversed(sorted_dates))
    tracking_state = {inst: {"shares": 0.0, "status": "none"} for inst in institutions}
    running_inst_shares = {inst: 0.0 for inst in institutions}

    daily_inst_data = {}
    daily_total_estimated = {}
    total_short_by_date = {}

    has_started = False
    latest_date = sorted_dates[0] if sorted_dates else None

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
                    daily_inst_data[(d, inst)] = {
                        "shares": shares,
                        "diff": diff,
                        "is_confirmed": True,
                        "status": "active"
                    }
                    day_sum += shares
                else:
                    tracking_state[inst] = {"shares": 0.0, "status": "released"}
                    running_inst_shares[inst] = 0.0
                    daily_inst_data[(d, inst)] = {
                        "shares": 0.0,
                        "diff": 0.0,
                        "is_confirmed": True,
                        "status": "released"
                    }
            else:
                prev_status = tracking_state[inst]["status"]
                prev_shares = tracking_state[inst]["shares"]

                if is_pending_day:
                    daily_inst_data[(d, inst)] = {"shares": None, "diff": None, "is_confirmed": False, "status": "none"}
                elif has_started and prev_status == "active" and prev_shares > 0:
                    daily_inst_data[(d, inst)] = {"shares": prev_shares, "diff": None, "is_confirmed": False, "status": "active"}
                    day_sum += prev_shares
                elif prev_status == "released":
                    daily_inst_data[(d, inst)] = {"shares": None, "diff": None, "is_confirmed": False, "status": "released"}
                else:
                    daily_inst_data[(d, inst)] = {"shares": None, "diff": None, "is_confirmed": False, "status": "none"}

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
        daily_inst_data=daily_inst_data,
        daily_total_estimated=daily_total_estimated,
        price_records=stock_prices
    )
