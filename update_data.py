import os
import json
import datetime
import re
import requests
from bs4 import BeautifulSoup
import pdfplumber
import io
import gspread
from google.oauth2.service_account import Credentials

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"

def get_latest_pdf_url():
    """JPXのページから最新の銘柄別信用取引残高PDFのURLを取得"""
    res = requests.get(JPX_URL)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '_mtall.pdf' in href:
            return href if href.startswith('http') else "https://www.jpx.co.jp" + href
    return None

def clean_val(text):
    if not text:
        return 0
    # カンマ、三角記号、パーセントを除去
    v = str(text).replace(',', '').replace('▲', '-').replace('%', '').strip()
    try:
        return int(float(v))
    except Exception:
        return 0

def parse_row_numbers(row_words):
    """
    行内の単語群から銘柄コード、社名、および数値列を堅牢に抽出
    """
    # X座標順にソート
    sorted_words = sorted(row_words, key=lambda w: w["x0"])
    
    code = None
    raw_name = ""
    num_tokens = []
    
    for w in sorted_words:
        text = w["text"].strip()
        x0 = w["x0"]
        
        # 銘柄名エリア（x0 < 170）
        if x0 < 170:
            raw_name += text
            continue
            
        # 銘柄コード（170 <= x0 < 220）: 英数字4文字（285A含む）に対応
        if 165 <= x0 < 220 and re.match(r'^[0-9A-Za-z]{4}[0A-Za-z]?$', text):
            code = text[:4].upper()
            continue
            
        # "Shs." などの単位文字列や市場名は除外
        if text in ["Shs.", "株", "Prime", "Standard", "Growth", "プライム", "スタンダード", "グロース", "Val.", "金額"]:
            continue
            
        # 数値またはハイフン、前日比記号を含むトークンを収集
        # 例: "2,575,900", "▲139,100", "-", "0", "2.5%"
        clean_cand = text.replace(',', '').replace('▲', '-').strip()
        if re.match(r'^[\-\+]?\d+(\.\d+)?%?$', clean_cand) or text in ['-', '*']:
            num_tokens.append(w)

    if not code or not num_tokens:
        return None, None, None

    # 各エリア（売残、買残、内訳）のX座標範囲に基づいて確実にクラスタリング
    # PDFの標準カラム帯域（余白を持たせた安全な範囲設定）
    # 売残合計エリア: 240 <= x0 < 340
    # 買残合計エリア: 340 <= x0 < 460
    # 一般売エリア:   470 <= x0 < 550
    # 制度売エリア:   550 <= x0 < 630
    # 一般買エリア:   630 <= x0 < 710
    # 制度買エリア:   710 <= x0 < 800
    
    tot_sell_candidates = [clean_val(w["text"]) for w in num_tokens if 240 <= w["x0"] < 350 and '%' not in w["text"]]
    tot_buy_candidates = [clean_val(w["text"]) for w in num_tokens if 350 <= w["x0"] < 470 and '%' not in w["text"]]
    gen_sell_candidates = [clean_val(w["text"]) for w in num_tokens if 470 <= w["x0"] < 550 and '%' not in w["text"]]
    std_sell_candidates = [clean_val(w["text"]) for w in num_tokens if 550 <= w["x0"] < 630 and '%' not in w["text"]]
    gen_buy_candidates = [clean_val(w["text"]) for w in num_tokens if 630 <= w["x0"] < 715 and '%' not in w["text"]]
    std_buy_candidates = [clean_val(w["text"]) for w in num_tokens if 715 <= w["x0"] < 800 and '%' not in w["text"]]

    # 各列の先頭トークン（残高数量）を取得（2つ目は前日比）
    tot_sell = tot_sell_candidates[0] if tot_sell_candidates else 0
    tot_buy = tot_buy_candidates[0] if tot_buy_candidates else 0
    gen_sell = gen_sell_candidates[0] if gen_sell_candidates else 0
    std_sell = std_sell_candidates[0] if std_sell_candidates else 0
    gen_buy = gen_buy_candidates[0] if gen_buy_candidates else 0
    std_buy = std_buy_candidates[0] if std_buy_candidates else 0

    # 【整合性自己検証＆自動補正】
    # 信用取引の基本原則: 合計 ＝ 一般 ＋ 制度
    calc_tot_sell = gen_sell + std_sell
    calc_tot_buy = gen_buy + std_buy

    # 合計値が0または極端にズレていて、内訳が揃っている場合は内訳合計を採用
    if (tot_sell == 0 and calc_tot_sell > 0) or (abs(tot_sell - calc_tot_sell) > 100 and calc_tot_sell > 0):
        tot_sell = calc_tot_sell
        
    if (tot_buy == 0 and calc_tot_buy > 0) or (abs(tot_buy - calc_tot_buy) > 100 and calc_tot_buy > 0):
        tot_buy = calc_tot_buy

    return code, raw_name, (str(tot_sell), str(gen_sell), str(std_sell), str(tot_buy), str(gen_buy), str(std_buy))

