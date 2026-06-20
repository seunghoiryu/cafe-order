import os
import re
import io
import pandas as pd
import streamlit as st
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

st.set_page_config(page_title="카페 발주 리스트", page_icon="☕", layout="wide")

SHEET_ID = "1HztR9CkmD2Y_URULXA9IK7DM8MHv57UWOEaej13N53A"
SHEET_GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

DEFAULT_PASSWORD = "1234"
APP_PASSWORD = st.secrets.get("APP_PASSWORD", DEFAULT_PASSWORD)

if "login_ok" not in st.session_state:
    st.session_state.login_ok = False

if not st.session_state.login_ok:
    st.title("☕ 카페 발주 리스트")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("입장"):
        if password == APP_PASSWORD:
            st.session_state.login_ok = True
            st.rerun()
        else:
            st.error("비밀번호가 맞지 않습니다.")
    st.stop()

def register_korean_font():
    font_candidates = [
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/AppleGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("KoreanFont", path))
                return "KoreanFont"
            except Exception:
                pass
    return "Helvetica"

PDF_FONT = register_korean_font()

def safe_filename(text):
    text = re.sub(r"[^\w가-힣.-]+", "_", str(text))
    return text.strip("_")

@st.cache_data(ttl=60)
def load_items_from_google_sheet():
    try:
        df = pd.read_csv(SHEET_CSV_URL)
    except Exception as e:
        st.error("구글시트를 불러오지 못했습니다. 시트 공유 설정을 확인해주세요.")
        st.caption(str(e))
        st.stop()

    required_cols = {"category", "item", "active"}
    if not required_cols.issubset(df.columns):
        st.error("구글시트 첫 줄은 category, item, active 컬럼이어야 합니다.")
        st.stop()

    df = df.fillna("")
    df["category"] = df["category"].astype(str).str.strip()
    df["item"] = df["item"].astype(str).str.strip()
    df["active"] = df["active"].astype(str).str.upper().str.strip()

    df = df[(df["category"] != "") & (df["item"] != "")]
    df = df[df["active"].isin(["Y", "YES", "TRUE", "1", "사용"])]

    if df.empty:
        st.warning("표시할 품목이 없습니다. 구글시트의 active 값을 Y로 입력해주세요.")
    return df

def make_pdf_bytes(order_date, staff_name, rows, memo):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "KoreanTitle",
        parent=styles["Title"],
        fontName=PDF_FONT,
        fontSize=18,
        leading=24,
        alignment=1,
    )
    normal_style = ParagraphStyle(
        "KoreanNormal",
        parent=styles["Normal"],
        fontName=PDF_FONT,
        fontSize=10,
        leading=14,
    )

    story = []
    story.append(Paragraph("카페 발주 리스트", title_style))
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph(f"발주일: {order_date}", normal_style))
    story.append(Paragraph(f"작성자: {staff_name or '-'}", normal_style))
    story.append(Spacer(1, 5 * mm))

    table_data = [["카테고리", "품목", "수량", "단위/비고"]]
    for r in rows:
        table_data.append([r["category"], r["item"], str(r["qty"]), r["note"]])

    table = Table(table_data, colWidths=[28 * mm, 70 * mm, 25 * mm, 62 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)

    if memo:
        story.append(Spacer(1, 7 * mm))
        story.append(Paragraph("전체 메모", normal_style))
        story.append(Paragraph(str(memo).replace("\n", "<br/>"), normal_style))

    doc.build(story)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value

st.title("☕ 카페 발주 리스트")
st.caption("구글시트 품목표를 기준으로 불러옵니다. 품목 수정은 구글시트에서 하면 됩니다.")

df = load_items_from_google_sheet()

with st.sidebar:
    st.header("발주 정보")
    order_date = st.date_input("발주일", date.today())
    staff_name = st.text_input("작성자", placeholder="예: 김직원")
    st.divider()
    if st.button("품목 새로고침"):
        st.cache_data.clear()
        st.rerun()
    if st.button("로그아웃"):
        st.session_state.login_ok = False
        st.rerun()

selected_rows = []

for category in df["category"].drop_duplicates():
    with st.expander(f"[{category}]", expanded=True):
        cat_df = df[df["category"] == category].reset_index(drop=True)
        cols = st.columns(2)
        for idx, row in cat_df.iterrows():
            item = row["item"]
            key_base = f"{category}_{idx}_{item}"
            with cols[idx % 2]:
                checked = st.checkbox(item, key=f"check_{key_base}")
                if checked:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        qty = st.number_input("수량", min_value=0.0, step=1.0, key=f"qty_{key_base}")
                    with c2:
                        note = st.text_input("단위/비고", placeholder="예: 박스, 개, 병", key=f"note_{key_base}")
                    selected_rows.append({
                        "category": category,
                        "item": item,
                        "qty": qty,
                        "note": note,
                    })

with st.expander("[기타] 리스트에 없는 품목 직접 입력", expanded=True):
    extra_count = st.number_input("기타 품목 개수", min_value=0, max_value=20, step=1, value=0)
    for i in range(int(extra_count)):
        c1, c2, c3 = st.columns([3, 1, 3])
        with c1:
            extra_item = st.text_input(f"기타 품목 {i+1}", key=f"extra_item_{i}", placeholder="예: 얼음컵 뚜껑")
        with c2:
            extra_qty = st.number_input("수량", min_value=0.0, step=1.0, key=f"extra_qty_{i}")
        with c3:
            extra_note = st.text_input("단위/비고", key=f"extra_note_{i}", placeholder="예: 1박스")
        if extra_item.strip():
            selected_rows.append({
                "category": "기타",
                "item": extra_item.strip(),
                "qty": extra_qty,
                "note": extra_note,
            })

st.divider()
memo = st.text_area("전체 메모", placeholder="특이사항이 있으면 입력하세요.")

st.subheader("선택한 발주 품목")
if selected_rows:
    preview = pd.DataFrame(selected_rows)
    st.dataframe(preview, use_container_width=True, hide_index=True)

    pdf_bytes = make_pdf_bytes(order_date, staff_name, selected_rows, memo)
    file_name = f"발주리스트_{order_date}_{safe_filename(staff_name or '직원')}.pdf"

    st.download_button(
        label="PDF 다운로드",
        data=pdf_bytes,
        file_name=file_name,
        mime="application/pdf",
        type="primary",
    )
else:
    st.info("발주할 품목을 체크하거나 기타 품목을 입력해주세요.")