from pathlib import Path

import pymupdf

from _kits import kit_dir
from exam_kit.geometry import (
    boxes,
    column_first_lines,
    column_lefts,
    column_lines,
    first_chunk_width,
    is_head,
    measure,
    separator_x,
    splits,
    tail_box_top,
)
from exam_kit.kit import load_kit

킷_디렉터리 = kit_dir()


def _합성_pdf(path: Path, kit, rows) -> Path:
    """rows: (단, y, [(dx, 폭), ...]) — 채움 사각형을 글리프 대용으로 그린다. 단 구분선은 y=100부터."""
    doc = pymupdf.open()
    page = doc.new_page(width=kit.page["width"] / 100, height=kit.page["height"] / 100)
    lefts = column_lefts(kit)
    sep_x = lefts[1] - kit.columns["gap"] / 200
    page.draw_line((sep_x, 100), (sep_x, 950), width=0.5)
    for col, y, boxes in rows:
        for dx, w in boxes:
            page.draw_rect(pymupdf.Rect(lefts[col - 1] + dx, y, lefts[col - 1] + dx + w, y + 9), color=None, fill=(0, 0, 0))
    doc.save(str(path))
    return path


def test_머리_줄과_분할(tmp_path):
    kit = load_kit(킷_디렉터리)
    rows = [
        (1, 200, [(0, 8), (12, 9), (22, 9)]),       # 머리: '1.' 덩어리 + 발문
        (1, 218, [(10.5, 9), (21, 9)]),             # 답지
        (2, 120, [(10.5, 9), (21, 9)]),             # 2단 첫 줄이 답지 → 분할
        (1, 50, [(0, 9)]),                          # 본문 상단(구분선) 위 — 무시
        (2, 980, [(0, 5)]),                         # 꼬리말 영역 — 무시
    ]
    pdf = _합성_pdf(tmp_path / "g.pdf", kit, rows)
    lines = column_lines(pdf, kit)
    assert [(l.col, round(l.dx, 1)) for l in lines] == [(1, 0.0), (1, 10.5), (2, 10.5)]
    assert round(first_chunk_width(lines[0]), 1) == 8.0
    assert column_first_lines(pdf, kit) == [(1, 1, lines[0].dx), (1, 2, lines[2].dx)]
    assert splits(pdf, kit) == [(1, 2, 10.5)]


def test_박스_찾기(tmp_path):
    kit = load_kit(킷_디렉터리)
    doc = pymupdf.open()
    page = doc.new_page(width=kit.page["width"] / 100, height=kit.page["height"] / 100)
    cl, w = column_lefts(kit)[0], kit.columns["body_table_width"] / 100
    page.draw_line((cl, 300), (cl, 360), width=0.36)            # 좌우 세로선(같은 y 구간)
    page.draw_line((cl + w, 300), (cl + w, 360), width=0.36)
    page.draw_line((cl + 5, 400), (cl + 5, 460), width=0.36)    # 짝 없는 세로선 — 박스 아님
    for y0, x in ((296, 130), (312, 20), (330, 30)):            # 윗선에 걸친 제목 + 내용 두 줄(둘째 줄 내어쓰기)
        page.draw_rect(pymupdf.Rect(cl + x, y0, cl + x + 9, y0 + 9), color=None, fill=(0, 0, 0))
    doc.save(str(tmp_path / "b.pdf"))
    [b] = boxes(tmp_path / "b.pdf", kit)
    assert (b.page, b.col, b.titled, len(b.lines)) == (1, 1, True, 2)
    assert [round(l[2]) for l in b.lines] == [20, 30]
    assert round(b.top_gap) == 12 and round(b.bottom_gap) == 21


def _글리프(page, x, y, w=9.0, h=9.0):
    page.draw_rect(pymupdf.Rect(x, y, x + w, y + h), color=None, fill=(0, 0, 0))


