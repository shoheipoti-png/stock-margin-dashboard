import pdfplumber

pdf_path = "20261001_mtall.pdf"  # PDFのパスに合わせて変更

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    table = page.extract_table()
    print(table[0])
