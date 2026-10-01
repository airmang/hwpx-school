"""로컬 조판 엔진(Part B) — 준비된 양식의 샘플 구역을 걷어내고 그 자리에 문항을 쓴다.

compose : 견본 채집(〈보기〉·자료 표, 세트 머리 글자 모양) → 문단 계획(머리·박스·답지·세트 머리) → 문단 보호
          → 샘플 구역 자리에 삽입(꼬리 뒤에 덧붙이지 않는다 — 한컴이 꼬리 뒤 내용을 버린다) → 정답 형광펜.

번호는 쓰지 않는다: 문항 머리는 스타일 `문항자동번호넣기`(paraPr heading NUMBER)라 한글이 `1.`을 그린다.
간격은 빈 문단이 아니라 문항 머리 paraPr의 prev 간격(kit.question_gap)으로만 만든다.
박스(〈보기〉·자료)는 양식 견본 표의 사본이다 — 셀 구조·테두리는 견본 그대로, 내용 셀과 레일 높이만 줄 수에 맞춘다.
md 표는 격자표(제출본 8번 모양), 그림은 회색조 사본, 답항표는 무테 표로 새로 짓는다 — 셋 다 글자처럼 취급한다.
답지는 들어가는 가장 촘촘한 배치형(2행 → 3행 → 5행)으로, 같은 줄 답지는 탭 하나로 잇는다 — 칸 자리는 양식 스타일의 탭.
1행은 자동으로 고르지 않는다(G3 판정 09-27 ③) — `{답항=1행}`으로 누를 때만 쓰고, 그때 칸을 고르게(가용 폭 ÷ 5, G2 판정
09-26) 문단 자체 탭(파생 tabPr·paraPr)을 단다. 양식 스타일은 그대로다.
원고의 ASCII `~`는 조판 전에 `∼`(U+223C)로 바꾼다(물결).
인라인 수식 `$…$`(LaTeX)은 한/글 수식(hp:equation, 글자처럼 취급)으로 쓴다(equation) — 그 자리 글자 크기를 수식 기준
크기로, 그 조각의 charPr run에 넣는다. 폭·줄 수 추정은 수식을 수식 상자 폭으로 센다. 물결·밑줄은 수식 안을 건드리지 않는다.
"""

from __future__ import annotations

import dataclasses
import io
import re
import xml.etree.ElementTree as StdET
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import lxml.etree as ET
from hwpx.document import HwpxDocument
from hwpx_automation.office.exam import profile_form
from PIL import Image, ImageOps

try:  # paragraph.add_picture가 쓰는 pic 생성기(private) — 칸 안에도 넣으려고 직접 부른다
    from hwpx.oxml.objects import _create_picture_element
except ImportError:  # 옮겨졌으면 임시 문단의 add_picture로 만든다(_Composer._pic_element)
    _create_picture_element = None

from . import HP, equation, q
from .kit import Kit, Metrics, style_ids
from .prepare import _top_tables, is_sample_box
from .scan import IMG_RE, TABLE_ROW_RE, Block, Question, QuestionSet, Scan
from .verify import question_heads

형광 = "#FFFF00"
_밑줄 = re.compile(r"__(.+?)__")

# 박스 내용 셀 높이 = (줄 수 − 1) × 줄 피치 + kit.metrics.box_extra. 제출본에서 한글이 스스로 늘린 내용 셀 5개 실측:
# 160%는 1760n + 261, 150%는 1652n + 369 — 둘 다 (n − 1) × 피치 + 2021. 한글은 셀을 늘리기만 하고 줄이지 않으므로
# 견본 높이(6336 = 3줄 + 여분 한 줄 가까이)를 두면 짧은 박스 아래가 빈다.
# 로마자 대문자는 반각보다 넓다 — Task 26 렌더 보정(답지 110개를 한 줄씩 렌더해 글리프 끝 − 원문자 시작을 잼):
# 한글·숫자·소문자·기호는 추정이 실측보다 0~9pt 크거나 같았고(안전 쪽), 대문자만 모자랐다(`④ MAC 주소` 실측 67.6 vs
# 추정 58.0 → 글자당 +320). 그래서 대문자를 534 + 320 = 854로 둔다(`I`처럼 좁은 글자는 넉넉해진다 — 안전 쪽).
# 단, +320은 사실상 표본 하나(`MAC`)에 기댄 값이다(`IP` 두 건은 좁은 I 덕에 모자라지 않았다). 대문자가 많은 실제 원고가
# 들어오면(약어·영문 용어) 같은 방식으로 다시 잰다.
# 박스 종류 → (견본 속성, 내용 셀 (열, 행), 레일 열들, 내용 스타일 역할)
# 〈보기〉 항목 내어쓰기(case, HWPUNIT) — 1학기 제출본 교사 박스의 다수 기하(Task 29 판정): ㄱ은 x = 0(앞 공백·왼여백 없음),
# 둘째 줄은 1950. 값 = 앞 공백 없이 내어쓰기를 준 교사 항목 23개(박스 6개)의 내어쓰기 중앙값(−1868~−2040, 최빈값도 −1950).
# 양식 스타일(앞 공백 + −2500)은 제출본 6번 박스만 썼다. 모든 박스에 같은 값을 쓴다.
def _박스(kit: Kit, kind: str) -> tuple[str, tuple[int, int], tuple[int, ...], str]:
    """박스 종류 → (견본 종류, 내용 셀 (열, 행), 레일 열들, 내용 스타일 역할) — 킷 boxes에서."""
    b = kit.boxes[kind]
    return kind, tuple(b["content_cell"]), tuple(b["rails"]), b["style"]


_항목_박스 = ("보기", "조건")  # 항목(ㄱ.·∙) 박스 — 글만 받고, 항목 문단 모양(item_pr)을 쓴다


def box_kind(kit: Kit, block: Block) -> str:
    """원고 블록 → 킷 박스 종류. 자료는 킷에 항목형 견본(use_when_items)이 있고 글 줄이 모두 그 모양이면 그 견본."""
    if block.kind not in kit.boxes:
        raise ValueError(f"L{block.line_no} :::{block.kind} — 이 킷({kit.name})에는 그 박스 견본이 없다")
    for kind, spec in kit.boxes.items():
        if kind.startswith(block.kind) and kind != block.kind and isinstance(spec, dict) and spec.get("use_when_items"):
            rx = re.compile(spec["use_when_items"])
            texts = [ln for ln in block.lines if ln.strip()]
            if texts and all(rx.match(ln.strip()) for ln in texts):
                return kind
    return block.kind

# 격자표·답항표 — 제출본 8번 표 실측: 셀 안여백 510/141, 바깥 여백 위아래 284, 한 줄 행 = 글자 1100 + 위아래 여백 282
# (표 높이 4146 = 3 × 1382). 글자처럼 취급한 개체의 줄 = 개체 높이 + 바깥 여백 + (피치 − 1100)(lineseg spacing 660).
# 답항 배치형 → (역할, 줄마다 답지 수). 5행은 한 줄에 하나(길면 내어쓰기로 접힌다)라 늘 들어간다.
배치형 = {"1행": ("choice1", (5,)), "2행": ("choice2", (3, 2)), "3행": ("choice3", (2, 2, 1)), "5행": ("choice5", (1,) * 5)}
자동_배치형 = ("2행", "3행", "5행")  # 1행은 눌러 둘 때만(G3 판정 09-27 — 짧은 답지도 두 줄로)
# 원고 머리 `답항: 1행부터`면 1행부터 고른다 — 답이 짧은 과목(수학 실물: 1행 배치가 주력, 10-01 오너 결정 3-가)
자동_배치형_1행부터 = ("1행",) + 자동_배치형
CM = 72000 / 25.4  # 1 cm = 2834.6 HWPUNIT
발문_이음_왼여백 = 1680  # 발문 둘째 줄부터의 자리(렌더 실측: 발문 이음 줄 첫 글리프 dx 17.3~17.8pt, 1770이면 참고 줄이 0.9pt 오른쪽) — 〈보기〉 뒤 참고 줄을 여기에 맞춘다
그림_DPI = 300      # 그림 원래 크기 = 원본 px ÷ 300dpi(인쇄 규격, Task 30) — 원고 폭이 이보다 작으면 줄여 넣는 것


_언어_키 = {"HANGUL": "hangul", "LATIN": "latin", "HANJA": "hanja", "JAPANESE": "japanese", "OTHER": "other",
          "SYMBOL": "symbol", "USER": "user"}


def code_font_ids(header, face: str) -> dict[str, str]:
    """언어 키(hangul …) → 고정폭 글꼴 face의 fontface 안 id. 없는 언어에는 그 글꼴을 덧붙인다(TTF — 인쇄 PC에 늘 있는 글꼴)."""
    out = {}
    for ff in header.element.iter(q("hh", "fontface")):
        key = _언어_키.get(ff.get("lang"))
        if key is None:
            continue
        font = next((f for f in ff.findall(q("hh", "font")) if f.get("face") == face), None)
        if font is None:
            ids = [int(f.get("id")) for f in ff.findall(q("hh", "font"))]
            font = ET.SubElement(ff, q("hh", "font"), {"id": str(max(ids, default=-1) + 1), "face": face, "type": "TTF",
                                                      "isEmbedded": "0"})
            ff.set("fontCnt", str(len(ff.findall(q("hh", "font")))))
            header.mark_dirty()
        out[key] = font.get("id")
    if "hangul" not in out:
        raise ValueError("양식이 바뀌었다: hh:fontface lang=HANGUL 없음")
    return out


def natural_width_cm(px: int) -> float:
    """그림 원본 폭(px)의 인쇄 크기(cm) — 그림_DPI 기준."""
    return px / 그림_DPI * 2.54
_구분행 = re.compile(r"^\|?(\s*:?-{3,}:?\s*\|)+\s*(:?-{3,}:?\s*)?$")
# 새 id를 매길 때 겹치면 안 되는 개체 — 표·그림만이 아니라 도형·수식도 같은 id 공간을 쓴다
_개체 = tuple(q("hp", t) for t in ("tbl", "pic", "rect", "ellipse", "line", "arc", "polygon", "curve", "connectLine",
                                  "container", "equation", "ole", "textart", "video", "chart"))


def _가림(text: str, m: Metrics):
    """원고 글 → (가린 글, 가린 글 조각의 추정 폭 함수, 수식들) — 가린 글은 수식 하나가 글자 하나(equation.mask),
    수식 폭은 수식 상자 폭 + 바깥 여백(기준 크기 m.char_height)."""
    masked, maths = equation.mask(text)
    ws = [equation.width(x, m.char_height) for x in maths]

    def 폭(s: str) -> int:
        return sum(ws[k] if (k := equation.자리_번호(ch)) is not None else m.char(ch) for ch in s)

    return masked, 폭, maths


def _글폭(text: str, m: Metrics) -> int:
    """원고 글의 추정 폭 — 수식 `$…$`은 수식 상자 폭으로 센다."""
    masked, 폭, _ = _가림(text, m)
    return 폭(masked)


