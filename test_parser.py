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

def debug_1570_page4():
    pdf_url = get_latest_pdf_url()
    print(f"対象PDF: {pdf_url}")
    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    
    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
        # 4ページ目（インデックス 3）
        p3 = pdf.pages[3]
        words = p3.extract_words(x_tolerance=2, y_tolerance=2)
        
        print("\n=== 4ページ目で「1570」を含む単語の探索 ===")
        found_words = [w for w in words if "1570" in w["text"]]
        for w in found_words:
            print(f"発見: '{w['text']}', x0={w['x0']:.1f}, x1={w['x1']:.1f}, top={w['top']:.1f}, bottom={w['bottom']:.1f}")
            
            # その単語と同じ行（Y座標が近い単語）を全列挙
            row_words = [rw for rw in words if abs(rw["top"] - w["top"]) <= 4.0]
            print("\n--- この行の全単語の物理配置 ---")
            for rw in sorted(row_words, key=lambda x: x["x0"]):
                print(f"  x0={rw['x0']:5.1f}..{rw['x1']:5.1f} | text='{rw['text']}'")

if __name__ == "__main__":
    debug_1570_page4()
