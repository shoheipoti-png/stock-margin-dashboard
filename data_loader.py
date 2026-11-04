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

# 東証33業種一覧
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
    主要ファンダメンタルズ概要を抽出（6時間キャッシュ）
    市場、時価総額、業種、PER、PBR、配当利回り、決算予定日
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

    # ---------------------------------------------------------
    # 1. Yahoo!ファイナンスからのデータ取得
    # ---------------------------------------------------------
    url_yahoo = f"https://finance.yahoo.co.jp/quote/{clean_code}.T"
    try:
        res = requests.get(url_yahoo, headers=headers, timeout=6)
        if res.status_code == 200:
            page_text = res.text
            soup = BeautifulSoup(page_text, 'html.parser')

            # 市場判定
            m_market = re.search(r'東証(プライム|スタンダード|グロース)', page_text)
            if m_market:
                data["market"] = m_market.group(1)
            else:
                m_gen = re.search(r'([A-Za-z0-9\u3000-\u9fff]+市場|名証|福証|札証)', page_text)
                if m_gen:
                    data["market"] = m_gen.group(1)

            # 数値データの抽出
            dl_items = soup.find_all(['li', 'tr', 'div'])
            for item in dl_items:
                txt = item.get_text()
                if "時価総額" in txt and data["market_cap"] == "-":
                    m_cap = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*(兆|億|百万円)', txt)
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

                if ("PER" in txt or "ＰＥＲ" in txt) and data["per"] == "-":
                    m_per = re.search(r'(?:PER|ＰＥＲ)[^0-9]*([0-9,]+(?:\.[0-9]+)?)\s*倍', txt)
                    if m_per:
                        data["per"] = f"{m_per.group(1)}倍"

                if ("PBR" in txt or "ＰＢＲ" in txt) and data["pbr"] == "-":
                    m_pbr = re.search(r'(?:PBR|ＰＢＲ)[^0-9]*([0-9,]+(?:\.[0-9]+)?)\s*倍', txt)
                    if m_pbr:
                        data["pbr"] = f"{m_pbr.group(1)}倍"

                if ("利回り" in txt or "配当" in txt) and data["dividend_yield"] == "-":
                    m_div = re.search(r'(?:配当利回り|利回り)[^0-9%]*([0-9,]+(?:\.[0-9]+)?)\s*[%％]', txt)
                    if m_div:
                        data["dividend_yield"] = f"{m_div.group(1)}%"

            # 貸借区分
            if "制度信用" in page_text and "貸借" not in page_text:
                data["margin_type"] = "制度"
            elif "貸借" in page_text:
                data["margin_type"] = "貸借"
    except Exception as e:
        print(f"Yahooファンダ取得エラー ({ticker_code}): {e}")

    # ---------------------------------------------------------
    # 2. 株探（Kabutan）から業種と正確な決算予定日を取得
    # ---------------------------------------------------------
    url_kabutan = f"https://kabutan.jp/stock/?code={clean_code}"
    try:
        res_k = requests.get(url_kabutan, headers=headers, timeout=5)
        if res_k.status_code == 200:
            k_soup = BeautifulSoup(res_k.text, 'html.parser')
            k_text = res_k.text

            # 業種（株探の業界パンくず・セクターリンクから取得）
            for sec in JPX_33_SECTORS:
                # 株探のセクターリンクやヘッダー内の業種を照合
                if f'>{sec}<' in k_text or f'業種：{sec}' in k_text or f'/{sec}/' in k_text:
                    data["industry"] = sec
                    break
            
            if data["industry"] == "-":
                sector_tag = k_soup.find('a', href=re.compile(r'/themes/\?industry='))
                if sector_tag and sector_tag.get_text().strip() in JPX_33_SECTORS:
                    data["industry"] = sector_tag.get_text().strip()

            # 決算発表予定日（日付け部分を厳格に正規表現マッチ：1〜31日）
            # 例: "2026/11/06", "11/06", "11月6日"
            match_k_date = re.search(r'決算発表予定日[^\d]*(\d{4})[/-](\d{1,2})[/-](0?[1-9]|[12][0-9]|3[01])(?!\d)', k_text)
            if match_k_date:
                data["settlement_date"] = f"{match_k_date.group(1)}/{int(match_k_date.group(2)):02d}/{int(match_k_date.group(3)):02d}"
            else:
                match_md = re.search(r'決算発表予定日[^\d]*(\d{1,2})[月/-](0?[1-9]|[12][0-9]|3[01])日?(?!\d)', k_text)
                if match_md:
                    data["settlement_date"] = f"{int(match_md.group(1)):02d}/{int(match_md.group(2)):02d}"

    except Exception as e:
        print(f"株探補完取得エラー ({ticker_code}): {e}")

    return data
