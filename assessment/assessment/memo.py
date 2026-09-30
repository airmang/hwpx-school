"""정답 메모 — 한컴이 쓰는 인라인 fieldBegin(type=MEMO) 모양을 그대로 만든다.
python-hwpx 의 memogroup API 는 이 모양을 만들지 않아 직접 짓는다(실한컴에서 메모 표시를 확인했다)."""

from __future__ import annotations

from lxml import etree

from assessment.kit import Kit
from assessment.ns import HP

_SUBLIST = {"id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK", "vertAlign": "TOP",
            "linkListIDRef": "0", "linkListNextIDRef": "0", "textWidth": "0", "textHeight": "0",
            "hasTextRef": "0", "hasNumRef": "0"}

_PARAMS = (
    ("integerParam", "Prop", "0"),
    ("stringParam", "ID", "memo{number}"),
    ("integerParam", "Number", "{number}"),
    ("stringParam", "Author", "assessment"),
    ("stringParam", "MemoShapeIDRef", "65535"),
)


def _q(tag: str) -> str:
    return f"{{{HP}}}{tag}"


def append_memo_run(run_element: etree._Element, anchor: str, lines: tuple[str, ...], *, number: int, kit: Kit) -> None:
    begin_id, field_id = str(1_000_000_000 + number), str(600_000_000 + number)
    fb = etree.SubElement(etree.SubElement(run_element, _q("ctrl")), _q("fieldBegin"), {
        "id": begin_id, "type": "MEMO", "name": "", "editable": "1", "dirty": "1",
        "zorder": str(number), "fieldid": field_id, "metaTag": "",
    })
    params = etree.SubElement(fb, _q("parameters"), {"cnt": str(len(_PARAMS)), "name": ""})
    for kind, name, value in _PARAMS:
        etree.SubElement(params, _q(kind), {"name": name}).text = value.format(number=number)
    sub = etree.SubElement(fb, _q("subList"), _SUBLIST)
    for line in lines:
        p = etree.SubElement(sub, _q("p"), {
            "id": "2147483648", "paraPrIDRef": str(kit.para_pr["memo"]), "styleIDRef": str(kit.memo_style),
            "pageBreak": "0", "columnBreak": "0", "merged": "0",
        })
        etree.SubElement(etree.SubElement(p, _q("run"), {"charPrIDRef": str(kit.char_pr["body"])}), _q("t")).text = line
    etree.SubElement(run_element, _q("t")).text = anchor
    etree.SubElement(etree.SubElement(run_element, _q("ctrl")), _q("fieldEnd"), {"beginIDRef": begin_id, "fieldid": field_id})
