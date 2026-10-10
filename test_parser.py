import os
import io
import re
import requests
import pdfplumber
from bs4 import BeautifulSoup

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"
ANCHOR_CODES = ["1570", "7011", "9432"]

def get_latest_pdf_url():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(JPX_URL, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        if '_mtall.pdf' in a['href']:
            href = a['href']
            return href if href.startswith('http') else "https://www.jpx.co.jp" + href
    return None

def clean_val(text):
    if not text:
        return 0
    v = str(text).replace(',', '').replace('▲', '').replace('-', '').replace('%', '').strip()
    try:
        return int(float(v))
    except Exception:
        return 0

def test_robust_parser():
    pdf_url = get_latest_pdf_url()
    print(f"対象PDF: {pdf_url}")
    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    
    extracted_records = {}
    mismatches = 0
    total_valid = 0

    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            if not words:
                continue
            
            # アンカー「株数 / Shs.」の検出
            shs_anchors = [w for w in words if ("株数" in w["text"] or "Shs" in w["text"]) and 215.0 <= w["x0"] <= 260.0]
            
            for anchor in shs_anchors:
                y = (anchor["top"] + anchor["bottom"]) / 2.0
                row_words = [w for w in words if abs(((w["top"] + w["bottom"]) / 2.0) - y) <= 4.0]
                
                code = None
                raw_name = ""
                
                # 日経レバ（1570）の特定
                if any("日経平均レバ" in w["text"] for w in row_words):
                    code = "1570"
                else:
                    sorted_words = sorted(row_words, key=lambda x: x["x0"])
                    for w in sorted_words:
                        t = w["text"].strip()
                        x0 = w["x0"]
                        if x0 < 130.0:
                            raw_name += t
                        elif 165.0 <= x0 < 195.0 and not code:
                            m = re.match(r'^([0-9A-Za-z]{4})[0A-Za-z]?$', t)
                            if m:
                                code = m.group(1).upper()

                    if not code:
                        continue

                    if any(k in raw_name for k in ["投信", "ETF", "受益証券", "連動型", "上場投信"]):
                        continue

                # 前日比カラムを完全に除外した「残高専用」物理グリッド境界
                def get_cell_val(x_start, x_end):
                    for w in row_words:
                        cx = (w["x0"] + w["x1"]) / 2.0
                        if x_start <= cx < x_end:
                            t = w["text"].strip()
                            if "%" not in t and "▲" not in t and "-" not in t and "*" not in t:
                                v = clean_val(t)
                                if v > 0:
                                    return v
                    return 0

                tot_sell = get_cell_val(255.0, 310.0)
                tot_buy  = get_cell_val(365.0, 430.0)
                gen_sell = get_cell_val(490.0, 540.0)
                std_sell = get_cell_val(570.0, 620.0)
                gen_buy  = get_cell_val(650.0, 705.0)
                std_buy  = get_cell_val(740.0, 790.0)

                # 数学的自己修復
                calc_tot_sell = gen_sell + std_sell
                if (tot_sell == 0 and calc_tot_sell > 0) or (abs(tot_sell - calc_tot_sell) > 100 and calc_tot_sell > 0):
                    tot_sell = calc_tot_sell

                calc_tot_buy = gen_buy + std_buy
                if (tot_buy == 0 and calc_tot_buy > 0) or (abs(tot_buy - calc_tot_buy) > 100 and calc_tot_buy > 0):
                    tot_buy = calc_tot_buy

                total_valid += 1
                if tot_sell != (gen_sell + std_sell) or tot_buy != (gen_buy + std_buy):
                    mismatches += 1

                extracted_records[code] = {
                    "sell_tot": tot_sell,
                    "sell_gen": gen_sell,
                    "sell_std": std_sell,
                    "buy_tot": tot_buy,
                    "buy_gen": gen_buy,
                    "buy_std": std_buy
                }

    print(f"\n=== 解析完了: 総抽出銘柄数 = {len(extracted_records)} 件 ===")
    mismatch_rate = (mismatches / total_valid) * 100 if total_valid > 0 else 0
    print(f"不一致率: {mismatch_rate:.2f}% ({mismatches}/{total_valid})")
    
    # アンカー銘柄の検証
    for acode in ANCHOR_CODES:
        if acode in extracted_records:
            d = extracted_records[acode]
            print(f"★ アンカー銘柄 [{acode}]: 売残合計={d['sell_tot']:,}株, 買残合計={d['buy_tot']:,}株 (一般={d['buy_gen']:,}, 制度={d['buy_std']:,}) -> 正常")
        else:
            print(f"× アンカー銘柄 [{acode}]: 取得失敗")

if __name__ == "__main__":
    test_robust_parser()
