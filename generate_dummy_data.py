"""
두 엑셀 더미 데이터 생성 스크립트
- data/sales_history.xlsx   : 판매이력 (한글 컬럼)
- data/product_catalog.xlsx : 제품카탈로그 (영문 컬럼, 다른 형식)
"""
import pandas as pd
import numpy as np
from pathlib import Path

np.random.seed(42)
Path("data").mkdir(exist_ok=True)

# ── 제품 마스터 (영문 컬럼, CSV처럼 flat한 형식) ─────────────────────
products = {
    "product_id": ["P001", "P002", "P003", "P004", "P005",
                   "P006", "P007", "P008", "P009", "P010"],
    "product_name": ["노트북 Pro 15", "스마트폰 Ultra", "태블릿 Air",
                     "무선 이어폰", "스마트워치 SE", "기계식 키보드",
                     "4K 모니터", "외장 SSD 1TB", "웹캠 HD", "USB 허브"],
    "category": ["노트북", "스마트폰", "태블릿", "음향기기", "웨어러블",
                 "주변기기", "모니터", "저장장치", "주변기기", "주변기기"],
    "brand": ["TechPro", "Samsung", "Apple", "Sony", "Apple",
              "Logitech", "LG", "Samsung", "Logitech", "Anker"],
    "cost_price": [800000, 600000, 450000, 80000, 200000,
                   120000, 350000, 90000, 45000, 30000],
    "supplier": ["TechPro Korea", "Samsung Elec", "Apple Korea", "Sony Korea", "Apple Korea",
                 "Logitech Korea", "LG Display", "Samsung SSD", "Logitech Korea", "Anker Korea"],
    "stock_qty": [50, 80, 60, 200, 100, 150, 30, 200, 100, 300],
    "release_year": [2023, 2024, 2023, 2023, 2024, 2022, 2023, 2024, 2023, 2023],
}

df_product = pd.DataFrame(products)
df_product.to_excel("data/product_catalog.xlsx", index=False)
print("✅ data/product_catalog.xlsx 생성 완료")

# ── 판매이력 (한글 컬럼, 트랜잭션 형식) ──────────────────────────────
branches = {"B01": "강남점", "B02": "홍대점", "B03": "신촌점", "B04": "판교점"}
payment_methods = ["신용카드", "현금", "간편결제", "포인트"]

product_ids = df_product["product_id"].tolist()
cost_map = dict(zip(df_product["product_id"], df_product["cost_price"]))

dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")

rows = []
for i in range(500):
    pid = np.random.choice(product_ids)
    qty = int(np.random.choice([1, 1, 1, 2, 2, 3], p=[0.5, 0.15, 0.15, 0.1, 0.05, 0.05]))
    base_price = cost_map[pid]
    margin = np.random.uniform(1.15, 1.45)
    unit_price = int(round(base_price * margin / 1000) * 1000)
    branch_code = np.random.choice(list(branches.keys()))

    rows.append({
        "주문번호": f"ORD-2024-{i+1:04d}",
        "주문일시": np.random.choice(dates),
        "고객번호": f"C{np.random.randint(1000, 9999)}",
        "상품코드": pid,
        "수량": qty,
        "단가": unit_price,
        "판매금액": unit_price * qty,
        "지점코드": branch_code,
        "지점명": branches[branch_code],
        "결제방법": np.random.choice(payment_methods, p=[0.5, 0.1, 0.3, 0.1]),
        "반품여부": np.random.choice(["N", "Y"], p=[0.95, 0.05]),
    })

df_sales = pd.DataFrame(rows)
df_sales["주문일시"] = pd.to_datetime(df_sales["주문일시"]).dt.date
df_sales.to_excel("data/sales_history.xlsx", index=False)
print("✅ data/sales_history.xlsx 생성 완료")
print(f"\n판매이력: {len(df_sales)}건 / 제품카탈로그: {len(df_product)}개")
