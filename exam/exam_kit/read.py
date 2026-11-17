"""문서 읽기 도우미 — python-hwpx 공개 API(모델 객체)로 문단·표의 글과 "빈 문단" 판정을 읽는다.

역변환(reverse)·검사(verify)·양식 손질(prepare)·보존 구간(preserve)·일반 규칙(generic)이 같이 쓴다. 옛 코드는 요소 아래
``itertext``로 읽었다. 그 뜻(글리프 요소는 글이 아니다, 칸 사이는 붙인다)을 ``nested_text``로 재현한다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

#: ``nested_text``가 글자로 내는 글리프(탭·줄 바꿈·묶음 빈칸·고정폭 빈칸·하이픈)와 토막 사이 줄 바꿈 — 옛 itertext처럼
#: 글로 세지 않는다.
GLYPHS = re.compile("[\t\n 　­]")


def nested_raw(paragraphs) -> str:
    """문단들의 글 — 문단 안 표 칸·글상자·캡션·각주·메모 글까지 문서 차례로(``nested_text``), 글리프는 빼고 공백은 그대로."""
    return "".join(GLYPHS.sub("", p.nested_text()) for p in paragraphs)


def flat(paragraphs) -> str:
    """``nested_raw``를 공백 하나로 접은 것."""
    return re.sub(r"\s+", " ", nested_raw(paragraphs)).strip()


def table_paragraphs(table) -> list:
    """표의 문단 — 캡션, 그리고 행·칸 차례(칸 안 표·글상자는 칸 문단의 nested_text가 읽는다)."""
    out = list(table.caption.paragraphs) if table.caption is not None else []
    return out + [p for row in table.rows for cell in row.cells for p in cell.paragraphs]


def table_text(table) -> str:
    """표의 글(``table_paragraphs``의 ``nested_raw``)."""
    return nested_raw(table_paragraphs(table))


def script(obj) -> str:
    """수식 개체의 스크립트 — 문서 전체 걷기(iter_objects)가 준 개체는 그 문단의 수식 객체(paragraph.equations)로 읽는다."""
    if hasattr(obj, "script"):
        return obj.script
    return next((eq.script for eq in obj.paragraph.equations if eq == obj), "") if obj.paragraph is not None else ""


def has_text(paragraphs) -> bool:
    """문단들 아래에 글이 있는가 — 글자(안쪽 표 칸·글상자·캡션·각주까지), 개체 설명(대체 글)·수식 스크립트, 누름틀
    매개변수·찾아보기 표시·덧말 글·입력 상자, 모르는 요소까지 센다(옛 판정이 요소 아래 모든 글을 셌다). 글리프는 글이 아니다."""
    if nested_raw(paragraphs).strip():
        return True
    for p in paragraphs:
        for place in p.iter_objects():
            o = place.object
            if hasattr(o, "description") and o.description.strip():
                return True
            if place.kind == "equation" and script(o).strip():
                return True
        for run in p.runs:
            for item in run.content:
                if item.kind in ("field_begin", "index_mark") or (item.kind == "unknown" and item.container != "t") \
                        or item.name == "edit":
                    # 모르는 요소(컨트롤 안에 잘못 든 글·표 등)·입력 상자는 내용으로 본다 — 빈 문단으로 지나치지 않는다
                    return True
                if item.kind == "ruby" and (item.object.text.strip() or item.object.ruby_text.strip()):
                    return True
    return False


def is_blank(paragraph) -> bool:
    """빈 문단 — 글이 없고(``has_text``) 안에 표·그림이 없다. 옛 판정(요소 아래 글 노드가 비고 표·그림 요소가 없다)과 같다."""
    return not has_text([paragraph]) and not any(True for _ in paragraph.iter_objects(kinds=("table", "picture")))


def t_text(paragraphs) -> str:
    """문단들의 글 조각(글 요소 안의 글)을 문서 차례로 — 안쪽 표 캡션·칸, 도형 안, 개체 캡션, 각주·메모까지.

    옛 ``"".join(t.itertext() …)``과 같은 글: 글 안에 글자로 적힌 빈칸·탭(묶음 빈칸 문자 등)은 그대로 두고, 탭·줄 바꿈·
    빈칸 요소(글리프)는 글로 세지 않는다(``nested_raw``는 글자로 적힌 것까지 지운다)."""
    out: list[str] = []

    def own(p) -> None:
        for run in p.runs:
            for item in run.content:
                if item.container == "t" and item.kind in ("text", "unknown"):
                    out.append(item.text)
                    continue
                o = item.object
                if o is None:
                    continue
                if item.kind == "table":
                    for q in table_paragraphs(o):
                        own(q)
                elif item.kind == "shape":
                    for place in o.iter_paragraphs():  # 도형 안 모든 문단(안쪽 표 칸까지) — 문단마다 제 글만
                        own_flat(place.paragraph)
                elif item.kind in ("footnote", "endnote", "field_begin") and hasattr(o, "paragraphs"):
                    for q in o.paragraphs:
                        own(q)
                elif getattr(o, "caption", None) is not None:
                    for q in o.caption.paragraphs:
                        own(q)

    def own_flat(p) -> None:
        out.extend(item.text for run in p.runs for item in run.content
                   if item.container == "t" and item.kind in ("text", "unknown"))

    for p in paragraphs:
        own(p)
    return "".join(out)


def tree(p) -> Iterator:
    """문단과 그 안의 문단(표 캡션·칸, 도형 안, 그림 등 개체 캡션, 각주·미주, 메모 누름틀)을 문서 차례로."""
    yield p
    for run in p.runs:
        for item in run.content:
            o = item.object
            if o is None:
                continue
            if item.kind == "table":
                for q in table_paragraphs(o):
                    yield from tree(q)
            elif item.kind == "shape":
                yield from (place.paragraph for place in o.iter_paragraphs())
            elif item.kind in ("footnote", "endnote", "field_begin") and hasattr(o, "paragraphs"):
                for q in o.paragraphs:
                    yield from tree(q)
            elif getattr(o, "caption", None) is not None:
                for q in o.caption.paragraphs:
                    yield from tree(q)
