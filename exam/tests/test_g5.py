"""킷 선택 키 box_fit·code_style과 원고 줄 규칙 W025·E030 — 합성 킷만(학교 킷 없이 돈다).

첫 등록 학교의 2학기 2차 지필(G5, owner 10-26)에서 정한 것을 엔진으로 옮겼다: 박스·본문 격자표를 단 폭으로(G5-1), 코드 줄
번호·주석 회색 + 번호 뒤 세로줄(G5-2), 코드 줄 넘침 알림(G5-3), 짧은 md 표 구분행(G5-4), 코드 안 역슬래시(G5-5),
md 표 열 수(G5-6), 단 폭 본문 박스와 꼬리 박스 가르기(G5-7)."""

import dataclasses
from pathlib import Path

import pymupdf
from exam_kit import q
from exam_kit.compose import _구분행, compose
from exam_kit.geometry import boxes, column_lefts, tail_box_rect, tail_box_top
from exam_kit.kit import load_kit
from exam_kit.lint import lint
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
합성 발문이다. 옳은 것만을 〈보기〉에서 있는 대로 고른 것은?

:::보기
ㄱ. 합성 항목이다.
ㄴ. 합성 항목이다.
:::

① ㄱ
*② ㄴ
③ ㄱ, ㄴ
④ 없음
⑤ 모두

## 2. [2.0점]
합성 코드를 보고 옳은 것은?

:::자료
```
    # 합성 주석
01  a = 1  # 끝 주석
02  b = f(a,
          2)
```
:::

| 열 | 값 |
|:-:|:-:|
| 가 | 1 |

```
출력 0
```