def _머리(page, cl, y, digits=1):
    """`N.` 머리 줄 — 숫자 글리프 + 마침표(1.3×1.4pt) + 틈 + 발문 글리프."""
    x = cl
    for _ in range(digits):
        _글리프(page, x, y, 5.5, 9.5)
        x += 6.5
    _글리프(page, x, y + 8, 1.3, 1.4)
    _글리프(page, x + 10, y, 9.7, 10.0)
    _글리프(page, x + 21, y, 9.7, 10.0)


def test_머리_판정(tmp_path):
    kit = load_kit(킷_디렉터리)
    doc = pymupdf.open()
    page = doc.new_page(width=kit.page["width"] / 100, height=kit.page["height"] / 100)
    cl = column_lefts(kit)[0]
    _머리(page, cl, 200)
    _머리(page, cl, 300, digits=2)
    for x in (0, 7.4, 14.8, 22.2):     # 세트 머리 `[3∼4]` — 덩어리가 마침표로 끝나지 않는다
        _글리프(page, cl + x, 400, 6.5, 11)
    _글리프(page, cl, 500, 9.7, 10)    # 바탕글 지문 `이 글은` — 첫 글자 뒤 공백
    _글리프(page, cl + 15, 500, 9.7, 10)
    _글리프(page, cl + 10.5, 600, 9.7, 10)  # 답지 줄(왼여백)
    doc.save(str(tmp_path / "h.pdf"))
    assert [is_head(ln) for ln in column_lines(tmp_path / "h.pdf", kit)] == [True, True, False, False, False]


def test_쪽_배치_측정(tmp_path):
    """쪽 1: 왼쪽 단 머리 둘(+ 아래 표 테두리가 마지막 내용), 오른쪽 단은 머리 아닌 줄로 시작. 쪽 2: 꼬리 박스만 → 빈 쪽."""
    kit = load_kit(킷_디렉터리)
    W, H = kit.page["width"] / 100, kit.page["height"] / 100
    doc = pymupdf.open()
    left, right = column_lefts(kit)
    p1 = doc.new_page(width=W, height=H)
    p1.draw_line((separator_x(kit), 100), (separator_x(kit), 950), width=0.5)  # 단 구분선
    _머리(p1, left, 200)
    _글리프(p1, left + 10.5, 218)
    _머리(p1, left, 400)
    p1.draw_line((left, 700), (left + kit.columns["body_table_width"] / 100, 700), width=0.36)  # 표 아랫선
    _글리프(p1, right + 10.5, 150)
    p2 = doc.new_page(width=W, height=H)
    top = tail_box_top(kit)
    x1 = right + kit.tailbox["width"] / 100
    for a, b in (((right, top), (x1, top)), ((right, top + 89.7), (x1, top + 89.7))):
        p2.draw_line(a, b, width=0.36)
    _글리프(p2, right + 10, top + 10)  # 꼬리 박스 안 글자는 본문이 아니다
    doc.save(str(tmp_path / "m.pdf"))
    lay = measure(tmp_path / "m.pdf", kit)
    c1, c2 = lay[0].columns
    assert [round(y) for y in c1.heads] == [200, 400] and c1.first_is_head is True
    assert round(c1.bottom) == 700                     # 표 테두리까지가 내용
    assert c2.heads == () and c2.first_is_head is False and round(c2.bottom) == 159
    assert lay[0].tail_box is None and not lay[0].blank
    assert lay[1].blank and round(lay[1].tail_box[1], 1) == round(top, 1)