def main():
    print("JPX個人信用データ取得（高精度パース＆整合性自動検証版）を開始します...")
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY")
    sheet_id = os.environ.get("SPREADSHEET_ID")
    
    if not creds_json or not sheet_id:
        print("エラー: 認証情報またはシートIDが設定されていません。")
        return

    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(sheet_id).sheet1
    
    pdf_url = get_latest_pdf_url()
    if not pdf_url:
        print("エラー: PDF URLが取得できませんでした。")
        return
    print(f"対象PDF URL: {pdf_url}")
    
    pdf_res = requests.get(pdf_url)
    pdf_file = io.BytesIO(pdf_res.content)
    
    report_date = None
    
    # 1. 1ページ目から基準日を取得
    with pdfplumber.open(pdf_file) as pdf:
        p0_text = pdf.pages[0].extract_text()
        date_match = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})\s*申込み現在', p0_text)
        if date_match:
            report_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
            print(f"★ 基準日: {report_date}")
        else:
            report_date = datetime.date.today().strftime("%Y-%m-%d")

    # 2. 既存データ（8列形式）の取得
    existing_data = worksheet.get_all_values()
    headers = ["日付", "銘柄コード", "売残(合計)", "売残(一般)", "売残(制度)", "買残(合計)", "買残(一般)", "買残(制度)"]
    data_rows = []
    
    if existing_data and len(existing_data[0]) > 0 and existing_data[0][0] == "日付":
        for r in existing_data[1:]:
            if len(r) >= 8:
                if len(r) >= 9 and not str(r[2]).replace('-', '').isdigit():
                    row_8 = [r[0], r[1], r[3], r[4], r[5], r[6], r[7], r[8]]
                else:
                    row_8 = r[:8]
                # 本日取得分と重複する日付は一旦除外して再構築
                if row_8[0] != report_date:
                    data_rows.append(row_8)

    print("PDF解析を開始...")
    new_rows = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            
            # 各銘柄行のアンカーとなる "Shs." を検出
            shs_anchors = [w for w in words if w["text"] == "Shs." and 215 <= w["x0"] <= 260]
            
            for anchor in shs_anchors:
                y = anchor["top"]
                row_words = [w for w in words if abs(w["top"] - y) <= 4]
                
                code, raw_name, values = parse_row_numbers(row_words)
                if not code or not values:
                    continue
                    
                # 【ETF・投信完全除外】1570以外はスキップ
                if code != "1570" and any(k in raw_name for k in ["投信", "ETF", "受益証券", "連動型", "上場投信"]):
                    continue
                
                tot_sell, gen_sell, std_sell, tot_buy, gen_buy, std_buy = values
                new_rows.append([
                    report_date, code, tot_sell, gen_sell, std_sell,
                    tot_buy, gen_buy, std_buy
                ])
                    
    print(f"抽出完了（ETF除外後）: {len(new_rows)} 銘柄")
    
    unique_rows = {}
    for r in new_rows:
        unique_rows[r[1]] = r
    final_rows = list(unique_rows.values())

    # 3. 450日ローリング
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=450)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    filtered_rows = [row for row in data_rows if len(row) > 0 and row[0] >= cutoff_date_str]
    filtered_rows.extend(final_rows)
    
    worksheet.clear()
    worksheet.update('A1', [headers] + filtered_rows)
    print(f"スプレッドシート更新完了（基準日: {report_date} / 行数: {len(final_rows)}）")

if __name__ == "__main__":
    main()
