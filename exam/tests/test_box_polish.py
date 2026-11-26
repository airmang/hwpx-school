"""킷 선택 키 typeset.box_hanging·code_gray·box_name, boxes.<종류>.from, md 표 칸 `<br>` — 합성 킷만(학교 킷 없이 돈다).

첫 등록 학교 2학기 2차 지필 검토 의견(11-26)에서 정한 것: 자료·〈조건〉 박스의 (가)·※·∘ 줄은 둘째 줄을 기호 뒤 글자 자리에
(내어쓰기), 코드 주석·줄 번호는 인쇄에서 흐리지 않게 검정, 박스가 여럿이면 박스 아래 가운데 이름, 양식에 견본이 없는
〈조건〉은 〈보기〉 견본을 빌려 제목만 바꾸기, 표 머리 칸 안 줄바꿈."""

import dataclasses
import re
from pathlib import Path

from exam_kit import q
from exam_kit.compose import _br, compose
from exam_kit.kit import load_kit
from exam_kit.prepare import prepare_document
from exam_kit.scan import scan_markdown
from exam_kit.slots import fill_slots

킷 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"

머리 = """---
양식: synthetic
학년도: 2026
학년: 1
학기: 1
차: 1
과목: 정보
시행: 4월 21일 (화) 1교시
출제교사: 김출제
만점: 4
---
"""
본문 = """
## 1. [2.0점]
합성 발문이다. 〈조건〉에 맞는 것은?

:::자료 이름="합성 자료"
(가) 합성 첫 줄이다.
※ 합성 참고 줄이다.
기호 없는 합성 줄이다.
| (가)<br>합성 머리 | 값 |
|:-:|:-:|
| 가 | 1 |
:::

:::조건
(가) 합성 조건이다.
:::

① 가
*② 나
③ 다
④ 라
⑤ 마

## 2. [2.0점]
합성 코드를 보고 옳은 것은?

:::자료
```
01  a = 1  # 끝 주석
```
:::

① 가
*② 나
③ 다
④ 라
⑤ 마
"""


def _kit(typeset=None, boxes=None):
    k = load_kit(킷)
    return dataclasses.replace(k, typeset={**k.typeset, **(typeset or {})}, boxes={**k.boxes, **(boxes or {})})


def _조판(kit):
    s = scan_markdown(머리 + 본문, kit.front_matter)
    assert s.errors == ()
    doc, _ = prepare_document(서식, kit)
    fill_slots(doc, kit, s.front, question_count=len(s.questions), total_points=sum(x.points for x in s.questions))
    compose(doc, s, kit, answer_key=False, image_root=킷)
    return doc


def _문단(doc) -> dict:
    return {"".join(p.itertext()): p for p in doc.sections[0].element.iter(q("hp", "p"))}


def _intent(doc, p) -> int:
    pp = next(x for x in doc.oxml.headers[0].element.iter(q("hh", "paraPr")) if x.get("id") == p.get("paraPrIDRef"))
    return int(pp.find(f".//{q('hp', 'case')}//{q('hc', 'intent')}").get("value"))


def test_box_hanging_기호_줄은_기호_폭만큼_내어쓴다():
    doc = _조판(_kit({"box_hanging": True}))
    ps = _문단(doc)
    가, 주 = _intent(doc, ps["(가) 합성 첫 줄이다."]), _intent(doc, ps["※ 합성 참고 줄이다."])
    assert 가 < 주 < 0  # (가)␣가 ※␣보다 넓다
    assert _intent(doc, ps["기호 없는 합성 줄이다."]) >= 0  # 기호 없는 줄은 스타일 그대로
    assert _intent(doc, ps["(가) 합성 조건이다."]) < 0  # 〈조건〉도 기호 폭(글자 크기는 그 박스 스타일)


def test_box_hanging_없으면_그대로():
    doc = _조판(_kit())
    ps = _문단(doc)
    assert _intent(doc, ps["(가) 합성 첫 줄이다."]) >= 0


def test_code_gray_검정():
    doc = _조판(_kit({"code_gray": "#000000"}))
    color = {c.get("id"): c.get("textColor") for c in doc.oxml.headers[0].element.iter(q("hh", "charPr"))}
    p = next(p for t, p in _문단(doc).items() if "끝 주석" in t)
    runs = [("".join(r.itertext()), color[r.get("charPrIDRef")]) for r in p.iter(q("hp", "run"))]
    assert runs and all(c == "#000000" for _, c in runs)


def test_box_name_박스_아래_가운데():
    doc = _조판(_kit({"box_name": "<{name}>"}))
    top = [("".join(p.itertext()), p) for p in doc.sections[0].element.findall(q("hp", "p"))]  # 최상위 문단
    i = next(k for k, (t, _) in enumerate(top) if t == "<합성 자료>")
    assert top[i - 1][1].find(f".//{q('hp', 'tbl')}") is not None  # 박스 문단 바로 다음
    pp = next(x for x in doc.oxml.headers[0].element.iter(q("hh", "paraPr")) if x.get("id") == top[i][1].get("paraPrIDRef"))
    assert pp.find(q("hh", "align")).get("horizontal") == "CENTER"


def test_boxes_from_다른_견본을_빌려_제목만_바꾼다():
    k = load_kit(킷)
    빌림 = {**k.boxes["보기"], "from": "보기", "title": "< 빌 림 >", "title_match": "빌 림"}
    doc = _조판(_kit(boxes={"조건": 빌림}))
    texts = "".join(doc.sections[0].element.itertext())
    assert "< 빌 림 >" in texts and "합성 조건이다." in texts


def test_표_칸_br은_칸_안_줄바꿈():
    assert _br("(가)<br>합성 머리") == ["(가)", "합성 머리"]
    assert _br("한 줄") == ["한 줄"]
    doc = _조판(_kit())
    cell = next(p for p in doc.sections[0].element.iter(q("hp", "p")) if "합성 머리" in "".join(p.itertext())
                and p.find(f".//{q('hp', 'tbl')}") is None)
    assert cell.find(f".//{q('hp', 'lineBreak')}") is not None
    assert not re.search(r"<br", "".join(cell.itertext()))
