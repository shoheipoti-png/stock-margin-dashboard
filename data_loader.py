import os
import json
import re
import pandas as pd
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import streamlit as st

DEFAULT_SPREADSHEET_ID = "1_YK99EVmXnTWHzE7oP9tO1jWYaxUiTinMyFQ-1n2M4g"
DEFAULT_SHORT_SPREADSHEET_ID = "1Fdfmwq_6CBAG495JJD4EPgT7EOfyB9kZ_QAwU6pAXaU"

def clean_ticker_code(val):
    if pd.isna(val) or val is None:
        return ""
    s = str(val).split('.')[0].strip().upper()
    return s[:4] if len(s) >= 4 else s

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
    """
    Yahoo!ファイナンスから東証株価・前日比・騰落率および夜間PTS情報を完全抽出
    """
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

        # -------------------------------------------------------------
        # 1. 東証リアルタイム株価
        # -------------------------------------------------------------
        price_elem = soup.find('span', class_=re.compile(r'_Price_'))
        if price_elem:
            result["price"] = price_elem.get_text().strip()

        # -------------------------------------------------------------
        # 2. 東証の前日比・騰落率
        # HTML構造:
        # PriceChangeLabel__primary の子 StyledNumber__value -> 前日比 (+700)
        # PriceChangeLabel__secondary の子 StyledNumber__value -> 騰落率 (+15.79)
        # -------------------------------------------------------------
        primary_box = soup.find(class_=re.compile(r'PriceChangeLabel__primary'))
        if primary_box:
            val_span = primary_box.find('span', class_=re.compile(r'StyledNumber__value'))
            if val_span:
                result["change_val"] = val_span.get_text().strip()

        # 東証側（PTSではない側）の secondary を探索
        all_secondary = soup.find_all(class_=re.compile(r'PriceChangeLabel__secondary'))
        if all_secondary:
            # 最初の secondary は通常、東証騰落率
            pct_span = all_secondary[0].find('span', class_=re.compile(r'StyledNumber__value'))
            if pct_span:
                raw_pct = pct_span.get_text().strip()
                result["change_pct"] = f"{raw_pct}%" if not raw_pct.endswith('%') else raw_pct

        # -------------------------------------------------------------
        # 3. 夜間PTS株価 & 東証終値比
        # HTML構造:
        # CommonPriceBoard__ptsPrice の子 StyledNumber__value -> PTS株価 (5,198)
        # 2つ目以降の PriceChangeLabel__secondary -> PTS終値比 (+64 / +1.25)
        # -------------------------------------------------------------
        pts_price_box = soup.find(class_=re.compile(r'CommonPriceBoard__ptsPrice'))
        if pts_price_box:
            pts_val_span = pts_price_box.find('span', class_=re.compile(r'StyledNumber__value'))
            if pts_val_span:
                result["pts_price"] = pts_val_span.get_text().strip()

        # PTSの変動値・騰落率（PTSブロック内の要素から抽出）
        pts_label = soup.find(class_=re.compile(r'CommonPriceBoard__ptsLabel'))
        if pts_label:
            pts_parent = pts_label.find_parent('li') or pts_label.find_parent('div') or pts_label.parent
            if pts_parent:
                pts_sec = pts_parent.find_all(class_=re.compile(r'PriceChangeLabel'))
                for sec in pts_sec:
                    sec_text = sec.get_text().strip()
                    # 変動値とパーセントを正規表現で捕捉 (例: +64 (+1.25%))
                    m = re.search(r'([+-]?[0-9,]+(?:\.[0-9]+)?)\s*\(?([+-]?[0-9.]+[%％]?)\)?', sec_text)
                    if m:
                        result["pts_diff_val"] = m.group(1).strip()
                        pct_val = m.group(2).strip()
                        result["pts_diff_pct"] = f"{pct_val}%" if not pct_val.endswith('%') else pct_val
                        break
                    
                    # 個別の StyledNumber__value を探索
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
    """yfinanceから株価履歴・出来高を取得"""
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
                    "pct": row['Pct'] if pd.notna(row['Pct']) else 0.0,
                    "volume": int(row['Volume']) if pd.notna(row['Volume']) else 0
                }
    except Exception:
        pass
    return prices