def _긴_낱말(text: str, m: Metrics) -> int:
    """띄어쓰기로 나눈 낱말 가운데 가장 넓은 것의 추정 폭 — 수식 `$…$`은 안에 공백이 있어도 한 낱말이다."""
    masked, 폭, _ = _가림(text, m)
    return max(폭(t) for t in re.split(r"\s+", masked.strip()))


def _글(segs) -> str:
    """문단 조각들의 글(오류 알림용) — 수식은 원고 표기 `$…$`로."""
    return "".join(t.source if isinstance(t, equation.Math) else t for t, _ in segs)


def _바꾸기(text: str, pairs) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def 물결(text: str, pairs=()) -> str:
    """킷 typeset.text_replace의 (찾을 글, 바꿀 글)을 차례로 바꾼다. 예: ASCII `~` → `∼`(U+223C) — 어떤 양식 글꼴에서는
    `~`가 위로 뜬 작은 물결 `˜`로 찍힌다(세트 머리 `[7∼8]`은 `∼`). 수식 `$…$` 안은 그대로 둔다(LaTeX의 `~`는 띄움이다)."""
    return equation.outside(text, lambda s: _바꾸기(s, pairs))


def _물결_블록(b: Block, pairs) -> Block:
    """블록 글 줄·답항표 머리 — 그림 줄(경로)은 글이 아니라 그대로 둔다. 코드 줄(코드 블록, 자료 안의 ``` 사이)은 수식이
    없는 글이라 원래대로 모두 바꾼다."""
    lines, code = [], b.kind == "코드"
    for ln in b.lines:
        if b.kind != "코드" and ln.strip().startswith("```"):
            code = not code
            lines.append(_바꾸기(ln, pairs))
        elif IMG_RE.match(ln.strip()):
            lines.append(ln)
        else:
            lines.append(_바꾸기(ln, pairs) if code else 물결(ln, pairs))
    lines = tuple(lines)
    attrs = dict(b.attrs)
    if isinstance(attrs.get("머리"), list):
        attrs["머리"] = [물결(h, pairs) for h in attrs["머리"]]
    return dataclasses.replace(b, lines=lines, attrs=attrs)


def _물결_문항(qn: Question, pairs) -> Question:
    return dataclasses.replace(qn, stem=tuple(물결(x, pairs) for x in qn.stem),
                               blocks=tuple(_물결_블록(b, pairs) for b in qn.blocks),
                               choices=tuple(dataclasses.replace(c, text=물결(c.text, pairs)) for c in qn.choices))


def 물결_원고(scan: Scan, pairs=()) -> Scan:
    """조판에 들어가는 글(발문·답지·자료·〈보기〉·표 칸·답항표 칸·세트 지문)에 킷 글자 바꾸기를 모두 — 원고 문법에 예외 자리(코드 등)가 없다."""
    return dataclasses.replace(
        scan, questions=tuple(_물결_문항(q, pairs) for q in scan.questions),
        sets=tuple(dataclasses.replace(s, passage=tuple(물결(x, pairs) for x in s.passage),
                                       blocks=tuple(_물결_블록(b, pairs) for b in s.blocks))
                   for s in scan.sets))


def _줄_추정(text: str, first: int, rest: int, m: Metrics) -> list[int]:
    """문단의 줄마다 수식 때문에 늘어나는 높이(HWPUNIT, 없으면 0) — 목록 길이가 곧 줄 수. first/rest = 첫 줄·다음 줄 가용 폭.

    렌더 실측: 한글은 낱말 안에서도 글자 단위로 줄이 바뀐다(`만/큼`). 로마자·숫자 낱말은 통째로 넘어가고,
    한 줄보다 길면 글자 단위로 끊긴다. 줄 끝 공백은 넘쳐도 된다. 수식은 한 덩어리다.
    한/글은 수식이 든 줄의 높이(lineseg vertsize)를 수식 높이까지 늘리고 줄 사이(spacing)는 그대로 둔다(합성 식 저장본:
    높이 2500 수식 줄의 vertsize 2500, spacing 600은 다른 줄과 같다) — 늘어나는 높이 = 가장 높은 수식 − 글자 높이로 어림한다.
    """
    masked, 폭, maths = _가림(text, m)
    extra, avail, cur = [0], first, 0
    for tok in re.findall(r"[!-~]+|.", masked):
        w = 폭(tok)
        k = equation.자리_번호(tok) if len(tok) == 1 else None
        up = 0 if k is None else max(0, equation.height(maths[k], m.char_height) - m.char_height)
        if tok == " " or cur + w <= avail:
            cur += w
            extra[-1] = max(extra[-1], up)
            continue
        if cur:
            extra.append(0)
            avail, cur = rest, 0
        while w > avail:
            extra.append(0)
            w, avail = w - avail, rest
        cur = w
        extra[-1] = max(extra[-1], up)
    return extra


def estimate_lines(text: str, first: int, rest: int, m: Metrics) -> int:
    """문단이 차지할 줄 수. first/rest = 첫 줄·다음 줄 가용 폭(HWPUNIT) — 나누는 규칙은 _줄_추정."""
    return len(_줄_추정(text, first, rest, m))


def estimate_extra(text: str, first: int, rest: int, m: Metrics) -> int:
    """수식 때문에 문단이 늘어나는 높이의 합(HWPUNIT) — 줄마다 그 줄의 가장 높은 수식(_줄_추정)."""
    return sum(_줄_추정(text, first, rest, m))


def _칸_글_높이(text: str, avail: int, pitch: int, m: Metrics) -> int:
    """칸 글(`\\n` = 줄바꿈)의 높이 − 글자 높이 = (줄 수 − 1) × 피치 + 수식 때문에 늘어나는 높이."""
    pieces = [p.replace("__", "") for p in text.split("\n")]
    lines = sum(estimate_lines(p, avail, avail, m) for p in pieces)
    return (lines - 1) * pitch + sum(estimate_extra(p, avail, avail, m) for p in pieces)


def fits(widths: list[int], rows: tuple[int, ...], starts: list[int], end: int, gap: int) -> bool:
    """줄마다 k번째 답지가 칸 starts[k]에서 시작해 다음 칸(줄의 마지막 답지는 단 끝 end) gap 앞에서 끝나는가.

    넘치면 한글은 탭을 그다음 탭 자리로 보내 칸이 어긋나고, 줄의 마지막 답지면 줄이 접힌다.
    """
    it = iter(widths)
    for n in rows:
        for k in range(n):
            stop = starts[k + 1] if k + 1 < n else end
            if starts[k] + next(it) + gap > stop:
                return False
    return True


def md_cells(row: str) -> list[str]:
    """`| a | b |` → ['a', 'b'] — 수식 `$…$` 안의 `|`(절댓값 등)로는 칸을 나누지 않는다."""
    return equation.split_cells(row)


def parse_md_table(lines, where: str) -> tuple[list[str] | None, list[list[str]]]:
    """md 표 줄들 → (머리행 또는 None, 본문 행들). 둘째 줄이 `|---|`면 첫 줄이 머리행이다."""
    rows = list(lines)
    header = None
    if len(rows) >= 2 and _구분행.match(rows[1].strip()):
        header, rows = md_cells(rows[0]), rows[2:]
    body = [md_cells(r) for r in rows]
    widths = {len(r) for r in ([header] if header else []) + body}
    if len(widths) != 1:
        raise ValueError(f"{where} 표의 열 수가 행마다 다르다: {sorted(widths)}")
    return header, body


def column_widths(rows: list[list[str]], total: int, minimum: int, pad: int = 0, *, m: Metrics) -> list[int]:
    """열 폭 = 열에서 가장 긴 칸의 글자 폭 + pad(셀 좌우 여백)에 비례, 최소 minimum, 합은 정확히 total.

    pad를 비례 몫에 넣어야 짧은 머리(`출석률`)가 최소 폭에 걸려 두 줄로 접히지 않는다 — 글자 폭 합이 total 안이면
    모든 열이 제 글자 폭 이상을 받는다.
    """
    n = len(rows[0])
    if n * minimum > total:
        raise ValueError(f"표가 {n}열이라 열 폭 {minimum} 이상으로 {total}에 들어가지 않는다")
    weight = [max(_글폭(r[c].replace("__", ""), m) for r in rows) + pad or 1 for c in range(n)]
    if sum(max(w, minimum) for w in weight) > total:
        # 모든 칸 글이 한 줄에 못 들어간다 — 비례로 나누면 모든 열이 조금씩 모자라 낱말 한가운데서 접힌다(Task 19 렌더:
        # `가나다`가 `가나/다`로). 열마다 가장 긴 낱말(띄어쓰기 단위) + pad를 먼저 주고, 남는 폭을 모자란 만큼에 비례해 나눈다.
        word = [max(_긴_낱말(r[c].replace("__", ""), m) for r in rows) + pad for c in range(n)]
        low = [max(minimum, w) for w in word]
        if sum(low) <= total:
            extra = [max(0, weight[c] - low[c]) for c in range(n)]
            rest, ex = total - sum(low), sum(extra)
            out = [low[c] + (int(rest * extra[c] / ex) if ex else 0) for c in range(n)]
            out[max(range(n), key=lambda c: extra[c] if ex else weight[c])] += total - sum(out)
            return out
    fixed: set[int] = set()
    while True:  # 최소 폭에 걸린 열은 최소로 묶고 나머지를 다시 나눈다
        free = [c for c in range(n) if c not in fixed]
        room = total - minimum * len(fixed)
        s = sum(weight[c] for c in free)
        small = {c for c in free if room * weight[c] / s < minimum}
        if not small:
            break
        fixed |= small
    out = [minimum if c in fixed else int(room * weight[c] / s) for c in range(n)]
    out[max(free, key=lambda c: weight[c])] += total - sum(out)  # 반올림 나머지는 가장 넓은 열에
    return out


def derive_para_pr(header, base: str, *, prev: int | None = None, align: str | None = None,
                   break_setting: dict | None = None, tab_pr: str | None = None, margins: dict | None = None) -> str:
    """base paraPr의 복제 id — prev·margins(intent·left·right·next)면 그 여백을 case 분기 = 값, default 분기 = 2배로(양식 실측).

    값이 None인 여백은 base 그대로 둔다. tab_pr면 탭 정의(tabPrIDRef)도 바꾼다. ensure_paragraph_format은 두 분기에 같은 값을
    넣고 같은 모양이 있으면 재사용하므로, 양식의 기존 paraPr를 재사용했는데 default 분기가 다르면 고치지 않고 멈춘다(양식 문단까지 바뀐다).
    """
    want = dict(margins or {})
    if prev is not None:
        want["prev"] = prev
    before = {pp.get("id") for pp in header.element.iter(q("hh", "paraPr"))}
    pid = header.ensure_paragraph_format(base_para_pr_id=base, alignment=align, margins=want or None,
                                         break_setting=break_setting, tab_pr_id_ref=tab_pr)
    pp = header.element.find(f".//{q('hh', 'paraPr')}[@id='{pid}']")
    for key, value in want.items():
        d = pp.find(f".//{q('hp', 'default')}/{q('hh', 'margin')}/{q('hc', key)}")
        if d is not None and d.get("value") != str(2 * value):
            if pid in before:
                raise RuntimeError(f"paraPr {pid}를 재사용했는데 default 분기 {key}가 다르다")
            d.set("value", str(2 * value))
    return pid


