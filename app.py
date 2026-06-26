"""
쇼핑몰 판매이력 대시보드
- 두 엑셀(판매이력 + 제품카탈로그) 병합
- 외부 API(환율) 로 USD 환산금액 컬럼 추가
- Streamlit Cloud 배포 대상
"""
import io
import html
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np
import requests
from pathlib import Path

st.set_page_config(
    page_title="쇼핑몰 판매 대시보드",
    page_icon="🛒",
    layout="wide",
)

# ── 외부 API: USD/KRW 환율 ──────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_usd_krw() -> float:
    """open.er-api.com — 무료, API 키 불필요"""
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        res.raise_for_status()
        return res.json()["rates"]["KRW"]
    except Exception:
        return 1350.0  # fallback

usd_krw = fetch_usd_krw()

# ── Gemini API 키 로드 (secrets.toml → 환경변수 순서로 탐색) ────────
import os

def _load_gemini_key() -> str:
    # 1순위: .streamlit/secrets.toml
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key and key != "YOUR_API_KEY_HERE":
            return key
    except Exception:
        pass
    # 2순위: 환경변수 GEMINI_API_KEY
    return os.environ.get("GEMINI_API_KEY", "")

GEMINI_API_KEY = _load_gemini_key()


# ── Gemini AI 보고서 헬퍼 함수 ──────────────────────────────────────

