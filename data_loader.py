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
                    "pct": float(row['Pct'])
