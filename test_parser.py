import pdfplumber
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://www.jpx.co.jp"
TARGET_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"

def get_latest_pdf_url():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(TARGET_PAGE_URL, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    
    for a in soup.find_all("a", href=True):
        if "mtall.pdf" in a["href"]:
            return urljoin(BASE_URL, a["href"])
    raise ValueError("PDFリンクが見つかりませんでした。")

def extract_column_boundaries():
    pdf_url = get_latest_pdf_url()
    print(f"取得したPDF URL: {pdf_url}")
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(pdf_url, headers=headers)
    res.raise_for_status()
    with open("test.pdf", "wb") as f:
        f.write(res.content)
        
    with pdfplumber.open("test.pdf") as pdf:
        page = pdf.pages[21]  # 22ページ目
        
        # 高さ8pt以上、幅3pt以下の「縦の仕切りrect」を抽出
        v_rects = [r for r in page.rects if r["height"] > 8.0 and r["width"] <= 3.0]
        
        # X座標を重複除外して昇順ソート
        x_coords = sorted(list(set([round(r["x0"], 1) for r in v_rects])))
        
        print("=== 検出された縦の仕切り枠（カラム境界）のX座標一覧 ===")
        print(f"仕切り線の本数: {len(x_coords)} 本")
        print(x_coords)

if __name__ == "__main__":
    extract_column_boundaries()