def build_data_summary(df: pd.DataFrame, start, end, usd_krw: float) -> str:
    """현재 필터링된 데이터로 텍스트 요약을 생성합니다."""
    total_revenue = df["판매금액"].sum()
    total_profit = df["이익"].sum()
    avg_profit_rate = df["이익률(%)"].mean()
    return_rate = (df["반품여부"] == "Y").mean() * 100

    cat_summary = (
        df.groupby("category")["판매금액"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )
    branch_summary = (
        df.groupby("지점명")["판매금액"]
        .sum()
        .sort_values(ascending=False)
    )
    top_products = (
        df.groupby("product_name")["판매금액"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )

    lines = [
        f"분석 기간: {start.date()} ~ {end.date()}",
        f"총 주문 건수: {len(df):,}건",
        f"총 매출: ₩{total_revenue:,.0f}  (USD ${total_revenue / usd_krw:,.0f})",
        f"총 이익: ₩{total_profit:,.0f}",
        f"평균 이익률: {avg_profit_rate:.1f}%",
        f"반품률: {return_rate:.1f}%",
        "",
        "카테고리별 매출 Top 5:",
    ]
    for cat, val in cat_summary.items():
        lines.append(f"  - {cat}: ₩{val:,.0f}")

    lines += ["", "지점별 매출:"]
    for branch, val in branch_summary.items():
        lines.append(f"  - {branch}: ₩{val:,.0f}")

    lines += ["", "베스트 상품 Top 5:"]
    for prod, val in top_products.items():
        lines.append(f"  - {prod}: ₩{val:,.0f}")

    return "\n".join(lines)


def generate_gemini_report(api_key: str, data_summary: str) -> str:
    """Gemini API를 호출해 한국어 분석 보고서를 생성합니다."""
    try:
        import google.generativeai as genai
    except ImportError:
        return "오류: `google-generativeai` 패키지가 설치되지 않았습니다. `pip install google-generativeai`를 실행하세요."

    import time

    prompt = f"""당신은 전문 비즈니스 분석가입니다.
아래 쇼핑몰 판매 데이터를 분석하여 한국어로 전문적인 요약 보고서를 작성해 주세요.

[판매 데이터 요약]
{data_summary}

다음 형식으로 보고서를 작성해 주세요:

1. 핵심 성과 요약 (Executive Summary)
2. 매출 분석
3. 카테고리 분석
4. 지점별 성과 분석
5. 주요 인사이트 및 개선 권고사항

각 섹션을 명확하게 구분하고 구체적인 수치를 인용하여 분석해 주세요.
"""

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-lite")

        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                err_str = str(e)
                # 429 quota 오류 → retry_delay 파싱 후 대기
                if "429" in err_str or "quota" in err_str.lower():
                    import re
                    delay_match = re.search(r"retry.*?(\d+).*?second", err_str, re.IGNORECASE)
                    wait = int(delay_match.group(1)) + 2 if delay_match else 30
                    if attempt < 2:
                        time.sleep(wait)
                        continue
                    return (
                        f"⚠️ API 요청 한도 초과입니다. {wait}초 후 다시 시도해 주세요.\n\n"
                        f"(무료 티어 한도: 1,500회/일, 15회/분)"
                    )
                return f"Gemini API 호출 오류: {e}"
    except Exception as e:
        return f"Gemini API 설정 오류: {e}"


def _get_korean_font() -> str:
    """OS에 맞는 한글 TTF 폰트를 찾아 ReportLab에 등록하고 폰트 이름을 반환합니다.
    시스템에 한글 폰트가 없으면 NanumGothic을 자동 다운로드합니다.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_name = "KoreanFont"

    # OS별 한글 폰트 후보 경로 (TTF/TTC 모두 포함)
    candidates = [
        # macOS
        "/Library/Fonts/NanumGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        # Windows
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/gulim.ttc",
        # Linux
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
                return font_name
            except Exception:
                continue  # 해당 폰트 파일 등록 실패 시 다음 후보로

    # 시스템에 한글 폰트 없음 → NanumGothic 자동 다운로드
    font_dir = Path.home() / ".streamlit" / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    font_path = font_dir / "NanumGothic.ttf"

    if not font_path.exists():
        url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        font_path.write_bytes(resp.content)

    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    return font_name


def create_pdf_report(report_text: str, data_summary: str) -> bytes:
    """보고서 텍스트를 한국어 PDF로 변환합니다."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

    KR = _get_korean_font()

    title_style = ParagraphStyle(
        "Title", fontName=KR, fontSize=18, spaceAfter=4, alignment=1,
        textColor=colors.HexColor("#1a1a2e"),
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", fontName=KR, fontSize=9, spaceAfter=10, alignment=1,
        textColor=colors.grey,
    )
    heading_style = ParagraphStyle(
        "Heading", fontName=KR, fontSize=13, spaceBefore=10, spaceAfter=4,
        textColor=colors.HexColor("#16213e"),
    )
    body_style = ParagraphStyle(
        "Body", fontName=KR, fontSize=10, spaceAfter=3, leading=16,
    )
    data_style = ParagraphStyle(
        "Data", fontName=KR, fontSize=9, spaceAfter=2, leading=14,
        textColor=colors.HexColor("#444444"),
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )

    story = []

    # 타이틀
    generated_at = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    story.append(Paragraph("쇼핑몰 판매 AI 분석 보고서", title_style))
    story.append(Paragraph(f"생성일시: {generated_at}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#16213e")))
    story.append(Spacer(1, 5 * mm))

    # 보고서 본문 (Gemini 응답)
    for line in report_text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 2 * mm))
            continue

        safe = html.escape(line)

        # 숫자로 시작하는 섹션 제목 (예: 1. 핵심 성과 요약)
        if len(line) > 2 and line[0].isdigit() and line[1] in ".）)":
            story.append(Paragraph(safe, heading_style))
        # 마크다운 굵은 제목
        elif line.startswith("##"):
            story.append(Paragraph(safe.lstrip("#").strip(), heading_style))
        # 불릿 포인트
        elif line.startswith(("- ", "* ", "• ")):
            story.append(Paragraph("• " + safe[2:], body_style))
        else:
            story.append(Paragraph(safe, body_style))

    # 데이터 요약 섹션
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("📊 분석 데이터 요약", heading_style))
    for line in data_summary.strip().split("\n"):
        if line.strip():
            story.append(Paragraph(html.escape(line), data_style))

    doc.build(story)
    return buf.getvalue()


# ── 데이터 로드 ─────────────────────────────────────────────────────
@st.cache_data
def load_data():
    base = Path(__file__).parent / "data"

    # 엑셀 1: 판매이력 (한글 컬럼)
    df_sales = pd.read_excel(base / "sales_history.xlsx", parse_dates=["주문일시"])

    # 엑셀 2: 제품카탈로그 (영문 컬럼)
    df_product = pd.read_excel(base / "product_catalog.xlsx")

    # ── 두 엑셀 병합 (판매이력.상품코드 ↔ 제품카탈로그.product_id) ──
    df = df_sales.merge(
        df_product[["product_id", "product_name", "category", "brand", "cost_price"]],
        left_on="상품코드",
        right_on="product_id",
        how="left",
    ).drop(columns=["product_id"])

    # ── 파생 컬럼 ──────────────────────────────────────────────────
    df["원가합계"] = df["cost_price"] * df["수량"]
    df["이익"] = df["판매금액"] - df["원가합계"]
    df["이익률(%)"] = (df["이익"] / df["판매금액"] * 100).round(1)

    return df


df_raw = load_data()

# USD 환산 컬럼 추가 (외부 API 값 활용)
df_raw["판매금액(USD)"] = (df_raw["판매금액"] / usd_krw).round(2)

