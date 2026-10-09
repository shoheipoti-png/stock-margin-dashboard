import pdfplumber
import requests

def check_pdf_lines():
    pdf_url = "https://www.jpx.co.jp/markets/statistics-equities/margin/tvdivq0000001rn1-att/20261008_mtall.pdf"
    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    with open("test.pdf", "wb") as f:
        f.write(res.content)
        
    with pdfplumber.open("test.pdf") as pdf:
        page = pdf.pages[21]  # キオクシア(285A)がある22ページ目を指定
        print(f"検出された直線(lines)の数: {len(page.lines)}")
        print(f"検出された矩形(rects)の数: {len(page.rects)}")
        print(f"検出された曲線(curves)の数: {len(page.curves)}")
        
        # 縦線のX座標を抽出して表示
        v_lines = sorted(list(set([round(l["x0"], 1) for l in page.lines if l["width"] <= 1.0])))
        print(f"縦線のX座標一覧: {v_lines}")

if __name__ == "__main__":
    check_pdf_lines()
