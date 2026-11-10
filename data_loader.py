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

@st.cache_data(ttl=300)
def load_data_from_sheet(sheet_type="margin"):
    """Googleスプレッドシートからデータを取得（TTLを300秒に延長して負荷低減）"""
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

@st.cache_data(ttl=3600)
def get_stock_prices(ticker_code):
    """yfinanceから過去株価履歴（終値・出来高）を取得"""
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
                    "pct": float(row['Pct']) if pd.notna(row['Pct']) else 0.0,
                    "volume": int(row['Volume']) if pd.notna(row['Volume']) else 0
                }
    except Exception:
        pass
    return prices

@st.cache_data(ttl=120)
def fetch_yahoo_complete_data(ticker_code):
    """
    Yahoo!ファイナンスへのリクエストを原則1回に集約し、
    銘柄名・株価・PTS・ファンダメンタルズ・決算予定を一度に抽出（夜間DOMフォールバック対応）
    """
    clean_code = clean_ticker_code(ticker_code)
    res_dict = {
        "company_name": "",
        "price": None,
        "change_val": None,
        "change_pct": None,
        "pts_price": None,
        "pts_diff_val": None,
        "pts_diff_pct": None,
        "market": "-",
        "margin_type": "貸借",
        "industry": "-",
        "market_cap": "-",
        "per": "-",
        "pbr": "-",
        "dividend_yield": "-",
        "settlement_date": "未定",
        "settlement_bg": "#f0f2f6",
        "settlement_color": "#666666"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://finance.yahoo.co.jp/"
    }

    url_quote = f"https://finance.yahoo.co.jp/quote/{clean_code}.T"
    future_date_str = None
    future_d_obj = None
    fiscal_month = 3
    today_date = datetime.date.today()

    try:
        res = requests.get(url_quote, headers=headers, timeout=6)
        if res.status_code == 200:
            page_text = res.text
            soup = BeautifulSoup(page_text, 'html.parser')

            # 1. 銘柄名抽出
            title_text = soup.title.string if soup.title else ""
            if "【" in title_text:
                res_dict["company_name"] = title_text.split("【")[0].replace("(株)", "").replace("（株）", "").replace("ホールディングス", "HD").strip()
            elif soup.find('h1'):
                res_dict["company_name"] = soup.find('h1').text.split("【")[0].replace("(株)", "").replace("（株）", "").replace("ホールディングス", "HD").strip()

            # 2. 夜間PTS株価（東証株価の誤判定防止のため先に抽出）
            pts_price_box = soup.find(class_=re.compile(r'CommonPriceBoard__ptsPrice'))
            if pts_price_box:
                pts_val_span = pts_price_box.find('span', class_=re.compile(r'StyledNumber__value'))
                if pts_val_span:
                    res_dict["pts_price"] = pts_val_span.get_text().strip()

            pts_label = soup.find(class_=re.compile(r'CommonPriceBoard__ptsLabel'))
            if pts_label:
                pts_parent = pts_label.find_parent('li') or pts_label.find_parent('div') or pts_label.parent
                if pts_parent:
                    pts_sec = pts_parent.find_all(class_=re.compile(r'PriceChangeLabel'))
                    for sec in pts_sec:
                        m = re.search(r'([+-]?[0-9,]+(?:\.[0-9]+)?)\s*\(?([+-]?[0-9.]+[%％]?)\)?', sec.get_text().strip())
                        if m:
                            res_dict["pts_diff_val"] = m.group(1).strip()
                            pct_val = m.group(2).strip()
                            res_dict["pts_diff_pct"] = f"{pct_val}%" if not pct_val.endswith('%') else pct_val
                            break

            # 3. 東証株価・前日比
            price_box = soup.find(class_=re.compile(r'CommonPriceBoard__price\b|CommonPriceBoard__price__'))
            if price_box:
                val_span = price_box.find('span', class_=re.compile(r'StyledNumber__value'))
                if val_span:
                    res_dict["price"] = val_span.get_text().strip()

            primary_box = soup.find(class_=re.compile(r'PriceChangeLabel__primary'))
            if primary_box:
                val_span = primary_box.find('span', class_=re.compile(r'StyledNumber__value'))
                if val_span:
                    res_dict["change_val"] = val_span.get_text().strip()

            all_secondary = soup.find_all(class_=re.compile(r'PriceChangeLabel__secondary'))
            if all_secondary:
                pct_span = all_secondary[0].find('span', class_=re.compile(r'StyledNumber__value'))
                if pct_span:
                    raw_pct = pct_span.get_text().strip()
                    res_dict["change_pct"] = f"{raw_pct}%" if not raw_pct.endswith('%') else raw_pct

            # ★ 夜間フォールバック：深夜や取引時間外に株価が抜け落ちた場合の多層救済
            if not res_dict["price"]:
                pts_clean = str(res_dict.get("pts_price", "")).replace(',', '').strip()
                for span in soup.find_all('span', class_=re.compile(r'StyledNumber__value')):
                    txt = span.get_text().strip().replace(',', '')
                    if txt.replace('.', '', 1).isdigit() and len(txt) >= 2:
                        if pts_clean and txt == pts_clean:
                            continue
                        parent_text = span.parent.get_text() if span.parent else ""
                        if "PTS" in parent_text:
                            continue
                        res_dict["price"] = f"{float(txt):,.0f}" if '.' not in txt else f"{float(txt):,}"
                        break

            # 4. 市場・業種・指標
            m_market = re.search(r'東証(PRM|STD|GRW|プライム|スタンダード|グロース)', page_text)
            if m_market:
                mapping = {"PRM": "プライム", "STD": "スタンダード", "GRW": "グロース"}
                res_dict["market"] = mapping.get(m_market.group(1), m_market.group(1))

            m_fisc = re.search(r'(?:決算期|決算月|事業年度)[^0-9]*(\d{1,2})月', page_text)
            if m_fisc:
                fiscal_month = int(m_fisc.group(1))

            for dt in soup.find_all(['dt', 'th']):
                dd = dt.find_next_sibling(['dd', 'td'])
                if not dd:
                    continue
                label = dt.get_text().strip()
                val = dd.get_text().strip()

                if "時価総額" in label and res_dict["market_cap"] == "-":
                    m_cap = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*(兆|億|百万円)', val)
                    if m_cap:
                        val_num = float(m_cap.group(1).replace(',', ''))
                        unit = m_cap.group(2)
                        if unit == "百万円":
                            oku = val_num / 100.0
                            res_dict["market_cap"] = f"{oku / 10000:.2f}兆円" if oku >= 10000 else f"{int(oku):,}億円"
                        else:
                            res_dict["market_cap"] = f"{m_cap.group(1)}{unit}円"

                if ("PER" in label or "ＰＥＲ" in label) and res_dict["per"] == "-":
                    m_per = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*倍', val)
                    if m_per: res_dict["per"] = f"{m_per.group(1)}倍"

                if ("PBR" in label or "ＰＢＲ" in label) and res_dict["pbr"] == "-":
                    m_pbr = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*倍', val)
                    if m_pbr: res_dict["pbr"] = f"{m_pbr.group(1)}倍"

                if ("利回り" in label or "配当" in label) and res_dict["dividend_yield"] == "-":
                    m_div = re.search(r'([0-9,]+(?:\.[0-9]+)?)\s*[%％]', val)
                    if m_div: res_dict["dividend_yield"] = f"{m_div.group(1)}%"

            # 5. 次回決算予定日
            for a_link in soup.find_all('a', href=re.compile(r'/financials')):
                l_text = a_link.get_text().strip()
                if "決算発表予定日" in l_text:
                    m_date = re.search(r'(\d{4})[/-](\d{1,2})[/-](0?[1-9]|[12][0-9]|3[01])\b', l_text)
                    if m_date:
                        y, m, d = int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))
                        future_d_obj = datetime.date(y, m, d)
                        future_date_str = f"{y}/{m:02d}/{d:02d}"
                        break

            if "制度信用" in page_text and "貸借" not in page_text:
                res_dict["margin_type"] = "制度"
            elif "貸借" in page_text:
                res_dict["margin_type"] = "貸借"

    except Exception as e:
        print(f"Yahoo一括取得エラー ({ticker_code}): {e}")

    # 業種判定（トップページから取れない場合のみprofileを参照）
    for sec in JPX_33_SECTORS:
        if f">{sec}<" in page_text[:15000] or f" {sec} " in page_text[:15000]:
            res_dict["industry"] = sec
            break

    if res_dict["industry"] == "-":
        try:
            r_prof = requests.get(f"https://finance.yahoo.co.jp/quote/{clean_code}.T/profile", headers=headers, timeout=4)
            if r_prof.status_code == 200:
                p_soup = BeautifulSoup(r_prof.text, 'html.parser')
                for tag in p_soup.find_all(['dd', 'td', 'a', 'span']):
                    txt = tag.get_text().strip()
                    if txt in JPX_33_SECTORS:
                        res_dict["industry"] = txt
                        break
        except Exception:
            pass

    # 決算予定日と背景色ステータスの確定
    if future_date_str and future_d_obj:
        q_label = deduce_quarter(fiscal_month, future_d_obj.month)
        res_dict["settlement_date"] = f"{future_date_str}{q_label}"
        days_left = (future_d_obj - today_date).days
        if days_left <= 3:
            res_dict["settlement_bg"] = "#ffebee"
            res_dict["settlement_color"] = "#c62828"
        elif days_left <= 7:
            res_dict["settlement_bg"] = "#fff3e0"
            res_dict["settlement_color"] = "#ef6c00"
        else:
            res_dict["settlement_bg"] = "#f0f2f6"
            res_dict["settlement_color"] = "#333333"
    else:
        # 次回予定がない場合のみ financials タグを参照
        try:
            r_fin = requests.get(f"https://finance.yahoo.co.jp/quote/{clean_code}.T/financials", headers=headers, timeout=4)
            if r_fin.status_code == 200:
                fin_text = r_fin.text
                m_announce = re.search(r'発表日[^\d]*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})', fin_text)
                if m_announce:
                    y, m, d = int(m_announce.group(1)), int(m_announce.group(2)), int(m_announce.group(3))
                    past_d_str = f"{y}/{m:02d}/{d:02d}"
                    q_str = " (Q2)" if "第2四半期" in fin_text or "中間" in fin_text else (
                            " (Q1)" if "第1四半期" in fin_text else (
                            " (Q3)" if "第3四半期" in fin_text else (
                            " (本決算)" if "本決算" in fin_text else deduce_quarter(fiscal_month, m))))
                    res_dict["settlement_date"] = f"{past_d_str}{q_str} (済)"
                    res_dict["settlement_bg"] = "#e3f2fd"
                    res_dict["settlement_color"] = "#1565c0"
        except Exception:
            pass

    return res_dict

def get_company_name_from_yahoo_japan(ticker_code):
    return fetch_yahoo_complete_data(ticker_code).get("company_name", "")

def get_yahoo_realtime_and_pts(ticker_code):
    d = fetch_yahoo_complete_data(ticker_code)
    return {k: d[k] for k in ["price", "change_val", "change_pct", "pts_price", "pts_diff_val", "pts_diff_pct"]}

def get_fundamentals_summary(ticker_code):
    return fetch_yahoo_complete_data(ticker_code)
