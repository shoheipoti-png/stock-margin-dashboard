import pdfplumber
import requests

def extract_column_boundaries():
    pdf_url = "https://www.jpx.co.jp/markets/statistics-equities/margin/tvdivq0000001rn1-att/20261008_mtall.pdf"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(pdf_url, headers=headers)
    with open("test.pdf", "wb") as f:
        f.write(res.content)
        
    with pdfplumber.open("test.pdf") as pdf:
        page = pdf.pages[21]  # 22ページ目
        
        # 高さ10pt以上、幅3pt以下の「縦の仕切りrect」を抽出
        v_rects = [r for r in page.rects if r["height"] > 10.0 and r["width"] <= 3.0]
        
        # 重複を除いてX座標（左端）をソート
        x_coords = sorted(list(set([round(r["x0"], 1) for r in v_rects])))
        
        print("=== 検出された縦の仕切り枠（カラム境界）のX座標一覧 ===")
        print(f"仕切り線の本数: {len(x_coords)} 本")
        print(x_coords)

if __name__ == "__main__":
    extract_column_boundaries()
