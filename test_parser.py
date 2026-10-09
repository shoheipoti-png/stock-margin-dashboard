import requests
import pdfplumber
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

def check_pdf_structure():
    pdf_url = get_latest_pdf_url()
    print(f"取得したPDF URL: {pdf_url}")
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(pdf_url, headers=headers)
    res.raise_for_status()
    
    with open("test.pdf", "wb") as f:
        f.write(res.content)
        
    with pdfplumber.open("test.pdf") as pdf:
        page = pdf.pages[21]  # 22ページ目（キオクシア等）
        
        print(f"--- 22ページ目のオブジェクト検出結果 ---")
        print(f"ページサイズ (幅 x 高さ): {page.width} x {page.height}")
        print(f"検出された直線 (lines): {len(page.lines)} 本")
        print(f"検出された矩形 (rects): {len(page.rects)} 個")
        print(f"検出された曲線/点線 (curves): {len(page.curves)} 個")
        
        # 縦方向の線（太さ1.5以下の縦線）のX座標を調査
        v_lines = sorted(list(set([round(l["x0"], 1) for l in page.lines if abs(l["x0"] - l["x1"]) < 1.0])))
        print(f"縦の直線 X座標一覧 (計 {len(v_lines)} 本): {v_lines}")
        
        # 曲線・点線オブジェクトのX座標も調査
        v_curves = sorted(list(set([round(c["x0"], 1) for c in page.curves if abs(c["x0"] - c["x1"]) < 1.0])))
        if v_curves:
            print(f"縦の点線/曲線 X座標一覧: {v_curves[:15]}...")

if __name__ == "__main__":
    check_pdf_structure()