# ── 사이드바 필터 ───────────────────────────────────────────────────
with st.sidebar:
    st.title("🛒 쇼핑몰 대시보드")
    st.caption(f"💱 USD/KRW: {usd_krw:,.1f}")

    st.divider()
    st.subheader("필터")

    date_min = df_raw["주문일시"].min().date()
    date_max = df_raw["주문일시"].max().date()
    date_range = st.date_input(
        "기간",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max,
    )

    all_branches = sorted(df_raw["지점명"].unique())
    selected_branches = st.multiselect("지점", all_branches, default=all_branches)

    all_categories = sorted(df_raw["category"].dropna().unique())
    selected_categories = st.multiselect("카테고리", all_categories, default=all_categories)

    show_returns = st.toggle("반품 건 포함", value=True)

# ── 필터 적용 ───────────────────────────────────────────────────────
if len(date_range) == 2:
    start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
else:
    start, end = pd.Timestamp(date_min), pd.Timestamp(date_max)

df = df_raw[
    (df_raw["주문일시"] >= start)
    & (df_raw["주문일시"] <= end)
    & (df_raw["지점명"].isin(selected_branches))
    & (df_raw["category"].isin(selected_categories))
]

if not show_returns:
    df = df[df["반품여부"] == "N"]

if df.empty:
    st.warning("선택 조건에 해당하는 데이터가 없습니다.")
    st.stop()

# ── KPI 카드 ────────────────────────────────────────────────────────
st.title("쇼핑몰 판매이력 대시보드")
st.caption(f"데이터 범위: {df['주문일시'].min().date()} ~ {df['주문일시'].max().date()} | 조회 건수: {len(df):,}건")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("총 매출", f"₩{df['판매금액'].sum():,.0f}")
c2.metric("USD 환산 매출", f"${df['판매금액(USD)'].sum():,.0f}")
c3.metric("총 주문수", f"{len(df):,}건")
c4.metric("평균 주문금액", f"₩{df['판매금액'].mean():,.0f}")
c5.metric("총 이익", f"₩{df['이익'].sum():,.0f}")

st.divider()

# ── 탭 레이아웃 ─────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📈 매출 트렌드", "📦 상품 분석", "🏪 지점 분석", "📋 원본 데이터", "🤖 AI 보고서"]
)

# ─ Tab 1: 매출 트렌드 ───────────────────────────────────────────────
with tab1:
    freq_label = {"일별": "D", "주별": "W", "월별": "ME"}
    freq_choice = st.radio("집계 단위", list(freq_label.keys()), horizontal=True, index=2)
    freq = freq_label[freq_choice]

    trend = (
        df.set_index("주문일시")
        .resample(freq)["판매금액"]
        .sum()
        .reset_index()
        .rename(columns={"주문일시": "날짜", "판매금액": "매출"})
    )

    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("매출 추이")
        st.line_chart(trend.set_index("날짜")["매출"], height=300)

    with col_r:
        st.subheader("카테고리별 매출 비중")
        cat_pie = df.groupby("category")["판매금액"].sum().reset_index()
        cat_pie.columns = ["카테고리", "매출"]
        st.dataframe(
            cat_pie.sort_values("매출", ascending=False)
            .assign(비중=lambda x: (x["매출"] / x["매출"].sum() * 100).round(1).astype(str) + "%"),
            use_container_width=True,
            hide_index=True,
        )

# ─ Tab 2: 상품 분석 ─────────────────────────────────────────────────
with tab2:
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("상품별 매출 Top 10")
        top_products = (
            df.groupby("product_name")
            .agg(매출합계=("판매금액", "sum"), 판매건수=("주문번호", "count"), 평균이익률=("이익률(%)", "mean"))
            .sort_values("매출합계", ascending=False)
            .head(10)
            .reset_index()
            .rename(columns={"product_name": "상품명"})
        )
        top_products["매출합계"] = top_products["매출합계"].map("₩{:,.0f}".format)
        top_products["평균이익률"] = top_products["평균이익률"].map("{:.1f}%".format)
        st.dataframe(top_products, use_container_width=True, hide_index=True)

    with col_r:
        st.subheader("카테고리 × 지점 매출 히트맵")
        pivot = df.pivot_table(
            index="category", columns="지점명", values="판매금액", aggfunc="sum", fill_value=0
        )
        st.dataframe(
            pivot.style.background_gradient(cmap="YlOrRd", axis=None).format("₩{:,.0f}"),
            use_container_width=True,
        )

    st.subheader("브랜드별 매출 & 이익")
    brand_summary = (
        df.groupby("brand")
        .agg(매출=("판매금액", "sum"), 이익=("이익", "sum"), 건수=("주문번호", "count"))
        .sort_values("매출", ascending=False)
        .reset_index()
    )
    st.bar_chart(brand_summary.set_index("brand")[["매출", "이익"]], height=280)

