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

def debug_1570_shs_row():
    pdf_url = get_latest_pdf_url()
    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    
    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
        # 4ページ目（インデックス 3）
        p3 = pdf.pages[3]
        words = p3.extract_words(x_tolerance=2, y_tolerance=2)
        
        # 1570の金額行が top=356 付近だったため、
        # その上段（株数行）を含む top=335〜365 の全単語をY座標順に出力
        print("\n=== 日経レバ周辺（上段・下段）の全単語配置 ===")
        near_words = [w for w in words if 335.0 <= w["top"] <= 365.0]
        
        # Y座標ごとにまとめて行として表示
        rows_by_y = {}
        for w in sorted(near_words, key=lambda x: (x["top"], x["x0"])):
            matched_key = None
            for y_k in rows_by_y:
                if abs(w["top"] - y_k) <= 3.0:
                    matched_key = y_k
                    break
            if matched_key is None:
                matched_key = round(w["top"], 1)
                rows_by_y[matched_key] = []
            rows_by_y[matched_key].append(w)
            
        for y_k, rwords in sorted(rows_by_y.items()):
            row_str = " ".join([f"{w['text']}(x={w['x0']:.0f})" for w in rwords])
            print(f"\n[Y={y_k} の行]:\n  {row_str}")

if __name__ == "__main__":
    debug_1570_shs_row()
