"""
app/components/pdf_export.py — 법률 자문 보고서 PDF 생성

generate_report_pdf(report, result) → bytes

ReportLab Platypus 직접 사용 (xhtml2pdf 우회 — 한글 폰트 완전 제어).
의존: reportlab (xhtml2pdf 설치 시 자동 포함)
"""

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


# ─────────────────────────────────────────────────────────────────────────────
# 한글 폰트 등록
# ─────────────────────────────────────────────────────────────────────────────

_FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    # Linux — Nanum (apt: fonts-nanum)
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    # Linux — Noto CJK (apt: fonts-noto-cjk)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKkr-Regular.otf",
    # macOS
    "/System/Library/Fonts/AppleGothic.ttf",
    "/Library/Fonts/AppleGothic.ttf",
    # 프로젝트 로컬 폰트 (fonts/ 폴더에 TTF 배치 시 최우선)
    str(Path(__file__).parent.parent.parent / "fonts" / "NanumGothic.ttf"),
    str(Path(__file__).parent.parent.parent / "fonts" / "malgun.ttf"),
]

_FONT_NAME  = "KoreanFont"
_REGISTERED = False


def _register() -> None:
    """한글 TTF 폰트를 pdfmetrics에 등록. 이미 등록됐으면 스킵."""
    global _REGISTERED, _FONT_NAME
    if _REGISTERED:
        return

    # pdfmetrics에 이미 등록된 경우(핫리로드 등) → 재등록 불필요
    try:
        if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
            _REGISTERED = True
            return
    except Exception:
        pass

    for path in _FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(_FONT_NAME, path))
            _REGISTERED = True
            return
        except Exception:
            continue

    # fallback: Helvetica (한글 깨짐이지만 예외 없이 동작)
    _FONT_NAME = "Helvetica"
    _REGISTERED = True


# ─────────────────────────────────────────────────────────────────────────────
# 스타일 팩토리
# ─────────────────────────────────────────────────────────────────────────────