# ─ Tab 3: 지점 분석 ─────────────────────────────────────────────────
with tab3:
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("지점별 매출 합계")
        branch_sales = (
            df.groupby("지점명")["판매금액"].sum().sort_values(ascending=False).reset_index()
        )
        st.bar_chart(branch_sales.set_index("지점명")["판매금액"], height=300)

    with col_r:
        st.subheader("결제방법 분포")
        pay = df["결제방법"].value_counts().reset_index()
        pay.columns = ["결제방법", "건수"]
        st.dataframe(pay, use_container_width=True, hide_index=True)

    st.subheader("지점별 상세 현황")
    branch_detail = (
        df.groupby("지점명")
        .agg(
            매출합계=("판매금액", "sum"),
            USD환산=("판매금액(USD)", "sum"),
            주문건수=("주문번호", "count"),
            평균단가=("단가", "mean"),
            총이익=("이익", "sum"),
            평균이익률=("이익률(%)", "mean"),
        )
        .reset_index()
    )
    branch_detail["매출합계"] = branch_detail["매출합계"].map("₩{:,.0f}".format)
    branch_detail["USD환산"] = branch_detail["USD환산"].map("${:,.0f}".format)
    branch_detail["평균단가"] = branch_detail["평균단가"].map("₩{:,.0f}".format)
    branch_detail["총이익"] = branch_detail["총이익"].map("₩{:,.0f}".format)
    branch_detail["평균이익률"] = branch_detail["평균이익률"].map("{:.1f}%".format)
    st.dataframe(branch_detail, use_container_width=True, hide_index=True)

# ─ Tab 4: 원본 데이터 ───────────────────────────────────────────────
with tab4:
    st.subheader("병합된 원본 데이터")
    st.caption("판매이력(sales_history.xlsx) + 제품카탈로그(product_catalog.xlsx) 병합 결과")

    display_cols = [
        "주문번호", "주문일시", "지점명", "product_name", "category", "brand",
        "수량", "단가", "판매금액", "판매금액(USD)", "원가합계", "이익", "이익률(%)",
        "결제방법", "반품여부",
    ]
    st.dataframe(df[display_cols].sort_values("주문일시", ascending=False), use_container_width=True, hide_index=True)

    csv = df[display_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ CSV 다운로드", csv, "sales_merged.csv", "text/csv")

# ─ Tab 5: AI 보고서 ─────────────────────────────────────────────────
with tab5:
    st.subheader("🤖 Gemini AI 판매 분석 보고서")
    st.caption("현재 필터 조건이 적용된 데이터를 기반으로 AI 보고서를 생성합니다.")

    if not GEMINI_API_KEY:
        st.error(
            "⚠️ Gemini API 키가 설정되지 않았습니다.\n\n"
            "관리자: `.streamlit/secrets.toml`의 `GEMINI_API_KEY` 값을 입력해 주세요."
        )
        st.stop()

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        generate_btn = st.button("📝 보고서 생성", type="primary", use_container_width=True)

    # 세션 스테이트에 보고서 캐싱
    if "ai_report_text" not in st.session_state:
        st.session_state["ai_report_text"] = None
    if "ai_report_summary" not in st.session_state:
        st.session_state["ai_report_summary"] = None

    if generate_btn:
        with st.spinner("Gemini AI가 데이터를 분석 중입니다..."):
            summary = build_data_summary(df, start, end, usd_krw)
            report = generate_gemini_report(GEMINI_API_KEY, summary)
            st.session_state["ai_report_text"] = report
            st.session_state["ai_report_summary"] = summary

    if st.session_state["ai_report_text"]:
        report_text = st.session_state["ai_report_text"]
        data_summary = st.session_state["ai_report_summary"]

        # 보고서 화면 표시
        st.markdown("---")
        st.markdown(report_text)

        # PDF 다운로드
        st.markdown("---")
        col_pdf, _ = st.columns([1, 3])
        with col_pdf:
            try:
                pdf_bytes = create_pdf_report(report_text, data_summary)
                filename = f"sales_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                st.download_button(
                    label="⬇️ PDF 다운로드",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"PDF 생성 오류: {e}")
