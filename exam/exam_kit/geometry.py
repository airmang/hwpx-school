"""렌더 PDF 기하 — 텍스트 층 없이(한양신명조는 곡선으로 나간다) 글리프 채움 도형의 bbox로 판정한다.

Task 2 스파이크(upstream/evidence/spike_synthetic.py)의 분할 판정을 킷 상수로 옮겨 왔다.
문항 분할: 단의 첫 줄이 단 왼끝에서 시작하지 않으면(번호 자리가 아니면) 앞 단에서 이어진 문항이다.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .kit import Kit

LINE_PT = 11.0 * 1.6  # 11pt × 160% — 한 줄 높이(줄 묶기 허용치의 기준)


@dataclass(frozen=True)
class Line:
    page: int          # 1부터
    col: int           # 1부터
    y0: float
    dx: float          # 줄 첫 글리프 x0 − 단 왼끝(pt)
    boxes: tuple       # 글리프 bbox(pymupdf.Rect), x 순
    text: str = ""     # 텍스트 층 글리프(킷 render.glyphs text)면 그 글자들, x 순 — 곡선이면 빈 글


def column_lefts(kit: Kit) -> list[float]:
    left = kit.page["margin"]["left"] / 100.0
    w, gap = kit.columns["width"] / 100.0, kit.columns["gap"] / 100.0
    return [left + i * (w + gap) for i in range(kit.columns["count"])]


def body_bottom(kit: Kit) -> float:
    """본문 하단 = 용지 − 아래 여백 − 꼬리말(꼬리말의 쪽 번호 글리프를 본문으로 세지 않는다)."""
    m = kit.page["margin"]
    return (kit.page["height"] - m["bottom"] - m["footer"]) / 100.0


def glyphs(page) -> list:
    """곡선(글리프) 채움 도형 — 표 테두리(채움 없음)·큰 도형은 뺀다."""
    return [d["rect"] for d in page.get_drawings()
            if d.get("fill") is not None and 0.3 < d["rect"].width < 40 and d["rect"].height < 40]


def separator_x(kit: Kit) -> float:
    """단 구분선 x — 왼쪽 단 끝 + 단 간격의 반."""
    return column_lefts(kit)[0] + (kit.columns["width"] + kit.columns["gap"] / 2) / 100.0


def page_body_top(page, kit: Kit) -> float:
    """단 구분선(단 사이 가는 세로 실선) y0 — 쪽마다 다른 본문 상단(1쪽은 결재란 아래)을 이걸로 잡는다.

    구분선은 그 쪽 내용 높이만큼만 그려진다(짧은 마지막 쪽은 쪽 절반보다 짧다). 그래서 구분선 x 근처의 세로선 가운데
    가장 긴 것을 쓴다(1쪽 결재란 칸선이 같은 x에 있어도 구분선이 더 길다). 없으면(빈 쪽) 위 여백 + 머리말.
    결재란·머리말 글자는 텍스트 층(굴림)이라 1pt 위까지 받아도 섞이지 않는다.
    """
    sx = separator_x(kit)
    rects = [d["rect"] for d in page.get_drawings()
             if d["rect"].width < 1.5 and d["rect"].height > LINE_PT * 2 and abs(d["rect"].x0 - sx) < 2.0]
    if not rects:
        m = kit.page["margin"]
        return (m["top"] + m["header"]) / 100.0
    return max(rects, key=lambda r: r.height).y0 - 1.0  # 단 맨 위 간격 0이면 `[` 같은 글리프가 구분선 위끝과 거의 같은 y


def text_lines(page) -> list:
    """텍스트 층 글자 줄 bbox — 곡선으로 안 나가는 글꼴(〈보기〉 ㄱ·ㄴ·ㄷ, `∼`, 굴림 등)."""
    return [pymupdf.Rect(ln["bbox"]) for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
            if "".join(sp["text"] for sp in ln["spans"]).strip()]


_위, _아래 = 8.5 / 11.0, 1.5 / 11.0  # 글자 상자: 기준선 위 0.77em ~ 아래 0.14em(11pt 실측 8.5·1.5pt의 비)


def body_text_chars(page, kit: Kit, *, with_text: bool = False) -> list:
    """텍스트 층 본문 글자(글꼴 킷 render.text_fonts) — 관리박스·머리말·꼬리 박스의 굴림·함초롬돋움은 뺀다.

    글자 bbox는 글꼴 올림폭 때문에 곡선 글리프보다 3pt 위에서 시작한다(렌더 실측: ㄱ bbox y0 411.1, 같은 줄 ① 414.1).
    곡선 글리프와 한 줄로 묶이도록 기준선(origin) 위 0.77em ~ 아래 0.14em(11pt면 8.5·1.5pt)으로 둔다.
    with_text면 (상자, 글자) 쌍.
    """
    fonts = tuple(kit.render["text_fonts"])
    out = [(pymupdf.Rect(ch["bbox"][0], ch["origin"][1] - sp["size"] * _위, ch["bbox"][2], ch["origin"][1] + sp["size"] * _아래),
            ch["c"])
           for b in page.get_text("rawdict")["blocks"] for ln in b.get("lines", [])
           for sp in ln["spans"] if sp["font"].startswith(fonts)
           for ch in sp["chars"] if ch["c"].strip()]
    return out if with_text else [r for r, _ in out]


def column_lines(pdf: Path, kit: Kit, *, text: bool = False) -> list[Line]:
    """읽는 차례(쪽 → 단 → y)의 글리프 줄. 같은 줄 = y0가 반 줄 이내. text면 텍스트 층 본문 글자도 넣는다."""
    lefts = column_lefts(kit)
    w = kit.columns["width"] / 100.0
    bottom = body_bottom(kit)
    out: list[Line] = []
    with pymupdf.open(str(pdf)) as doc:
        for pno, page in enumerate(doc, 1):
            top = page_body_top(page, kit)
            if kit.render["glyphs"] == "text":  # 본문이 텍스트 층(학교 B) — 글자가 곧 글리프, 줄에 글도 담는다
                gs = body_text_chars(page, kit, with_text=True)
            else:
                gs = [(g, "") for g in glyphs(page) + (body_text_chars(page, kit) if text else [])]
            tail = tail_box_rect(page, kit)  # 꼬리 박스 안 글자는 본문 줄이 아니다(학교 B는 꼬리 글도 본문 글꼴)
            if tail is not None:
                zone = pymupdf.Rect(tail.x0 - 1, tail.y0 - 1, tail.x1 + 1, tail.y1 + 1)
                gs = [gt for gt in gs if not zone.contains(gt[0])]
            for ci, cl in enumerate(lefts, 1):
                col = sorted((gt for gt in gs if cl - 2 <= gt[0].x0 < cl + w and top <= gt[0].y0 < bottom),
                             key=lambda gt: gt[0].y0)
                cur: list = []
                for gt in col:
                    if cur and gt[0].y0 >= cur[0][0].y0 + LINE_PT * 0.5:
                        out.append(_line(pno, ci, cl, cur))
                        cur = []
                    cur.append(gt)
                if cur:
                    out.append(_line(pno, ci, cl, cur))
    return out


def _line(pno: int, ci: int, cl: float, items: list) -> Line:
    items = sorted(items, key=lambda gt: gt[0].x0)
    boxes = tuple(g for g, _ in items)
    return Line(pno, ci, min(g.y0 for g in boxes), boxes[0].x0 - cl, boxes, "".join(t for _, t in items))


def column_first_lines(pdf: Path, kit: Kit) -> list[tuple[int, int, float]]:
    """(쪽, 단, 첫 줄 dx) — 문항 머리(번호 자리)면 ≈ 0, 이어진 줄이면 > 2pt."""
    seen: set[tuple[int, int]] = set()
    out = []
    for ln in column_lines(pdf, kit):
        if (ln.page, ln.col) not in seen:
            seen.add((ln.page, ln.col))
            out.append((ln.page, ln.col, ln.dx))
    return out


def splits(pdf: Path, kit: Kit, *, tol: float = 2.0) -> list[tuple[int, int, float]]:
    """문항 분할 — 첫 줄이 단 왼끝에서 tol pt 넘게 들어간 단."""
    return [(p, c, round(dx, 1)) for p, c, dx in column_first_lines(pdf, kit) if dx > tol]


def first_chunk_width(line: Line, *, gap: float = 3.0) -> float:
    """줄 첫 덩어리(글리프 사이 틈이 gap pt 이하로 이어진 무리)의 폭 — 머리 줄이면 자동번호 `N.`."""
    boxes = line.boxes
    x1 = boxes[0].x1
    for g in boxes[1:]:
        if g.x0 - x1 > gap:
            break
        x1 = max(x1, g.x1)
    return x1 - boxes[0].x0


@dataclass(frozen=True)
class Box:
    """단 왼끝에 붙은 테두리 틀 — 좌우 세로선이 같은 y 구간인 쌍. kind: "박스"(〈보기〉·자료) | "표"(격자표)."""

    page: int
    col: int
    top: float                              # 테두리 윗선 y(〈보기〉는 제목이 걸친 선)
    bottom: float
    titled: bool                            # 윗선에 걸친 글리프(`< 보 기 >`)가 있다
    lines: tuple[tuple[float, float, float], ...]  # 안쪽 글리프 줄 (y0, y1, dx)
    kind: str = "박스"

    @property
    def top_gap(self) -> float:
        return self.lines[0][0] - self.top

    @property
    def bottom_gap(self) -> float:
        """마지막 줄 글리프 아래 ~ 테두리 아랫선."""
        return self.bottom - self.lines[-1][1]


def boxes(pdf: Path, kit: Kit, *, width: float | None = None) -> list[Box]:
    """쪽 → 단 → y 차례의 테두리 틀. width = 틀 폭(pt, 기본 본문 표 폭) — 좌우 세로선 짝을 찾는 데 쓴다.

    격자표는 열 구분선이 틀 윗선에서 곧장 내려오므로 "표"로 가른다(자료 안의 표는 안여백만큼 아래에서 시작해
    "박스" 그대로). 안에 글리프 줄이 없는 틀은 버린다.
    """
    w = (width if width is not None else kit.columns["body_table_width"] / 100.0)
    out: list[Box] = []
    with pymupdf.open(str(pdf)) as doc:
        for pno, page in enumerate(doc, 1):
            strokes = [d["rect"] for d in page.get_drawings() if d.get("fill") is None]
            gs = glyphs(page)
            for ci, cl in enumerate(column_lefts(kit), 1):
                def 세로(x):
                    return {(round(r.y0, 1), round(r.y1, 1)) for r in strokes
                            if r.width < 0.5 and r.height > LINE_PT and abs(r.x0 - x) < 1.0}
                for top, bottom in sorted(세로(cl) & 세로(cl + w)):
                    inner = [g for g in gs if cl < g.x0 < cl + w and top - LINE_PT * 0.5 < g.y0 < bottom]
                    titled = any(g.y0 < top < g.y1 for g in inner)
                    lines: list[list[float]] = []
                    for g in sorted((g for g in inner if g.y0 > top + 1.0), key=lambda g: g.y0):
                        if lines and g.y0 < lines[-1][0] + LINE_PT * 0.5:
                            lines[-1][1], lines[-1][2] = max(lines[-1][1], g.y1), min(lines[-1][2], g.x0 - cl)
                        else:
                            lines.append([g.y0, g.y1, g.x0 - cl])
                    if not lines:
                        continue
                    grid = any(cl + 2 < r.x0 < cl + w - 2 and r.width < 0.5 and abs(r.y0 - top) < 1.0
                               and r.y1 <= bottom + 1.0 for r in strokes)
                    out.append(Box(pno, ci, top, bottom, titled, tuple(tuple(x) for x in lines), "표" if grid else "박스"))
    return out


# ---- Task 26: 쪽 배치 측정(단별 사용 높이·문항 머리·꼬리 박스) ------------------

HEAD_CHUNK_MAX = 25.0  # 머리 줄 첫 덩어리 `N.`/`NN.` 폭 상한(실측 8.3~15.1pt)
_점 = 3.0              # 번호 뒤 마침표 글리프(실측 1.3×1.4pt) — 덩어리 끝이 이보다 작으면 번호


_글_머리 = re.compile(r"^\d{1,3}\.")


def is_head(line: Line, *, tol: float = 2.0) -> bool:
    """문항 머리 줄 — 단 왼끝에서 시작하고 첫 덩어리가 `N.`(끝 글리프가 마침표 크기).
    텍스트 층 줄(line.text)이면 글이 `N.`으로 시작하는지로 본다.

    세트 머리 `[a∼b]`·세트 지문(바탕글)도 단 왼끝에서 시작하지만 첫 덩어리가 마침표로 끝나지 않는다.
    """
    if line.dx > tol:
        return False
    if line.text:
        return bool(_글_머리.match(line.text))
    boxes = line.boxes
    chunk = [boxes[0]]
    for g in boxes[1:]:
        if g.x0 - chunk[-1].x1 > 3.0:
            break
        chunk.append(g)
    last = chunk[-1]
    return len(chunk) >= 2 and last.width < _점 and last.height < _점 and first_chunk_width(line) < HEAD_CHUNK_MAX


def tail_box_rect(page, kit: Kit):
    """꼬리 박스(폭 = kit.tailbox.width) 테두리의 외곽 — 단 왼끝에서 시작하는 그 폭의 가로선 무리. 없으면 None.

    본문 표(격자·박스)는 폭이 body_table_width라 여기 걸리지 않는다(30088 vs 30888, 8pt 차). 1쪽 관리박스의
    유의 박스는 폭이 같지만 쪽 위쪽에 있어 아래 절반만 본다(꼬리 박스는 용지 기준 아래에 고정).
    """
    w = kit.tailbox["width"] / 100.0
    lefts = column_lefts(kit)
    half = page.rect.height / 2
    hs = [d["rect"] for d in page.get_drawings()
          if d.get("fill") is None and d["rect"].height < 1.5 and abs(d["rect"].width - w) < 2.0
          and d["rect"].y0 > half and any(abs(d["rect"].x0 - cl) < 1.5 for cl in lefts)]
    if not hs:
        return None
    # 꼬리 박스는 쪽 맨 아래에 있다 — 폭이 비슷한 다른 상자(학교 B의 ◦ 자료 상자 295.1 vs 296.2pt)가 걸려도
    # 가장 아래 가로선에서 박스 높이 안의 무리만 꼬리로 본다.
    low = max(r.y1 for r in hs) - kit.tailbox["height"] / 100.0 - 2.0
    hs = [r for r in hs if r.y0 >= low]
    return pymupdf.Rect(min(r.x0 for r in hs), min(r.y0 for r in hs), max(r.x1 for r in hs), max(r.y1 for r in hs))


def tail_box_top(kit: Kit) -> float:
    """꼬리 박스 윗선 y(pt) — 용지 기준 세로 오프셋 + 바깥 여백(렌더 실측 856.92 = 854 + 2.84)."""
    return (kit.tailbox["vertOffset"] + kit.tailbox.get("outMargin", 0)) / 100.0


@dataclass(frozen=True)
class ColumnLayout:
    page: int
    col: int
    top: float                       # 본문 상단(단 구분선 위끝)
    bottom: float | None             # 단의 마지막 내용 아래끝(글리프·테두리·그림, 꼬리 박스 제외). 빈 단이면 None
    heads: tuple[float, ...]         # 문항 머리 줄 y0
    first_is_head: bool | None       # 단 맨 윗줄이 문항 머리인가(빈 단이면 None)


@dataclass(frozen=True)
class PageLayout:
    page: int
    columns: tuple[ColumnLayout, ...]
    tail_box: tuple[float, float, float, float] | None  # 꼬리 박스 외곽(x0, y0, x1, y1)

    @property
    def blank(self) -> bool:
        """본문 내용이 하나도 없는 쪽(꼬리 박스만 있어도 빈 쪽)."""
        return all(c.bottom is None for c in self.columns)


def measure(pdf: Path, kit: Kit) -> list[PageLayout]:
    """쪽마다 두 단의 (a) 맨 윗줄이 머리인가 (b) 마지막 내용 y (c) 머리 y 목록, 그리고 꼬리 박스 자리."""
    lefts = column_lefts(kit)
    w = kit.columns["width"] / 100.0
    bottom = body_bottom(kit)
    lines = column_lines(pdf, kit)
    out: list[PageLayout] = []
    with pymupdf.open(str(pdf)) as doc:
        for pno, page in enumerate(doc, 1):
            top = page_body_top(page, kit)
            tail = tail_box_rect(page, kit)
            zone = None if tail is None else pymupdf.Rect(tail.x0 - 1, tail.y0 - 1, tail.x1 + 1, tail.y1 + 1)
            strokes = [d["rect"] for d in page.get_drawings() if d.get("fill") is None]
            images = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
            texts = text_lines(page)
            cols = []
            for ci, cl in enumerate(lefts, 1):
                mine = [ln for ln in lines if ln.page == pno and ln.col == ci]
                ys = [g.y1 for ln in mine for g in ln.boxes if zone is None or not zone.contains(g)]
                ys += [r.y1 for r in strokes + images + texts
                       if cl - 2 <= r.x0 and r.x1 <= cl + w + 2 and top <= r.y0 and r.y1 <= bottom
                       and not (zone is not None and zone.contains(r))]
                cols.append(ColumnLayout(pno, ci, top, max(ys) if ys else None,
                                         tuple(ln.y0 for ln in mine if is_head(ln)),
                                         is_head(mine[0]) if mine else None))
            out.append(PageLayout(pno, tuple(cols), None if tail is None else tuple(tail)))
    return out


# ---- Task 30: 문항 묶음 높이(균형 배치·간격 상한) -----------------------------------------

@dataclass(frozen=True)
class Extent:
    """문항 묶음 하나가 렌더에서 차지한 조각 — 단마다 (쪽, 단, 윗끝, 아랫끝). 둘 이상이면 단을 넘겨 나뉘었다."""

    segments: tuple[tuple[int, int, float, float], ...]

    @property
    def top(self) -> tuple[int, int, float]:
        p, c, y0, _ = self.segments[0]
        return p, c, y0

    @property
    def height(self) -> float:
        return sum(y1 - y0 for _, _, y0, y1 in self.segments)


def group_extents(pdf: Path, kit: Kit, set_first: set[int] = frozenset()) -> list[Extent]:
    """읽는 차례 문항 묶음의 조각. 묶음 윗끝 = 문항 머리 줄 윗끝, 세트 첫 문항(set_first, 0부터)은 그 앞의 세트 머리 줄
    (머리 앞에서 단 왼끝에 붙은 첫 줄 — 문항 안 줄은 번호·원문자·박스 여백만큼 들어가 있다). 아랫끝 = 다음 묶음 윗끝 앞까지
    그 단에 있는 글리프·텍스트 층 글자·선(박스·표 테두리)·그림의 아래끝 최댓값(꼬리 박스 제외)."""
    lines = column_lines(pdf, kit, text=True)
    heads = [i for i, ln in enumerate(lines) if is_head(ln)]
    tops: list[tuple[int, int, float]] = []
    for k, h in enumerate(heads):
        top = lines[h]
        if k in set_first:
            lo = heads[k - 1] + 1 if k else 0
            first = next((lines[j] for j in range(lo, h) if lines[j].dx < 2.0 and not is_head(lines[j])), None)
            if first is not None:
                top = first
        tops.append((top.page, top.col, top.y0))
    lefts = column_lefts(kit)
    w = kit.columns["width"] / 100.0
    bottom_limit = body_bottom(kit)
    items: dict[tuple[int, int], list[tuple[float, float]]] = {}
    col_top: dict[tuple[int, int], float] = {}
    with pymupdf.open(str(pdf)) as doc:
        for pno, page in enumerate(doc, 1):
            top = page_body_top(page, kit)
            tail = tail_box_rect(page, kit)
            zone = None if tail is None else pymupdf.Rect(tail.x0 - 1, tail.y0 - 1, tail.x1 + 1, tail.y1 + 1)
            rects = ([d["rect"] for d in page.get_drawings()] + [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
                     + text_lines(page))
            for ci, cl in enumerate(lefts, 1):
                col_top[(pno, ci)] = top
                items[(pno, ci)] = [(r.y0, r.y1) for r in rects
                                    if cl - 2 <= r.x0 and r.x1 <= cl + w + 2 and top <= r.y0 and r.y1 <= bottom_limit
                                    and not (zone is not None and zone.contains(r))]
    order = sorted(items)
    out = []
    for k, (p, c, y0) in enumerate(tops):
        end = tops[k + 1] if k + 1 < len(tops) else None
        segs = []
        for key in order[order.index((p, c)):]:
            if end is not None and key > end[:2]:
                break
            start = y0 if key == (p, c) else col_top[key]
            stop = end[2] if end is not None and key == end[:2] else float("inf")
            ys = [b for a, b in items[key] if start - 0.5 <= a < stop - 5.0]  # 다음 머리의 텍스트 층 글자(글리프보다 3pt 위)는 빼고
            if ys:
                segs.append((key[0], key[1], start, max(ys)))
        out.append(Extent(tuple(segs) or ((p, c, y0, y0),)))
    return out
