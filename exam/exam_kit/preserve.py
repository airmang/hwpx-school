"""보존 블록 — 아직 조판하지 않는 구간(서술형·논술형 등)을 원본 모양 그대로 떼어 두었다가 그 자리에 다시 심는다.

- 역변환: 원안지 본문에서 보존 구간(첫 서술형·논술형 머리 ~ 꼬리 박스 앞)을 `보존_NN.hwpx`로 떼어 원고 옆에 둔다. 원고에는
  `## 보존` + `:::보존 src="보존_NN.hwpx"`와 읽기용 미리보기 줄만 — 그 글은 원고에서 고치지 않는다(한/글에서 고친다).
- 조판: python-hwpx 공개 API `hwpx.tools.document_merge.insert_document`가 그 파일의 문단을 넣는다 — 글자·문단·스타일·
  테두리·그림 id를 대상 문서에 맞춰 새로 매긴다(원본 모양 그대로). 넣은 구간의 앞뒤에 책갈피(`보존_NN_시작`·`보존_NN_끝`)를
  달아, 문서만 보고도 보존 구간을 안다 — 문항 머리 찾기(verify.question_heads)가 이 구간을 빼고, 다시 역변환하면 같은
  구간이 다시 보존 블록이 된다.
"""

from __future__ import annotations

import re
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.tools.document_merge import insert_document

from . import q

# 보존 구간의 시작 — 문단 글이 이렇게 시작하면 서술형·논술형 구간이다(【서술형 1】·[논술형]·서답형 1. 등).
START_RE = re.compile(r"^\s*[\[【〔<(■□◆◇▶]?\s*(?:서\s*[·ㆍ]?\s*논술형|서술형|논술형|서답형)")
_책갈피 = re.compile(r"^(보존_\d+)_(시작|끝)$")


def _plain(el) -> str:
    """문단 자신의 글(hp:t만 — 수식 스크립트·설명 글은 넣지 않는다), 공백 하나로."""
    return re.sub(r"\s+", " ", "".join("".join(t.itertext()) for t in el.iter(q("hp", "t")))).strip()


def ranges(doc: HwpxDocument) -> list[tuple[int, int]]:
    """책갈피로 표시한 보존 구간들 — (첫 문단, 끝 문단) 번호(구역 0의 최상위 문단 기준, 끝 포함)."""
    marks: dict[str, dict[str, int]] = {}
    for i, p in enumerate(doc.sections[0].paragraphs):
        for bm in p.element.iter(q("hp", "bookmark")):
            m = _책갈피.match(bm.get("name") or "")
            if m:
                marks.setdefault(m.group(1), {})[m.group(2)] = i
    return sorted((v["시작"], v["끝"]) for v in marks.values() if "시작" in v and "끝" in v)


def inside(i: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= i <= b for a, b in spans)


def find_start(paras: list, first: int, end: int) -> int | None:
    """보존 구간의 시작 문단 번호(first ≤ i < end) — 책갈피가 없는 원안지는 서술형·논술형 머리 글(START_RE)로 찾는다."""
    return next((i for i in range(first, end) if START_RE.match(_plain(paras[i]))), None)


def preview(paras: list) -> list[str]:
    """읽기용 미리보기 — 구간 최상위 문단마다 글 한 줄(빈 문단은 뺀다). 조판은 이 줄을 쓰지 않는다."""
    return [t for p in paras if (t := _plain(p))]


def write_region(src: Path, start: int, end: int, out: Path) -> None:
    """src(hwpx)의 최상위 문단 [start, end)만 남긴 hwpx를 out에 쓴다. 문단 0은 구역 설정(secPr)만 남긴다 — 넣을 때
    insert_document가 secPr·단 설정을 떼고, 머리말·꼬리말 같은 다른 컨트롤은 여기서 미리 뺀다(대상 문서에 겹치지 않게)."""
    doc = HwpxDocument.open(str(src))
    sec = doc.sections[0]
    ps = list(sec.paragraphs)
    for run in ps[0].element.findall(q("hp", "run")):
        for ch in list(run):
            if ch.tag != q("hp", "secPr"):
                run.remove(ch)
    for i in range(len(ps) - 1, 0, -1):
        if not start <= i < end:
            sec.remove_paragraph(ps[i])
    sec.mark_dirty()
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(str(out))


def _empty(p_el) -> bool:
    """글도 개체(표·그림·수식·도형)도 없는 문단 — 구역 설정만 남긴 문단 0이 넣은 뒤 이렇게 남는다."""
    objects = ("tbl", "pic", "equation", "rect", "ellipse", "line", "polygon", "curve", "arc", "container", "ole", "textart")
    return not _plain(p_el) and not any(p_el.find(f".//{q('hp', t)}") is not None for t in objects)


def _bookmark(p_el, name: str, *, first: bool) -> None:
    runs = p_el.findall(q("hp", "run"))
    if not runs:
        runs = [p_el.makeelement(q("hp", "run"), {"charPrIDRef": "0"})]
        p_el.insert(0, runs[0])
    ctrl = p_el.makeelement(q("hp", "ctrl"), {})
    ctrl.append(ctrl.makeelement(q("hp", "bookmark"), {"name": name}))
    if first:
        runs[0].insert(0, ctrl)
    else:
        runs[-1].append(ctrl)


def insert_region(doc: HwpxDocument, path: Path, after: int, name: str) -> int:
    """path(보존 구간 hwpx)의 문단을 doc 구역 0의 after 문단 뒤에 넣고 앞뒤에 책갈피를 단다 — 넣은 마지막 문단 번호.
    path의 문단 0(구역 설정만 남은 빈 문단)은 넣은 뒤 지운다."""
    if not Path(path).is_file():
        raise ValueError(f"보존 블록 파일이 없다: {path}")
    sec = doc.sections[0]
    before = len(sec.paragraphs)
    insert_document(doc, str(path), after_paragraph_index=after)
    n = len(sec.paragraphs) - before
    ps = list(sec.paragraphs)
    head = ps[after + 1]
    if n > 1 and _empty(head.element):
        sec.remove_paragraph(head)
        n -= 1
    ps = list(sec.paragraphs)
    _bookmark(ps[after + 1].element, f"{name}_시작", first=True)
    _bookmark(ps[after + n].element, f"{name}_끝", first=False)
    sec.mark_dirty()
    return after + n
