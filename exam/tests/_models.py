"""시험이 XML로 지은 문단·개체를 문서에 넣고 python-hwpx 모델 객체(Paragraph·Table·Picture·Equation)로 돌려준다.

역변환(exam_kit.reverse)은 요소가 아니라 모델 객체를 받는다. 시험은 지금처럼 작은 XML 조각으로 경우를 짓고, 이 도우미로
새 문서의 구역에 넣어 모델 객체로 건넨다(문서 밖에 떨어진 요소는 안쪽 문단 걷기가 받지 않는다).
"""

from __future__ import annotations

from hwpx import HwpxDocument
from hwpx.model import Paragraph
from lxml import etree as ET

from exam_kit import HP


def paragraphs(elements) -> list[Paragraph]:
    """hp:p 요소들을 새 문서 구역 0 끝에 차례로 붙이고 그 문단 객체들."""
    section = HwpxDocument.new().sections[0]
    out = []
    for el in elements:
        section.element.append(el)
        out.append(Paragraph(el, section))
    return out


def paragraph(element) -> Paragraph:
    """hp:p 요소 하나 → 문단 객체."""
    return paragraphs([element])[0]


def _holder(obj_element) -> Paragraph:
    p = ET.fromstring(f'<hp:p xmlns:hp="{HP}" paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"/></hp:p>')
    p[0].append(obj_element)
    return paragraph(p)


def table(element):
    """hp:tbl 요소 → 표 객체(문단 run 안에 넣는다)."""
    return _holder(element).tables[0]


def obj(element):
    """hp:pic·hp:equation·도형 요소 → 개체 객체(문단 run 안에 넣는다)."""
    return _holder(element).objects[0]
