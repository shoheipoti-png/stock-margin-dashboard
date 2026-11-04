import os
import json
import re
import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import streamlit as st

DEFAULT_SPREADSHEET_ID = "1_YK99EVmXnTWHzE7oP9tO1jWYaxUiTinMyFQ-1n2M4g"
DEFAULT_SHORT_SPREADSHEET_ID = "1Fdfmwq_6CBAG495JJD4EPgT7EOfyB9kZ_QAwU6pAXaU"

JPX_33_SECTORS = [
    "水産・農林業", "鉱業", "建設業", "食料品", "繊維製品", "パルプ・紙", "化学",
    "医薬品", "石油・石炭製品", "ゴム製品", "ガラス・土石製品", "鉄鋼", "非鉄金属",
    "金属製品", "機械", "電気機器", "輸送用機器", "精密機器", "その他製品",
    "電気・ガス業", "陸運業", "海運業", "空運業", "倉庫・運輸関連業", "情報・通信業",
    "卸売業", "小売業", "銀行業", "証券、商品先物取引業", "保険業", "その他金融業",
    "不動産業", "サービス業"
]

def clean_ticker_code(val):
    if pd.isna(val) or val is None:
        return ""
    s = str(val).split('.')[0].strip().upper()
    return s[:4] if len(s) >= 4 else s

def deduce_quarter(fiscal_month: int, announce_month: int) -> str:
    """決算月と発表予定月から第何四半期かを判定"""
    diff = (announce_month - fiscal_month) % 12
    if diff in [1, 2, 3]:
        return " (本決算)"
    elif diff in [4, 5, 6]:
        return " (Q1)"
    elif diff in [7, 8, 9]:
        return " (Q2)"
    elif diff in [10, 11, 0]:
        return " (Q3)"
    return ""

@st.cache_data(ttl=60)
def load_data_from_sheet(sheet_type="margin"):
    """Googleスプレッドシートからデータを取得"""
    try:
        creds_raw = st.secrets.get("GCP_SERVICE_ACCOUNT_KEY") or os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
        if not creds_raw:
            return pd.DataFrame()
        if isinstance(creds_raw, dict):
            creds_dict = creds_raw
        elif hasattr(creds_raw, "to_dict"):
            creds_dict = creds_raw.to_dict()
        else:
            creds_dict = json.loads(str(creds_raw).strip())

        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        sheet_id = DEFAULT_SPREADSHEET_ID if sheet_type == "margin" else DEFAULT_SHORT_SPREADSHEET_ID
        worksheet = client.open_by_key(sheet_id).sheet1
        return pd.DataFrame(worksheet.get_all_records())
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_company_name_from_yahoo_japan(ticker_code):
    """Yahoo!ファイナンス（日本）から銘柄名を確実にスクレイピング"""
    clean_code = clean_ticker_code(ticker_code)
    url = f"https://finance.yahoo.co.jp/quote/{clean_code}.T"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            title_text = soup.title.string if soup.title else ""
            if "【" in title_text:
                raw_name = title_text.split("【")[0].strip()
                return raw_name.replace("(株)", "").replace("（株）", "").replace("ホールディングス", "HD").strip()
            h1 = soup.find('h1')
            if h1:
                return h1.text.split("【")[0].replace("(株)", "").replace("（株）", "").replace("ホールディングス", "HD").strip()
    except Exception:
        pass
    return ""

