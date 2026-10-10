import os
import re
import requests
import pdfplumber
import io
from bs4 import BeautifulSoup

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"

def get_latest_pdf_url():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(JPX_URL, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        if '_mtall.pdf' in a['href']:
            href = a['href']
            return href if href.startswith('http') else "https://www.jpx.co.jp" + href
    return None

def diagnose_page_one():
    pdf_url = get_latest_pdf_url()
    print(f"取得PDF URL: {pdf_url}")
    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    
    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
        p0 = pdf.pages[0]
        words = p0.extract_words(x_tolerance=2, y_tolerance=2)
        
        print("\n=== 1. 1ページ目で検出された「1570」または関連文字列 ===")
        target_words = [w for w in words if "1570" in w["text"] or "レバレッジ" in w["text"]]
        for w in target_words:
            print(f"テキスト: '{w['text']}', x0={w['x0']:.1f}, x1={w['x1']:.1f}, top={w['top']:.1f}, bottom={w['bottom']:.1f}")

        if target_words:
            ref_y = target_words[0]["top"]
            print(f"\n=== 2. 日経レバと同じ高さ帯（Y={ref_y:.1f}付近）にある全単語の物理配置 ===")
            row_words = [w for w in words if abs(w["top"] - ref_y) <= 6.0]
            for w in sorted(row_words, key=lambda x: x["x0"]):
                print(f"  x0={w['x0']:.1f}..{w['x1']:.1f} | text='{w['text']}'")

        print("\n=== 3. 1ページ目で検出された「Shs.」または「株数」アンカー一覧 ===")
        anchors = [w for w in words if "Shs" in w["text"] or "株数" in w["text"]]
        for a in anchors[:10]:  # 最初の10件
            print(f"  x0={a['x0']:.1f}..{a['x1']:.1f}, top={a['top']:.1f} | text='{a['text']}'")

if __name__ == "__main__":
    diagnose_page_one()