① 가
*② 나
③ 다
④ 라
⑤ 마
"""


def _kit(**kw):
    return dataclasses.replace(load_kit(킷), **kw)


def _조판(kit, md=머리 + 본문):
    s = scan_markdown(md, kit.front_matter)
    assert s.errors == ()
    doc, _ = prepare_document(서식, kit)
    fill_slots(doc, kit, s.front, question_count=len(s.questions), total_points=sum(x.points for x in s.questions))
    res = compose(doc, s, kit, answer_key=False, image_root=킷)
    return doc, res


def _표_폭(doc) -> list[int]:
    return [int(t.find(q("hp", "sz")).get("width")) for t in doc.sections[0].element.iter(q("hp", "tbl"))
            if t.find(q("hp", "pos")).get("treatAsChar") == "1"]


def test_G5_1_박스와_격자표는_단_폭():
    kit = _kit(box_fit="column")
    doc, _ = _조판(kit)
    assert set(_표_폭(doc)) == {kit.columns["width"]}  # 〈보기〉·자료 박스·본문 격자표 모두
    doc0, _ = _조판(_kit())  # 기본(sample)은 견본 폭 그대로 — 합성 견본의 본문 표는 단보다 좁다
    assert kit.columns["body_table_width"] in _표_폭(doc0)


def test_G5_2_코드_줄_번호와_주석은_회색_세로줄():
    doc, _ = _조판(_kit(code_style="gutter"))
    color = {c.get("id"): c.get("textColor") for c in doc.oxml.headers[0].element.iter(q("hh", "charPr"))}

    def runs(p):
        return [("".join(r.itertext()), color[r.get("charPrIDRef")]) for r in p.iter(q("hp", "run"))]

    ps = {"".join(p.itertext()): p for p in doc.sections[0].element.iter(q("hp", "p"))}
    grey = "#666666"
    r1 = runs(ps["01 │ a = 1  # 끝 주석"])
    assert r1[0] == ("01 ", grey) and r1[1] == ("│ ", grey) and r1[-1] == ("# 끝 주석", grey)
    assert r1[2][0] == "a = 1  " and r1[2][1] != grey
    assert runs(ps["   │ # 합성 주석"])[-1] == ("# 합성 주석", grey)
    assert "   │       2)" in ps  # 번호 없는 이음 줄도 세로줄 자리
    assert [t for t, _ in runs(ps["출력 0"])] == ["출력 0"]  # 번호 줄이 없는 블록은 그대로


def test_G5_3_코드_줄_넘침_알림():
    md = 머리.replace("만점: 4", "만점: 2") + ("\n## 1. [2.0점]\n합성 코드를 보고 옳은 것은?\n\n:::자료\n```\n01  " + "a" * 70
                                         + "\n02  b = 1\n```\n:::\n\n① 가\n*② 나\n③ 다\n④ 라\n⑤ 마\n")
    _, res = _조판(_kit(code_style="gutter"), md)
    notes = [n for n in res.notes if "코드" in n]
    assert len(notes) == 1 and "1째 줄 75칸" in notes[0]


def test_G5_4_짧은_구분행도_구분행():
    assert _구분행.match("|:-:|:-:|") and _구분행.match("|---|:-:|") and _구분행.match("| - | - |")
    assert not _구분행.match("| 1 | 2 |")


def _q(body: str) -> str:
    return 머리.replace("만점: 4", "만점: 2") + f"\n## 1. [2.0점]\n합성 발문이다. 옳은 것은?\n\n{body}\n① 가\n*② 나\n③ 다\n④ 라\n⑤ 마\n"


def test_G5_5_코드_역슬래시는_W025():
    codes = lambda md: [v.code for v in lint(md)]  # noqa: E731
    assert "W025" in codes(_q(":::자료\n```\n01  x = \\\n02      1\n```\n:::\n"))
    assert "W025" not in codes(_q("역슬래시 \\ 는 코드 밖이면 괜찮다\n"))


def test_G5_6_md_표_8열부터_E030():
    def tbl(n):
        return (":::자료\n| " + " | ".join("가나다라마바사아자"[:n]) + " |\n|" + "---|" * n + "\n| "
                + " | ".join("123456789"[:n]) + " |\n:::\n")
    assert "E030" in [v.code for v in lint(_q(tbl(9)))]
    assert "E030" not in [v.code for v in lint(_q(tbl(7)))]


def _쪽(kit):
    doc = pymupdf.open()
    return doc, doc.new_page(width=kit.page["width"] / 100, height=kit.page["height"] / 100)


def _테두리(page, x0, y0, x1, y1):
    for a, b in (((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))):
        page.draw_line(a, b, color=(0, 0, 0), width=0.36)


def test_G5_1_박스_판정_기본_폭이_단_폭(tmp_path):
    kit = _kit(box_fit="column")
    doc, page = _쪽(kit)
    cl, w = column_lefts(kit)[0], kit.columns["width"] / 100
    page.draw_line((cl, 200), (cl, 260), width=0.36)
    page.draw_line((cl + w, 200), (cl + w, 260), width=0.36)
    page.draw_rect(pymupdf.Rect(cl + 10, 220, cl + 19, 229), color=None, fill=(0, 0, 0))
    doc.save(str(tmp_path / "c.pdf"))
    [b] = boxes(tmp_path / "c.pdf", kit)
    assert (round(b.top), b.kind) == (200, "박스")


def test_G5_7_단_폭_본문_박스와_꼬리_박스를_가른다():
    """본문 박스가 꼬리 박스와 같은 폭(단 폭)이어도 높이가 꼬리 박스인 무리를 고르고, 꼬리 박스 없는 쪽의 단 폭 본문
    박스는 꼬리로 잡지 않는다 — 잡으면 measure가 그 안 글자를 빼 단 높이를 낮게 세고 간격 나눔이 넘친다."""
    kit = _kit(box_fit="column")
    kit = dataclasses.replace(kit, tailbox={**kit.tailbox, "width": kit.columns["width"]})  # 같은 폭이 되는 학교 상황
    x0, w = column_lefts(kit)[-1], kit.columns["width"] / 100
    top, h = tail_box_top(kit), kit.tailbox["height"] / 100
    _, page = _쪽(kit)
    _테두리(page, x0, top - 140, x0 + w, top - 60)  # 같은 단 아래 절반의 단 폭 본문 박스
    _테두리(page, x0, top, x0 + w, top + h)          # 꼬리 박스
    r = tail_box_rect(page, kit)
    assert r is not None and abs(r.y0 - top) < 1 and abs(r.height - h) < 1
    _, page = _쪽(kit)
    _테두리(page, x0, top - 140, x0 + w, top - 60)
    assert tail_box_rect(page, kit) is None