def case_prev(header, pid: str) -> int:
    """paraPr pid의 문단 위 간격(case 분기, HWPUNIT)."""
    pp = header.element.find(f".//{q('hh', 'paraPr')}[@id='{pid}']")
    el = pp.find(f".//{q('hp', 'case')}/{q('hh', 'margin')}/{q('hc', 'prev')}")
    return int(el.get("value")) if el is not None else 0


@dataclass(frozen=True)
class Samples:
    """샘플 구역을 지우기 전에 떠 둔 양식 견본(문서와 분리된 사본). Task 23이 복제해 쓴다."""

    보기_tbl: ET._Element
    자료_tbl: ET._Element
    세트_charpr: str  # `[a∼b]` 표지의 글자 모양(13pt 굵게) — 양식 견본 run에서 읽는다
    번호_charpr: str | None = None  # 글자 번호(킷 number literal)의 글자 모양 — 견본 번호 run에서 읽는다
    extra: dict = field(default_factory=dict)  # 보기·자료 밖의 견본(〈조건〉·◦ 자료 등) — 킷 boxes 종류 → 표

    def table(self, kind: str) -> ET._Element:
        return {"보기": self.보기_tbl, "자료": self.자료_tbl}.get(kind) if kind in ("보기", "자료") else self.extra[kind]


@dataclass
class ComposeResult:
    answers: dict[str, str]
    layouts: dict[str, str]
    notes: list[str] = field(default_factory=list)


@dataclass
class _Para:
    """삽입 전 문단 계획. segs의 charPr가 None이면 그 역할 스타일의 charPr."""

    role: str
    segs: list[tuple[str | equation.Math, str | None]]
    keep: bool = False
    gap: bool = False
    brk: str | None = None  # 나눔 지시("column"·"page") — 문항 묶음 첫 문단에만(원고 {단나눔}·{쪽나눔})
    mark: str | None = None  # 형광펜을 칠할 원문자
    obj: ET._Element | None = None  # 글자처럼 취급하는 표·그림 — 이 문단의 유일한 내용
    align: str | None = None  # 문단 정렬을 바꿀 때만(그림은 가운데)
    tabs: list[int] = field(default_factory=list)  # segs 속 \t마다 hp:tab width(추정 — 한글이 다시 잰다)
    left: int | None = None  # 왼여백을 바꿀 때만(〈보기〉 뒤 참고 줄 — 발문 이음 줄 자리)


def _body_region(doc: HwpxDocument, kit: Kit) -> tuple[int, int]:
    """조판기가 바꿀 샘플 구역(최상위 문단 번호, 양 끝 포함) — 킷 sample_region."""
    if kit.sample_region == "admin_to_tail":  # 관리박스(0) 뒤 ~ 꼬리 박스(마지막 문단) 앞 전부
        return 1, len(doc.sections[0].paragraphs) - 2
    prof = profile_form(doc, role_style_names=kit.styles)
    return prof.body_start, prof.body_end


def harvest_samples(doc: HwpxDocument, kit: Kit) -> Samples:
    """샘플 구역에서 〈보기〉(4×5)·자료(3×3) 견본 표와 세트 표지 charPr를 뜬다 — 못 찾으면 '양식이 바뀌었다'."""
    start, end = _body_region(doc, kit)
    ids = style_ids(doc)
    paras = list(doc.sections[0].paragraphs)[start:end + 1]
    tables = [t for p in paras for t in _top_tables(p.element)]
    보기, 자료 = (next((t for t in tables if is_sample_box(t, kit.boxes[k], ids[kit.styles[kit.boxes[k]["style"]]][0])), None)
                for k in ("보기", "자료"))
    sm = kit.set_marker
    표지_re = re.compile(sm["pattern"])
    표지 = next((r.get("charPrIDRef") for p in paras for r in p.element.findall(q("hp", "run"))
               if 표지_re.match("".join(r.itertext()).strip())), None)
    실패 = [what for what, v in (("〈보기〉 견본", 보기), ("자료 견본", 자료), ("세트 표지 [a∼b]", 표지)) if v is None]
    if 실패:
        raise ValueError("양식이 바뀌었다: 샘플 구역에 " + ", ".join(실패) + " 없음")
    cp = doc.headers[0].element.find(f".//{q('hh', 'charPr')}[@id='{표지}']")
    if cp is None or cp.get("height") != str(sm["char_height"]) or (cp.find(q("hh", "bold")) is not None) != sm["bold"]:
        raise ValueError(f"양식이 바뀌었다: 세트 표지 charPr {표지}가 킷 set_marker(높이 {sm['char_height']}, 굵게 {sm['bold']})와 다르다")
    번호 = None
    if kit.number["mode"] == "literal":
        번호_re = re.compile(kit.number["sample_pattern"])
        번호 = next((r.get("charPrIDRef") for p in paras for r in p.element.findall(q("hp", "run"))
                   if 번호_re.match("".join(t.text or "" for t in r.findall(q("hp", "t"))))), None)
        if 번호 is None:
            raise ValueError("양식이 바뀌었다: 샘플 구역에 글자 번호 견본(킷 number.sample_pattern) 없음")
    extra = {}
    for kind, spec in kit.boxes.items():
        if kind in ("보기", "자료") or not isinstance(spec, dict):
            continue
        t = next((t for t in tables if is_sample_box(t, spec, ids[kit.styles[spec["style"]]][0])), None)
        if t is None:
            raise ValueError(f"양식이 바뀌었다: 샘플 구역에 {kind} 견본 없음")
        extra[kind] = deepcopy(t)
    return Samples(deepcopy(보기), deepcopy(자료), 표지, 번호, extra)


