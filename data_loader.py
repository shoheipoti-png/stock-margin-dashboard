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
    Yahoo!ファイナンスから東証リアルタイム株価と夜間PTS株価情報を確実に抽出
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

        # --------------------------------------------------
        # 1. 東証リアルタイム株価 & 前日比の抽出
        # --------------------------------------------------
        # 「リアルタイム株価」のラベル要素を基点底上げ
        rt_marker = soup.find(string=re.compile(r'リアルタイム株価'))
        if rt_marker:
            # ヘッダー内の価格ボックス全体（最大親コンテナ）を取得
            header_box = rt_marker.find_parent('div')
            for _ in range(4):
                if header_box and header_box.parent and len(header_box.get_text()) < 300:
                    header_box = header_box.parent

            if header_box:
                box_text = header_box.get_text(separator=' ')
                # 価格の抽出（例: 5,134）
                for sp in header_box.find_all(['span', 'div', 'p']):
                    t = sp.get_text().strip()
                    if re.match(r'^[1-9][0-9]{0,2}(?:,[0-9]{3})+(?:\.[0-9]+)?$', t) or (t.isdigit() and len(t) >= 3 and t != clean_code):
                        result["price"] = t
                        break

                # 前日比数値の抽出（例: +700 または -50）
                diff_val_match = re.search(r'前日比\s*[:：]?\s*([+-]?[0-9,]+(?:\.[0-9]+)?)', box_text)
                if diff_val_match:
                    result["change_val"] = diff_val_match.group(1).strip()
                else:
                    # 符号付き数値単体のマッチ
                    val_candidates = re.findall(r'([+-][0-9,]+(?:\.[0-9]+)?)', box_text)
                    if val_candidates:
                        result["change_val"] = val_candidates[0]

                # 前日比パーセントの抽出（例: +15.79%）
                pct_match = re.search(r'\(([+-]?[0-9.]+(?:%|％))\)', box_text)
                if pct_match:
                    result["change_pct"] = pct_match.group(1).strip()

        # --------------------------------------------------
        # 2. 夜間PTS株価 & 東証終値比の抽出
        # --------------------------------------------------
        pts_marker = soup.find(string=re.compile(r'夜間PTS'))
        if pts_marker:
            pts_elem = pts_marker.find_parent('li') or pts_marker.find_parent('div') or pts_marker.parent
            if pts_elem:
                pts_text = pts_elem.get_text(separator=' ')
                
                # PTS価格の抽出: "夜間PTS"の直後に続く数値を正規表現で確実に捕捉
                # 例: "夜間PTS 5,198" または "夜間PTS5,198"
                price_match = re.search(r'夜間PTS\s*([0-9,]+(?:\.[0-9]+)?)', pts_text)
                if price_match:
                    result["pts_price"] = price_match.group(1).strip()

                # 東証終値比（値と％）の抽出
                # パターン1: "東証終値比 +64 (+1.25%)"
                pts_diff_match = re.search(r'東証終値比\s*[:：]?\s*([+-]?[0-9,]+(?:\.[0-9]+)?)\s*(?:\(([+-]?[0-9.]+[%％]?)\)|([+-]?[0-9.]+[%％]))', pts_text)
                if pts_diff_match:
                    result["pts_diff_val"] = pts_diff_match.group(1).strip()
                    result["pts_diff_pct"] = (pts_diff_match.group(2) or pts_diff_match.group(3)).strip()
                else:
                    # パターン2: "東証終値比+0.42%" のようにパーセントのみの場合
                    pts_pct_only = re.search(r'東証終値比\s*[:：]?\s*([+-]?[0-9.]+[%％])', pts_text)
                    if pts_pct_only:
                        result["pts_diff_pct"] = pts_pct_only.group(1).strip()

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
