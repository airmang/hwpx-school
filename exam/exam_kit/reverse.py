"""원안지(.hwp·.hwpx) → md v2. 교사가 한/글에서 만든 원안지를 원고로 되돌린다. 실문항 출력은 미추적 폴더에만.

읽는 구조(설계 §1): 자동번호 머리 문단(문항) · 〈보기〉 4×5 · 자료 3×3 · 격자표 · 탭으로 이은 답지 ·
노랑 형광펜 정답(흰색은 손편집 잔재라 무시) · 밑줄 run → `__…__` · 공백으로 열을 맞춘 짝짓기 답지 → `:::답항표`.
그림은 BinData를 md 옆 PNG 파일로 꺼내고(BMP·JPG 등도 PNG로 — 회색조는 조판이 한다) 문서의 폭(cm)으로 참조한다.
규칙 밖 구조는 조용히 버리지 않고 멈춘다(ReverseStop — 문항·쪽 어림·문단·까닭).

양식에서 알아야 하는 것(본문 범위·박스·머리 값)은 FormProfile이 준다. 지금은 학교 킷 프로필(kit_profile)뿐이고,
킷 없는 양식의 일반 규칙 프로필은 같은 틀로 더한다(이슈 #8). 입력 열기는 source.open_source.
"""

from __future__ import annotations

import io
import re
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import lxml.etree as ET
from hwpx.document import HwpxDocument
from hwpx.equation import EquationConversionError, eqedit_to_latex
from PIL import Image, UnidentifiedImageError

from . import equation, preserve, q
from .kit import Kit
from .prepare import _text, _top_tables
from .slots import read_text_slots
from .source import Source, SourceError, open_source
from .verify import _tail_index, question_heads

원문자 = "①②③④⑤"
노랑 = "#FFFF00"
CM = 72000 / 25.4  # 1 cm = 2834.6 HWPUNIT (compose.CM과 같은 값)
_배점 = re.compile(r"\s*\[(\d+(?:\.\d+)?)점\]\s*$")
_세트 = re.compile(r"^\[(\d+)\s*[∼~]\s*(\d+)\]\s*")
_머리기호 = re.compile(r"^(?:[ㄱㄴㄷㄹㅁ]|[㉠㉡㉢㉣㉤]|\((?:[가나다라마]|[ㄱㄴㄷㄹㅁ]|[A-E])\)|[A-E])$")
_보기_항목 = re.compile(r"^(?:[ㄱㄴㄷㄹㅁ]\.|∘)\s")
_답지_시작 = re.compile(r"(?:^|\s{2,})(\*?)([①②③④⑤])")
_열맞춤_답지 = re.compile(r"^\*?[①②③④⑤]\s{3,}")  # 원문자 뒤 공백 3칸+ = 열을 맞춘 짝짓기 행
_OPF = {"opf": "http://www.idpf.org/2007/opf/"}

Picture = Callable[[ET._Element], str]  # hp:pic → md 그림 줄


class ReverseStop(ValueError):
    """역변환이 모르는 구조를 만나 멈췄다 — 어디서(문항·쪽 어림·문단)와 까닭. 조용히 넘기지 않는다."""

    def __init__(self, reason: str, *, question: int | None = None, page: int | None = None,
                 paragraph: int | None = None, snippet: str = ""):
        self.reason, self.question, self.page, self.paragraph, self.snippet = reason, question, page, paragraph, snippet
        where = [x for x in (f"약 {page}쪽" if page else "", f"{question}번 문항" if question else "문항 앞",
                             f"문단 {paragraph}" if paragraph is not None else "") if x]
        super().__init__(f"{' · '.join(where)}: {reason}" + (f" — 글 {snippet!r}" if snippet else ""))


def mono_char_prs(doc: HwpxDocument) -> set[str]:
    """고정폭 글꼴 charPr — 한글 글꼴의 typeInfo proportion 9(고정폭) 또는 이름이 '…체'(굴림체·돋움체·바탕체·궁서체).
    이 글꼴로만 된 문단은 코드 블록으로 되돌린다(Task 30)."""
    hdr = doc.headers[0].element
    ff = next((f for f in hdr.iter(q("hh", "fontface")) if f.get("lang") == "HANGUL"), None)
    mono = set() if ff is None else {
        f.get("id") for f in ff.findall(q("hh", "font"))
        if (f.get("face") or "").endswith("체") or (f.find(q("hh", "typeInfo")) is not None
                                                    and f.find(q("hh", "typeInfo")).get("proportion") == "9")}
    return {c.get("id") for c in hdr.iter(q("hh", "charPr"))
            if c.find(q("hh", "fontRef")) is not None and c.find(q("hh", "fontRef")).get("hangul") in mono}


def is_code(p_el, mono: set[str]) -> bool:
    """고정폭 글꼴 run뿐인 문단(표·그림 없음) — 빈 줄도 코드 줄이 될 수 있다."""
    runs = p_el.findall(q("hp", "run"))
    return bool(mono) and bool(runs) and all(r.get("charPrIDRef") in mono for r in runs) \
        and not _top_tables(p_el) and not _pics(p_el)


def code_text(p_el) -> str:
    """코드 줄 글 — 앞 공백 그대로(끝 공백만 뺀다)."""
    return "".join(_run_text(r) for r in p_el.findall(q("hp", "run"))).rstrip()


def underlined_char_prs(doc: HwpxDocument) -> set[str]:
    out = set()
    for c in doc.headers[0].element.iter(q("hh", "charPr")):
        u = c.find(q("hh", "underline"))
        if u is not None and (u.get("type") or "NONE") != "NONE":
            out.add(c.get("id"))
    return out