def _styles() -> dict:
    _register()
    f = _FONT_NAME
    return {
        "title": ParagraphStyle(
            "title", fontName=f, fontSize=20, leading=28,
            textColor=colors.HexColor("#1a3c6e"), spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "meta", fontName=f, fontSize=9, leading=13,
            textColor=colors.HexColor("#666666"), spaceAfter=10,
        ),
        "summary": ParagraphStyle(
            "summary", fontName=f, fontSize=10.5, leading=16,
            textColor=colors.HexColor("#1a3c6e"),
            leftIndent=10, rightIndent=10,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=f, fontSize=12, leading=18,
            textColor=colors.HexColor("#1a3c6e"),
            spaceBefore=14, spaceAfter=6,
        ),
        "card_title": ParagraphStyle(
            "card_title", fontName=f, fontSize=10.5, leading=15,
            textColor=colors.HexColor("#1a3c6e"), spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body", fontName=f, fontSize=10, leading=16, spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "small", fontName=f, fontSize=9, leading=14,
            textColor=colors.HexColor("#555555"),
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", fontName=f, fontSize=8.5, leading=13,
            textColor=colors.HexColor("#888888"), spaceBefore=10,
        ),
        "warn_body": ParagraphStyle(
            "warn_body", fontName=f, fontSize=10, leading=16,
            textColor=colors.HexColor("#7a5c00"),
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 보조 빌더
# ─────────────────────────────────────────────────────────────────────────────

import re as _re


def _safe(text) -> str:
    """None → 빈 문자열, HTML 이스케이프 + 줄바꿈 → <br/>."""
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _md(text) -> str:
    """
    마크다운 → ReportLab Paragraph 호환 HTML 변환.
    지원: **bold**, *italic*, `code`, ### 제목(bold 처리).
    """
    t = str(text or "")
    # HTML 이스케이프 먼저
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # ### 제목 → bold
    t = _re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", t, flags=_re.MULTILINE)
    # **bold**
    t = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    # *italic* (단독 *)
    t = _re.sub(r"\*([^*]+?)\*", r"<i>\1</i>", t)
    # `code`
    t = _re.sub(r"`([^`]+?)`", r"<font face='Courier'>\1</font>", t)
    # 줄바꿈
    t = t.replace("\n", "<br/>")
    return t


def _md_paragraphs(text, style) -> list:
    """
    마크다운 텍스트를 단락별로 분리해 Paragraph 리스트로 반환.
    - 빈 줄로 단락 구분
    - '- ' / '* ' 로 시작하는 줄은 bullet 처리
    """
    from reportlab.platypus import Paragraph as _Para
    bullet_style = ParagraphStyle(
        "bullet_md", parent=style, leftIndent=12, bulletIndent=0, spaceAfter=2,
    )
    elems = []
    for block in _re.split(r"\n{2,}", text.strip()):
        lines = block.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _re.match(r"^[-*•]\s+", stripped):
                content = _re.sub(r"^[-*•]\s+", "", stripped)
                elems.append(_Para(f"• {_md(content)}", bullet_style))
            else:
                elems.append(_Para(_md(stripped), style))
    return elems or [_Para("", style)]


_CARD_INDENT = 9  # 카드 leftPadding과 동일 (포인트)


def _card(title: str, body_lines: list[str], s: dict) -> list:
    """테두리 카드 블록 — 제목 행 + 본문을 각 행으로 분리해 페이지 분할 허용."""
    elems = []
    # 제목 카드
    title_tbl = Table([[Paragraph(title, s["card_title"])]], colWidths=[155 * mm])
    title_tbl.setStyle(TableStyle([
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#dde3ed")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef3fa")),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), _CARD_INDENT),
        ("RIGHTPADDING",  (0, 0), (-1, -1), _CARD_INDENT),
    ]))
    elems.append(title_tbl)
    elems.append(Spacer(1, 4))
    # 본문: 카드와 동일한 들여쓰기 + 마크다운 렌더링
    body_style = ParagraphStyle(
        "body_indented",
        parent=s["body"],
        leftIndent=_CARD_INDENT,
        rightIndent=_CARD_INDENT,
    )
    for raw in body_lines:
        elems += _md_paragraphs(raw, body_style)
    elems.append(Spacer(1, 8))
    return elems


def _warn_card(lines: list[str], s: dict) -> list:
    """회색지대 경고 — Paragraph 직접 추가."""
    elems = []
    header_tbl = Table(
        [[Paragraph("⚠  불확실 영역 (회색지대)", s["card_title"])]],
        colWidths=[155 * mm],
    )
    header_tbl.setStyle(TableStyle([
        ("BOX",        (0, 0), (-1, -1), 0.8, colors.HexColor("#f0c040")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff8e1")),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 9),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 9),
    ]))
    elems.append(header_tbl)
    for line in lines:
        elems.append(Paragraph(f"• {_md(line)}", s["warn_body"]))
    elems.append(Paragraph("위 사유로 인해 외부 법률 전문가 자문을 권고합니다.", s["warn_body"]))
    elems.append(Spacer(1, 6))
    return elems


def _summary_card(text: str, s: dict) -> list:
    """요약 박스 — 짧은 텍스트이므로 Table 유지."""
    tbl = Table(
        [[Paragraph(f"<b>요청 요약:</b>  {_safe(text)}", s["summary"])]],
        colWidths=[155 * mm],
    )
    tbl.setStyle(TableStyle([
        ("BOX",      (0, 0), (-1, -1), 1, colors.HexColor("#1a3c6e")),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING",   (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 9),
        ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#eef4fb")),
    ]))
    return [tbl, Spacer(1, 10)]


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────

def generate_report_pdf(report: dict, result: dict) -> bytes:
    """
    보고서 dict + 결과 dict → PDF bytes.

    Args:
        report: DB에서 조회한 report row (dict)
        result: json.loads(report["result"]) 결과

    Returns:
        PDF 바이트

    Raises:
        RuntimeError: PDF 변환 실패 시
    """
    _register()
    s = _styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title="법률 자문 보고서",
    )

    date_str = (report.get("created_at") or "")[:10] or "-"
    story = []

    # ── 헤더 ────────────────────────────────────────────────────────────────
    story.append(Paragraph("법률 자문 보고서", s["title"]))
    story.append(Paragraph(f"작성일: {date_str}", s["meta"]))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=colors.HexColor("#1a3c6e"), spaceAfter=10))

    # ── 요약 ────────────────────────────────────────────────────────────────
    summary = result.get("summary") or report.get("summary") or ""
    story += _summary_card(summary, s)

    # ── 1. 적용 법령 ─────────────────────────────────────────────────────────
    story.append(Paragraph("1. 적용 법령", s["h2"]))
    laws = result.get("applicable_laws", [])
    if laws:
        for law in laws:
            title = _md(f"{law.get('law_name','')}  {law.get('article','')}")
            content = law.get("content", "")
            story += _card(title, [content], s)
    else:
        story.append(Paragraph("해당 법령 없음", s["small"]))

    # ── 2. 관련 판례 ─────────────────────────────────────────────────────────
    story.append(Paragraph("2. 관련 판례", s["h2"]))
    precs = result.get("precedents", [])
    if precs:
        for p in precs:
            lines = []
            if p.get("summary"):
                lines.append(f"**판결 요지:** {p['summary']}")
            if p.get("relevance"):
                lines.append(f"**관련성:** {p['relevance']}")
            story += _card(_md(p.get("case_no", "판례")), lines, s)
    else:
        story.append(Paragraph("관련 판례 없음", s["small"]))

    # ── 3. 결론 ──────────────────────────────────────────────────────────────
    story.append(Paragraph("3. 결론", s["h2"]))
    conclusion = result.get("conclusion", "")
    if conclusion:
        story += _md_paragraphs(conclusion, s["body"])
        story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("-", s["small"]))

    # ── 4. 회색지대 (있을 때만) ───────────────────────────────────────────────
    gray_areas = result.get("gray_areas", [])
    if gray_areas:
        story.append(Paragraph("4. 불확실 영역 (회색지대)", s["h2"]))
        story += _warn_card(gray_areas, s)

    # ── 5. 자문 요청 원문 ─────────────────────────────────────────────────────
    prompt_text = report.get("prompt", "")
    if prompt_text:
        story.append(Paragraph("자문 요청 원문", s["h2"]))
        story += _md_paragraphs(prompt_text, s["small"])
        story.append(Spacer(1, 6))

    # ── 면책 고지 ─────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#cccccc"), spaceBefore=14))
    story.append(Paragraph(
        "본 보고서는 법적 효력이 없으며 참고용입니다. "
        "중요 사안은 반드시 법률 전문가 상담을 받으시기 바랍니다.",
        s["disclaimer"],
    ))

    try:
        doc.build(story)
    except Exception as e:
        raise RuntimeError(f"PDF 생성 실패: {e}") from e

    return buf.getvalue()
