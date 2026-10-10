import os
import io
import re
import requests
import pdfplumber
from bs4 import BeautifulSoup

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"

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

def diagnose_mismatches():
    pdf_url = get_latest_pdf_url()
    print(f"対象PDF: {pdf_url}")
    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    
    mismatches = []
    total_count = 0

    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            if not words:
                continue
            
            shs_anchors = [w for w in words if ("株数" in w["text"] or "Shs" in w["text"]) and 215.0 <= w["x0"] <= 260.0]
            
            for anchor in shs_anchors:
                y = (anchor["top"] + anchor["bottom"]) / 2.0
                row_words = [w for w in words if abs(((w["top"] + w["bottom"]) / 2.0) - y) <= 4.0]
                
                code = None
                raw_name = ""
                
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

                def get_cell_val(x_start, x_end):
                    for w in row_words:
                        cx = (w["x0"] + w["x1"]) / 2.0
                        if x_start <= cx < x_end:
                            t = w["text"].strip()
                            if "%" not in t and "▲" not in t and "-" not in t:
                                v = clean_val(t)
                                if v > 0:
                                    return v
                    return 0

                tot_sell = get_cell_val(185.0, 250.0)
                tot_buy  = get_cell_val(290.0, 363.6)
                gen_sell = get_cell_val(405.0, 477.2)
                std_sell = get_cell_val(477.2, 560.0)
                gen_buy  = get_cell_val(560.0, 684.2)
                std_buy  = get_cell_val(684.2, 808.4)

                total_count += 1
                
                # 不一致の検出
                sell_match = (tot_sell == (gen_sell + std_sell))
                buy_match  = (tot_buy == (gen_buy + std_buy))

                if not sell_match or not buy_match:
                    mismatches.append({
                        "code": code,
                        "sell": (tot_sell, gen_sell, std_sell, sell_match),
                        "buy": (tot_buy, gen_buy, std_buy, buy_match),
                        "words": [f"{w['text']}({w['x0']:.0f}..{w['x1']:.0f})" for w in row_words if w['x0'] >= 180]
                    })

    print(f"\n総銘柄数: {total_count} 件, 不一致件数: {len(mismatches)} 件 ({len(mismatches)/total_count*100:.2f}%)")
    print("\n=== 不一致サンプルの詳細（最初の10件）===")
    for m in mismatches[:10]:
        print(f"銘柄 [{m['code']}]:")
        if not m['sell'][3]:
            print(f"  売残不一致: 合計={m['sell'][0]:,} vs (一般={m['sell'][1]:,} + 制度={m['sell'][2]:,} = {m['sell'][1]+m['sell'][2]:,})")
        if not m['buy'][3]:
            print(f"  買残不一致: 合計={m['buy'][0]:,} vs (一般={m['buy'][1]:,} + 制度={m['buy'][2]:,} = {m['buy'][1]+m['buy'][2]:,})")
        print(f"  行内数値単語: {' '.join(m['words'][:8])}")

if __name__ == "__main__":
    diagnose_mismatches()