def test_박스와_격자표_가르기_빈_틀_버리기(tmp_path):
    kit = load_kit(킷_디렉터리)
    doc = pymupdf.open()
    page = doc.new_page(width=kit.page["width"] / 100, height=kit.page["height"] / 100)
    cl, w = column_lefts(kit)[0], kit.columns["body_table_width"] / 100

    def 틀(y0, y1):
        page.draw_line((cl, y0), (cl, y1), width=0.36)
        page.draw_line((cl + w, y0), (cl + w, y1), width=0.36)

    틀(200, 260)                                                 # 자료 박스 — 안의 표는 안여백만큼 아래에서 시작
    page.draw_line((cl + 100, 215), (cl + 100, 245), width=0.36)
    _글리프(page, cl + 20, 220)
    틀(300, 340)                                                 # 격자표 — 열 구분선이 윗선에서 곧장
    page.draw_line((cl + 100, 300), (cl + 100, 340), width=0.36)
    _글리프(page, cl + 20, 305)
    틀(400, 440)                                                 # 글자 없는 틀 — 버린다
    doc.save(str(tmp_path / "k.pdf"))
    assert [(round(b.top), b.kind) for b in boxes(tmp_path / "k.pdf", kit)] == [(200, "박스"), (300, "표")]


def test_짧은_쪽의_본문_상단과_텍스트_층_글자(tmp_path):
    """짧은 마지막 쪽: 구분선이 쪽 절반보다 짧아도 본문 상단으로 잡는다. 텍스트 층 글자(ㄱ·ㄴ·ㄷ 등)도 단의 내용이다."""
    from exam_kit.geometry import page_body_top

    kit = load_kit(킷_디렉터리)
    W, H = kit.page["width"] / 100, kit.page["height"] / 100
    doc = pymupdf.open()
    left = column_lefts(kit)[0]
    sx = separator_x(kit)
    p1 = doc.new_page(width=W, height=H)
    p1.draw_line((sx, 99.2), (sx, 300), width=0.5)       # 짧은 구분선
    p1.draw_line((sx, 40), (sx, 80), width=0.5)          # 같은 x의 더 짧은 칸선(결재란 흉내) — 무시
    _머리(p1, left, 120)
    p1.insert_text((left + 12, 280), "ㄱ ㄴ ㄷ", fontsize=11)  # 텍스트 층, 글리프(곡선) 없음
    p2 = doc.new_page(width=W, height=H)                  # 구분선 없는 쪽
    doc.save(str(tmp_path / "t.pdf"))
    with pymupdf.open(str(tmp_path / "t.pdf")) as d:
        assert round(page_body_top(d[0], kit), 1) == 98.2
        m = kit.page["margin"]
        assert page_body_top(d[1], kit) == (m["top"] + m["header"]) / 100
    lay = measure(tmp_path / "t.pdf", kit)
    assert [round(y) for y in lay[0].columns[0].heads] == [120]
    assert lay[0].columns[0].bottom > 280  # 텍스트 층 줄까지가 내용


def test_잉크_상자는_글자_폭_상자_안의_잉크에_붙는다():
    """Windows 한컴 PDF의 Type3 글자 상자(글자 폭)를 잉크에 붙인다 — 노란 형광펜은 잉크가 아니고, 잉크가 없으면 원래 상자."""
    import pymupdf

    from exam_kit.geometry import _잉크_상자

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    page.draw_rect(pymupdf.Rect(52, 61, 57, 69), color=None, fill=(0, 0, 0))  # 글리프 잉크
    page.draw_rect(pymupdf.Rect(80, 60, 90, 70), color=None, fill=(1, 1, 0))  # 형광펜
    boxes = [pymupdf.Rect(50, 58, 60, 72), pymupdf.Rect(78, 58, 92, 72), pymupdf.Rect(100, 58, 110, 72)]
    a, b, c = _잉크_상자(page, boxes)
    assert all(abs(u - v) <= 0.3 for u, v in zip(a, (52, 61, 57, 69))), a
    assert b == boxes[1] and c == boxes[2]


def test_Windows_한컴_PDF가_아니면_Type3_글자를_더하지_않는다(tmp_path):
    import pymupdf

    from exam_kit.geometry import hancom_windows_pdf, type3_glyphs

    p = tmp_path / "mac.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "1. x")
    doc.set_metadata({"producer": "macOS Quartz PDFContext"})
    doc.save(str(p))
    with pymupdf.open(str(p)) as d:
        assert type3_glyphs(d[0]) == []
    assert hancom_windows_pdf(p) is False