_run_자식 = {q("hp", "t"), q("hp", "tbl"), q("hp", "pic"), q("hp", "equation")}  # 표·그림은 부르는 쪽이 따로 옮긴다
# 글을 싣지 않는 컨트롤(누름틀 경계·책갈피·단 설정·쪽 번호·감추기) — 건너뛴다. 각주·미주·새 번호 등은 글이 있어 오류.
_무해_컨트롤 = {q("hp", t) for t in ("fieldBegin", "fieldEnd", "bookmark", "colPr", "pageNum", "pageHiding")}
_공백_자식 = {q("hp", "lineBreak"), q("hp", "nbSpace"), q("hp", "fwSpace")}
_t_자식 = {q("hp", "tab"), q("hp", "markpenBegin"), q("hp", "markpenEnd")} | _공백_자식
_펜 = "\x00"  # 노랑 형광펜 자리 — 문단 글을 다 이은 뒤 다음 원문자 앞 `*`로 바꾼다(run을 건너 걸친 형광펜)
_펜_답 = re.compile(_펜 + r"\s*(__)?\s*([①②③④⑤])")


def _tag(el) -> str:
    return el.tag.split("}")[-1] if isinstance(el.tag, str) else str(el.tag)


def _check_run(run) -> None:
    for ch in run:
        if ch.tag == q("hp", "ctrl"):
            bad = [_tag(c) for c in ch if c.tag not in _무해_컨트롤]
            if bad:
                raise ValueError(f"run 안의 컨트롤 hp:{', hp:'.join(bad)} — 역변환하지 않는다")
        elif ch.tag not in _run_자식:
            raise ValueError(f"run 안의 모르는 요소 hp:{_tag(ch)} — 역변환하지 않는다")


def _수식_원고(eq) -> str:
    """hp:equation → 원고 수식 `$LaTeX$`(hwpx.equation.eqedit_to_latex). 되돌린 LaTeX가 다시 한/글 수식으로 바뀌지 않으면
    (조판할 수 없는 원고가 되면) 오류."""
    s = eq.find(q("hp", "script"))
    script = "" if s is None else (s.text or "").strip()
    if not script:
        raise ValueError("빈 수식(hp:script 없음) — 역변환하지 않는다")
    try:
        latex = eqedit_to_latex(script)
        equation.to_script(latex)
    except (EquationConversionError, equation.MathError) as e:
        raise ValueError(f"수식 {script!r}을 원고 LaTeX로 되돌릴 수 없다 — {e}") from e
    return f"${latex}$"


def _run_text(run, *, escape: bool = False) -> str:
    """run 글. 모르는 자식(도형·각주 등)은 조용히 버리지 않고 오류. 노랑 형광펜은 자리표(_펜)로 남긴다.
    수식은 원고 표기 `$LaTeX$`로. escape면 글의 달러 글자를 `\\$`로 쓴다(수식 표기와 겹치지 않게 — 코드 줄은 그대로)."""
    _check_run(run)
    buf: list[str] = []
    for x in run:
        if x.tag == q("hp", "equation"):
            buf.append(_수식_원고(x))
            continue
        if x.tag != q("hp", "t"):
            continue
        piece = [x.text or ""]
        for ch in x:
            if ch.tag not in _t_자식:
                raise ValueError(f"글 안의 모르는 요소 hp:{_tag(ch)} — 역변환하지 않는다")
            if ch.tag == q("hp", "tab"):
                piece.append("\t")
            elif ch.tag == q("hp", "markpenBegin") and (ch.get("color") or "").upper() == 노랑:
                piece.append(_펜)
            elif ch.tag in _공백_자식:
                piece.append(" ")
            piece.append(ch.tail or "")
        text = "".join(piece)
        buf.append(text.replace("$", "\\$") if escape else text)
    return "".join(buf)


def _resolve_pens(s: str) -> str:
    """형광펜 자리표 → 바로 뒤(공백·run 경계 건너) 원문자 앞 `*`. 원문자가 아닌 글에 걸린 형광펜은 모호해 오류."""
    s = _펜_답.sub(lambda m: f"{m.group(1) or ''}*{m.group(2)}", s)
    if _펜 in s:
        i = s.index(_펜)
        raise ValueError(f"노랑 형광펜이 원문자가 아닌 글에 있다 {s[i + 1:i + 11]!r} — 정답 표시가 모호하다")
    return s


def paragraph_text(p_el, underlined: set[str]) -> str:
    """문단 글: 탭 → `\\t`, 밑줄 run → `__…__`(앞뒤 공백은 밑줄 밖), 노랑 형광펜 → 원문자 앞 `*`."""
    groups: list[list] = []  # [글, 밑줄?] — 이웃한 밑줄 run은 한 덩어리로
    for run in p_el.findall(q("hp", "run")):
        s = _run_text(run, escape=True)
        ul = run.get("charPrIDRef") in underlined and bool(s.replace(_펜, "").strip())
        if groups and groups[-1][1] == ul:
            groups[-1][0] += s
        else:
            groups.append([s, ul])
    parts = []
    for s, ul in groups:
        if ul:
            m = re.match(r"^(\s*)(.*?)(\s*)$", s, re.S)
            s = f"{m.group(1)}__{m.group(2)}__{m.group(3)}"
        parts.append(s)
    return _resolve_pens("".join(parts)).strip()


