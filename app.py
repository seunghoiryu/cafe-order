import os
import re
import io
import tempfile
from datetime import date

import pandas as pd
import streamlit as st
import requests
from PIL import Image, ImageDraw, ImageFont

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

st.set_page_config(page_title="카페 발주 리스트", page_icon="☕", layout="wide")

# ===== 구글시트 설정 =====
SHEET_ID = "1HztR9CkmD2Y_URULXA9IK7DM8MHv57UWOEaej13N53A"
SHEET_GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# ===== 비밀번호 설정 =====
DEFAULT_PASSWORD = "0928"
APP_PASSWORD = st.secrets.get("APP_PASSWORD", DEFAULT_PASSWORD)

# 이미지 생성용 한글 폰트: 서버 실행 시 임시 다운로드
FONT_URL = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf"

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

@st.cache_resource
def get_korean_font_path():
    font_path = os.path.join(tempfile.gettempdir(), "NotoSansCJKkr-Regular.otf")
    if not os.path.exists(font_path):
        r = requests.get(FONT_URL, timeout=20)
        r.raise_for_status()
        with open(font_path, "wb") as f:
            f.write(r.content)
    return font_path

@st.cache_resource
def setup_pdf_font():
    # ReportLab 기본 내장 CID 폰트라 클라우드에서도 한글 PDF 깨짐 방지
    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    return "HYGothic-Medium"

PDF_FONT = setup_pdf_font()

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

def build_kakao_text(order_date, staff_name, rows, memo):
    lines = []
    lines.append("☕ 카페 발주 리스트")
    lines.append(f"발주일: {order_date}")
    lines.append(f"작성자: {staff_name or '-'}")
    lines.append("")

    current_category = None
    for r in rows:
        if r["category"] != current_category:
            current_category = r["category"]
            lines.append(f"[{current_category}]")
        note = f" / {r['note']}" if str(r["note"]).strip() else ""
        lines.append(f"- {r['item']}: {r['qty']}{note}")
    if memo:
        lines.append("")
        lines.append("[메모]")
        lines.append(str(memo))
    return "\n".join(lines)

def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def wrap_text(draw, text, font, max_width):
    words = list(str(text))
    lines = []
    current = ""
    for ch in words:
        test = current + ch
        if text_size(draw, test, font)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines

def make_order_image_bytes(order_date, staff_name, rows, memo):
    font_path = get_korean_font_path()

    width = 1080
    margin = 70
    y = 70
    bg = "white"
    img = Image.new("RGB", (width, 1600), bg)
    draw = ImageDraw.Draw(img)

    font_title = ImageFont.truetype(font_path, 58)
    font_header = ImageFont.truetype(font_path, 34)
    font_body = ImageFont.truetype(font_path, 30)
    font_small = ImageFont.truetype(font_path, 26)

    def add_text(text, x, y, font, fill=(20, 20, 20), max_width=None, line_gap=12):
        if max_width:
            lines = wrap_text(draw, text, font, max_width)
        else:
            lines = [text]
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += text_size(draw, line, font)[1] + line_gap
        return y

    y = add_text("☕ 카페 발주 리스트", margin, y, font_title)
    y += 20
    y = add_text(f"발주일: {order_date}", margin, y, font_small, fill=(80, 80, 80))
    y = add_text(f"작성자: {staff_name or '-'}", margin, y, font_small, fill=(80, 80, 80))
    y += 30

    current_category = None
    for r in rows:
        if y > img.height - 220:
            new_img = Image.new("RGB", (width, img.height + 900), bg)
            new_img.paste(img, (0, 0))
            img = new_img
            draw = ImageDraw.Draw(img)

        if r["category"] != current_category:
            current_category = r["category"]
            y += 18
            draw.rounded_rectangle((margin, y, width - margin, y + 56), radius=16, fill=(242, 242, 242))
            y = add_text(f"[{current_category}]", margin + 20, y + 11, font_header)
            y += 8

        note = f" / {r['note']}" if str(r["note"]).strip() else ""
        item_line = f"• {r['item']}  {r['qty']}{note}"
        y = add_text(item_line, margin + 18, y, font_body, max_width=width - margin * 2 - 36, line_gap=14)
        y += 6

    if memo:
        y += 20
        draw.rounded_rectangle((margin, y, width - margin, y + 56), radius=16, fill=(242, 242, 242))
        y = add_text("[메모]", margin + 20, y + 11, font_header)
        y += 8
        y = add_text(str(memo), margin + 18, y, font_body, max_width=width - margin * 2 - 36)

    y += 70
    img = img.crop((0, 0, width, min(y, img.height)))

    output = io.BytesIO()
    img.save(output, format="PNG")
    png_value = output.getvalue()
    output.close()
    return png_value

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

    file_base = f"발주리스트_{order_date}_{safe_filename(staff_name or '직원')}"

    pdf_bytes = make_pdf_bytes(order_date, staff_name, selected_rows, memo)
    img_bytes = make_order_image_bytes(order_date, staff_name, selected_rows, memo)
    kakao_text = build_kakao_text(order_date, staff_name, selected_rows, memo)

    st.subheader("공유용 이미지 미리보기")
    st.image(img_bytes, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            label="이미지 PNG 다운로드",
            data=img_bytes,
            file_name=f"{file_base}.png",
            mime="image/png",
            type="primary",
        )
    with c2:
        st.download_button(
            label="PDF 다운로드",
            data=pdf_bytes,
            file_name=f"{file_base}.pdf",
            mime="application/pdf",
        )

    st.caption("모바일에서는 PNG 다운로드 후 사진/파일에서 카카오톡 공유하면 됩니다.")
    st.text_area("카카오톡 복사용 텍스트", kakao_text, height=220)
else:
    st.info("발주할 품목을 체크하거나 기타 품목을 입력해주세요.")
