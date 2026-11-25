"""스타일 기반 킷(style_based · 선택 역할 스타일) — 양식이 자리마다 스타일을 정해 둔 학교(11-23 owner).

학교 킷 없이 합성 킷(kits/synthetic)으로 돈다. 합성 서식에는 지문·세트 지시문 같은 이름의 스타일이 없어, 남는 스타일
(본문·캡션·개요 N)을 선택 역할에 이어 붙여 '그 자리에 그 스타일이 들어가는가'만 본다.
"""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from exam_kit.compose import compose
from exam_kit.kit import load_kit, style_ids
from exam_kit.onboard import suggest_style_roles
from exam_kit.prepare import prepare_document
from exam_kit.scan import scan_markdown
from exam_kit.slots import fill_slots

_합성 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
_픽스처 = Path(__file__).resolve().parent / "fixtures"
_선택 = {"passage": "본문", "set_head": "캡션", "box_anchor": "개요 1", "figure": "개요 2", "box_prose": "자료안"}


def _원고() -> str:
    md = (_픽스처 / "견본_전유형.md").read_text(encoding="utf-8")
    # 세트 지시문 뒤에 지문 두 문단, 첫 〈보기〉 맨 앞에 항목 기호 없는 제시문 한 줄
    세트 = "## 7~8. 세트\n다음 글을 읽고 물음에 답하시오.\n"
    보기 = ":::보기\n"
    assert 세트 in md and 보기 in md
    md = md.replace(세트, 세트 + "첫째 지문 문단이다.\n둘째 지문 문단이다.\n", 1)
    return md.replace(보기, 보기 + "다음은 논리 연산에 대한 설명이다.\n", 1)


def _조판(kit):
    scan = scan_markdown(_원고())
    assert not scan.errors
    doc, _ = prepare_document(_합성 / "synthetic_form.hwpx", kit)
    fill_slots(doc, kit, scan.front, question_count=len(scan.questions),
               total_points=sum(x.points for x in scan.questions))
    compose(doc, scan, kit, answer_key=False, image_root=_픽스처)
    names = {sid: name for name, (sid, _, _) in style_ids(doc).items()}
    return doc, names


def _문단(doc, names):
    """(스타일 이름, 글) — 최상위 문단."""
    return [(names.get(str(p.style_id_ref)), p.text) for p in doc.sections[0].paragraphs]


def test_선택_역할_스타일이_그_자리에_들어간다():
    kit = load_kit(_합성)
    kit = replace(kit, styles={**kit.styles, **_선택})
    doc, names = _조판(kit)
    ps = _문단(doc, names)
    head = next(i for i, (_, t) in enumerate(ps) if t.startswith("[7"))
    assert ps[head][0] == "캡션"  # 세트 지시문
    assert [s for s, _ in ps[head + 1:head + 3]] == ["본문", "본문"]  # 지문 두 문단
    holders = [s for p, (s, _) in zip(doc.sections[0].paragraphs, ps) if p.tables and s in ("개요 1", "개요 2")]
    assert "개요 1" in holders and "개요 2" in holders  # 박스를 담는 문단 · 박스 밖 격자표를 담는 문단
    # 〈보기〉 안: 제시문은 box_prose, ㄱ. 항목은 box_guide
    inner = [(names.get(str(x.style_id_ref)), x.text) for p in doc.sections[0].paragraphs for t in p.tables
             for g in t.iter_grid() if g.is_anchor for x in g.cell.paragraphs]
    assert ("자료안", "다음은 논리 연산에 대한 설명이다.") in inner
    assert any(s == "보기안" and t.startswith("ㄱ.") for s, t in inner)


def test_선택_역할이_없으면_바탕글로_짓는다():
    kit = load_kit(_합성)
    doc, names = _조판(kit)
    ps = _문단(doc, names)
    head = next(i for i, (_, t) in enumerate(ps) if t.startswith("[7"))
    assert ps[head][0] == "바탕글" and [s for s, _ in ps[head + 1:head + 3]] == ["바탕글", "바탕글"]