class _Composer:
    def __init__(self, doc: HwpxDocument, kit: Kit, samples: Samples, *, answer_key: bool,
                 image_root: Path | None = None):
        self.doc, self.kit, self.samples, self.answer_key = doc, kit, samples, answer_key
        self.image_root = image_root
        self.header = doc.headers[0]
        ids = style_ids(doc)
        self.style = {role: ids[name] for role, name in kit.styles.items()}  # role → (style, paraPr, charPr)
        self._pp: dict[tuple, str] = {}
        self._ul: dict[str, str] = {}
        self._bf: dict[tuple, str] = {}
        self.answers: dict[str, str] = {}
        self.layouts: dict[str, str] = {}
        self.notes: list[str] = []
        self.자동 = 자동_배치형  # 답지 배치형 자동 선택 차례 — plan이 원고 머리(답항)로 정한다

    # ---- 서식 파생 -----------------------------------------------------------

    def para_pr(self, role: str, *, keep: bool, gap: bool, align: str | None = None, left: int | None = None) -> str:
        """역할 스타일 paraPr의 복제 — keepWithNext=keep, keepLines=1, gap이면 prev = question_gap(case)·2배(default).

        1행답항은 한 번에 균등 칸 탭(tab_pr)도 단다 — 양식의 1행답항 문단·스타일은 그대로.
        """
        key = (role, keep, gap, align, left)
        if key in self._pp:
            return self._pp[key]
        margins = {"left": left} if left is not None else None
        if role == "number" and self.kit.typeset.get("stem_hanging") == "space":
            # 발문이 다음 줄로 넘어가면 번호 자릿수와 무관하게 공백 한 칸만 들여 쓴다(학교 B 결정표 6) — 첫 줄은 그대로.
            # 한글 문단: 왼여백은 모든 줄, 음수 intent(내어쓰기)는 둘째 줄부터 |intent|만큼 더 들어간다(09-29 렌더 실측)
            margins = {"intent": -self.kit.metrics.space}
        pid = derive_para_pr(self.header, self.style[role][1], prev=self.kit.question_gap if gap else None,
                             align=align, break_setting={"keep_with_next": keep, "keep_lines": True},
                             margins=margins,
                             tab_pr=self.tab_pr(self.slots(role)[1:]) if role == "choice1" else None)
        self._pp[key] = pid
        return pid

    def tab_pr(self, positions: list[int]) -> str:
        """왼쪽 탭 positions(단 왼끝 기준 HWPUNIT)의 tabPr id — 1행답항 스타일 tabPr을 본뜬다: 탭마다 hp:switch 하나,
        case 분기 = pos(unit HWPUNIT), default 분기 = 2배(양식 실측 6000 → 12000). 같은 모양이 있으면 재사용."""
        hdr = self.header.element
        pp = hdr.find(f".//{q('hh', 'paraPr')}[@id='{self.style['choice1'][1]}']")
        src = hdr.find(f".//{q('hh', 'tabPr')}[@id='{pp.get('tabPrIDRef')}']")
        sw = None if src is None else src.find(q("hp", "switch"))
        if sw is None or sw.find(f"{q('hp', 'case')}/{q('hh', 'tabItem')}") is None \
                or sw.find(f"{q('hp', 'default')}/{q('hh', 'tabItem')}") is None:
            raise ValueError(f"양식이 바뀌었다: {self.kit.styles['choice1']} tabPr에 hp:switch case/default tabItem이 없다")
        want = deepcopy(src)
        for old in want.findall(q("hp", "switch")):
            want.remove(old)
        for pos in positions:
            new = deepcopy(sw)
            new.find(f"{q('hp', 'case')}/{q('hh', 'tabItem')}").set("pos", str(pos))
            new.find(f"{q('hp', 'default')}/{q('hh', 'tabItem')}").set("pos", str(2 * pos))
            want.append(new)

        def 모양(t) -> bytes:
            c = deepcopy(t)
            c.attrib.pop("id", None)
            return ET.tostring(c, method="c14n")

        box = src.getparent()
        found = next((t.get("id") for t in box.findall(q("hh", "tabPr")) if 모양(t) == 모양(want)), None)
        if found is None:
            found = str(max(int(t.get("id")) for t in box.findall(q("hh", "tabPr"))) + 1)
            want.set("id", found)
            box.append(want)
            box.set("itemCnt", str(len(box.findall(q("hh", "tabPr")))))
            self.header.mark_dirty()
        return found

    def underline(self, base: str) -> str:
        """base charPr와 밑줄(BOTTOM)만 다른 charPr — 있으면 재사용, 없으면 복제."""
        if base in self._ul:
            return self._ul[base]
        hdr = self.header.element
        src = hdr.find(f".//{q('hh', 'charPr')}[@id='{base}']")

        def 모양(c) -> tuple:
            속성 = tuple(sorted((k, v) for k, v in c.attrib.items() if k != "id"))
            자식 = tuple((x.tag, tuple(sorted(x.attrib.items()))) for x in c if x.tag != q("hh", "underline"))
            return 속성, 자식

        want = 모양(src)

        def 같다(c) -> bool:
            u = c.find(q("hh", "underline"))
            return u is not None and u.get("type") == "BOTTOM" and u.get("shape") == "SOLID" and 모양(c) == want

        def 긋기(c) -> None:
            u = c.find(q("hh", "underline"))
            if u is None:
                raise ValueError(f"charPr {base}에 hh:underline 자식이 없다 — 밑줄 모양을 복제할 수 없다")
            u.set("type", "BOTTOM")
            u.set("shape", "SOLID")

        cid = self.header.ensure_char_property(predicate=같다, modifier=긋기, base_char_pr_id=base).get("id")
        self._ul[base] = cid
        return cid

    def code_char_pr(self, role: str) -> str:
        """코드 블록 글자 모양 — 역할 charPr 복제에서 글꼴만 킷 고정폭 글꼴(kit.code_font), 장평 100·자간 0(Task 30).
        양식 fontface에 그 글꼴이 없으면 언어마다 덧붙인다. 같은 모양이 있으면 재사용."""
        key = ("코드", role)
        if key in self._ul:
            return self._ul[key]
        ids = code_font_ids(self.header, self.kit.code_font)
        base = self.style[role][2]

        def 모양(c) -> tuple:
            return tuple(sorted((k, v) for k, v in c.attrib.items() if k != "id")), tuple(
                (x.tag, tuple(sorted(x.attrib.items()))) for x in c if x.tag not in (q("hh", "fontRef"), q("hh", "ratio"),
                                                                                    q("hh", "spacing")))

        want = 모양(self.header.element.find(f".//{q('hh', 'charPr')}[@id='{base}']"))

        def 같다(c) -> bool:
            fr, ra, sp = c.find(q("hh", "fontRef")), c.find(q("hh", "ratio")), c.find(q("hh", "spacing"))
            return (fr is not None and all(fr.get(k) == v for k, v in ids.items()) and ra is not None
                    and all(v == "100" for v in ra.attrib.values()) and sp is not None
                    and all(v == "0" for v in sp.attrib.values()) and 모양(c) == want)

        def 바꾸기(c) -> None:
            for k, v in ids.items():
                c.find(q("hh", "fontRef")).set(k, v)
            for tag, val in (("ratio", "100"), ("spacing", "0")):
                el = c.find(q("hh", tag))
                for k in el.attrib:
                    el.set(k, val)

        cid = self.header.ensure_char_property(predicate=같다, modifier=바꾸기, base_char_pr_id=base).get("id")
        self._ul[key] = cid
        return cid

    def code_para_pr(self, role: str) -> str:
        """코드 블록 문단 모양 — 역할 paraPr에서 왼쪽 정렬·들여쓰기 0(칸 안이면 여백도 그 역할 그대로)."""
        key = ("코드문단", role)
        if key not in self._pp:
            self._pp[key] = derive_para_pr(self.header, self.style[role][1], align="LEFT", margins={"intent": 0})
        return self._pp[key]

    def item_pr(self) -> str:
        """〈보기〉 항목 paraPr — 양식 스타일 복제에서 내어쓰기만 보기_내어쓰기로(case, default 2배). 왼여백은 스타일 그대로(0)."""
        if "보기항목" not in self._pp:
            self._pp["보기항목"] = derive_para_pr(self.header, self.style["box_guide"][1], margins={"intent": self.kit.bogi_hanging_indent})
        return self._pp["보기항목"]

    def cell_pr(self, role: str) -> str:
        """표 칸 문단 paraPr — 역할 스타일 paraPr를 가운데 정렬로, 왼·오른 여백과 들여쓰기는 0(두 분기 모두).

        역할 여백을 물려받으면 안 된다: 5행답항(왼 1000·내어쓰기 −1600)을 그대로 쓰면 1600 폭 원문자 칸에
        ①이 넘치고 넓은 칸의 가운데도 ≈5pt 오른쪽으로 밀린다. 문단 보호는 칸 안에서 뜻이 없어 건드리지 않는다.
        """
        key = ("칸", role)
        if key not in self._pp:
            self._pp[key] = self.header.ensure_paragraph_format(
                base_para_pr_id=self.style[role][1], alignment="CENTER",
                margins={"left": 0, "right": 0, "intent": 0})
        return self._pp[key]

    def _border_fills(self) -> ET._Element:
        fills = self.header.element.find(f".//{q('hh', 'borderFills')}")
        if fills is None:
            raise ValueError("양식이 바뀌었다: hh:borderFills 없음")
        return fills

    def plain_bf(self) -> str:
        """양식의 사방 SOLID 0.12 mm 검정·채움 없음 borderFill(격자표의 바탕)."""
        for b in self._border_fills().findall(q("hh", "borderFill")):
            sides = [b.find(q("hh", f"{s}Border")) for s in ("left", "right", "top", "bottom")]
            if all(x is not None and (x.get("type"), x.get("width"), x.get("color")) == ("SOLID", "0.12 mm", "#000000")
                   for x in sides) and b.find(q("hc", "fillBrush")) is None:
                return b.get("id")
        raise ValueError("양식이 바뀌었다: 사방 0.12 mm 실선 borderFill이 없다")

    def bf_variant(self, base: str, **sides: tuple[str, str]) -> str:
        """base borderFill에서 지정 변(top/bottom/left/right)만 (type, width)로 바꾼 것 — 같은 것이 있으면 재사용."""
        key = (base, tuple(sorted(sides.items())))
        if key in self._bf:
            return self._bf[key]
        fills = self._border_fills()
        src = fills.find(f"{q('hh', 'borderFill')}[@id='{base}']")
        want = deepcopy(src)
        for side, (typ, width) in sides.items():
            b = want.find(q("hh", f"{side}Border"))
            b.set("type", typ)
            b.set("width", width)

        def 모양(b) -> bytes:
            c = deepcopy(b)
            c.attrib.pop("id", None)
            return ET.tostring(c, method="c14n")

        found = next((b.get("id") for b in fills.findall(q("hh", "borderFill")) if 모양(b) == 모양(want)), None)
        if found is None:
            found = str(max(int(b.get("id")) for b in fills.findall(q("hh", "borderFill"))) + 1)
            want.set("id", found)
            fills.append(want)
            fills.set("itemCnt", str(len(fills.findall(q("hh", "borderFill")))))
            self.header.mark_dirty()
        self._bf[key] = found
        return found

    def _cell_p(self, segs: list[tuple[str | equation.Math, str | None]], role: str, *, pid: str | None = None,
                mark: str | None = None) -> ET._Element:
        """칸 안 문단(줄 캐시 없이) — segs의 charPr가 None이면 역할 스타일 charPr. mark는 그 글자에 형광펜."""
        sid, _, cp = self.style[role]
        p = ET.Element(q("hp", "p"), {"id": "2147483648", "paraPrIDRef": pid or self.cell_pr(role), "styleIDRef": sid,
                                      "pageBreak": "0", "columnBreak": "0", "merged": "0"}, nsmap={"hp": HP})
        for text, c in segs:
            if isinstance(text, equation.Math):
                p.append(self._수식_run(text, c or cp))
                continue
            mark = _fill_t(ET.SubElement(ET.SubElement(p, q("hp", "run"), {"charPrIDRef": c or cp}), q("hp", "t")),
                           text, mark)
        if mark:
            raise ValueError(f"형광펜 {mark}를 칠할 자리가 없다: {_글(segs)!r}")
        return p

    def 글자_크기(self, cp: str) -> int:
        """charPr의 글자 크기(height, HWPUNIT) — 수식 기준 크기(baseUnit)로 쓴다(한/글도 넣는 자리의 글자 크기로 만든다)."""
        el = self.header.element.find(f".//{q('hh', 'charPr')}[@id='{cp}']")
        if el is None or not (el.get("height") or "").isdigit():
            raise ValueError(f"양식이 바뀌었다: charPr {cp}의 글자 크기(height)가 없다")
        return int(el.get("height"))

    def _수식_run(self, m: equation.Math, cp: str) -> ET._Element:
        """칸 안 문단에 넣을 수식 run — 임시 문단에 공개 API(add_equation)로 만들고 떼어 낸다(그림 _pic_element와 같은 방식)."""
        sec = self.doc.sections[0]
        tmp = sec.add_paragraph("")
        tmp.add_equation(m.script, base_unit=self.글자_크기(cp), char_pr_id_ref=cp)
        run = tmp.element.findall(q("hp", "run"))[-1]
        tmp.element.remove(run)
        sec.remove_paragraph(tmp)
        return run

    def _table(self, cells: list[list[tuple[ET._Element, str]]], widths: list[int], heights: list[int], *,
               bf: str, in_margin: dict, out_margin: dict) -> ET._Element:
        """글자처럼 취급하는 표 — cells[행][열] = (칸 문단, borderFill). 칸은 표 안여백을 쓴다(hasMargin=0)."""
        m = {k: str(v) for k, v in in_margin.items()}
        tbl = ET.Element(q("hp", "tbl"), {
            "id": "0", "zOrder": "0", "numberingType": "TABLE", "textWrap": "TOP_AND_BOTTOM", "textFlow": "BOTH_SIDES",
            "lock": "0", "dropcapstyle": "None", "pageBreak": "CELL", "repeatHeader": "1", "rowCnt": str(len(cells)),
            "colCnt": str(len(widths)), "cellSpacing": "0", "borderFillIDRef": bf, "noAdjust": "0"}, nsmap={"hp": HP})
        ET.SubElement(tbl, q("hp", "sz"), {"width": str(sum(widths)), "widthRelTo": "ABSOLUTE",
                                           "height": str(sum(heights)), "heightRelTo": "ABSOLUTE", "protect": "0"})
        ET.SubElement(tbl, q("hp", "pos"), {
            "treatAsChar": "1", "affectLSpacing": "0", "flowWithText": "1", "allowOverlap": "0", "holdAnchorAndSO": "0",
            "vertRelTo": "PARA", "horzRelTo": "PARA", "vertAlign": "TOP", "horzAlign": "LEFT",
            "vertOffset": "0", "horzOffset": "0"})
        ET.SubElement(tbl, q("hp", "outMargin"), {k: str(v) for k, v in out_margin.items()})
        ET.SubElement(tbl, q("hp", "inMargin"), m)
        for r, row in enumerate(cells):
            tr = ET.SubElement(tbl, q("hp", "tr"))
            for c, (p, cell_bf) in enumerate(row):
                tc = ET.SubElement(tr, q("hp", "tc"), {"name": "", "header": "0", "hasMargin": "0", "protect": "0",
                                                       "editable": "0", "dirty": "0", "borderFillIDRef": cell_bf})
                sub = ET.SubElement(tc, q("hp", "subList"), {
                    "id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK", "vertAlign": "CENTER",
                    "linkListIDRef": "0", "linkListNextIDRef": "0", "textWidth": "0", "textHeight": "0",
                    "hasTextRef": "0", "hasNumRef": "0"})
                sub.append(p)
                ET.SubElement(tc, q("hp", "cellAddr"), {"colAddr": str(c), "rowAddr": str(r)})
                ET.SubElement(tc, q("hp", "cellSpan"), {"colSpan": "1", "rowSpan": "1"})
                ET.SubElement(tc, q("hp", "cellSz"), {"width": str(widths[c]), "height": str(heights[r])})
                ET.SubElement(tc, q("hp", "cellMargin"), m)
        return tbl

    def grid(self, lines, width: int, where: str) -> ET._Element:
        """md 표 → 격자표(제출본 8번): 사방 0.12 mm, 머리행 아래·첫 본문행 위 겹선 0.4 mm, 칸은 가운데·바탕글."""
        header, body = parse_md_table(lines, where)
        rows = ([header] if header else []) + body
        pad = self.kit.grid["in_margin"]["left"] + self.kit.grid["in_margin"]["right"]
        widths = column_widths(rows, width, self.kit.grid["min_col"], pad, m=self.kit.metrics)
        base = self.plain_bf()
        pitch = self._line_pitch("normal")
        cells, heights = [], []
        for r, row in enumerate(rows):
            if header and r == 0:
                bf = self.bf_variant(base, bottom=("DOUBLE_SLIM", "0.4 mm"))
            elif header and r == 1:
                bf = self.bf_variant(base, top=("DOUBLE_SLIM", "0.4 mm"))
            else:
                bf = base
            wrapped = [wrap_words(text, w - pad, self.kit.metrics) for text, w in zip(row, widths)]
            cells.append([(self._cell_p(self._segs(text, "normal"), "normal"), bf) for text in wrapped])
            h = max(_칸_글_높이(text, w - pad, pitch, self.kit.metrics) for text, w in zip(wrapped, widths))
            heights.append(h + self.kit.metrics.char_height + self.kit.grid["in_margin"]["top"] + self.kit.grid["in_margin"]["bottom"])
        return self._table(cells, widths, heights, bf=base, in_margin=self.kit.grid["in_margin"], out_margin=self.kit.grid["out_margin"])

    def answer_table(self, qn: Question, block: Block) -> ET._Element:
        """:::답항표 → 무테 표: 머리행(기호 밑줄) + ①~⑤, 첫 열 원문자 폭 self.kit.metrics.mark_col, 나머지 균등, 모든 칸 가운데."""
        head = block.attrs.get("머리")
        if not head:
            raise ValueError(f"L{block.line_no} {qn.number}번 답항표에 머리 속성이 없다")
        rows = [[c.mark, *md_cells(c.text)] for c in qn.choices]
        if any(len(r) != len(head) + 1 for r in rows):
            raise ValueError(f"L{block.line_no} {qn.number}번 답항표 열 수 {[len(r) - 1 for r in rows]} ≠ 머리 {len(head)}")
        left = self._margins("choice5")["left"]
        room = self.kit.columns["body_table_width"] - left - self.kit.metrics.mark_col  # 답지 자리(왼여백)에서 시작해 박스 오른끝까지
        texts = [list(head)] + [r[1:] for r in rows]
        need = [max(_글폭(t[c].replace("__", ""), self.kit.metrics) for t in texts) + 282 for c in range(len(head))]  # 칸 좌우 여백 141×2
        if max(need) <= room // len(head):  # 균등 칸에 다 들어가면 균등(G2 판정 모양) — 아니면 글 길이에 맞춘다(Task 19)
            widths = [self.kit.metrics.mark_col] + [room // len(head)] * len(head)
            widths[-1] += room - sum(widths[1:])
        else:
            widths = [self.kit.metrics.mark_col] + column_widths(texts, room, min(self.kit.grid["min_col"], room // len(head)), 282, m=self.kit.metrics)
        none = self.bf_variant(self.plain_bf(), **{s: ("NONE", "0.1 mm") for s in ("left", "right", "top", "bottom")})
        pitch = self._line_pitch("choice5")
        v = (pitch - self.kit.metrics.char_height) // 2  # 행 높이 = 5행 답지 줄 피치 — 위아래 여백으로 채운다
        in_m = {"left": 141, "right": 141, "top": v, "bottom": v}
        ul = self.underline(self.style["choice5"][2])
        cells = [[(self._cell_p([("", None)], "choice5"), none)]
                 + [(self._cell_p([(x, ul) for x in equation.pieces(*equation.mask(h))] or [("", ul)], "choice5"), none)
                    for h in head]]
        for c, row in zip(qn.choices, rows):
            mark = c.mark if (c.correct and self.answer_key) else None
            cells.append([(self._cell_p([(row[0], None)], "choice5", mark=mark), none)]
                         + [(self._cell_p(self._segs(wrap_words(t, w - 282, self.kit.metrics), "choice5"), "choice5"), none)
                            for t, w in zip(row[1:], widths[1:])])
        heights = [self.kit.metrics.char_height + 2 * v]  # 머리행
        for row in rows:  # 칸 글이 접히면(wrap_words 줄 수) 그만큼 행이 높아진다 — grid()와 같다
            h = max(_칸_글_높이(wrap_words(t, w - 282, self.kit.metrics), w - 282, pitch, self.kit.metrics)
                    for t, w in zip(row[1:], widths[1:]))
            heights.append(h + self.kit.metrics.char_height + 2 * v)
        return self._table(cells, widths, heights, bf=none, in_margin=in_m, out_margin=dict.fromkeys(self.kit.grid["out_margin"], 0))

    def picture(self, block: Block, avail: int) -> ET._Element:
        """`![](경로){width=Ncm}` → 회색조 사본을 문서에 넣고 글자처럼 취급하는 그림(높이는 원본 비율)."""
        src, cm = block.attrs.get("src"), block.attrs.get("width_cm")
        if src is None:  # :::그림 펜스 — 안의 그림 줄을 쓴다
            m = next((IMG_RE.match(ln.strip()) for ln in block.lines if IMG_RE.match(ln.strip())), None)
            if m is None:
                raise ValueError(f"L{block.line_no} :::그림 안에 그림 줄이 없다")
            src, cm = m.group("src"), float(m.group("w")) if m.group("w") else None
        if cm is None:
            raise ValueError(f"L{block.line_no} 그림 폭이 없다 — `![]({src}){{width=Ncm}}`")
        if self.image_root is None:
            raise ValueError(f"L{block.line_no} 그림 {src}: 그림 경로의 기준(image_root)이 없다")
        path = Path(self.image_root) / src
        if not path.is_file():
            raise ValueError(f"L{block.line_no} 없는 그림: {path}")
        w = round(cm * CM)
        with Image.open(path) as src_im:
            im = ImageOps.exif_transpose(src_im)  # 사진의 EXIF 회전을 픽셀에 반영(비율·방향이 보이는 대로)
            natural = natural_width_cm(im.width)
            if w > avail:  # 엔진은 그림을 줄여 넣지 않는다(Task 30) — 그림을 단 폭에 맞게 다시 만든다
                raise ValueError(f"L{block.line_no} 그림 {src} 폭 {cm}cm가 {'박스 안' if avail < self.kit.columns['width'] else '단'} 폭"
                                 f"({avail / CM:.1f}cm)보다 넓다(원래 크기 {natural:.1f}cm @ {그림_DPI}dpi) — 그림을 이 폭 안으로 다시 만든다")
            if cm < natural * 0.98:
                self.notes.append(f"그림 {src}: 원고 폭 {cm}cm < 원래 크기 {natural:.1f}cm({그림_DPI}dpi) — 줄여 넣으면 "
                                  f"그림 속 글자가 작아진다(규격 검사 W022)")
            h = round(w * im.height / im.width)
            if im.mode in ("RGBA", "LA", "P"):  # 투명한 곳은 흰 바탕으로(그대로 L로 바꾸면 검게 된다)
                bg = Image.new("RGBA", im.size, "white")
                im = Image.alpha_composite(bg, im.convert("RGBA"))
            buf = io.BytesIO()
            # 킷 typeset.grayscale_pictures(예: 원안지 칼라 인쇄 금지) — 회색조 사본을 넣는다
            im.convert("L" if self.kit.typeset["grayscale_pictures"] else "RGB").save(buf, "PNG")
        bid = str(self.doc.media.add_image(buf.getvalue(), "png"))
        return self._pic_element(bid, w, h)

    def _pic_element(self, bid: str, w: int, h: int) -> ET._Element:
        """글자처럼 취급하는 hp:pic — paragraph.add_picture와 같은 모양, 문서와 분리된 요소로."""
        if _create_picture_element is not None:
            el = _create_picture_element(bid, w, h, treat_as_char=True)
            return ET.fromstring(StdET.tostring(el, encoding="utf-8"))
        sec = self.doc.sections[0]  # 폴백: 임시 문단에 add_picture로 그리고 떼어 낸다
        tmp = sec.add_paragraph("")
        pic = tmp.add_picture(bid, width=w, height=h, treat_as_char=True).element
        pic.getparent().remove(pic)
        sec.remove_paragraph(tmp)
        return pic

    # ---- 문단 계획 -----------------------------------------------------------

    def _segs(self, text: str, role: str) -> list[tuple[str | equation.Math, str | None]]:
        """`__x__` → 밑줄 run, `$…$` → 수식(equation.Math — 밑줄 안이면 그 charPr run에). 나머지는 역할 스타일 charPr(None).
        밑줄은 수식 밖의 `__`로만 찾는다(가린 글)."""
        masked, maths = equation.mask(text)
        out: list[tuple[str | equation.Math, str | None]] = []

        def 붙이기(s: str, c: str | None) -> None:
            out.extend((x, c) for x in equation.pieces(s, maths))

        pos = 0
        for m in _밑줄.finditer(masked):
            if m.start() > pos:
                붙이기(masked[pos:m.start()], None)
            붙이기(m.group(1), self.underline(self.style[role][2]))
            pos = m.end()
        if pos < len(masked):
            붙이기(masked[pos:], None)
        return out

    def _case(self, role: str, child: str) -> ET._Element:
        """역할 스타일 paraPr의 hp:switch/hp:case 분기 자식(margin·lineSpacing) — 없으면 '양식이 바뀌었다'."""
        pp = self.header.element.find(f".//{q('hh', 'paraPr')}[@id='{self.style[role][1]}']")
        el = None if pp is None else pp.find(f"{q('hp', 'switch')}/{q('hp', 'case')}/{q('hh', child)}")
        if el is None:
            raise ValueError(f"양식이 바뀌었다: {self.kit.styles[role]} paraPr에 hp:switch/hp:case/hh:{child}가 없다")
        return el

    def _margins(self, role: str) -> dict[str, int]:
        return {c.tag.split("}")[1]: int(c.get("value")) for c in self._case(role, "margin")}

    def _widths(self, role: str, cell_width: int) -> tuple[int, int]:
        """셀 안 문단의 첫 줄·다음 줄 가용 폭 — 셀 폭 − 표 안여백(셀 hasMargin=0) − 문단 여백·들여쓰기."""
        m = self._margins(role)
        w = cell_width - m["left"] - m["right"]
        intent = m["intent"]
        return (w - intent, w) if intent >= 0 else (w, w + intent)  # 음수 = 내어쓰기: 둘째 줄부터 들어간다

    def slot_end(self, role: str) -> int:
        """답지 줄의 오른끝(단 왼끝 기준) = 단 폭 − 역할 오른여백."""
        return self.kit.columns["width"] - self._margins(role)["right"]

    def slots(self, role: str, need: int = 0) -> list[int]:
        """답지 칸 시작(단 왼끝 기준) = 왼여백 + 스타일 탭 자리(case 분기). need개보다 적으면 '양식이 바뀌었다'.

        탭 자리는 단 왼끝 기준이다 — 제출본 렌더에서 2행 ② 107.4~107.6pt·③ 203.4pt(탭 10772·20408).
        1행은 스타일 탭(50/50/60/60pt)을 쓰지 않고 가용 폭(왼여백 ~ slot_end)을 5등분한다(G2 판정) — para_pr가 이 자리로
        문단 자체 탭을 단다.
        """
        if role == "choice1":
            left = self._margins(role)["left"]
            w = (self.slot_end(role) - left) // 5
            return [left + i * w for i in range(5)]
        pp = self.header.element.find(f".//{q('hh', 'paraPr')}[@id='{self.style[role][1]}']")
        tab = self.header.element.find(f".//{q('hh', 'tabPr')}[@id='{pp.get('tabPrIDRef')}']")
        pos = [] if tab is None else sorted(
            int(t.get("pos")) for t in tab.findall(f"{q('hp', 'switch')}/{q('hp', 'case')}/{q('hh', 'tabItem')}"))
        left = self._margins(role)["left"]
        out = [left] + [x for x in pos if x > left]
        if len(out) < need:
            raise ValueError(f"양식이 바뀌었다: {self.kit.styles[role]} 탭 자리 {pos} — 한 줄 답지 {need}개의 칸이 없다")
        return out

    def _line_pitch(self, role: str) -> int:
        ls = self._case(role, "lineSpacing")
        pct = int(ls.get("value")) if ls.get("type") == "PERCENT" else None
        if pct not in self.kit.metrics.line_pitch:
            raise ValueError(f"양식이 바뀌었다: {self.kit.styles[role]} 줄간격 {ls.get('type')} {ls.get('value')}")
        return self.kit.metrics.line_pitch[pct]

    def _box(self, block: Block) -> _Para:
        """`:::보기`/`:::자료` → 견본 표 사본. 내용 셀을 비우고 줄마다 한 문단, 내용 행 높이를 줄 수에 맞춘다.

        자료 안의 md 표·그림 줄은 가운데 정렬 문단 하나에 글자처럼 앉는다(표 폭 = 내용 셀 가용 폭).
        """
        kind_ = box_kind(self.kit, block)
        attr, (cc, cr), rails, role = _박스(self.kit, kind_)
        tbl = deepcopy(self.samples.table(attr))
        if self.kit.boxes[kind_].get("inline"):  # 떠 있는 견본(학교 B 자료 상자) → 글자처럼 취급(다른 박스와 같게)
            pos = tbl.find(q("hp", "pos"))
            pos.attrib.update({"treatAsChar": "1", "vertRelTo": "PARA", "horzRelTo": "PARA", "vertOffset": "0",
                               "horzOffset": "0", "flowWithText": "1"})
        cells = {(int(a.get("colAddr")), int(a.get("rowAddr"))): tc
                 for tc in tbl.iter(q("hp", "tc")) for a in [tc.find(q("hp", "cellAddr"))]}
        content = cells[(cc, cr)]
        sub = content.find(q("hp", "subList"))
        for p in sub.findall(q("hp", "p")):
            sub.remove(p)
        in_m = tbl.find(q("hp", "inMargin"))
        first, rest = self._widths(role, int(content.find(q("hp", "cellSz")).get("width"))
                                   - int(in_m.get("left")) - int(in_m.get("right")))
        pitch = self._line_pitch(role)
        _, pid, _ = self.style[role]
        h = 0  # 줄 높이 합 — 글 줄은 피치, 개체 줄은 개체 높이 + 바깥 여백 + (피치 − 글자 높이)
        for kind, part in _box_parts(block):
            if kind != "글" and block.kind in _항목_박스:
                raise ValueError(f"L{block.line_no} 〈{block.kind}〉 안의 {kind}는 조판하지 않는다 — 자료 박스로 옮긴다")
            if kind == "코드":  # 고정폭 글꼴·왼쪽 정렬, 줄마다 한 문단(공백 그대로) — 높이는 한 줄씩(렌더 뒤 resize_boxes가 맞춘다)
                cp = self.code_char_pr(role)
                for code_line in part:
                    h += pitch
                    sub.append(self._cell_p([(code_line.replace("\t", "    "), cp)], role, pid=self.code_para_pr(role)))
                continue
            if kind == "글":
                # 〈보기〉 항목은 앞 공백 없이 ㄱ을 x = 0에, 내어쓰기는 self.kit.bogi_hanging_indent(제출본 교사 다수 기하, Task 29)
                more = first + self.kit.bogi_hanging_indent if block.kind in _항목_박스 else rest
                plain = part.replace("__", "")
                h += (estimate_lines(plain, first, more, self.kit.metrics) * pitch
                      + estimate_extra(plain, first, more, self.kit.metrics))
                sub.append(self._cell_p(self._segs(part, role), role, pid=self.item_pr() if block.kind in _항목_박스 else pid))
                continue
            obj = self.grid(part, first, f"L{block.line_no} :::자료 안의") if kind == "표" else self.picture(part, first)
            osz, om = obj.find(q("hp", "sz")), obj.find(q("hp", "outMargin"))
            h += int(osz.get("height")) + int(om.get("top")) + int(om.get("bottom")) + pitch - self.kit.metrics.char_height
            p = self._cell_p([("", None)], role, pid=self.cell_pr(role))
            p.find(q("hp", "run")).insert(0, obj)
            sub.append(p)
        if h == 0:
            raise ValueError(f"L{block.line_no} :::{block.kind} 내용이 비었다")
        if kind in ("표", "그림"):  # 박스 끝의 표·그림은 아래 바깥 여백을 없앤다 — 있으면 아래 여백이 위보다 그만큼(2.8pt) 크다
            h -= int(om.get("bottom"))
            om.set("bottom", "0")
        h += self.kit.metrics.box_extra - pitch  # 마지막 줄은 줄간격을 뺀 자리 + 셀 여백(실측 (n − 1) × 피치 + self.kit.metrics.box_extra)
        row_old = int(content.find(q("hp", "cellSz")).get("height"))  # 견본에서 내용 행 높이 = 내용 셀(레일보다 크다)
        h = max(h, row_old)  # 견본 높이 밑으로 내리지 않는다 — 제출본 세 줄 박스도 견본 높이(한글은 늘리기만 한다, Task 29)
        for col in (cc, *rails):
            cells[(col, cr)].find(q("hp", "cellSz")).set("height", str(h))
        sz = tbl.find(q("hp", "sz"))
        sz.set("height", str(int(sz.get("height")) - row_old + h))
        return _Para("normal", [("", None)], obj=tbl)

    def _blocks(self, blocks, where: str) -> list[_Para]:
        """답지 앞 블록들 → 문단. 답항표는 답지 자리라 plan이 따로 다룬다."""
        out = []
        for b in blocks:
            if b.kind in self.kit.boxes:
                out.append(self._box(b))
            elif b.kind == "표":
                out.append(_Para("normal", [("", None)],
                                 obj=self.grid(b.lines, self.kit.columns["body_table_width"], f"L{b.line_no} {where}")))
            elif b.kind == "그림":
                out.append(_Para("normal", [("", None)], obj=self.picture(b, self.kit.columns["width"]), align="CENTER"))
            elif b.kind == "코드":  # 문항·세트의 코드 블록 — 줄마다 고정폭·왼쪽 정렬 문단(Task 30)
                cp = self.code_char_pr("normal")
                out += [_Para("normal", [(ln.replace("\t", "    "), cp)], align="LEFT") for ln in b.lines]
            elif b.kind == "주":  # 〈보기〉 뒤 참고 줄 — 바탕글 문단, 발문 글자 모양, 발문 이음 줄 자리(09-29 결정)
                cp = self.style["number"][2]
                out += [_Para("normal", [(t, c or cp) for t, c in self._segs(ln, "number")], left=발문_이음_왼여백)
                        for ln in b.lines]
            elif b.kind != "답항표":
                raise ValueError(f"L{b.line_no} {where} 모르는 블록 {b.kind}")
        return out

    def _head(self, qn: Question) -> _Para:
        if qn.points is None:
            raise ValueError(f"{qn.number}번 배점이 없다")
        stem = " ".join(s for s in qn.stem if s)
        segs = self._segs(stem + self.kit.typeset["score_suffix"].format(points=qn.points), "number")
        if self.kit.number["mode"] == "literal":  # 스타일에 자동번호가 없다 — 견본 번호 글자 모양으로 `N. `을 쓴다
            segs = [(self.kit.number["format"].format(n=qn.number), self.samples.번호_charpr)] + segs
        return _Para("number", segs, gap=True)

    def _choices(self, qn: Question) -> tuple[str, list[_Para]]:
        """답지 → (배치형, 줄 문단들). 들어가는 가장 촘촘한 자동 형(2행부터 — 원고 머리 `답항: 1행부터`면 1행부터),
        `{답항=N행}`이면 그 형(넘치면 notes에 남긴다)."""
        texts = [f"{c.mark} {c.text}" for c in qn.choices]
        widths = [_글폭(t.replace("__", ""), self.kit.metrics) for t in texts]

        def 칸(kind: str) -> tuple[list[int], int]:
            role, rows = 배치형[kind]
            return self.slots(role, max(rows)), self.slot_end(role)

        def 들어감(kind: str) -> bool:
            return kind == "5행" or fits(widths, 배치형[kind][1], *칸(kind), self.kit.metrics.full)

        kind = qn.override or next(k for k in self.자동 if 들어감(k))
        if not 들어감(kind):
            self.notes.append(f"{qn.number}번 {{답항={kind}}} — 추정 폭이 칸을 넘는다(렌더에서 칸 어긋남·줄 접힘을 본다)")
        role, rows = 배치형[kind]
        starts = 칸(kind)[0] if kind != "5행" else []
        out, i = [], 0
        for n in rows:
            segs: list[tuple[str | equation.Math, str | None]] = []
            for k in range(n):
                s = self._segs(texts[i + k], role)
                if k:  # 답지 글은 원문자로 시작한다(첫 조각이 글)
                    s[0] = ("\t" + str(s[0][0]), s[0][1])
                segs += s
            tabs = [max(1, starts[k] - starts[k - 1] - widths[i + k - 1]) for k in range(1, n)]
            mark = next((c.mark for c in qn.choices[i:i + n] if c.correct and self.answer_key), None)
            out.append(_Para(role, segs, mark=mark, tabs=tabs))
            i += n
        return kind, out

    def _set_head(self, s: QuestionSet) -> list[_Para]:
        a, b = s.rng
        segs: list[tuple[str | equation.Math, str | None]] = [(self.kit.typeset["set_head"].format(a=a, b=b), self.samples.세트_charpr)]
        if s.passage:
            segs += self._segs(" " + s.passage[0], "normal")
        return [_Para("normal", segs, gap=True)] + [_Para("normal", self._segs(line, "normal")) for line in s.passage[1:]]

    @staticmethod
    def _keep(paras: list[_Para]) -> None:
        """한 보호 묶음: 마지막을 뺀 전부 keepWithNext. keepLines는 para_pr가 늘 켠다."""
        for p in paras[:-1]:
            p.keep = True
        paras[-1].keep = False

    def plan(self, scan: Scan) -> list[_Para]:
        if scan.errors:
            raise ValueError("스캔 오류: " + "; ".join(f"L{e.line_no} {e.reason}" for e in scan.errors))
        self.자동 = 자동_배치형_1행부터 if scan.front.답항 == "1행부터" else 자동_배치형
        sets = {s.rng: s for s in scan.sets}
        done_sets: set[tuple[str, str]] = set()
        out: list[_Para] = []
        for k, qn in enumerate(scan.questions, 1):
            if qn.number != str(k):
                raise ValueError(f"문항 번호 {qn.number} ≠ 차례 {k} — 자동번호와 어긋난다")
            boxes = self._blocks(qn.blocks, f"{qn.number}번")
            tables = [b for b in qn.blocks if b.kind == "답항표"]
            if len(tables) > 1:
                raise ValueError(f"{qn.number}번 답항표가 {len(tables)}개")
            if len(qn.choices) != 5:
                raise ValueError(f"{qn.number}번 답지 {len(qn.choices)}개(5개여야 한다)")
            correct = [c.mark for c in qn.choices if c.correct]
            if len(correct) != 1:
                raise ValueError(f"{qn.number}번 정답 표시 {len(correct)}개(1개여야 한다)")
            self.answers[qn.number] = correct[0]
            if tables:
                self.layouts[qn.number] = "답항표"
                if qn.override:
                    self.notes.append(f"{qn.number}번 {{답항={qn.override}}} — 답항표 문항이라 무시했다")
                choices = [_Para("choice5", [("", None)], obj=self.answer_table(qn, tables[0]))]
            else:
                self.layouts[qn.number], choices = self._choices(qn)
            group = [self._head(qn)] + boxes + choices
            if qn.set_rng is not None and qn.set_rng not in done_sets:
                done_sets.add(qn.set_rng)
                s = sets[qn.set_rng]
                group = self._set_head(s) + self._blocks(s.blocks, self.kit.typeset["set_head"].format(a=s.rng[0], b=s.rng[1]) + " 세트의") + group  # 세트 머리 ~ 첫 문항 끝까지 한 묶음
            group[0].brk = qn.brk  # 나눔 지시는 묶음 첫 문단(세트 첫 문항이면 세트 머리)에
            self._keep(group)
            out += group
        if out:
            out[0].gap = False  # 첫 문단은 관리박스 바로 아래(제출본도 빈 줄 없음)
        return out

    # ---- 문서에 쓰기 ---------------------------------------------------------

    def materialize(self, spec: _Para):
        sid, _, cp = self.style[spec.role]
        pid = self.para_pr(spec.role, keep=spec.keep, gap=spec.gap, align=spec.align, left=spec.left)
        sec = self.doc.sections[0]
        p = sec.add_paragraph("", para_pr_id_ref=pid, style_id_ref=sid, char_pr_id_ref=cp, inherit_style=False)
        if spec.brk:
            p.element.set("columnBreak", "1" if spec.brk == "column" else "0")
            p.element.set("pageBreak", "1" if spec.brk == "page" else "0")
        for run in p.element.findall(q("hp", "run")):  # run은 직접 쓴다 — add_run은 \t를 run 바로 아래 hp:tab으로 둔다
            p.element.remove(run)
        mark, tabs = spec.mark, iter(spec.tabs)
        for text, c in spec.segs:
            if isinstance(text, equation.Math):  # 공개 API — 문단 끝에 수식 run을 붙인다(조각 차례 그대로)
                p.add_equation(text.script, base_unit=self.글자_크기(c or cp), char_pr_id_ref=c or cp)
                continue
            run = ET.SubElement(p.element, q("hp", "run"), {"charPrIDRef": c or cp})
            mark = _fill_t(ET.SubElement(run, q("hp", "t")), text, mark, tabs)
        if mark:
            raise ValueError(f"형광펜 {mark}를 칠할 자리가 없다: {_글(spec.segs)!r}")
        if spec.obj is not None:
            p.element.find(q("hp", "run")).insert(0, spec.obj)  # 견본처럼 <hp:run><hp:tbl/><hp:t/></hp:run>
        return p


_낱말 = re.compile(r"((?:__.+?__|[^\s_]|_(?!_))+)(\s*)")  # 낱말 = 공백 없는 덩어리, 밑줄 `__…__`은 공백이 있어도 한 덩어리


def wrap_words(text: str, avail: int, m: Metrics) -> str:
    """칸 글이 avail(HWPUNIT)에 한 줄로 들어가지 않으면 낱말 사이 공백을 줄바꿈(\\n → hp:lineBreak)으로 바꾼다 — 낱말 단위로
    앞에서부터 채운다(추정 글자 폭). 한글은 표 칸에서 KEEP_WORD여도 낱말 한가운데서 접는다(Task 19 렌더: `가나다`가
    `가나/다`로) — 접을 자리를 조판이 정한다. 밑줄 `__…__`은 안에 공백이 있어도 한 낱말로 다룬다(가운데서 끊으면 밑줄이
    풀린다). 접지 않는 자리의 공백은 원고 그대로(두 칸이면 두 칸). 한 낱말이 avail보다 길면 그 낱말은 그대로 둔다.
    수식 `$…$`은 안에 공백이 있어도 한 덩어리다(가린 글에서 나눈다)."""
    masked, 폭, maths = _가림(text, m)
    if 폭(masked.replace("__", "")) <= avail:
        return text
    parts = [(x.group(1), x.group(2)) for x in _낱말.finditer(masked.strip())]
    if len(parts) < 2:
        return text
    out, cur, sep = [], parts[0][0], parts[0][1]
    for word, nxt in parts[1:]:
        cand = cur + sep + word
        if 폭(cand.replace("__", "")) > avail:
            out.append(cur)
            cur = word
        else:
            cur = cand
        sep = nxt
    out.append(cur)
    return equation.unmask("\n".join(out), maths)


def _fill_t(t: ET._Element, text: str, mark: str | None, tabs=None) -> str | None:
    """hp:t 채우기 — \t는 hp:tab(제출본 모양 `① ㄱ, ㄴ<hp:tab …/>② …`, width는 tabs에서), \n은 hp:lineBreak, mark로 시작하는
    조각은 원문자에 형광펜(add_highlight와 같은 모양 <markpenBegin/>①<markpenEnd/>). 칠했으면 None, 못 칠했으면 mark를 돌려준다."""
    tabs = iter(()) if tabs is None else tabs
    last = None  # 다음 글자를 붙일 자리 — None이면 t.text, 아니면 last.tail
    for piece in re.split(r"(\t|\n)", text):
        if piece == "\n":
            last = ET.SubElement(t, q("hp", "lineBreak"))
            continue
        if piece == "\t":
            last = ET.SubElement(t, q("hp", "tab"), {"width": str(next(tabs)), "leader": "0", "type": "1"})
            continue
        if mark and piece.startswith(mark):
            ET.SubElement(t, q("hp", "markpenBegin"), {"color": 형광}).tail = mark
            last, piece, mark = ET.SubElement(t, q("hp", "markpenEnd")), piece[len(mark):], None
        if piece:
            if last is None:
                t.text = (t.text or "") + piece
            else:
                last.tail = (last.tail or "") + piece
    return mark


def _box_parts(block: Block) -> list[tuple[str, object]]:
    """박스 줄들 → [("글", 줄) | ("표", md 표 줄들) | ("그림", Block) | ("코드", 줄들)] — 이어진 표 줄은 한 표.
    ``` … ``` 사이 줄은 코드(앞 공백·빈 줄 그대로)."""
    out: list[tuple[str, object]] = []
    code: list[str] | None = None
    for raw in block.lines:
        ln = raw.strip()
        if code is not None:
            if ln == "```":
                out.append(("코드", code))
                code = None
            else:
                code.append(raw.rstrip())
            continue
        if ln.startswith("```"):
            code = []
            continue
        m = IMG_RE.match(ln)
        if TABLE_ROW_RE.match(ln):
            if out and out[-1][0] == "표":
                out[-1][1].append(ln)
            else:
                out.append(("표", [ln]))
        elif m:
            out.append(("그림", Block("그림", (ln,), {"src": m.group("src"),
                                                    "width_cm": float(m.group("w")) if m.group("w") else None},
                                    block.line_no)))
        elif ln:
            out.append(("글", ln))
    if code is not None:
        raise ValueError(f"L{block.line_no} :::{block.kind} 안의 코드 블록이 닫히지 않았다(```)")
    return out


def _renumber(doc: HwpxDocument, fresh: list[ET._Element]) -> None:
    """새로 넣은 문단 속 개체(표·그림·…)에 id와 zOrder를 차례로 — 문서의 다른 모든 개체보다 크게.

    insert_paragraphs는 복제하면서 개체 id를 무작위(31비트)로 다시 매긴다 — 겹침이 확률로만 막히므로 여기서 확정한다.
    """
    mine = [e for p in fresh for e in p.iter(*_개체)]
    skip = set(mine)
    used = [int(e.get("id")) for s in doc.sections for e in s.element.iter(*_개체)
            if e not in skip and (e.get("id") or "").isdigit()]
    n = max(used, default=0)
    if n + len(mine) > 0x7FFFFFFF:
        raise ValueError(f"새 개체 id가 31비트를 넘는다(기존 최댓값 {n}) — 양식의 id가 너무 크다")
    z = max((int(e.get("zOrder")) for s in doc.sections for e in s.element.iter(*_개체)
             if e not in skip and (e.get("zOrder") or "").lstrip("-").isdigit()), default=-1)
    for k, e in enumerate(mine, 1):
        e.set("id", str(n + k))
        e.set("zOrder", str(z + k))  # 견본 사본·새 표가 같은 zOrder로 겹치지 않게 차례로


def compose(doc: HwpxDocument, scan: Scan, kit: Kit, *, answer_key: bool, image_root: Path | None = None) -> ComposeResult:
    """prepare_form(+fill_slots+refresh)을 거친 문서의 샘플 구역을 견본 채집 뒤 문항으로 바꾼다."""
    samples = harvest_samples(doc, kit)
    scan = 물결_원고(scan, [tuple(x) for x in kit.typeset["text_replace"]])
    c = _Composer(doc, kit, samples, answer_key=answer_key, image_root=image_root)
    specs = c.plan(scan)
    if not specs:
        raise ValueError("조판할 문항이 없다")
    sec = doc.sections[0]
    start, end = _body_region(doc, kit)
    paras = list(sec.paragraphs)
    old = paras[start:end + 1]
    temp = [c.materialize(s) for s in specs]  # 꼬리 뒤에 임시로 붙였다가
    new = sec.insert_paragraphs(start, temp)   # 샘플 구역 자리로 복제하고
    for w in reversed(temp):                   # 임시본과 샘플 구역을 지운다
        sec.remove_paragraph(w)
    for w in reversed(old):
        sec.remove_paragraph(w)
    _renumber(doc, [p.element for p in new])
    sec.mark_dirty()
    return ComposeResult(answers=dict(c.answers), layouts=dict(c.layouts), notes=list(c.notes))


LOOSER = {"1행": "2행", "2행": "3행", "3행": "5행"}  # 답지가 접히면 한 단계 느슨한 형으로(렌더 루프)


def _문단_글(el) -> str:
    """문단 글(hp:t) — 수식은 그 한/글 수식 문자열로(수식 설명 글 '수식입니다.'는 넣지 않는다)."""
    out = []
    for node in el.iter(q("hp", "t"), q("hp", "equation")):
        if node.tag == q("hp", "equation"):
            s = node.find(q("hp", "script"))
            out.append("" if s is None else s.text or "")
        else:
            out.append("".join(node.itertext()))
    return "".join(out)


def _원고_글(text: str) -> str:
    """원고 글 → _문단_글과 견줄 글 — 수식 `$…$`은 한/글 수식 문자열로, `\\$`는 `$`로."""
    masked, maths = equation.mask(text)
    return "".join(maths[k].script if (k := equation.자리_번호(ch)) is not None else ch for ch in masked)


def choice_paragraphs(doc: HwpxDocument, kit: Kit, number: int) -> list[int]:
    """number번 문항의 답지 줄 문단 인덱스(답항 스타일 4종) — 머리부터 다음 머리(또는 꼬리) 앞까지."""
    ids = style_ids(doc)
    roles = {ids[kit.styles[r]][0] for r in ("choice1", "choice2", "choice3", "choice5")}
    heads = question_heads(doc)
    ps = list(doc.sections[0].paragraphs)
    start = heads[number - 1]
    end = heads[number] if number < len(heads) else len(ps) - 1
    return [i for i in range(start, end) if str(ps[i].element.get("styleIDRef")) in roles]


def relayout_choices(doc: HwpxDocument, kit: Kit, qn: Question, kind: str, *, answer_key: bool) -> None:
    """조판이 끝난 문서에서 qn의 답지 줄 문단만 kind 배치형으로 다시 쓴다(보호 묶음·정답 형광펜 유지)."""
    qn = _물결_문항(qn, [tuple(x) for x in kit.typeset["text_replace"]])  # 조판 때처럼 — 문서의 답지는 이미 바뀐 글이다
    old = choice_paragraphs(doc, kit, int(qn.number))
    if not old:
        raise ValueError(f"{qn.number}번 답지 줄 문단이 없다")
    sec = doc.sections[0]
    ps = list(sec.paragraphs)
    victims = [ps[i] for i in old]
    have = re.sub(r"\s", "", "".join(_문단_글(v.element) for v in victims))
    want = re.sub(r"\s", "", "".join(_원고_글(f"{c.mark}{c.text}".replace("__", "")) for c in qn.choices))
    if have != want:  # 원고가 이 문서와 다르다 — 다른 문항의 답지로 덮어쓰지 않게 멈춘다
        raise ValueError(f"{qn.number}번 답지가 원고와 다르다: 문서 {have!r} ≠ 원고 {want!r}")
    c = _Composer(doc, kit, Samples(None, None, None), answer_key=answer_key)  # 답지 조판은 견본을 쓰지 않는다
    _, specs = c._choices(dataclasses.replace(qn, override=kind))
    last_pp = doc.headers[0].element.find(f".//{q('hh', 'paraPr')}[@id='{victims[-1].element.get('paraPrIDRef')}']")
    last_bs = None if last_pp is None else last_pp.find(q("hh", "breakSetting"))
    for s in specs[:-1]:
        s.keep = True  # 묶음 안 답지 줄은 keepWithNext
    specs[-1].keep = last_bs is not None and last_bs.get("keepWithNext") == "1"  # 마지막 줄은 원래 줄을 따른다
    temp = [c.materialize(s) for s in specs]
    sec.insert_paragraphs(old[0], temp)
    for w in reversed(temp):
        sec.remove_paragraph(w)
    for w in reversed(victims):
        sec.remove_paragraph(w)
    sec.mark_dirty()


def _mark_at(t: ET._Element, anchor, mark: str) -> None:
    """t 안에서 anchor(None = t.text, 아니면 그 자식의 tail) 앞머리 mark를 <markpenBegin/>mark<markpenEnd/>로 감싼다."""
    rest = (t.text if anchor is None else anchor.tail)[len(mark):]
    if anchor is None:
        t.text = None
    else:
        anchor.tail = None
    at = 0 if anchor is None else list(t).index(anchor) + 1
    begin = ET.SubElement(t, q("hp", "markpenBegin"), {"color": 형광})  # SubElement — 부모의 hp 접두를 물려받는다
    end = ET.SubElement(t, q("hp", "markpenEnd"))
    t.insert(at, begin)
    t.insert(at + 1, end)
    begin.tail, end.tail = mark, rest or None


def add_answer_marks(doc: HwpxDocument, kit: Kit, answers: dict[str, str]) -> None:
    """굳힌 문항지에 정답 형광펜만 더한다(답 표시본) — 조판의 answer_key와 같은 자리·모양, 글자·서식·나눔은 그대로.

    자리 = 그 문항 답지 줄 문단(답항표면 그 표의 칸)에서 조각 첫머리가 정답 원문자인 곳(줄 첫머리 또는 탭 뒤).
    """
    ps = list(doc.sections[0].paragraphs)
    n = len(question_heads(doc))
    missing = [k for k in range(1, n + 1) if not answers.get(str(k))]
    if missing:  # 칠하기 전에 — 반쯤 칠한 문서를 남기지 않게
        raise ValueError(f"{', '.join(f'{k}번' for k in missing)} 정답이 없다 — answers에 없다(원고의 * 표시를 본다)")
    for k in range(1, n + 1):
        mark = answers[str(k)]
        spot = None
        for i in choice_paragraphs(doc, kit, k):
            for t in ps[i].element.iter(q("hp", "t")):
                if (t.text or "").startswith(mark):
                    spot = (t, None)
                else:
                    spot = next(((t, ch) for ch in t if ch.tag == q("hp", "tab") and (ch.tail or "").startswith(mark)), None)
                if spot:
                    break
            if spot:
                break
        if spot is None:
            raise ValueError(f"{k}번 정답 {mark}를 칠할 자리가 답지 줄에 없다")
        _mark_at(*spot, mark)
    doc.sections[0].mark_dirty()


def resize_boxes(doc: HwpxDocument, kit: Kit, lines: dict) -> int:
    """〈보기〉·자료 박스의 내용 행 높이를 한컴이 잰 실제 줄 수(lines: fit.Lines, 키 = (최상위 문단, 안 문단 차례))로
    다시 맞춘다 — 바뀐 박스 수. 조판은 추정 줄 수로 셀 높이를 잡는데 한글은 셀을 늘리기만 하고 줄이지 않는다. 그래서
    자간 맞춤이 줄을 당긴 항목(또는 추정이 넘친 항목)이 있으면 박스 아래가 한 줄 빈다(Task 29 발견, 아랫여백 20.4 vs 11.6pt).
    높이 식은 _box와 같다: 글 줄 = 줄 수 × 피치(+ 수식이 든 줄은 한컴 줄 높이 − 글자 높이), 개체 줄 = 개체 높이 + 바깥 여백
    + (피치 − 글자 높이), 끝에 kit.metrics.box_extra − 피치.
    내용 셀 글 문단 가운데 하나라도 lines에 없으면 그 박스는 그대로 둔다. 높이는 kit.box_min_height(양식 견본 내용 셀)
    밑으로 내리지 않는다 — 교사도 양식 박스에서 시작하고 한글은 셀을 늘리기만 해서 제출본 세 줄 박스는 모두 이 높이다.
    """
    ids = style_ids(doc)
    c = _Composer(doc, kit, Samples(None, None, None), answer_key=False)
    shapes = {tuple(str(n) for n in spec["shape"]): k for k, spec in kit.boxes.items() if isinstance(spec, dict)}
    changed = 0
    paras = list(doc.sections[0].paragraphs)
    for i, p in enumerate(paras):
        if i == 0 or i == len(paras) - 1:  # 관리박스·꼬리 박스 문단의 표는 박스가 아니다(학교 B 꼬리 박스도 1×1)
            continue
        subs = list(p.element.iter(q("hp", "p")))[1:]  # 키의 둘째 값 = 이 목록의 차례(fit.read_lines와 같다)
        for tbl in _top_tables(p.element):
            kind = shapes.get((tbl.get("rowCnt"), tbl.get("colCnt")))
            if kind is None:
                continue
            _, (cc, cr), rails, role = _박스(kit, kind)
            cells = {(int(a.get("colAddr")), int(a.get("rowAddr"))): tc
                     for tc in tbl.iter(q("hp", "tc")) for a in [tc.find(q("hp", "cellAddr"))]}
            content = cells.get((cc, cr))
            if content is None:
                continue
            paras = content.find(q("hp", "subList")).findall(q("hp", "p"))
            if not paras or ids[kit.styles[role]][0] not in {x.get("styleIDRef") for x in paras}:
                continue  # 박스 모양이지만 우리 박스가 아니다(양식 견본 등)
            pitch, h, ok = c._line_pitch(role), 0, True
            for para in paras:
                obj = next((x for r in para.findall(q("hp", "run")) for x in r
                            if x.tag in (q("hp", "tbl"), q("hp", "pic"))), None)
                if obj is not None:
                    osz, om = obj.find(q("hp", "sz")), obj.find(q("hp", "outMargin"))
                    h += int(osz.get("height")) + int(om.get("top")) + int(om.get("bottom")) + pitch - kit.metrics.char_height
                    continue
                j = next((n for n, e in enumerate(subs) if e is para), None)
                got = None if j is None else lines.get((i, j))
                if got is None:
                    ok = False
                    break
                h += got.n * pitch + got.extra(kit.metrics.char_height)  # 수식이 든 줄은 한컴이 잰 만큼 더 높다
            if not ok:
                continue
            h += kit.metrics.box_extra - pitch
            if kit.box_min_height is not None:
                h = max(h, kit.box_min_height)  # 양식 견본 내용 셀 높이 밑으로 내리지 않는다
            old = int(content.find(q("hp", "cellSz")).get("height"))
            if old == h:
                continue
            for col in (cc, *rails):
                if (col, cr) in cells:
                    cells[(col, cr)].find(q("hp", "cellSz")).set("height", str(h))
            sz = tbl.find(q("hp", "sz"))
            sz.set("height", str(int(sz.get("height")) - old + h))
            changed += 1
    if changed:
        doc.sections[0].mark_dirty()
    return changed