def split_choices(text: str) -> list[str]:
    """한 문단에 이은 답지 → 답지 하나씩. 탭으로 가르고, 탭 없이 이었으면 두 칸 이상 공백 + 다음 차례 원문자에서만.

    답지 본문 속 원문자(`③ ④번 과정이…`, `② ③과 같다`)는 한 칸 공백 뒤라 자르지 않는다.
    """
    out: list[str] = []
    for chunk in text.split("\t"):
        chunk = chunk.strip()
        if not chunk:
            continue
        cuts = [0]
        last = None
        for m in _답지_시작.finditer(chunk):
            mark = m.group(2)
            if last is None:
                last = mark
            elif 원문자.index(mark) == 원문자.index(last) + 1:
                cuts.append(m.start(1))
                last = mark
        out += [chunk[a:b].strip() for a, b in zip(cuts, cuts[1:] + [len(chunk)]) if chunk[a:b].strip()]
    return out


def _row_cells(line: str) -> list[str]:
    cells = [c for c in re.split(r"\s{2,}|\t", line.strip()) if c]
    m = re.match(r"^(\*?[①②③④⑤])\s+(.+)$", cells[0]) if cells else None
    if m:  # 원문자와 첫 값 사이가 한 칸뿐인 줄
        cells[:1] = [m.group(1), m.group(2)]
    return cells


def _head_cells(line: str) -> list[str]:
    return line.split()  # 머리 기호에는 공백이 없다 — 한 칸 띄운 `ㄱ ㄴ ㄷ`도 머리


def _is_matching_head(line: str) -> bool:
    head = _head_cells(line)
    return len(head) >= 2 and all(_머리기호.match(h) for h in head)