def _킷_복사(tmp_path, **more) -> Path:
    root = tmp_path / "킷"
    shutil.copytree(_합성, root)
    d = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    d.update(more)
    (root / "kit.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def test_style_based면_발문_모양과_보기_내어쓰기를_양식에서(tmp_path):
    kit = load_kit(_킷_복사(tmp_path, style_based=True))
    assert kit.style_based is True
    assert (kit.stem_align, kit.stem_word_break, kit.stem_condense) == (None, None, None)
    base = load_kit(_합성)
    assert base.style_based is False and base.stem_align == "LEFT"


def test_style_based는_참거짓만(tmp_path):
    with pytest.raises(ValueError, match="style_based"):
        load_kit(_킷_복사(tmp_path, style_based="예"))


def test_style_based면_보기_항목_내어쓰기는_양식_보기_스타일():
    kit = replace(load_kit(_합성), style_based=True)
    doc, names = _조판(kit)
    hd = doc.parts.headers[0]
    sid = {v: k for k, v in names.items()}["보기안"]
    form_pid = next(pid for name, (s, pid, _) in style_ids(doc).items() if name == "보기안")
    want = hd.paragraph_property(form_pid).margin.intent
    items = [x for p in doc.sections[0].paragraphs for t in p.tables for g in t.iter_grid() if g.is_anchor for x in g.cell.paragraphs
             if str(x.style_id_ref) == sid and x.text.startswith("ㄱ.")]
    assert items and all(hd.paragraph_property(x.para_pr_id_ref).margin.intent == want for x in items)


def test_등록은_양식_스타일_이름으로_선택_역할을_제안한다():
    names = ["바탕글", "문두", "세트문항지시문", "국어 영어 지문", "보기/박스위치", "표/그림 가운데 정렬",
             "박스 안 제시문", "보기제시문", "5행답항"]
    assert suggest_style_roles(names) == {"passage": "국어 영어 지문", "set_head": "세트문항지시문",
                                          "box_anchor": "보기/박스위치", "figure": "표/그림 가운데 정렬",
                                          "box_prose": "박스 안 제시문"}
    assert suggest_style_roles(["바탕글", "문항", "5행답항"]) == {}


def test_번호만_텍스트_층인_서식은_글_없는_줄을_머리로_보지_않는다():
    """Windows 한컴 PDF(본문 Type3)에서 줄 첫머리 '있다.' 같은 짧은 덩어리를 `N.`으로 잘못 보던 것(11-23 실측: 머리 11 ≠ 8)."""
    import pymupdf

    from exam_kit.geometry import Line, is_head

    점 = [pymupdf.Rect(0, 0, 5, 10), pymupdf.Rect(5.5, 7, 7, 9)]  # 글자 하나 + 마침표 크기 글리프 = 모양으로는 머리
    assert is_head(Line(1, 1, 100, 0, tuple(점)))                      # 옛 길(곡선 번호 서식)
    assert not is_head(Line(1, 1, 100, 0, tuple(점), "", True))        # 번호가 텍스트 층인 서식: 글 없으면 머리 아님
    assert is_head(Line(1, 1, 100, 0, tuple(점), "3.", True))


def test_세트_지문이_단을_넘어_흐른_단은_분할이_아니다(monkeypatch):
    """긴 지문(국어)은 단을 넘어 공백 없이 이어진다(11-23 owner) — 세트 머리가 앞 단에서 시작했고 그 세트 첫 문항 머리가
    이 단이거나 뒤에 있으면 지문 흐름 단이다. 그 뒤 단(문항이 나뉜 단)은 여전히 분할이다."""
    from exam_kit import layout
    from exam_kit.geometry import ColumnLayout, Extent, PageLayout

    # 문항 1(단독) · 문항 2~3 세트(머리 2쪽 1단에서 시작, 지문이 2쪽 2단·3쪽 1단으로 흘러 3쪽 1단에 2번 머리)
    monkeypatch.setattr(layout, "group_starts", lambda doc: [0, 3, 9])
    monkeypatch.setattr(layout, "question_heads", lambda doc: [0, 7, 9])
    ext = [Extent(((2, 1, 60.0, 200.0),)),
           Extent(((2, 1, 220.0, 900.0), (2, 2, 60.0, 900.0), (3, 1, 60.0, 500.0))),
           Extent(((3, 1, 520.0, 900.0), (3, 2, 60.0, 120.0)))]
    monkeypatch.setattr(layout, "group_extents", lambda pdf, kit, set_first: ext)

    def col(p, c, heads):
        return ColumnLayout(p, c, 60.0, 900.0, tuple(heads), bool(heads))

    lay = [PageLayout(1, (col(1, 1, []), col(1, 2, [])), None),
           PageLayout(2, (col(2, 1, [60.0]), col(2, 2, [])), None),
           PageLayout(3, (col(3, 1, [400.0, 520.0]), col(3, 2, [])), None)]
    assert layout.flow_columns(Path("x.pdf"), None, None, lay) == {(2, 2), (3, 1)}


def test_지문_문단은_보호_묶음_밖이고_묶음_첫_문단은_세트_머리다():
    """긴 지문이 앞 단을 비우고 통째로 다음 단으로 밀리지 않게(11-23 owner) — 지문 문단은 keepWithNext·keepLines를 끄고
    외톨이줄 보호만 켠다. group_starts는 지문을 건너 세트 머리를 묶음 첫 문단으로 본다(분할 해소는 문항 머리에 나눔)."""
    from exam_kit.layout import flows_into, group_starts
    from exam_kit.verify import question_heads

    kit = load_kit(_합성)
    kit = replace(kit, styles={**kit.styles, **_선택})
    doc, names = _조판(kit)
    ps = list(doc.sections[0].paragraphs)
    hd = doc.parts.headers[0]
    body = [i for i, p in enumerate(ps) if names.get(str(p.style_id_ref)) == "본문"]
    assert len(body) == 2
    for i in body:
        bs = hd.paragraph_property(ps[i].para_pr_id_ref).break_setting
        assert (bs.keep_with_next, bs.keep_lines, bs.widow_orphan) == (False, False, True)
    head = body[0] - 1
    assert names.get(str(ps[head].style_id_ref)) == "캡션"  # 세트 머리
    assert hd.paragraph_property(ps[head].para_pr_id_ref).break_setting.keep_with_next
    starts, heads = group_starts(doc), question_heads(doc)
    k = next(k for k, h in enumerate(heads) if h > body[-1])  # 세트 첫 문항
    assert starts[k] == head and flows_into(doc, starts[k], heads[k])
    assert not flows_into(doc, starts[0], heads[0])