@st.cache_data(ttl=60)
def get_yahoo_realtime_and_pts(ticker_code):
    """Yahoo!ファイナンスから東証株価・前日比・騰落率および夜間PTS情報を完全抽出"""
    clean_code = clean_ticker_code(ticker_code)
    url = f"https://finance.yahoo.co.jp/quote/{clean_code}.T"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    result = {
        "price": None,
        "change_val": None,
        "change_pct": None,
        "pts_price": None,
        "pts_diff_val": None,
        "pts_diff_pct": None,
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return result
        
        soup = BeautifulSoup(res.text, 'html.parser')

        price_box = soup.find(class_=re.compile(r'CommonPriceBoard__price\b|CommonPriceBoard__price__'))
        if price_box:
            val_span = price_box.find('span', class_=re.compile(r'StyledNumber__value'))
            if val_span:
                result["price"] = val_span.get_text().strip()
        
        if not result["price"]:
            for sp in soup.find_all(class_=re.compile(r'[Pp]rice')):
                val_span = sp.find('span', class_=re.compile(r'StyledNumber__value'))
                if val_span:
                    txt = val_span.get_text().strip()
                    if re.match(r'^[1-9][0-9]{0,2}(?:,[0-9]{3})+(?:\.[0-9]+)?$', txt):
                        result["price"] = txt
                        break

        primary_box = soup.find(class_=re.compile(r'PriceChangeLabel__primary'))
        if primary_box:
            val_span = primary_box.find('span', class_=re.compile(r'StyledNumber__value'))
            if val_span:
                result["change_val"] = val_span.get_text().strip()

        all_secondary = soup.find_all(class_=re.compile(r'PriceChangeLabel__secondary'))
        if all_secondary:
            pct_span = all_secondary[0].find('span', class_=re.compile(r'StyledNumber__value'))
            if pct_span:
                raw_pct = pct_span.get_text().strip()
                result["change_pct"] = f"{raw_pct}%" if not raw_pct.endswith('%') else raw_pct

        pts_price_box = soup.find(class_=re.compile(r'CommonPriceBoard__ptsPrice'))
        if pts_price_box:
            pts_val_span = pts_price_box.find('span', class_=re.compile(r'StyledNumber__value'))
            if pts_val_span:
                result["pts_price"] = pts_val_span.get_text().strip()

        pts_label = soup.find(class_=re.compile(r'CommonPriceBoard__ptsLabel'))
        if pts_label:
            pts_parent = pts_label.find_parent('li') or pts_label.find_parent('div') or pts_label.parent
            if pts_parent:
                pts_sec = pts_parent.find_all(class_=re.compile(r'PriceChangeLabel'))
                for sec in pts_sec:
                    sec_text = sec.get_text().strip()
                    m = re.search(r'([+-]?[0-9,]+(?:\.[0-9]+)?)\s*\(?([+-]?[0-9.]+[%％]?)\)?', sec_text)
                    if m:
                        result["pts_diff_val"] = m.group(1).strip()
                        pct_val = m.group(2).strip()
                        result["pts_diff_pct"] = f"{pct_val}%" if not pct_val.endswith('%') else pct_val
                        break
                    
                    vals = sec.find_all('span', class_=re.compile(r'StyledNumber__value'))
                    if len(vals) >= 2:
                        result["pts_diff_val"] = vals[0].get_text().strip()
                        pct_v = vals[1].get_text().strip()
                        result["pts_diff_pct"] = f"{pct_v}%" if not pct_v.endswith('%') else pct_v
                        break
                    elif len(vals) == 1:
                        txt = vals[0].get_text().strip()
                        if '.' in txt:
                            result["pts_diff_pct"] = f"{txt}%" if not txt.endswith('%') else txt
                        else:
                            result["pts_diff_val"] = txt

    except Exception as e:
        print(f"Yahoo取得エラー ({ticker_code}): {e}")

    return result

@st.cache_data(ttl=3600)
def get_stock_prices(ticker_code):
    """yfinanceから株価履歴（終値・騰落率・出来高）を取得"""
    clean_code = clean_ticker_code(ticker_code)
    prices = {}
    try:
        stock = yf.Ticker(f"{clean_code}.T")
        hist = stock.history(period="1y")
        if not hist.empty:
            hist = hist.sort_index(ascending=True)
            hist['Pct'] = hist['Close'].pct_change() * 100
            for dt, row in hist.iterrows():
                d_str = dt.strftime("%Y-%m-%d")
                prices[d_str] = {
                    "close": float(row['Close']) if pd.notna(row['Close']) else None,
                    "pct": row['Pct'] if pd.notna(row['Pct']) else 0.0,
                    "volume": int(row['Volume']) if pd.notna(row['Volume']) else 0
                }
    except Exception:
        pass
    return prices

@st.cache_data(ttl=21600)
def get_fundamentals_summary(ticker_code):
    """
    Yahoo!ファイナンスから主要ファンダメンタルズ概要を抽出（6時間キャッシュ）
    市場、時価総額、業種、PER、PBR、配当利回り、決算予定日（未発表時は直近発表実績を自動表示）
    """
    clean_code = clean_ticker_code(ticker_code)
    data = {
        "market": "-",
        "margin_type": "貸借",
        "market_cap": "-",
        "industry": "-",
        "per": "-",
        "pbr": "-",
        "dividend_yield": "-",
        "settlement_date": "-"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    fiscal_month = 3
    today_str = datetime.date.today().strftime("%Y/%m/%d")
    future_settle_date = None
    future_announce_month = None

    # 1. トップページから各種指標と「次回決算予定日」を取得
    url_quote = f"https://finance.yahoo.co.jp/quote/{clean_code}.T"
    try:
        res = requests.get(url_quote, headers=headers, timeout=6)
        if res.status_code == 200:
            page_text = res.text
            soup = BeautifulSoup(page_text, 'html.parser')

            # 決算期（月）の判定
            m_fisc = re.search(r'(?:決算期|決算月|事業年度)[^0-9]*(\d{1,2})月', page_text)
            if m_fisc:
                fiscal_month = int(m_fisc.group(1))

            # 市場判定
            m_market = re.search(r'東証(プライム|スタンダード|グロース)', page_text)
            if m_market:
                data["market"] = m_market.group(1)
            else:
                m_gen = re.search(r'([A-Za-z0-9\u3000-\u9fff]+市場|名証|福証|札証)', page_text)
                if m_gen:
                    data["market"] = m_gen.group(1)

            # 定義リストや行単位で各項目を特定
            for row in soup.find_all(['li', 'tr', 'div']):
                dt = row.find(['dt', 'th', 'span'])
                dd = row.find(['dd', 'td'])
                if not dt or not dd:
                    continue
                label = dt.get_text().strip()
                val = dd.get_text().strip()

                if "時価総額" in label and data["market_cap"] == "-":
                    m_cap = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*(兆|億|百万円)', val)
                    if m_cap:
                        val_num = float(m_cap.group(1).replace(',', ''))
                        unit = m_cap.group(2)
                        if unit == "百万円":
                            oku = val_num / 100.0
                            if oku >= 10000:
                                data["market_cap"] = f"{oku / 10000:.2f}兆円"
                            else:
                                data["market_cap"] = f"{int(oku):,}億円"
                        else:
                            data["market_cap"] = f"{m_cap.group(1)}{unit}円"

                if ("PER" in label or "ＰＥＲ" in label) and data["per"] == "-":
                    m_per = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*倍', val)
                    if m_per:
                        data["per"] = f"{m_per.group(1)}倍"

                if ("PBR" in label or "ＰＢＲ" in label) and data["pbr"] == "-":
                    m_pbr = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*倍', val)
                    if m_pbr:
                        data["pbr"] = f"{m_pbr.group(1)}倍"

                if ("配当利回り" in label or "利回り" in label) and data["dividend_yield"] == "-":
                    m_div = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*[%％]', val)
                    if m_div:
                        data["dividend_yield"] = f"{m_div.group(1)}%"

                # 決算発表予定日（明確にラベル付けされた値のみチェック）
                if "決算発表" in label and future_settle_date is None:
                    m_date = re.search(r'(\d{4})[/-](\d{1,2})[/-](0?[1-9]|[12][0-9]|3[01])\b', val)
                    if m_date:
                        y = m_date.group(1)
                        m = int(m_date.group(2))
                        d = int(m_date.group(3))
                        cand_date = f"{y}/{m:02d}/{d:02d}"
                        # 本日以降の未来日付である場合のみ「次回予定」として採用
                        if cand_date >= today_str:
                            future_settle_date = cand_date
                            future_announce_month = m

            if "制度信用" in page_text and "貸借" not in page_text:
                data["margin_type"] = "制度"
            elif "貸借" in page_text:
                data["margin_type"] = "貸借"
    except Exception as e:
        print(f"Yahooファンダ取得エラー ({ticker_code}): {e}")

    # 2. プロファイルページから「業種」と「本決算月」を取得
    url_profile = f"https://finance.yahoo.co.jp/quote/{clean_code}.T/profile"
    try:
        res_prof = requests.get(url_profile, headers=headers, timeout=5)
        if res_prof.status_code == 200:
            prof_soup = BeautifulSoup(res_prof.text, 'html.parser')
            for a_tag in prof_soup.find_all(['a', 'dd', 'td', 'span']):
                txt = a_tag.get_text().strip()
                if txt in JPX_33_SECTORS:
                    data["industry"] = txt

            p_text = res_prof.text
            m_fisc_p = re.search(r'決算期[^0-9]*(\d{1,2})月', p_text)
            if m_fisc_p:
                fiscal_month = int(m_fisc_p.group(1))
    except Exception as e:
        print(f"Yahooプロファイル取得エラー ({ticker_code}): {e}")

    # 3. 決算日の確定
    if future_settle_date:
        # A. 次回予定が公表されている場合（未来の日付）
        q_label = deduce_quarter(fiscal_month, future_announce_month) if future_announce_month else ""
        data["settlement_date"] = f"{future_settle_date}{q_label}"
    else:
        # B. 次回予定が未定（直近決算を終えたばかり）の場合：直近実績日を取得
        url_fin = f"https://finance.yahoo.co.jp/quote/{clean_code}.T/financial"
        past_settle_date = None
        past_announce_month = None
        try:
            res_fin = requests.get(url_fin, headers=headers, timeout=5)
            if res_fin.status_code == 200:
                fin_soup = BeautifulSoup(res_fin.text, 'html.parser')
                # 発表日リストから最も直近の過去日付（本日以前）を抽出
                for tag in fin_soup.find_all(['td', 'th', 'span', 'li', 'time']):
                    t_str = tag.get_text().strip()
                    m_past = re.search(r'(\d{4})[/-](\d{1,2})[/-](0?[1-9]|[12][0-9]|3[01])\b', t_str)
                    if m_past:
                        y = m_past.group(1)
                        m = int(m_past.group(2))
                        d = int(m_past.group(3))
                        cand_past = f"{y}/{m:02d}/{d:02d}"
                        if cand_past <= today_str:
                            if past_settle_date is None or cand_past > past_settle_date:
                                past_settle_date = cand_past
                                past_announce_month = m
        except Exception as e:
            print(f"Yahoo業績実績取得エラー ({ticker_code}): {e}")

        if past_settle_date:
            q_label = deduce_quarter(fiscal_month, past_announce_month) if past_announce_month else ""
            data["settlement_date"] = f"{past_settle_date}{q_label}"
        else:
            data["settlement_date"] = "未定"

    return data