def detect_matching(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """공백으로 열을 맞춘 짝짓기 답지(머리 줄 + 원문자 5줄) → (머리, 행[원문자, 칸…]). 아니면 None."""
    if len(lines) != 6:
        return None
    if not _is_matching_head(lines[0]):
        return None
    head = _head_cells(lines[0])
    rows = []
    for mark, ln in zip(원문자, lines[1:]):
        cells = _row_cells(ln)
        if not cells or cells[0].lstrip("*") != mark or len(cells) != len(head) + 1:
            return None
        rows.append(cells)
    return head, rows


def _cells(tbl) -> list:
    """이 표 자신의 칸만 — 칸 안에 든 표의 칸은 섞지 않는다."""
    return [tc for tr in tbl.findall(q("hp", "tr")) for tc in tr.findall(q("hp", "tc"))]


def _cell(tbl, row: int, col: int):
    for tc in _cells(tbl):
        a = tc.find(q("hp", "cellAddr"))
        if a is not None and a.get("rowAddr") == str(row) and a.get("colAddr") == str(col):
            return tc
    return None


def _span(tc) -> tuple[int, int]:
    s = tc.find(q("hp", "cellSpan"))
    return (1, 1) if s is None else (int(s.get("rowSpan", "1")), int(s.get("colSpan", "1")))


def _cell_paras(tc) -> list:
    sub = tc.find(q("hp", "subList"))
    return [] if sub is None else sub.findall(q("hp", "p"))


def _pics(p_el) -> list:
    return [pic for run in p_el.findall(q("hp", "run")) for pic in run.findall(q("hp", "pic"))]


def _box_lines(tc, underlined: set[str], picture: Picture | None, where: str, mono: set[str] = frozenset(),
               boxes: dict | None = None) -> list[str]:
    """박스 내용 칸 → md 줄(글 · 칸 안 격자표 · 칸 안 그림 · 고정폭 문단 = ``` 코드 블록)."""
    out: list[str] = []
    code: list[str] | None = None
    for p in _cell_paras(tc):
        if is_code(p, mono):
            code = (code or []) + [code_text(p)]
            continue
        if code is not None:
            out += ["```", *code, "```"]
            code = None
        for t in _top_tables(p):
            kind, lines = classify_table(t, underlined, boxes=boxes, picture=picture, mono=mono)
            if kind != "표":
                raise ValueError(f"{where}: 박스 안에 {kind} 박스가 있다 — 역변환하지 않는다")
            out += lines
        for pic in _pics(p):
            if picture is None:
                raise ValueError(f"{where}: 그림이 있는데 그림 저장 자리가 없다")
            out.append(picture(pic))
        t = paragraph_text(p, underlined)
        if t:
            out.append(t)
    if code is not None:
        out += ["```", *code, "```"]
    return out


def _join_items(lines: list[str]) -> list[str]:
    """〈보기〉 항목이 문단 둘 이상으로 이어졌으면(기호 없는 줄) 앞 항목에 붙인다."""
    out: list[str] = []
    for ln in lines:
        if out and not _보기_항목.match(ln) and _보기_항목.match(out[-1]):
            out[-1] += " " + ln
        else:
            out.append(ln)
    return out


def _blank_cell(tc) -> bool:
    return tc is not None and not _text(tc).strip() and not any(_pics(p) or _top_tables(p) for p in _cell_paras(tc))


def _is_box_frame(tbl, spec: dict) -> bool:
    """자료 박스 틀(킷 boxes["자료"]): 칸 수가 spec cells이고 내용 칸(병합 없음) 밖의 칸은 모두 빈 칸.
    예: 3×3 = 0행·2행 3칸 병합 빈 칸 + 1행 [빈 레일 | 내용 | 빈 레일]. 하나라도 어긋나면 격자표다."""
    tcs = _cells(tbl)
    cc, cr = spec["content_cell"]
    body = _cell(tbl, cr, cc)
    return (len(tcs) == spec["cells"] and body is not None and _span(body) == (1, 1)
            and all(_blank_cell(tc) for tc in tcs if tc is not body))


def answer_table(tbl, underlined: set[str]) -> list[str] | None:
    """조판기의 짝짓기 답항표(compose.answer_table — 무테 6행: 머리행 [빈 칸, 기호…] + ①~⑤ 행) → `:::답항표` 몸 줄
    [머리 줄, 행 다섯]. 아니면 None. 머리 기호의 밑줄은 조판이 다는 것이라 뺀다."""
    trs = tbl.findall(q("hp", "tr"))
    if len(trs) != 6 or any(_span(tc) != (1, 1) for tc in _cells(tbl)):
        return None

    def 글(tc) -> str:
        return " ".join(t for p in _cell_paras(tc) if (t := paragraph_text(p, underlined)))

    rows = [[글(tc) for tc in tr.findall(q("hp", "tc"))] for tr in trs]
    if rows[0][0] or len({len(r) for r in rows}) != 1 or len(rows[0]) < 3:
        return None
    if [r[0].lstrip("*") for r in rows[1:]] != list(원문자):
        return None
    head = [h.replace("__", "").strip() for h in rows[0][1:]]
    return [f'머리="{"|".join(head)}"'] + [f"{r[0]} " + " | ".join(r[1:]) for r in rows[1:]]


def classify_table(tbl, underlined: set[str], *, boxes: dict | None = None, picture: Picture | None = None,
                   mono: set[str] = frozenset()) -> tuple[str, list[str]]:
    """본문 표 → ("보기", 항목 줄) | ("자료", 내용 줄) | ("표", md 표 줄). 병합 칸 격자표·그림 칸은 오류.
    boxes = 킷 boxes — 없으면 박스를 가리지 않고 모두 격자표로 본다."""
    rows, cols = tbl.get("rowCnt"), tbl.get("colCnt")
    shape = [int(rows), int(cols)]
    specs = {k: v for k, v in (boxes or {}).items() if isinstance(v, dict) and "shape" in v}
    for kind, spec in specs.items():  # 제목 있는 박스(〈보기〉·〈조건〉): 모양 + 제목 글
        if not spec.get("title_match") or shape != spec["shape"] or spec["title_match"] not in _text(tbl):
            continue
        name = kind.rstrip("◦")
        cc, cr = spec["content_cell"]
        cell = _cell(tbl, cr, cc)
        rails = spec.get("rails") or []
        width = rails[-1] - rails[0] - 1 if rails else shape[1] - cc  # 레일 사이, 레일이 없으면 내용 칸부터 오른쪽 끝까지
        if cell is None or _span(cell) != (1, width):
            raise ValueError(f"〈{name}〉 박스 모양이 양식과 다르다({cr}행 {cc}열 내용 칸이 1×{width}가 아니다)")
        lines = _box_lines(cell, underlined, picture, f"〈{name}〉", mono, boxes)
        return name, (_join_items(lines) if name == "보기" else lines)
    for kind, spec in specs.items():  # 제목 없는 박스(자료): 칸 수 + 내용 칸 밖은 모두 빈 칸
        if spec.get("title_match") or shape != spec["shape"] or not _is_box_frame(tbl, spec):
            continue
        cc, cr = spec["content_cell"]
        return kind.rstrip("◦"), _box_lines(_cell(tbl, cr, cc), underlined, picture, "자료 박스", mono, boxes)
    table = answer_table(tbl, underlined)
    if table is not None:
        return "답항표", table
    md: list[list[str]] = []
    for tr in tbl.findall(q("hp", "tr")):
        row = []
        for tc in tr.findall(q("hp", "tc")):
            if _span(tc) != (1, 1):
                raise ValueError(f"병합 칸이 있는 표 ({rows}×{cols}) — md 표로 옮길 수 없다")
            if any(_pics(p) or _top_tables(p) for p in _cell_paras(tc)):
                raise ValueError(f"그림·표가 든 표 ({rows}×{cols}, 그림 자료표?) — 역변환하지 않는다")
            row.append(" ".join(t for p in _cell_paras(tc) if (t := paragraph_text(p, underlined))))
        md.append(row)
    lines = ["| " + " | ".join(r) + " |" for r in md]
    lines.insert(1, "|" + "---|" * len(md[0]))
    return "표", lines


def picture_line(pic, name: str) -> str:
    """hp:pic → `![](name){width=Ncm}` — 폭은 문서의 현재 폭(hp:sz) 그대로."""
    cm = int(pic.find(q("hp", "sz")).get("width")) / CM
    return f"![]({name}){{width={f'{cm:.2f}'.rstrip('0').rstrip('.')}cm}}"


def _bin_items(hwpx: Path) -> dict[str, tuple[str, bytes]]:
    """BinData id → (확장자, 바이트) — content.hpf 목록에서."""
    with zipfile.ZipFile(hwpx) as z:
        hpf = ET.fromstring(z.read("Contents/content.hpf"))
        out = {}
        for it in hpf.iterfind(".//opf:item", _OPF):
            href = it.get("href") or ""
            if href.startswith("BinData/"):
                out[it.get("id")] = (Path(href).suffix or ".bin", z.read(href))
        return out


# 누름틀 슬롯 이름 → 같은 뜻의 글자 자리 값 이름(slots.read_text_slots) — 글자 자리 양식은 머리·대상 학년이 한 자리다
_글자_자리_이름 = {"머리_학년": "학년", "머리_학기": "학기", "머리_차": "차", "머리_과목": "과목"}
_머리_차례 = ("양식", "학년도", "학년", "학기", "차", "과목", "과목코드", "시행", "대상", "인쇄", "출제교사", "만점")


def kit_front(doc: HwpxDocument, kit: Kit) -> dict[str, str | None]:
    """학교 킷으로 읽은 머리 값 — 누름틀(kit.slots)에서, 누름틀이 없으면 글자 자리(kit.text_slots, slots.read_text_slots)에서.
    읽지 못한 키는 None(누름틀이 없다 — 양식이 바뀌었거나 교사가 누름틀을 지우고 글로 썼다). 비었으면 자리표시를 둘 수 있는
    키(시행·대상의 반·인쇄)는 `__`·`_`로 남긴다(초안). 숫자여야 하는 키(학년도·학년·학기·차)는 숫자가 아니면 모름."""
    v = {f.field_id: f.value for f in doc.list_form_fields()}
    ts = read_text_slots(doc, kit) if kit.text_slots else {}

    def g(slot: str) -> str | None:
        """누름틀 값(없으면 같은 뜻의 글자 자리 값) — 둘 다 없으면 None, 비었거나 자리표시면 ""."""
        fid = kit.slots.get(slot)
        if fid is not None and fid in v:
            x = v[fid] or ""
            return "" if x == kit.placeholders.get(slot) else x
        x = ts.get(_글자_자리_이름.get(slot, slot))
        return None if x is None else ("" if re.search(r"_|○", x) else x)

    def 칸(slot: str, blank: str) -> str:  # 자리표시를 둘 수 있는 칸 — 없거나 비면 자리표시
        return g(slot) or blank

    def 값(slot: str, digits: bool = False) -> str | None:  # 자리표시를 둘 수 없는 칸 — 없거나 비면 모름
        x = g(slot) or None
        return None if x is None or (digits and not x.isdigit()) else x

    header = " ".join(_text(h) for h in doc.sections[0].element.iter(q("hp", "header")))
    학년도 = re.search(r"(\d{4})학년도", header)
    tc = kit.teacher_cell or {"label": "출제교사", "template": "{name}", "placeholder": ""}  # 글자 자리 양식은 칸 글 그대로
    pre, post = (re.escape(x.strip()) for x in tc["template"].split("{name}"))
    teacher = re.search(rf"{re.escape(tc['label'])}\s*{pre}\s*(\S+?)\s*{post}",
                        _text(doc.sections[0].paragraphs[kit.admin["paragraph"]].element))
    grade = 값("학년", digits=True)
    names = set(kit.slots) | {n for t in kit.text_slots for n in re.findall(r"{(\w+)}", t["fill"])}

    def 있음(*slots: str) -> bool:  # 이 양식에 그 머리 값의 자리가 있다(없으면 원고 머리에 쓰지 않는다 — 선택 키)
        return any(x in names for x in slots)

    front: dict[str, str | None] = {
        "양식": kit.name, "학년도": 학년도.group(1) if 학년도 else 값("학년도", digits=True),
        "학년": 값("머리_학년", digits=True), "학기": 값("머리_학기", digits=True), "차": 값("머리_차", digits=True),
        "과목": 값("과목"), "과목코드": 값("과목코드"),
        "시행": f"{칸('월', '__')}.{칸('일', '__')}.({칸('요일', '_')}) {칸('교시', '_')}교시",
        "대상": None if grade is None or not 있음("반_시작", "반_끝") else f"{grade}학년 {칸('반_시작', '_')}반~{칸('반_끝', '_')}반",
        "인쇄": f"{칸('인쇄매수', '__')}매 * {칸('묶음', '_')}묶음" if 있음("인쇄매수", "묶음") else None,
        "출제교사": (값("출제교사") if kit.teacher_cell is None else None)  # 글자 자리 양식은 칸 글 그대로(슬롯)
                    or (teacher.group(1) if teacher and teacher.group(1) != tc["placeholder"] else None) or "미상",
        "대상_반": f"{칸('반_시작', '_')}반~{칸('반_끝', '_')}반",  # 학년 누름틀이 없을 때 --front 학년과 다시 짓는다(머리에는 안 쓴다)
    }
    만점 = g("선택형_만점") or ""
    if re.fullmatch(r"\d+(?:\.\d+)?", 만점) and float(만점) != 100:
        front["만점"] = 만점
    return front


def resolve_front(read: dict[str, str | None], given: dict[str, str], required) -> list[str]:
    """읽은 머리 값 + 사용자가 준 값(given, `--front 키=값`) → 머리 줄. given이 이긴다. 학년을 주었고 대상을 못 읽었으면
    대상은 그 학년과 읽은 반으로 다시 짓는다. 필수 키가 하나라도 비면 멈춘다 — 무엇을 어떻게 주는지 알린다."""
    unknown = sorted(set(given) - set(_머리_차례))
    if unknown:
        raise ReverseStop(f"모르는 머리 키 {unknown} — 아는 키: {', '.join(_머리_차례)}")
    front = dict(read)
    front.update(given)
    if front.get("대상") is None and "학년" in given and read.get("대상_반"):
        front["대상"] = f"{given['학년']}학년 {read['대상_반']}"
    missing = [k for k in required if not front.get(k)]
    if missing:
        raise ReverseStop(f"머리 값을 문서에서 읽지 못했다: {', '.join(missing)} — 누름틀이 없거나 비었다. "
                          f"`--front {' '.join(f'{k}=…' for k in missing)}`로 준다")
    return ["---"] + [f"{k}: {front[k]}" for k in _머리_차례 if front.get(k)] + ["---", ""]


class _Question:
    def __init__(self, k: int, head: str, member: bool):
        pm = _배점.search(head)
        self.k, self.member = k, member
        self.points = float(pm.group(1)) if pm else None
        stem = re.sub(rf"^{k}\.\s*", "", _배점.sub("", head).strip())  # 글자 번호 양식의 `N. `은 번호 — 원고는 머리에 쓴다
        self.lines = [self._head_line(), stem]
        self.text_at: list[int] = [1]  # 글 줄(발문·발문 이음)의 자리 — 배점이 머리 문단이 아니라 뒤 줄 끝에 있을 때 찾는다
        self.blocked = False  # 블록(박스·표·그림 등)을 지났는가 — 그 전의 글 문단은 발문 문단이다
        self.matching_head: str | None = None
        self.choice_paras: list[str] = []
        self.answer_table: list[str] | None = None  # 조판기 답항표(answer_table) — 답지 대신

    def add_block(self, kind: str, lines: list[str]) -> None:
        self.blocked = True
        if kind == "답항표":
            if self.answer_table is not None or self.choice_paras:
                raise ValueError(f"{self.k}번: 답항표가 둘이거나 답지 줄과 함께 있다")
            self.answer_table = lines
            return
        self.lines += [""] + _block_md(kind, lines)

    def _head_line(self) -> str:
        points = f" [{self.points:.1f}점]" if self.points is not None else ""
        return f"{'###' if self.member else '##'} {self.k}.{points}"

    def add_text(self, t: str, where: str) -> None:
        if t.lstrip("*")[:1] in 원문자:
            self.choice_paras.append(t)
        elif self.choice_paras:
            raise ValueError(f"{where}: 답지 뒤에 본문 줄 {t[:20]!r}")
        elif _is_matching_head(t):
            self.matching_head = t  # 짝짓기 머리 줄(ㄱ  ㄴ  ㄷ)
        else:
            if not self.blocked and self.lines[-1]:  # 발문 문단이 나뉘어 있다 — 빈 줄로 나눠 교사가 나눈 문단을 지킨다
                self.lines.append("")
            self.text_at.append(len(self.lines))
            self.lines.append(t)

    def _points_from_text(self) -> None:
        """머리 문단에 배점이 없으면 발문이 이어진 뒤 줄(그림 뒤 발문 등) 끝의 `[N점]`을 머리로 옮긴다 — 마지막 것 하나."""
        if self.points is not None:
            return
        for i in reversed(self.text_at):
            m = _배점.search(self.lines[i])
            if m:
                self.points = float(m.group(1))
                self.lines[i] = _배점.sub("", self.lines[i]).rstrip()
                self.lines[0] = self._head_line()
                return

    def finish(self) -> list[str]:
        self._points_from_text()
        if self.answer_table is not None:
            if self.choice_paras or self.matching_head is not None:
                raise ValueError(f"{self.k}번: 답항표 뒤에 답지 줄이 또 있다")
            head, *rows = self.answer_table
            return self.lines + ["", f":::답항표 {head}", *rows, ":::", ""]
        if self.matching_head is not None:
            m = detect_matching([self.matching_head] + self.choice_paras)
            if m is None:
                raise ValueError(f"{self.k}번: 짝짓기 머리 {self.matching_head.strip()!r} 아래 답지가 5행 열 맞춤이 아니다")
            head, rows = m
            return self.lines + ["", f':::답항표 머리="{"|".join(head)}"'] + [f"{r[0]} " + " | ".join(r[1:]) for r in rows] + [":::", ""]
        choices = [c for t in self.choice_paras for c in split_choices(t)]
        if any(_열맞춤_답지.match(c) for c in choices):
            raise ValueError(f"{self.k}번: 열을 맞춘 답지 행이 있는데 짝짓기 머리를 못 찾았다 — 머리 줄을 확인")
        marks = "".join(c.lstrip("*")[0] for c in choices)
        if marks != 원문자:
            raise ValueError(f"{self.k}번: 답지 {marks!r} — ①~⑤ 다섯 개가 아니다")
        return self.lines + [""] + choices + [""]


def _block_md(kind: str, lines: list[str]) -> list[str]:
    if kind == "코드":
        return ["```", *lines, "```"]
    return lines if kind in ("표", "그림") else [f":::{kind}", *lines, ":::"]


def as_png(data: bytes, ext: str) -> bytes:
    """그림 바이트 → PNG(무손실). PNG는 그대로, BMP·JPG·GIF 등은 PNG로 다시 쓴다 — 원고 그림은 PNG로 통일한다
    (조판이 회색조 사본을 만든다). 열 수 없는 형식(WMF·EMF 같은 벡터 등)은 멈춘다."""
    if ext.lower() == ".png":
        return data
    try:
        with Image.open(io.BytesIO(data)) as im:
            buf = io.BytesIO()
            im.save(buf, "PNG")
            return buf.getvalue()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError(f"그림 형식 {ext}을 PNG로 바꿀 수 없다 — 한/글에서 그림을 PNG·BMP·JPG로 바꿔 넣는다") from e


def page_guess(paras: list, columns: int) -> list[int | None]:
    """문단마다 쪽 어림 — 저장된 줄 배치(hp:lineseg vertpos)가 줄어드는 곳을 새 단으로 센다. 한/글이 저장할 때 잰 배치라
    렌더 없이 알 수 있지만, 줄 캐시가 없는 문단(새로 만든 문서)은 앞 문단의 쪽을 이어 쓴다. 오류 위치 알림용."""
    out: list[int | None] = []
    col, prev, page = 0, None, None
    for el in paras:
        seg = el.find(f"{q('hp', 'linesegarray')}/{q('hp', 'lineseg')}")
        if seg is not None and seg.get("vertpos") is not None:
            y = int(seg.get("vertpos"))
            if prev is not None and y < prev:
                col += 1
            prev = y
            page = col // max(1, columns) + 1
        out.append(page)
    return out


def _saver(bins: dict[str, tuple[str, bytes]], image_dir: Path | None):
    """그림 저장기 — 이름표(문항 번호·세트)를 바꿔 가며 hp:pic을 파일로 쓰고 md 그림 줄을 돌려준다."""
    owner = {"label": "", "n": 0}

    def picture(pic) -> str:
        ref = pic.find(f".//{q('hc', 'img')}")
        rid = None if ref is None else ref.get("binaryItemIDRef")
        if rid not in bins:
            raise ValueError(f"그림 BinData {rid!r}가 문서에 없다")
        if image_dir is None:
            raise ValueError("그림이 있는데 image_dir가 없다")
        owner["n"] += 1
        ext, data = bins[rid]
        name = f"그림_{owner['label']}_{owner['n']}.png"
        Path(image_dir).mkdir(parents=True, exist_ok=True)
        (Path(image_dir) / name).write_bytes(as_png(data, ext))
        return picture_line(pic, name)

    def relabel(label: str) -> None:
        owner.update(label=label, n=0)

    return picture, relabel


def reverse_body(paras: list, heads: set[int], underlined: set[str], *,
                 bins: dict[str, tuple[str, bytes]] | None = None, image_dir: Path | None = None,
                 mono: set[str] = frozenset(), skip_prefix: str | None = None,
                 boxes: dict | None = None, pages: list[int | None] | None = None) -> list[str]:
    """본문 문단(관리박스·꼬리 박스 뺀 것) → md 줄. heads = 자동번호 머리 문단의 index(paras 기준).
    mono = 고정폭 charPr — 이어진 고정폭 문단은 ``` 코드 블록 하나로. skip_prefix(킷 leftover_prefix)를 품은
    문단은 서식 안내 줄이라 건너뛴다. 모르는 구조는 ReverseStop — 문항 번호·쪽 어림(pages, paras 기준)·문단을 붙인다."""
    picture, relabel = _saver(bins or {}, image_dir)
    out: list[str] = []
    cur: _Question | None = None
    set_rng: tuple[int, int] | None = None
    k = 0
    code: list[str] = []

    def flush_code() -> None:
        nonlocal code
        if not code:
            return
        if cur is not None:
            cur.add_block("코드", code)
        elif set_rng is not None:
            out.extend([""] + _block_md("코드", code))
        else:
            raise ValueError("문항 앞에 코드 블록이 있다")
        code = []

    def step(i: int, el) -> None:
        nonlocal cur, set_rng, k
        where = f"문단 {i}"
        if i not in heads and is_code(el, mono):
            code.append(code_text(el))
            return
        flush_code()
        t = paragraph_text(el, underlined)
        if i in heads:
            if cur is not None:
                out.extend(cur.finish())
            k += 1
            if set_rng and k > set_rng[1]:
                set_rng = None
            relabel(f"{k:02d}")
            cur = _Question(k, t, member=set_rng is not None)
            t = ""  # 머리 글은 이미 썼다 — 머리 문단 안의 표·그림만 아래에서
        elif (m := _세트.match(t)) and not _top_tables(el):
            if cur is not None:
                out.extend(cur.finish())
                cur = None
            set_rng = (int(m.group(1)), int(m.group(2)))
            relabel(f"세트{m.group(1)}")
            out.append(f"## {m.group(1)}~{m.group(2)}. 세트")
            t = t[m.end():].strip()
            if t:
                out.append(t)
            return
        if skip_prefix and skip_prefix in t:
            return
        blocks = [classify_table(tb, underlined, boxes=boxes, picture=picture, mono=mono) for tb in _top_tables(el)]
        blocks += [("그림", [picture(pic)]) for pic in _pics(el)]
        if cur is None:
            if set_rng is None:
                if t or blocks:
                    raise ValueError(f"{where}: 문항 앞에 내용이 있다 {t[:20]!r}")
                return
            for kind, lines in blocks:  # 세트 지문
                out.extend([""] + _block_md(kind, lines))
            if t:
                out.append(t)
            return
        for kind, lines in blocks:
            cur.add_block(kind, lines)
        if t:
            cur.add_text(t, f"{k}번 {where}")

    def stop(e: ValueError, i: int | None) -> ReverseStop:
        el = paras[i] if i is not None else None
        snippet = "" if el is None else re.sub(r"\s+", " ", "".join("".join(t.itertext()) for t in el.iter(q("hp", "t")))).strip()[:20]
        page = None if not pages else pages[i if i is not None else -1]
        return ReverseStop(str(e), question=k or None, page=page, paragraph=i, snippet=snippet)

    for i, el in enumerate(paras):
        try:
            step(i, el)
        except ReverseStop:
            raise
        except ValueError as e:
            raise stop(e, i) from e
    try:
        flush_code()
        if cur is not None:
            out.extend(cur.finish())
    except ReverseStop:
        raise
    except ValueError as e:
        raise stop(e, None) from e
    return out


@dataclass(frozen=True)
class FormProfile:
    """역변환이 양식에서 알아야 하는 것 — 학교 킷이 있으면 kit_profile이 짓는다. 킷 없는 양식은 일반 규칙 프로필이
    같은 틀로 짓는다(이슈 #8)."""

    name: str
    tail_marker: str | None             # 꼬리 박스를 가리키는 글(None이면 용지 기준 고정 표로 찾는다)
    skip_prefix: str | None             # 이 글을 품은 문단은 서식 안내 줄 — 건너뛴다
    boxes: dict | None                  # 〈보기〉·자료 박스 모양(None이면 박스를 가리지 않고 격자표로)
    required: tuple[str, ...]           # 원고 머리 필수 키
    front: Callable[[HwpxDocument], dict[str, str | None]]  # 문서에서 읽은 머리 값(못 읽으면 None)


def kit_profile(kit: Kit) -> FormProfile:
    return FormProfile(kit.name, kit.tailbox["match_text"], kit.leftover_prefix, kit.boxes,
                       tuple(kit.front_matter["required"]), lambda doc: kit_front(doc, kit))


def _columns(doc: HwpxDocument) -> int:
    c = next(doc.sections[0].element.iter(q("hp", "colPr")), None)
    return int(c.get("colCount") or 1) if c is not None else 1


def reverse(src: Path | Source, kit: Kit | FormProfile, *, image_dir: Path | None = None,
            front: dict[str, str] | None = None) -> str:
    """원안지(.hwp·.hwpx 경로 또는 열어 둔 Source) → md v2 전문. 머리 값은 누름틀에서 읽고 front(`--front`)가 이긴다.
    그림은 image_dir에 PNG로. 모르는 구조·읽지 못한 필수 머리 값은 ReverseStop."""
    profile = kit if isinstance(kit, FormProfile) else kit_profile(kit)
    if not isinstance(src, Source):
        with tempfile.TemporaryDirectory() as tmp:  # .hwp 변환 사본 자리 — 그림을 다 꺼낸 뒤 지운다
            return reverse(open_source(Path(src), Path(tmp)), profile, image_dir=image_dir, front=front)
    doc = src.doc
    ps = [p.element for p in doc.sections[0].paragraphs]
    heads = question_heads(doc)
    if not heads:
        raise ReverseStop("문항 머리(자동번호 문단 또는 글자 번호 `N.`)를 찾지 못했다 — 원안지가 아닌가?")
    tail = _tail_index(doc, profile.tail_marker)
    pages = page_guess(ps, _columns(doc))
    # 보존 구간(서술형·논술형 등 — 아직 조판하지 않는다): 다시 조판한 문서는 책갈피로, 원안지는 머리 글로 찾는다
    spans = preserve.ranges(doc)
    keep = spans[0][0] if spans else preserve.find_start(ps, heads[0] + 1, tail)
    end = tail if keep is None else keep
    body = reverse_body(ps[1:end], {i - 1 for i in heads if i < end}, underlined_char_prs(doc),
                        bins=_bin_items(src.hwpx), image_dir=image_dir, mono=mono_char_prs(doc),
                        skip_prefix=profile.skip_prefix, boxes=profile.boxes, pages=pages[1:end])
    if keep is not None:
        body += _preserved(src, ps, keep, tail, image_dir, pages[keep])
    head = resolve_front(profile.front(doc), front or {}, profile.required)
    md = "\n".join(head + body).rstrip() + "\n"
    _check_md(md, len(head))
    return md


def _check_md(md: str, head_lines: int) -> None:
    """되돌린 원고가 원고 문법에 맞는지 — 아니면 그 줄이 든 문항 번호를 대고 멈춘다(조판 단계까지 가서 줄 번호로 알게 두지 않는다)."""
    from .scan import scan_markdown

    errs = scan_markdown(md).errors
    if not errs:
        return
    lines = md.splitlines()
    e = errs[0]
    number = next((m.group(1) for ln in reversed(lines[:e.line_no]) if (m := re.match(r"^##+\s+(\d+)\.", ln))), None)
    raise ReverseStop(f"되돌린 원고가 원고 문법에 맞지 않는다(원고 {e.line_no}줄): {e.reason}",
                      question=int(number) if number else None, snippet=e.text.strip()[:20])


def _preserved(src: Source, ps: list, start: int, end: int, image_dir: Path | None, page: int | None) -> list[str]:
    """보존 구간 [start, end) → `보존_01.hwpx`(image_dir) + 원고 줄(`## 보존` · :::보존 · 미리보기)."""
    if image_dir is None:
        raise ReverseStop("보존 구간(서술형·논술형 등)이 있는데 그 파일을 둘 자리(image_dir)가 없다", page=page, paragraph=start)
    name = "보존_01.hwpx"
    preserve.write_region(src.hwpx, start, end, Path(image_dir) / name)
    lines = [re.sub(r"^\s*(```|:::)+", "", x) for x in preserve.preview(ps[start:end])]  # 미리보기가 원고 문법을 깨지 않게
    return ["", "## 보존", f':::보존 src="{name}"', *[x for x in lines if x.strip()], ":::"]


def _given(pairs: list[str]) -> dict[str, str]:
    out = {}
    for x in pairs:
        if "=" not in x:
            raise SystemExit(f"--front 값은 키=값이다: {x!r}")
        k, v = x.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .kit import load_kit
    from .lint import errors, lint
    from .scan import scan_markdown

    ap = argparse.ArgumentParser(description="원안지(.hwp·.hwpx) → md v2 (그림은 md 옆에 PNG로). 끝 코드: 0 · 1 원고 문법 오류 · 2 멈춤")
    ap.add_argument("원안지", help=".hwp 또는 .hwpx")
    ap.add_argument("--kit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--front", nargs="*", default=[], metavar="키=값", help="문서에서 읽지 못한 머리 값(예: 학년=3 과목=기하)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    kit = load_kit(Path(a.kit))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = open_source(Path(a.원안지), Path(tmp))
            md = reverse(src, kit, image_dir=out.parent, front=_given(a.front))
    except (ReverseStop, SourceError) as e:
        print(f"역변환 멈춤 — {e}")
        return 2
    out.write_text(md, encoding="utf-8")
    for n in src.notes:
        print(f"알림: {n}")
    s = scan_markdown(md)
    vs = lint(md, md_dir=out.parent, rules=kit.rules)
    n_err = len(errors(vs))
    print(f"wrote {out} — 문항 {len(s.questions)} · 배점 합 {sum(x.points or 0 for x in s.questions):.1f}"
          f" · lint 오류 {n_err} · 경고 {len(vs) - n_err}")
    if s.errors:
        print(f"scan 오류 {len(s.errors)}개 — 역변환 md가 원고 문법에 맞지 않는다:")
        for e in s.errors[:5]:
            print(f"  L{e.line_no} {e.reason}: {e.text[:40]!r}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
