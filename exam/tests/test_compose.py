from pathlib import Path

import pytest

from _helpers import 텍스트, 최상위_문단
from _kits import kit_dir
from exam_kit import q
from exam_kit.compose import Samples, compose, harvest_samples
from exam_kit.kit import load_kit, style_ids
from exam_kit.prepare import finalize_form, prepare_document
from exam_kit.scan import scan_markdown
from exam_kit.slots import fill_slots
from exam_kit.verify import errors, extract_answers, question_heads, verify_document

킷_디렉터리 = kit_dir()
픽스처 = Path(__file__).resolve().parent / "fixtures"
기대_정답 = {"1": "②", "2": "④", "3": "①", "4": "⑤", "5": "③"}

_M = load_kit(kit_dir()).metrics


def _조판(양식_hwpx, md: str, *, answer_key: bool, doctor=None):
    kit = load_kit(킷_디렉터리)
    scan = scan_markdown(md)
    doc, prepared = prepare_document(양식_hwpx, kit)
    fill_slots(doc, kit, scan.front, question_count=len(scan.questions),
               total_points=sum(x.points for x in scan.questions))
    prepared = prepared.refresh(doc)
    if doctor is not None:  # 조판 직전 문서를 손보는 테스트용
        doctor(doc)
    res = compose(doc, scan, kit, answer_key=answer_key, image_root=픽스처)
    return kit, doc, prepared, res


@pytest.fixture(params=[False, True], ids=["문항지", "답표시"])
def 조판(request, 양식_hwpx):
    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8")
    return (request.param, *_조판(양식_hwpx, md, answer_key=request.param))


def _헤더(doc):
    return doc.headers[0].element


def _para_pr(doc, pid):
    return _헤더(doc).find(f".//{q('hh', 'paraPr')}[@id='{pid}']")


def _char_pr(doc, cid):
    return _헤더(doc).find(f".//{q('hh', 'charPr')}[@id='{cid}']")


def _prev(pp, branch):
    return int(pp.find(f".//{q('hp', branch)}/{q('hh', 'margin')}/{q('hc', 'prev')}").get("value"))


def _break(pp):
    b = pp.find(q("hh", "breakSetting"))
    return b.get("keepWithNext"), b.get("keepLines")


def test_머리는_자동번호_스타일이고_번호_글자가_없다(조판):
    _, kit, doc, _, _ = 조판
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    assert len(heads) == 5
    ids = style_ids(doc)
    for i in heads:
        el = ps[i].element
        assert el.get("styleIDRef") == ids["문항자동번호넣기"][0]
        t = 텍스트(el)
        assert not t.lstrip()[:1].isdigit(), t  # (a) '1.' 텍스트 머리 0
    assert 텍스트(ps[heads[0]].element) == "합성 문항 첫째 발문이다. 다음 중 가장 적절한 것은? [3.5점]"
    # 발문 두 줄이 한 문단으로(공백 하나로 잇는다)
    assert 텍스트(ps[heads[2]].element).startswith("합성 문항 셋째 발문이다. 발문 두 줄이")
    assert 텍스트(ps[heads[1]].element).endswith("옳지 않은 것은? [4.0점]")


def test_밑줄_run(조판):
    _, kit, doc, _, _ = 조판
    ps = 최상위_문단(doc)
    head = ps[question_heads(doc)[1]].element
    runs = head.findall(q("hp", "run"))
    ul = [r for r in runs if "".join(r.itertext()) == "않은"]
    assert len(ul) == 1
    cp = _char_pr(doc, ul[0].get("charPrIDRef"))
    assert cp.find(q("hh", "underline")).get("type") == "BOTTOM"
    body_cp = style_ids(doc)["문항자동번호넣기"][2]
    assert _char_pr(doc, runs[0].get("charPrIDRef")).get("id") == body_cp
    # 밑줄 말고는 본문 글자와 같다(크기·글꼴·장평)
    base = _char_pr(doc, body_cp)
    assert cp.get("height") == base.get("height")
    assert cp.find(q("hh", "fontRef")).attrib == base.find(q("hh", "fontRef")).attrib


def test_답지_5행_한_줄에_하나(조판):
    _, kit, doc, _, res = 조판
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    ids = style_ids(doc)
    for k, h in enumerate(heads):
        choices = ps[h + 1:h + 6]
        assert [p.element.get("styleIDRef") for p in choices] == [ids["5행답항"][0]] * 5
        assert [텍스트(p.element)[:2] for p in choices] == [f"{m} " for m in "①②③④⑤"]
    assert 텍스트(ps[heads[0] + 2].element) == "② 합성 답지 나"
    assert res.layouts == {str(k): "5행" for k in range(1, 6)}
    assert res.answers == 기대_정답


def test_문단_보호와_문항_간격(조판):
    _, kit, doc, _, _ = 조판
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    tail = len(ps) - 1
    bounds = heads + [tail]
    for k, h in enumerate(heads):
        grp = ps[h:bounds[k + 1]]
        flags = [_break(_para_pr(doc, p.element.get("paraPrIDRef"))) for p in grp]
        assert flags[:-1] == [("1", "1")] * (len(grp) - 1)
        assert flags[-1] == ("0", "1")
        pp = _para_pr(doc, ps[h].element.get("paraPrIDRef"))
        gap = 0 if k == 0 else kit.question_gap
        assert (_prev(pp, "case"), _prev(pp, "default")) == (gap, 2 * gap)
        assert pp.find(q("hh", "heading")).get("type") == "NUMBER"
    # 양식 원래 paraPr(24·34)는 건드리지 않는다
    assert _break(_para_pr(doc, "24")) == ("0", "0") and _prev(_para_pr(doc, "24"), "case") == 0
    assert _break(_para_pr(doc, "34")) == ("0", "0")


def test_샘플_구역이_사라진다(조판):
    _, kit, doc, _, _ = 조판
    text = 텍스트(doc.sections[0].element)
    assert not [w for w in kit.forbidden_text if w in text]  # (b)
    assert kit.boxes["보기"]["title"] not in text
    ps = 최상위_문단(doc)
    assert not [t for p in ps[1:-1] for t in p.element.iter(q("hp", "tbl"))]  # 견본 표 잔존 0
    assert len(ps) == 1 + 5 * 6 + 1


def test_형광펜_판본(조판):
    answer_key, kit, doc, _, _ = 조판
    pens = list(doc.sections[0].element.iter(q("hp", "markpenBegin")))
    assert len(pens) == (5 if answer_key else 0)  # (c)
    if answer_key:
        assert {p.get("color").upper() for p in pens} == {"#FFFF00"}
        assert extract_answers(doc) == 기대_정답


def test_검사_통과와_마무리(조판):
    answer_key, kit, doc, prepared, _ = 조판
    fs = verify_document(doc, kit, expect_answers=기대_정답 if answer_key else None, answer_key=answer_key, draft=True)
    assert errors(fs) == []  # (d) 빈 문단(M7a)·양식 밖 스타일(M7b)·금지 문구·형광펜
    finalize_form(doc, kit, prepared)  # (e)
    assert "저작권" in 텍스트(최상위_문단(doc)[-1].element)


def test_견본_채집(양식_hwpx):
    kit = load_kit(킷_디렉터리)
    doc, _ = prepare_document(양식_hwpx, kit)
    s = harvest_samples(doc, kit)
    assert isinstance(s, Samples)
    assert (s.보기_tbl.get("rowCnt"), s.보기_tbl.get("colCnt")) == ("4", "5") and kit.boxes["보기"]["title"] in 텍스트(s.보기_tbl)
    assert (s.자료_tbl.get("rowCnt"), s.자료_tbl.get("colCnt")) == ("3", "3")
    assert s.보기_tbl.getparent() is None and s.자료_tbl.getparent() is None  # 사본(문서와 분리)
    cp = _char_pr(doc, s.세트_charpr)
    assert cp.get("height") == "1300" and cp.find(q("hh", "bold")) is not None
    assert s.세트_charpr == "12"


세트_md = """---
양식: 예시-원안지
학년도: 2026
학년: 2
학기: 2
차: 2
과목: 인공지능 기초
과목코드: 16
시행: 12.14.(월) 3교시
대상: 2학년 6반~10반
인쇄: 30매 * 4묶음
출제교사: 홍길동
만점: 10
---

## 1. [3.0점]
합성 단독 발문이다. 옳은 것은?

*① 가
② 나
③ 다
④ 라
⑤ 마

## 2~3. 세트
다음 합성 글을 읽고 물음에 답하시오.
공통 지문 둘째 줄이다.

### 2. [3.0점]
세트 첫 문항 발문이다. 옳은 것은?

① 가
*② 나
③ 다
④ 라
⑤ 마

### 3. [4.0점]
세트 둘째 문항 발문이다. 옳은 것은?

① 가
② 나
*③ 다
④ 라
⑤ 마
"""


def test_세트_머리와_보호_묶음(양식_hwpx):
    kit, doc, _, res = _조판(양식_hwpx, 세트_md, answer_key=False)
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    assert len(heads) == 3
    # 1번(머리+답지 줄) 뒤에 세트 머리, 지문 둘째 줄, 2번 머리
    set_head = ps[heads[1] - 2].element
    assert 텍스트(set_head) == "[2∼3] 다음 합성 글을 읽고 물음에 답하시오."
    ids = style_ids(doc)
    assert set_head.get("styleIDRef") == ids["바탕글"][0]
    runs = set_head.findall(q("hp", "run"))
    assert "".join(runs[0].itertext()) == "[2∼3]" and runs[0].get("charPrIDRef") == "12"
    assert runs[1].get("charPrIDRef") == ids["바탕글"][2]
    assert 텍스트(ps[heads[1] - 1].element) == "공통 지문 둘째 줄이다."
    assert 텍스트(ps[heads[1] - 3].element).startswith("④ 라")  # 1번 마지막 답지 줄(2행 둘째 줄) 바로 뒤가 세트 머리
    # 세트 머리 ~ 2번 마지막 답지까지 한 묶음, 2번 마지막 답지에서 끊는다
    grp = ps[heads[1] - 2:heads[2]]
    flags = [_break(_para_pr(doc, p.element.get("paraPrIDRef"))) for p in grp]
    assert flags == [("1", "1")] * (len(grp) - 1) + [("0", "1")]
    # 문항 간격: 세트 머리가 간격을 받고, 세트 첫 문항 머리도 문항 머리로서 받는다
    sp = _para_pr(doc, set_head.get("paraPrIDRef"))
    assert _prev(sp, "case") == kit.question_gap
    assert res.answers == {"1": "①", "2": "②", "3": "③"}


def test_견본_전유형이_모두_조판된다(양식_hwpx):
    md = (픽스처 / "견본_전유형.md").read_text(encoding="utf-8")
    kit, doc, prepared, res = _조판(양식_hwpx, md, answer_key=True)
    fs = verify_document(doc, kit, expect_answers=res.answers, answer_key=True, draft=True)
    assert errors(fs) == []
    assert len(res.answers) == len(question_heads(doc))
    finalize_form(doc, kit, prepared)


def test_스캔_오류와_번호_어긋남은_거부(양식_hwpx):
    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8").replace("## 3. [4.5점]", "## 7. [4.5점]")
    with pytest.raises(ValueError, match="번호"):
        _조판(양식_hwpx, md, answer_key=False)


def test_렌더_번호_글리프와_분할(양식_hwpx, 오라클, tmp_path):
    from exam_kit.geometry import column_lines, first_chunk_width, splits
    from exam_kit.render import render

    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8")
    kit, doc, prepared, _ = _조판(양식_hwpx, md, answer_key=True)
    finalize_form(doc, kit, prepared)
    out = tmp_path / "기본_5문항.hwpx"
    doc.save_to_path(str(out))
    r = render(out, tmp_path / "r", oracle=오라클)
    lines = column_lines(r.pdf, kit)
    # 머리 줄 = 단 왼끝에서 시작하는 줄(답지는 왼여백 1000 ≈ 10pt, 발문 이음 줄은 번호 폭만큼 들어간다)
    heads = [ln for ln in lines if ln.dx < 2.0]
    assert len(heads) == 5  # (a) 번호가 문항당 한 번
    assert all(first_chunk_width(ln) < 25 for ln in heads), [round(first_chunk_width(ln), 1) for ln in heads]
    assert splits(r.pdf, kit) == []  # (f)
    # 1번 머리가 관리박스 바로 아래(제출본 실측 y≈303pt — 줄 캐시가 남으면 ≈326pt)
    assert heads[0].page == 1 and heads[0].col == 1 and heads[0].y0 < 312


# ---- Task 23: 〈보기〉·자료 박스 -------------------------------------------------

박스_줄 = {"1": 2, "2": 4, "3": 1, "4": 3}  # 박스_4문항.md 문항별 내용 줄 수(항목 접힘 포함)
박스_종류 = {"1": "보기", "2": "보기", "3": "자료", "4": "자료"}


@pytest.fixture(scope="module")
def 박스(양식_hwpx):
    md = (픽스처 / "박스_4문항.md").read_text(encoding="utf-8")
    return _조판(양식_hwpx, md, answer_key=True)


def _표(p_el):
    from exam_kit.prepare import _top_tables
    return _top_tables(p_el)


def _셀(tbl, col, row):
    for tc in tbl.iter(q("hp", "tc")):
        a = tc.find(q("hp", "cellAddr"))
        if (a.get("colAddr"), a.get("rowAddr")) == (str(col), str(row)):
            return tc
    raise KeyError((col, row))


def _구조(tbl):
    out = []
    for tc in tbl.iter(q("hp", "tc")):
        a, s = tc.find(q("hp", "cellAddr")), tc.find(q("hp", "cellSpan"))
        out.append((a.get("colAddr"), a.get("rowAddr"), s.get("colSpan"), s.get("rowSpan"), tc.get("borderFillIDRef"),
                    tc.find(q("hp", "cellSz")).get("width")))
    return tbl.get("rowCnt"), tbl.get("colCnt"), out


def _높이(tc):
    return int(tc.find(q("hp", "cellSz")).get("height"))


def test_박스는_견본과_같은_셀_구조로_발문_다음_문단에_앉는다(박스, 양식_hwpx):
    kit, doc, _, res = 박스
    견본 = harvest_samples(prepare_document(양식_hwpx, kit)[0], kit)
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    ids = style_ids(doc)
    tbl_ids = [t.get("id") for t in doc.sections[0].element.iter(q("hp", "tbl"))]
    assert len(tbl_ids) == len(set(tbl_ids))  # 복제한 표도 id가 겹치지 않는다
    assert not {견본.보기_tbl.get("id"), 견본.자료_tbl.get("id")} & set(tbl_ids)  # 견본 id를 그대로 쓰지 않는다
    for k, h in enumerate(heads, 1):
        host = ps[h + 1].element
        assert host.get("styleIDRef") == ids["바탕글"][0]
        assert "".join(x.text or "" for x in host.iterfind(f"{q('hp', 'run')}/{q('hp', 't')}")) == ""  # 표 말고 글자 없음
        [tbl] = _표(host)
        src = 견본.보기_tbl if 박스_종류[str(k)] == "보기" else 견본.자료_tbl
        assert _구조(tbl) == _구조(src)
        pos = tbl.find(q("hp", "pos"))
        assert pos.get("treatAsChar") == "1"
        assert ps[h + 2].element.get("styleIDRef") == ids[f"{res.layouts[str(k)]}답항"][0]  # 박스 뒤에 곧바로 그 문항의 답지
    assert res.answers == {"1": "②", "2": "④", "3": "③", "4": "①"}


def test_박스_내용_문단(박스):
    kit, doc, _, _ = 박스
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    ids = style_ids(doc)
    보기1 = _셀(_표(ps[heads[0] + 1].element)[0], 1, 2)
    paras = 보기1.findall(f"{q('hp', 'subList')}/{q('hp', 'p')}")
    # 앞 공백 없이 ㄱ을 x = 0에, 내어쓰기 −1950(1학기 제출본 교사 항목의 중앙값) — 파생 paraPr, 양식 스타일은 그대로
    assert [텍스트(p) for p in paras] == ["ㄱ. 합성 보기 첫째 항목이다.", "ㄴ. 합성 보기 둘째 항목이다."]
    [(sid, pid)] = {(p.get("styleIDRef"), p.get("paraPrIDRef")) for p in paras}
    assert sid == ids["(보기)박스안내용"][0] and pid != ids["(보기)박스안내용"][1]
    def 여백(pp):
        return [{c.tag.split("}")[1]: int(c.get("value")) for c in b.find(q("hh", "margin"))}
                for b in pp.find(q("hp", "switch"))]
    got, base = 여백(_para_pr(doc, pid)), 여백(_para_pr(doc, ids["(보기)박스안내용"][1]))
    assert base[0]["intent"] == -2500 and got[0] == base[0] | {"intent": -1950}
    assert got[1] == {k: 2 * v for k, v in got[0].items()}  # default 분기 = 2배(양식 규칙)
    assert all(p.find(q("hp", "linesegarray")) is None for p in paras)  # 줄 캐시 없음 — 한컴이 새로 잰다
    자료 = _셀(_표(ps[heads[3] + 1].element)[0], 1, 1)
    paras = 자료.findall(f"{q('hp', 'subList')}/{q('hp', 'p')}")
    assert len(paras) == 1 and 텍스트(paras[0]).startswith("합성 자료 문단이다.")
    assert (paras[0].get("styleIDRef"), paras[0].get("paraPrIDRef")) == ids["박스안내용"][:2]
    assert {r.get("charPrIDRef") for p in paras for r in p.findall(q("hp", "run"))} == {ids["박스안내용"][2]}


def test_박스_높이는_줄_수에_비례(박스):

    kit, doc, _, _ = 박스
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    for k, h in enumerate(heads, 1):
        tbl = _표(ps[h + 1].element)[0]
        n = 박스_줄[str(k)]
        if 박스_종류[str(k)] == "보기":
            row, rails, pitch = 2, (0, 4), _M.line_pitch[160]
        else:
            row, rails, pitch = 1, (0, 2), _M.line_pitch[150]
        want = max((n - 1) * pitch + _M.box_extra, kit.box_min_height)  # 양식 견본 내용 셀(6336) 밑으로는 안 간다
        assert _높이(_셀(tbl, 1, row)) == want, (k, n)
        assert [_높이(_셀(tbl, c, row)) for c in rails] == [want, want]
        rows = tbl.findall(q("hp", "tr"))
        합 = sum(max(_높이(tc) for tc in tr.findall(q("hp", "tc"))
                    if tc.find(q("hp", "cellSpan")).get("rowSpan") == "1") for tr in rows)
        assert int(tbl.find(q("hp", "sz")).get("height")) == 합


def test_줄_수_추정():
    from exam_kit.compose import estimate_lines

    assert estimate_lines("가" * 26, 28680, 26180, _M) == 1
    assert estimate_lines("가" * 27, 28680, 26180, _M) == 2  # 27 × 1067 > 28680
    # 한글은 낱말 안에서도 끊긴다(렌더 실측 `만/큼`) — 낱말 단위였다면 3줄
    assert estimate_lines("가가가가가 나나나나나나나나 다다다다다", 10670, 10670, _M) == 2
    # 로마자 낱말은 통째로 넘어간다 — 글자 단위였다면 1줄
    assert estimate_lines("가" * 8 + " abcd", 10670, 10670, _M) == 2
    # 둘째 줄부터 내어쓰기만큼 좁다
    assert estimate_lines("가" * 40, 28680, 26180, _M) == 2 and estimate_lines("가" * 51, 28680, 26180, _M) == 3


def test_박스_보호_묶음과_검사(박스):
    kit, doc, prepared, _ = 박스
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    for h in heads:
        pp = _para_pr(doc, ps[h + 1].element.get("paraPrIDRef"))
        assert _break(pp) == ("1", "1")  # 박스 문단도 문항 묶음 안
    fs = verify_document(doc, kit, expect_answers={"1": "②", "2": "④", "3": "③", "4": "①"}, answer_key=True, draft=True)
    assert errors(fs) == []


def test_간격_없는_문단은_여백을_건드리지_않는다(양식_hwpx, monkeypatch):
    from exam_kit.compose import _Composer

    kit = load_kit(킷_디렉터리)
    doc, _ = prepare_document(양식_hwpx, kit)
    c = _Composer(doc, kit, harvest_samples(doc, kit), answer_key=False)
    받은 = []
    원래 = c.header.ensure_paragraph_format

    def 엿봄(**kw):
        받은.append(kw.get("margins"))
        return 원래(**kw)

    monkeypatch.setattr(c.header, "ensure_paragraph_format", 엿봄)
    c.para_pr("choice5", keep=True, gap=False)
    c.para_pr("number", keep=True, gap=True)
    assert 받은 == [None, {"prev": kit.question_gap}]


def test_밑줄_자식이_없는_charPr는_거부(양식_hwpx):
    from exam_kit.compose import _Composer

    kit = load_kit(킷_디렉터리)
    doc, _ = prepare_document(양식_hwpx, kit)
    c = _Composer(doc, kit, harvest_samples(doc, kit), answer_key=False)
    cp = _char_pr(doc, "25")
    cp.remove(cp.find(q("hh", "underline")))
    with pytest.raises(ValueError, match="underline"):
        c.underline("25")


def test_렌더_박스_높이와_제목(양식_hwpx, 오라클, tmp_path):
    from exam_kit.geometry import LINE_PT, boxes, splits
    from exam_kit.render import RenderUnavailable, render

    md = (픽스처 / "박스_4문항.md").read_text(encoding="utf-8")
    kit, doc, prepared, _ = _조판(양식_hwpx, md, answer_key=False)
    finalize_form(doc, kit, prepared)
    out = tmp_path / "박스_4문항.hwpx"
    doc.save_to_path(str(out))
    try:
        r = render(out, tmp_path / "r", oracle=오라클)
    except RenderUnavailable:  # 다른 에이전트와 렌더가 겹칠 수 있다 — 한 번 더
        r = render(out, tmp_path / "r2", oracle=오라클)
    bs = [b for b in boxes(r.pdf, kit) if b.lines]
    assert [len(b.lines) for b in bs] == [박스_줄[k] for k in "1234"]  # 추정한 줄 수 = 한컴이 그린 줄 수
    assert [b.titled for b in bs] == [박스_종류[k] == "보기" for k in "1234"]  # `< 보 기 >`가 윗선에 걸친다

    for b, k in zip(bs, "1234"):
        pitch = _M.line_pitch[160 if 박스_종류[k] == "보기" else 150]
        if (len(b.lines) - 1) * pitch + _M.box_extra >= kit.box_min_height:  # 견본 최소 높이보다 큰 박스만
            assert b.bottom_gap < LINE_PT and b.top_gap < LINE_PT, b  # 마지막 줄 아래 빈 줄 없음
        assert abs(b.bottom_gap - b.top_gap) < 2.0, b             # 위아래 여백이 고르다(가운데 정렬 셀)
    둘째 = bs[1].lines
    assert 둘째[3][2] - 둘째[2][2] > 5.0  # 〈보기〉 ㄷ의 둘째 줄은 내어쓰기 자리에서 시작
    assert splits(r.pdf, kit) == []


def test_세트_자료_박스는_지문_다음_묶음_안(양식_hwpx):
    md = 세트_md.replace("공통 지문 둘째 줄이다.\n", "공통 지문 둘째 줄이다.\n\n:::자료\n세트 공통 자료 한 줄이다.\n:::\n")
    kit, doc, _, _ = _조판(양식_hwpx, md, answer_key=False)
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    host = ps[heads[1] - 1].element  # 세트 머리, 지문 둘째 줄, 그다음 자료, 2번 머리
    [tbl] = _표(host)
    assert (tbl.get("rowCnt"), tbl.get("colCnt")) == ("3", "3")
    assert 텍스트(_셀(tbl, 1, 1)) == "세트 공통 자료 한 줄이다."
    assert 텍스트(ps[heads[1] - 3].element).startswith("[2∼3]")
    assert _break(_para_pr(doc, host.get("paraPrIDRef"))) == ("1", "1")


# ---- Task 24: 격자표 · 그림 · 답항표 -------------------------------------------

@pytest.fixture(scope="module")
def 표그림(양식_hwpx):
    md = (픽스처 / "표그림_3문항.md").read_text(encoding="utf-8")
    return _조판(양식_hwpx, md, answer_key=True)


def _테두리(doc, bf_id) -> dict:
    bf = _헤더(doc).find(f".//{q('hh', 'borderFill')}[@id='{bf_id}']")
    return {s: (bf.find(q("hh", f"{s}Border")).get("type"), bf.find(q("hh", f"{s}Border")).get("width"))
            for s in ("left", "right", "top", "bottom")}


def _셀_문단(tc):
    return tc.findall(f"{q('hp', 'subList')}/{q('hp', 'p')}")


def _폭들(tbl, row=0):
    return [int(_셀(tbl, c, row).find(q("hp", "cellSz")).get("width")) for c in range(int(tbl.get("colCnt")))]


def _칸_여백(pp):
    """paraPr 두 분기(case·default)의 (left, right, intent)."""
    return [tuple(int(pp.find(f".//{q('hp', br)}/{q('hh', 'margin')}/{q('hc', k)}").get("value"))
                  for k in ("left", "right", "intent")) for br in ("case", "default")]


실선 = ("SOLID", "0.12 mm")
겹선 = ("DOUBLE_SLIM", "0.4 mm")


def _격자_검사(doc, tbl, texts, width):
    """md 표 → 격자표: 폭·열 폭·테두리(머리행 아래 / 첫 본문행 위 겹선)·가운데 정렬·바탕글 글자."""
    ids = style_ids(doc)
    rows, cols = len(texts), len(texts[0])
    assert (tbl.get("rowCnt"), tbl.get("colCnt")) == (str(rows), str(cols))
    assert int(tbl.find(q("hp", "sz")).get("width")) == width
    assert tbl.find(q("hp", "pos")).get("treatAsChar") == "1"
    폭 = _폭들(tbl)
    assert sum(폭) == width and min(폭) >= 4000
    for r in range(rows):
        assert _폭들(tbl, r) == 폭
        for c in range(cols):
            tc = _셀(tbl, c, r)
            [p] = _셀_문단(tc)
            assert 텍스트(p) == texts[r][c]
            assert p.get("styleIDRef") == ids["바탕글"][0]
            pp = _para_pr(doc, p.get("paraPrIDRef"))
            assert pp.find(q("hh", "align")).get("horizontal") == "CENTER"
            assert _칸_여백(pp) == [(0, 0, 0)] * 2
            assert {x.get("charPrIDRef") for x in p.findall(q("hp", "run"))} == {ids["바탕글"][2]}
            assert tc.find(q("hp", "subList")).get("vertAlign") == "CENTER"
            want = {"left": 실선, "right": 실선, "top": 겹선 if r == 1 else 실선, "bottom": 겹선 if r == 0 else 실선}
            assert _테두리(doc, tc.get("borderFillIDRef")) == want, (r, c)
    # 표 전체 높이 = 행 높이 합
    합 = sum(_높이(_셀(tbl, 0, r)) for r in range(rows))
    assert int(tbl.find(q("hp", "sz")).get("height")) == 합
    return 폭


def test_격자표(표그림):
    kit, doc, _, res = 표그림
    ps = 최상위_문단(doc)
    h = question_heads(doc)[0]
    host = ps[h + 1].element
    assert host.get("styleIDRef") == style_ids(doc)["바탕글"][0]
    [tbl] = _표(host)
    폭 = _격자_검사(doc, tbl, [["측정일", "관측 지점 수", "평균 온도", "다음날 비 예보 여부"],
                             ["14", "6", "23", "아니오"], ["27", "4", "18", "예"]], kit.columns["body_table_width"])
    assert 폭[3] == max(폭) and 폭[0] == min(폭)  # 글자 수 비례: `다음날 비 예보 여부`가 가장 넓다
    assert _break(_para_pr(doc, host.get("paraPrIDRef"))) == ("1", "1")  # 문항 묶음 안
    assert ps[h + 2].element.get("styleIDRef") == style_ids(doc)[f"{res.layouts['1']}답항"][0]


def test_열_폭():
    from exam_kit.compose import _글폭, column_widths  # noqa: F401

    assert column_widths([["가", "가나다라마바사아자차"]], 30000, 4000, m=_M) == [4000, 26000]  # 최소 폭 4000
    w = column_widths([["가나", "가나다라"], ["1", "2"]], 30000, 4000, m=_M)
    assert sum(w) == 30000 and w[1] == 2 * w[0]
    assert sum(column_widths([["a", "bb", "ccc"]], 30088, 4000, m=_M)) == 30088  # 반올림 나머지까지 정확히
    with pytest.raises(ValueError, match="열"):
        column_widths([["가"] * 8], 30088, 4000, m=_M)  # 8 × 4000 > 30088
    # 셀 여백까지 비례 몫에 넣으면 짧은 머리도 제 글자 폭 이상을 받는다(렌더에서 세 글자 머리가 접혔던 결함)
    row = ["측정일", "관측 지점 수", "평균 온도", "다음날 비 예보 여부"]
    w = column_widths([row], 30088, 4000, pad=1020, m=_M)
    assert all(wi >= _글폭(t, _M) + 1020 for wi, t in zip(w, row)), w


def test_그림은_회색조_사본이_가운데_문단에_앉는다(표그림, tmp_path):
    import io
    import zipfile

    from PIL import Image

    kit, doc, _, _ = 표그림
    ps = 최상위_문단(doc)
    h = question_heads(doc)[1]
    host = ps[h + 1].element
    assert host.get("styleIDRef") == style_ids(doc)["바탕글"][0]
    assert _para_pr(doc, host.get("paraPrIDRef")).find(q("hh", "align")).get("horizontal") == "CENTER"
    assert _break(_para_pr(doc, host.get("paraPrIDRef"))) == ("1", "1")
    [pic] = host.iter(q("hp", "pic"))
    assert pic.find(q("hp", "pos")).get("treatAsChar") == "1"
    sz = pic.find(q("hp", "sz"))
    w, hgt = int(sz.get("width")), int(sz.get("height"))
    assert w == round(6 * 72000 / 25.4)  # {width=6cm}
    src = Image.open(픽스처 / "그림.png")
    assert hgt == round(w * src.height / src.width)  # 원본 비율
    ref = pic.find(f".//{q('hc', 'img')}").get("binaryItemIDRef")
    out = tmp_path / "그림.hwpx"
    doc.save_to_path(str(out))
    with zipfile.ZipFile(out) as z:
        [name] = [n for n in z.namelist() if n.startswith("BinData/") and ref in n]
        img = Image.open(io.BytesIO(z.read(name)))
    assert img.mode == "L" and img.size == src.size  # 회색조(원안지 칼라 인쇄 금지)


def test_자료_안의_표(표그림):
    kit, doc, _, _ = 표그림
    ps = 최상위_문단(doc)
    h = question_heads(doc)[2]
    [box] = _표(ps[h + 1].element)
    assert (box.get("rowCnt"), box.get("colCnt")) == ("3", "3")
    content = _셀(box, 1, 1)
    paras = _셀_문단(content)
    assert 텍스트(paras[0]) == "두 합성 모델의 지표는 다음과 같다."
    [inner] = _표(paras[1])
    in_m = box.find(q("hp", "inMargin"))
    width = int(content.find(q("hp", "cellSz")).get("width")) - int(in_m.get("left")) - int(in_m.get("right"))
    _격자_검사(doc, inner, [["모델", "정밀도", "재현율"], ["A", "0.9", "0.5"], ["B", "0.6", "0.9"]], width)
    assert len(paras) == 2
    # 내용 셀 높이는 글 한 줄 + 표를 담는다(한글은 늘리기만 한다 — 넘치게 잡으면 아래가 빈다)
    assert _높이(content) >= _M.line_pitch[150] + int(inner.find(q("hp", "sz")).get("height"))
    assert _높이(content) <= _M.box_extra + _M.line_pitch[150] + int(inner.find(q("hp", "sz")).get("height")) + 1000


def test_답항표(표그림):

    kit, doc, _, res = 표그림
    ps = 최상위_문단(doc)
    ids = style_ids(doc)
    heads = question_heads(doc)
    h = heads[2]
    host = ps[h + 2].element  # 머리, 자료 박스, 답항표
    [tbl] = _표(host)
    assert (tbl.get("rowCnt"), tbl.get("colCnt")) == ("6", "4")
    assert _break(_para_pr(doc, host.get("paraPrIDRef")))[1] == "1"
    assert len(ps) - 1 == h + 3  # 답항표가 마지막 문단(꼬리 앞) — 5행 답지 문단은 없다
    폭 = _폭들(tbl)
    assert 폭[0] == _M.mark_col and max(폭[1:]) - min(폭[1:]) < len(폭)  # 균등(나머지만 끝 열에)
    # 답지 자리(5행답항 왼여백)에서 박스 오른끝까지
    assert sum(폭) == int(tbl.find(q("hp", "sz")).get("width")) == kit.columns["body_table_width"] - 1000
    assert host.get("styleIDRef") == ids["5행답항"][0]
    무테 = {s: ("NONE", _테두리(doc, tbl.get("borderFillIDRef"))[s][1]) for s in ("left", "right", "top", "bottom")}
    assert _테두리(doc, tbl.get("borderFillIDRef")) == 무테
    body_cp = ids["5행답항"][2]
    rows = [["", "ㄱ", "ㄴ", "ㄷ"], ["①", "정밀도", "재현율", "정확도"], ["②", "재현율", "정밀도", "정확도"],
            ["③", "정확도", "재현율", "정밀도"], ["④", "정밀도", "정확도", "재현율"], ["⑤", "재현율", "정확도", "정밀도"]]
    for r, row in enumerate(rows):
        for c, want in enumerate(row):
            tc = _셀(tbl, c, r)
            assert all(v[0] == "NONE" for v in _테두리(doc, tc.get("borderFillIDRef")).values())
            [p] = _셀_문단(tc)
            assert 텍스트(p) == want
            pp = _para_pr(doc, p.get("paraPrIDRef"))
            assert pp.find(q("hh", "align")).get("horizontal") == "CENTER"
            assert _칸_여백(pp) == [(0, 0, 0)] * 2  # 5행답항의 왼여백·내어쓰기를 물려받지 않는다
            cps = {x.get("charPrIDRef") for x in p.findall(q("hp", "run"))}
            if r == 0 and c > 0:  # 머리 기호는 밑줄
                [cp] = cps
                assert _char_pr(doc, cp).find(q("hh", "underline")).get("type") == "BOTTOM"
            else:
                assert cps == {body_cp}
    # 정답 형광펜은 첫 열 원문자에
    pens = list(tbl.iter(q("hp", "markpenBegin")))
    assert len(pens) == 1 and pens[0].tail == "③"
    assert pens[0].getparent() is _셀_문단(_셀(tbl, 0, 3))[0].find(f"{q('hp', 'run')}/{q('hp', 't')}")
    assert res.answers["3"] == "③" and res.layouts["3"] == "답항표"
    assert extract_answers(doc) == {"1": "②", "2": "④", "3": "③"}


def test_표그림_검사와_마무리(표그림, tmp_path):
    import zipfile

    kit, doc, prepared, res = 표그림
    fs = verify_document(doc, kit, expect_answers=res.answers, answer_key=True, draft=True)
    assert errors(fs) == []
    finalize_form(doc, kit, prepared)
    out = tmp_path / "표그림.hwpx"
    doc.save_to_path(str(out))
    with zipfile.ZipFile(out) as z:
        assert [n for n in z.namelist() if n.startswith("BinData/")]  # 문항 그림은 마무리 뒤에도 남는다


def test_답항표_문항지_판은_형광펜_없음(양식_hwpx):
    md = (픽스처 / "표그림_3문항.md").read_text(encoding="utf-8")
    _, doc, _, res = _조판(양식_hwpx, md, answer_key=False)
    assert not list(doc.sections[0].element.iter(q("hp", "markpenBegin")))
    assert res.answers == {"1": "②", "2": "④", "3": "③"}


def test_답항표_문항의_답항_덮어쓰기는_무시하고_알린다(양식_hwpx):
    md = (픽스처 / "표그림_3문항.md").read_text(encoding="utf-8").replace("## 3. [5.0점]", "## 3. [5.0점] {답항=2행}")
    _, _, _, res = _조판(양식_hwpx, md, answer_key=False)
    assert res.layouts["3"] == "답항표"
    assert [n for n in res.notes if n.startswith("3번") and "무시" in n]


def test_칸_문단에_칠할_원문자가_없으면_거부(양식_hwpx):
    from exam_kit.compose import _Composer

    kit = load_kit(킷_디렉터리)
    doc, _ = prepare_document(양식_hwpx, kit)
    c = _Composer(doc, kit, harvest_samples(doc, kit), answer_key=True)
    assert 텍스트(c._cell_p([("③", None)], "choice5", mark="③")) == "③"
    with pytest.raises(ValueError, match="형광펜"):
        c._cell_p([("정밀도", None)], "choice5", mark="③")


_객체 = ("tbl", "pic", "rect", "ellipse", "line", "container", "equation")


def test_새_객체_id는_모든_객체_id_위에서_발급(양식_hwpx):
    def 큰_id_도형(doc):  # 관리박스 문단에 id가 큰 도형 하나 — 표·그림이 아니어도 id 공간을 공유한다
        run = doc.sections[0].paragraphs[0].element.find(q("hp", "run"))
        ET_ = __import__("lxml.etree", fromlist=["SubElement"])
        ET_.SubElement(run, q("hp", "rect"), {"id": "2000000000", "zOrder": "500"})

    md = (픽스처 / "표그림_3문항.md").read_text(encoding="utf-8")
    _, doc, _, _ = _조판(양식_hwpx, md, answer_key=False, doctor=큰_id_도형)
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    new = [int(e.get("id")) for p in ps[heads[0]:-1] for e in p.element.iter(*(q("hp", t) for t in _객체))]
    old = [int(e.get("id")) for p in ps[:heads[0]] + ps[-1:] for e in p.element.iter(*(q("hp", t) for t in _객체))]
    assert len(new) == 5  # 격자표, 그림, 자료 박스와 그 안의 표, 답항표
    assert min(new) > max(old) >= 2000000000
    assert new == sorted(new) and len(set(new)) == len(new)  # 차례대로, 겹침 없음
    zs = [int(e.get("zOrder")) for p in ps[heads[0]:-1] for e in p.element.iter(*(q("hp", t) for t in _객체))]
    old_z = [int(e.get("zOrder")) for p in ps[:heads[0]] + ps[-1:] for e in p.element.iter(*(q("hp", t) for t in _객체))]
    assert max(old_z) == 500 and zs == list(range(501, 501 + len(zs)))  # zOrder도 차례로, 기존 개체 위


def test_양식_분기가_없으면_양식이_바뀌었다(양식_hwpx):
    from exam_kit.compose import _Composer

    kit = load_kit(킷_디렉터리)
    doc, _ = prepare_document(양식_hwpx, kit)
    c = _Composer(doc, kit, harvest_samples(doc, kit), answer_key=False)
    pp = _para_pr(doc, c.style["box"][1])
    sw = pp.find(q("hp", "switch"))
    pp.remove(sw)
    with pytest.raises(ValueError, match="양식이 바뀌었다"):
        c._widths("box", 28000)
    with pytest.raises(ValueError, match="양식이 바뀌었다"):
        c._line_pitch("box")


def _그림_md(줄: str) -> str:
    md = (픽스처 / "표그림_3문항.md").read_text(encoding="utf-8")
    return md.replace("![](그림.png){width=6cm}", 줄)


def test_그림_오류는_드러낸다(양식_hwpx):
    with pytest.raises(ValueError, match="단 폭"):
        _조판(양식_hwpx, _그림_md("![](그림.png){width=12cm}"), answer_key=False)
    with pytest.raises(ValueError, match="그림 폭"):
        _조판(양식_hwpx, _그림_md("![](그림.png)"), answer_key=False)
    with pytest.raises(ValueError, match="없는 그림"):
        _조판(양식_hwpx, _그림_md("![](없음.png){width=5cm}"), answer_key=False)
    kit = load_kit(킷_디렉터리)
    doc, _ = prepare_document(양식_hwpx, kit)
    with pytest.raises(ValueError, match="image_root"):
        compose(doc, scan_markdown(_그림_md("![](그림.png){width=5cm}")), kit, answer_key=False)


def test_자료_안의_그림(양식_hwpx):
    md = (픽스처 / "박스_4문항.md").read_text(encoding="utf-8").replace(
        "합성 자료 한 줄이다.", "합성 자료 한 줄이다.\n![](그림.png){width=5cm}")
    _, doc, _, _ = _조판(양식_hwpx, md, answer_key=False)
    ps = 최상위_문단(doc)
    [box] = _표(ps[question_heads(doc)[2] + 1].element)
    paras = _셀_문단(_셀(box, 1, 1))
    assert len(paras) == 2 and 텍스트(paras[0]) == "합성 자료 한 줄이다."
    [pic] = paras[1].iter(q("hp", "pic"))
    assert int(pic.find(q("hp", "sz")).get("width")) == round(5 * 72000 / 25.4)
    assert _para_pr(doc, paras[1].get("paraPrIDRef")).find(q("hh", "align")).get("horizontal") == "CENTER"


def test_보기_안의_표는_거부(양식_hwpx):
    md = (픽스처 / "박스_4문항.md").read_text(encoding="utf-8").replace(
        "ㄱ. 합성 보기 첫째 항목이다.", "| 가 | 나 |\n|---|---|\n| 1 | 2 |")
    with pytest.raises(ValueError, match="〈보기〉 안의 표"):
        _조판(양식_hwpx, md, answer_key=False)


def test_답항표_열_수가_머리와_다르면_거부(양식_hwpx):
    md = (픽스처 / "표그림_3문항.md").read_text(encoding="utf-8").replace("① 정밀도 | 재현율 | 정확도", "① 정밀도 | 재현율")
    with pytest.raises(ValueError, match="답항표"):
        _조판(양식_hwpx, md, answer_key=False)


def test_렌더_격자표_그림_답항표(양식_hwpx, 오라클, tmp_path):
    import pymupdf

    from exam_kit.geometry import LINE_PT, boxes, column_lefts, column_lines, splits
    from exam_kit.render import RenderUnavailable, render

    md = (픽스처 / "표그림_3문항.md").read_text(encoding="utf-8")
    kit, doc, prepared, _ = _조판(양식_hwpx, md, answer_key=False)
    finalize_form(doc, kit, prepared)
    out = tmp_path / "표그림_3문항.hwpx"
    doc.save_to_path(str(out))
    try:
        r = render(out, tmp_path / "r", oracle=오라클)
    except RenderUnavailable:  # 다른 에이전트와 렌더가 겹칠 수 있다 — 한 번 더
        r = render(out, tmp_path / "r2", oracle=오라클)
    assert splits(r.pdf, kit) == []
    lefts = column_lefts(kit)
    col_w = kit.columns["width"] / 100.0
    with pymupdf.open(str(r.pdf)) as pdf:
        page = pdf[0]
        # 그림: 6 cm 폭, 단 가운데
        [img] = [i for i in page.get_image_info() if i["width"] == 600]
        x0, _, x1, _ = img["bbox"]
        assert abs((x1 - x0) - 6 * 72 / 2.54) < 1.0
        assert abs((x0 + x1) / 2 - (lefts[0] + col_w / 2)) < 1.0
        # 격자표(1번 머리와 그림 사이): 머리행 아래 겹선 = 0.7pt 간격 가로선 두 줄. 한컴 PDF는 선을 칸마다 쪼갠다
        head1 = [ln for ln in column_lines(r.pdf, kit) if ln.col == 1 and ln.dx < 2.0][0]
        hs = sorted({round(d["rect"].y0, 2) for d in page.get_drawings()
                     if d.get("fill") is None and d["rect"].height < 1.5 and d["rect"].width > 20
                     and abs(d["rect"].x0 - lefts[0]) < 1.0 and head1.y0 < d["rect"].y0 < img["bbox"][1]})
    pairs = [(a, b) for a, b in zip(hs, hs[1:]) if 0.3 < b - a < 1.2]
    assert len(hs) == 5 and len(pairs) == 1, hs  # 윗선·겹선 두 줄·행 사이·아랫선, 겹선은 머리행 아래 하나뿐
    # 격자표 첫 행이 한 줄(열 폭이 `측정일`을 접지 않는다): 윗선 → 겹선 = 한 줄 행(1382 ≈ 13.8pt)
    assert abs(pairs[0][0] - hs[0] - 13.8) < 0.8, hs
    # 답항표: 다섯 줄이 5행 답지와 같은 피치로, 칸마다 가운데가 줄끼리 맞는다(제출본은 공백 정렬이라 ±2.7pt 흔들림)
    rows = [ln for ln in column_lines(r.pdf, kit) if ln.col == 2 and ln.dx > 5]
    rows = [ln for ln in rows if ln.boxes and 10 < ln.dx < 20][-5:]
    assert len(rows) == 5
    assert all(abs((b.y0 - a.y0) - LINE_PT) < 0.5 for a, b in zip(rows, rows[1:])), [x.y0 for x in rows]

    def 가운데들(ln):
        xs = sorted(ln.boxes, key=lambda g: g.x0)
        chunks = [[xs[0]]]
        for g in xs[1:]:
            (chunks.append([g]) if g.x0 - chunks[-1][-1].x1 > 8 else chunks[-1].append(g))
        return [(c[0].x0 + c[-1].x1) / 2 for c in chunks]

    cs = [가운데들(ln) for ln in rows]
    assert {len(c) for c in cs} == {4}
    for k in range(4):
        col = [c[k] for c in cs]
        assert max(col) - min(col) < 1.0, (k, col)
    # 칸 여백 0: ①은 원문자 칸(답지 왼여백 10pt + 16pt 폭) 가운데, 머리 기호 밑줄은 제 칸 글자와 같은 가운데
    right = lefts[1]
    assert abs(cs[0][0] - (right + 10.0 + 8.0)) < 1.0, cs[0][0] - right
    with pymupdf.open(str(r.pdf)) as pdf:
        uls = sorted((d["rect"].x0 + d["rect"].x1) / 2 for d in pdf[0].get_drawings()
                     if d.get("fill") is None and d["rect"].height < 0.5 and 5 < d["rect"].width < 40
                     and d["rect"].x0 > right and rows[0].y0 - LINE_PT < d["rect"].y0 < rows[0].y0)
    assert len(uls) == 3, uls
    칸 = (kit.columns["body_table_width"] - 1000 - 1600) / 3 / 100.0
    for k in range(1, 4):  # 넓은 칸 글자도 칸 한가운데(여백을 물려받으면 ≈5pt 오른쪽으로 밀린다)
        assert abs(cs[0][k] - (right + 10.0 + 16.0 + 칸 * (k - 0.5))) < 1.0, (k, cs[0][k] - right)
    for k, u in enumerate(uls, 1):
        assert abs(u - cs[0][k]) < 1.0, (k, u, cs[0][k])
    # 자료 박스 안의 표: 박스 위·아래 여백이 글 박스와 같은 수준(표 아래 바깥 여백을 뺐다)
    [자료] = [b for b in boxes(r.pdf, kit) if b.col == 2 and not b.titled and b.lines]
    assert 자료.top_gap < LINE_PT and 자료.bottom_gap < LINE_PT


def test_그림_생성기_폴백과_EXIF_회전(양식_hwpx, tmp_path, monkeypatch):
    import io
    import zipfile

    from PIL import Image

    import exam_kit.compose as C

    im = Image.new("RGB", (300, 100), (200, 30, 30))
    exif = Image.Exif()
    exif[0x0112] = 6  # 오른쪽으로 90° 돌려 보라는 사진 — 보이는 모양은 100×300
    im.save(tmp_path / "사진.jpg", exif=exif)
    md = (픽스처 / "표그림_3문항.md").read_text(encoding="utf-8").replace("그림.png){width=6cm}", "사진.jpg){width=3cm}")
    kit = load_kit(킷_디렉터리)
    monkeypatch.setattr(C, "_create_picture_element", None)  # private 생성기가 없어도 add_picture 폴백으로
    doc, _ = prepare_document(양식_hwpx, kit)
    compose(doc, scan_markdown(md), kit, answer_key=False, image_root=tmp_path)
    ps = 최상위_문단(doc)
    [pic] = ps[question_heads(doc)[1] + 1].element.iter(q("hp", "pic"))
    assert pic.find(q("hp", "pos")).get("treatAsChar") == "1"
    w, h = int(pic.find(q("hp", "sz")).get("width")), int(pic.find(q("hp", "sz")).get("height"))
    assert (w, h) == (round(3 * 72000 / 25.4), round(3 * 72000 / 25.4 * 3))  # 세로로 선 모양
    assert len(ps) == len(최상위_문단(doc)) and not [p for p in ps[1:-1] if 텍스트(p.element) == "" and
                                                  p.element.find(f".//{q('hp', 'pic')}") is None
                                                  and p.element.find(f".//{q('hp', 'tbl')}") is None]  # 임시 문단 없음
    out = tmp_path / "사진.hwpx"
    doc.save_to_path(str(out))
    ref = pic.find(f".//{q('hc', 'img')}").get("binaryItemIDRef")
    with zipfile.ZipFile(out) as z:
        [name] = [n for n in z.namelist() if n.startswith("BinData/") and ref in n]
        got = Image.open(io.BytesIO(z.read(name)))
    assert got.mode == "L" and got.size == (100, 300)


# ---- Task 25: 답항 배치형 1·2·3·5행 + 탭 --------------------------------------------

배치_기대 = {"1": "1행", "2": "2행", "3": "2행", "4": "2행", "5": "3행", "6": "5행", "7": "5행"}  # 1번은 {답항=1행}로 눌렀다


def _1행_강제(md: str) -> str:
    """답항배치_7문항의 1번을 {답항=1행}로 — 1행은 자동으로 고르지 않으므로(G3 판정 ③) 1행 조판을 보려면 누른다."""
    return md.replace("## 1. [3.0점]", "## 1. [3.0점] {답항=1행}", 1)
배치_줄 = {"1행": ["①②③④⑤"], "2행": ["①②③", "④⑤"], "3행": ["①②", "③④", "⑤"], "5행": list("①②③④⑤")}
배치_스타일 = {"1행": "1행답항", "2행": "2행답항", "3행": "3행답항", "5행": "5행답항"}
배치_정답 = {"1": "③", "2": "④", "3": "⑤", "4": "②", "5": "②", "6": "①", "7": "④"}


@pytest.fixture(scope="module", params=[False, True], ids=["문항지", "답표시"])
def 배치(request, 양식_hwpx):
    md = _1행_강제((픽스처 / "답항배치_7문항.md").read_text(encoding="utf-8"))
    return (request.param, *_조판(양식_hwpx, md, answer_key=request.param))


def _탭_텍스트(el) -> str:
    """문단 글자 — hp:t 안의 hp:tab은 \\t로."""
    out = []
    for t in el.iter(q("hp", "t")):
        out.append(t.text or "")
        for ch in t:
            out.append(("\t" if ch.tag == q("hp", "tab") else "") + (ch.tail or ""))
    return "".join(out)


def _답지_문단(doc, k):
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    end = heads[k] if k < len(heads) else len(ps) - 1
    return [p.element for p in ps[heads[k - 1] + 1:end]]


def test_배치형_자동_선택과_줄_구성(배치):
    _, kit, doc, _, res = 배치
    assert res.layouts == 배치_기대
    ids = style_ids(doc)
    md = scan_markdown(_1행_강제((픽스처 / "답항배치_7문항.md").read_text(encoding="utf-8")))
    for qn in md.questions:
        kind = 배치_기대[qn.number]
        paras = _답지_문단(doc, int(qn.number))
        assert len(paras) == len(배치_줄[kind]), qn.number
        texts = {c.mark: f"{c.mark} {c.text}" for c in qn.choices}
        for p, marks in zip(paras, 배치_줄[kind]):
            assert p.get("styleIDRef") == ids[배치_스타일[kind]][0]
            assert _탭_텍스트(p) == "\t".join(texts[m] for m in marks)  # 같은 줄 답지는 탭 하나로
            # 탭은 hp:t 안(제출본 모양 `<hp:t>① ㄱ, ㄴ<hp:tab …/>② …</hp:t>`), run 바로 아래에는 없다
            assert not [x for r in p.findall(q("hp", "run")) for x in r if x.tag == q("hp", "tab")]
            for tab in p.iter(q("hp", "tab")):
                assert tab.getparent().tag == q("hp", "t")
                assert (tab.get("leader"), tab.get("type")) == ("0", "1") and int(tab.get("width")) > 0
            # 글자 모양은 스타일 것, 탭 자리는 스타일 paraPr의 탭(tabPrIDRef가 같다) — 1행만 균등 칸 자체 탭(G2)
            assert {r.get("charPrIDRef") for r in p.findall(q("hp", "run"))} == {ids[배치_스타일[kind]][2]}
            pp = _para_pr(doc, p.get("paraPrIDRef"))
            same = pp.get("tabPrIDRef") == _para_pr(doc, ids[배치_스타일[kind]][1]).get("tabPrIDRef")
            assert same == (kind != "1행"), (qn.number, kind)


def test_1행은_자동으로_고르지_않는다(양식_hwpx):
    """G3 판정(09-27 ③): 짧은 답지도 자동 선택은 2행부터 — 1행(한 줄 5칸)은 {답항=1행}로 누를 때만."""
    md = (픽스처 / "답항배치_7문항.md").read_text(encoding="utf-8")
    _, doc, _, res = _조판(양식_hwpx, md, answer_key=False)
    assert res.layouts == 배치_기대 | {"1": "2행"}
    assert "1행" not in res.layouts.values() and not [n for n in res.notes if n.startswith("1번")]
    assert len(_답지_문단(doc, 1)) == 2


def test_배치형_보호_묶음과_형광펜(배치):
    answer_key, kit, doc, _, res = 배치
    for k in range(1, 8):
        paras = _답지_문단(doc, k)
        flags = [_break(_para_pr(doc, p.get("paraPrIDRef"))) for p in paras]
        assert flags == [("1", "1")] * (len(paras) - 1) + [("0", "1")]  # 머리~마지막 답지 줄 한 묶음
        pens = [m for p in paras for m in p.iter(q("hp", "markpenBegin"))]
        if answer_key:
            assert len(pens) == 1 and pens[0].tail == 배치_정답[str(k)], k
            assert pens[0].getparent().tag == q("hp", "t")
        else:
            assert pens == []
    assert res.answers == 배치_정답
    if answer_key:
        assert extract_answers(doc) == 배치_정답
    fs = verify_document(doc, kit, expect_answers=배치_정답 if answer_key else None, answer_key=answer_key, draft=True)
    assert errors(fs) == []


def test_배치형_덮어쓰기(양식_hwpx):
    md = (픽스처 / "답항배치_7문항.md").read_text(encoding="utf-8")
    md = md.replace("## 1. [3.0점]", "## 1. [3.0점] {답항=3행}").replace("## 6. [4.0점]", "## 6. [4.0점] {답항=2행}")
    _, doc, _, res = _조판(양식_hwpx, md, answer_key=False)
    assert res.layouts["1"] == "3행" and len(_답지_문단(doc, 1)) == 3  # 들어가는 형보다 느슨하게 눌러도 따른다
    assert res.layouts["6"] == "2행" and len(_답지_문단(doc, 6)) == 2  # 넘치는 형으로 눌러도 따르되 알린다
    assert [n for n in res.notes if n.startswith("6번")] and not [n for n in res.notes if n.startswith("1번")]
    assert res.layouts["7"] == "5행"


def test_칸_시작과_들어감_판정(양식_hwpx):
    from exam_kit.compose import _Composer, fits

    kit = load_kit(킷_디렉터리)
    doc, _ = prepare_document(양식_hwpx, kit)
    c = _Composer(doc, kit, harvest_samples(doc, kit), answer_key=False)
    # 칸 시작 = 왼여백 + 스타일의 탭 자리(case 분기). 양식에는 스타일마다 필요한 만큼 탭이 정의돼 있다
    # 1행만 가용 폭(1000 ~ 단 끝 30898)을 5등분(G2 판정 — 양식 탭 50/50/60/60pt는 고르지 않다)
    assert c.slots("choice1") == [1000, 6979, 12958, 18937, 24916]
    assert c.slots("choice2") == [1000, 10772, 20408]
    assert c.slots("choice3") == [1000, 15876]
    end, gap = 30898, 1067
    # 2행 칸: ① 1000~10772, ② ~20408, ③ ~30898 — 칸 끝 전 한 글자(gap) 여유
    # 둘째 줄 ⑤는 둘째 칸에서 단 끝까지 쓴다
    starts = [1000, 10772, 20408]
    ok = [10772 - 1000 - gap, 20408 - 10772 - gap, end - 20408 - gap, 10772 - 1000 - gap, end - 10772 - gap]
    assert fits(ok, (3, 2), starts, end, gap)
    for i in range(5):  # 어느 답지든 한 단위만 넘쳐도 들어가지 않는다
        assert not fits(ok[:i] + [ok[i] + 1] + ok[i + 1:], (3, 2), starts, end, gap), i
    # 칸이 모자라면(탭 자리가 줄의 답지 수 − 1보다 적으면) 양식이 바뀐 것
    pp = _para_pr(doc, c.style["choice3"][1])
    tab = _헤더(doc).find(f".//{q('hh', 'tabPr')}[@id='{pp.get('tabPrIDRef')}']")
    for sw in tab.findall(q("hp", "switch")):
        tab.remove(sw)
    with pytest.raises(ValueError, match="양식이 바뀌었다"):
        c.slots("choice3", need=2)


def test_렌더_배치형_칸_자리(양식_hwpx, 오라클, tmp_path):
    from exam_kit.geometry import column_lines, splits
    from exam_kit.render import RenderUnavailable, render

    md = _1행_강제((픽스처 / "답항배치_7문항.md").read_text(encoding="utf-8"))
    kit, doc, prepared, res = _조판(양식_hwpx, md, answer_key=False)
    finalize_form(doc, kit, prepared)
    out = tmp_path / "답항배치_7문항.hwpx"
    doc.save_to_path(str(out))
    try:
        r = render(out, tmp_path / "r", oracle=오라클)
    except RenderUnavailable:
        r = render(out, tmp_path / "r2", oracle=오라클)
    assert splits(r.pdf, kit) == []
    lines = column_lines(r.pdf, kit)
    heads = [i for i, ln in enumerate(lines) if ln.dx < 2.0]
    assert len(heads) == 7
    # 답지 줄 수가 배치형 줄 수와 같다 = 줄이 접히지 않았다(접히면 이음 줄도 왼여백에서 시작한다)
    bounds = heads + [len(lines)]
    칸 = {"1행": [10.0, 69.79, 129.58, 189.37, 249.16], "2행": [10.0, 107.72, 204.08], "3행": [10.0, 158.76]}  # 탭 자리/100
    for k in range(7):
        kind = 배치_기대[str(k + 1)]
        n = len(배치_줄[kind])
        body = lines[heads[k] + 1:bounds[k + 1]]
        choice = [ln for ln in body if 9.0 < ln.dx < 12.0]  # 답지 왼여백 10pt에서 시작하는 줄(5행 접힌 줄은 ≈27pt)
        assert len(choice) == n, (k + 1, [round(ln.dx, 1) for ln in body])
        if kind == "5행":
            continue
        for ln, marks in zip(choice, 배치_줄[kind]):
            xs = _원문자_x(ln)
            for want in 칸[kind][:len(marks)]:  # 칸마다 원문자가 탭 자리에 — 넘친 답지가 있으면 탭이 다음 자리로 밀린다
                assert any(abs(x - want - 원문자_곁) < 0.5 for x in xs), (k + 1, marks, want, xs)


# 원문자 글리프 x0 = 앉은 자리 + 0.5~0.6pt(5행 ① 10.5 @ 1000). 제출본 2행 ② 107.4~107.6·③ 203.4는 한컴이 저장해 둔
# 줄 캐시(탭 width)를 그대로 쓴 값이다 — 제출본 사본에서 2행 문단의 linesegarray만 지우고 다시 렌더하면 108.3·204.7로
# 엔진과 같아진다(Task 25 보고).
원문자_곁 = 0.55


def _원문자_x(ln) -> list[float]:
    """답지 줄에서 원문자 모양 글리프(폭 9.3~10.1pt)의 x0 — 단 왼끝 기준 pt."""
    cl = ln.boxes[0].x0 - ln.dx
    return [round(g.x0 - cl, 2) for g in ln.boxes if 9.3 < g.width < 10.1]


# ---- Task 15b: G2 판정 — 1행 균등 칸 · `~` → `∼` ---------------------------------------

def _탭_자리(doc, pid) -> list[tuple[int, int]]:
    """paraPr pid의 tabPr 탭 자리 [(case, default)]."""
    tab = _헤더(doc).find(f".//{q('hh', 'tabPr')}[@id='{_para_pr(doc, pid).get('tabPrIDRef')}']")
    return [(int(sw.find(f"{q('hp', 'case')}/{q('hh', 'tabItem')}").get("pos")),
             int(sw.find(f"{q('hp', 'default')}/{q('hh', 'tabItem')}").get("pos"))) for sw in tab.findall(q("hp", "switch"))]


def test_1행은_균등_칸_자체_탭(배치):
    """1행 칸 = 가용 폭(왼여백 1000 ~ 단 끝 30898) ÷ 5, 문단은 탭만 다른 파생 paraPr — 양식 1행답항 스타일·탭은 그대로."""
    _, kit, doc, _, _ = 배치
    ids = style_ids(doc)
    _, style_pp, _ = ids["1행답항"]
    assert _탭_자리(doc, style_pp) == [(6000, 12000), (11000, 22000), (17000, 34000), (23000, 46000)]  # 양식 원래 탭
    w = (30898 - 1000) // 5
    [p] = _답지_문단(doc, 1)
    assert p.get("styleIDRef") == ids["1행답항"][0]
    assert _탭_자리(doc, p.get("paraPrIDRef")) == [(1000 + k * w, 2 * (1000 + k * w)) for k in range(1, 5)]
    pp, base = _para_pr(doc, p.get("paraPrIDRef")), _para_pr(doc, style_pp)
    assert _칸_여백(pp) == _칸_여백(base)  # 여백·줄간격은 스타일 그대로
    tab = _헤더(doc).find(f".//{q('hh', 'tabPr')}[@id='{pp.get('tabPrIDRef')}']")
    assert tab.getparent().get("itemCnt") == str(len(tab.getparent().findall(q("hh", "tabPr"))))
    # 2행·3행은 여전히 양식 스타일 탭
    for k, name in ((2, "2행답항"), (5, "3행답항")):
        assert _para_pr(doc, _답지_문단(doc, k)[0].get("paraPrIDRef")).get("tabPrIDRef") \
            == _para_pr(doc, ids[name][1]).get("tabPrIDRef")


def test_1행_탭은_한_번만_만든다(양식_hwpx):
    md = _1행_강제((픽스처 / "답항배치_7문항.md").read_text(encoding="utf-8"))
    md = md.replace("## 2. [3.5점]", "## 2. [3.5점] {답항=1행}")
    _, doc, _, res = _조판(양식_hwpx, md, answer_key=False)
    assert res.layouts["1"] == res.layouts["2"] == "1행"
    [a], [b] = _답지_문단(doc, 1), _답지_문단(doc, 2)
    assert _para_pr(doc, a.get("paraPrIDRef")).get("tabPrIDRef") == _para_pr(doc, b.get("paraPrIDRef")).get("tabPrIDRef")
    tabs = _헤더(doc).findall(f".//{q('hh', 'tabPr')}")
    shapes = [tuple((sw.find(f"{q('hp', 'case')}/{q('hh', 'tabItem')}").get("pos")) for sw in t.findall(q("hp", "switch")))
              for t in tabs]
    assert len(shapes) == len(set(shapes))  # 같은 모양 tabPr가 둘 생기지 않는다


물결_md = """---
양식: 예시-원안지
학년도: 2026
학년: 2
학기: 2
차: 2
과목: 인공지능 기초
과목코드: 16
시행: 12.14.(월) 3교시
대상: 2학년 6반~10반
인쇄: 30매 * 4묶음
출제교사: 홍길동
만점: 14
---

## 1~2. 세트
세트 지문 (가)~(나) 줄이다.

### 1. [4.0점]
(가)~(다)에 해당하는 것을 고른 것은?

:::보기
ㄱ. 1~3단계
:::

:::자료
| 구간 | 값 |
|---|---|
| 1~5 | 3~4 |
:::

① 1~2
*② 2~3
③ 3~4
④ 4~5
⑤ 5~6

### 2. [5.0점]
빈칸 ㄱ~ㄴ에 알맞은 것은?

:::답항표 머리="ㄱ~|ㄴ"
① 1~2 | 가
*② 2~3 | 나
③ 3~4 | 다
④ 4~5 | 라
⑤ 5~6 | 마
:::

## 3. [5.0점]
세 번째 ~ 발문이다.

① 가
② 나
*③ 다
④ 라
⑤ 마
"""


def test_물결은_조판에서_모두_전각_물결로(양식_hwpx):
    from exam_kit.compose import 물결

    assert 물결("(가)~(다)", [("~", "∼")]) == "(가)∼(다)" and 물결("a~b") == "a~b"  # 바꾸기는 킷 typeset.text_replace에서
    kit, doc, prepared, res = _조판(양식_hwpx, 물결_md, answer_key=True)
    ps = 최상위_문단(doc)
    heads = question_heads(doc)
    body = "".join("".join(p.element.itertext()) for p in ps[heads[0] - 1:-1])  # 세트 머리 ~ 꼬리 앞
    assert "~" not in body
    for want in ("(가)∼(나)", "(가)∼(다)", "1∼3단계", "1∼5", "3∼4", "① 1∼2", "ㄱ∼ㄴ", "ㄱ∼", "세 번째 ∼ 발문", "[1∼2]"):
        assert want in body, want
    assert res.answers == {"1": "②", "2": "②", "3": "③"}
    finalize_form(doc, kit, prepared)
    assert errors(verify_document(doc, kit, expect_answers=res.answers, answer_key=True, draft=True)) == []


def test_답지_다시_쓰기도_물결을_바꾼다(양식_hwpx):
    from exam_kit.compose import relayout_choices

    kit, doc, _, res = _조판(양식_hwpx, 물결_md, answer_key=False)
    qn = scan_markdown(물결_md).questions[0]
    relayout_choices(doc, kit, qn, "5행", answer_key=False)  # 원고(~)와 문서(∼) 대조가 물결 뒤에 맞는다
    texts = ["".join(p.itertext()) for p in _답지_문단(doc, 1)]
    assert texts[-5:] == ["① 1∼2", "② 2∼3", "③ 3∼4", "④ 4∼5", "⑤ 5∼6"]


@pytest.mark.parametrize("name", ["답항배치_7문항.md", "견본_전유형.md"])
def test_조판이_만든_paraPr는_모두_쓰인다(양식_hwpx, name):
    """새 paraPr마다 문단(칸 문단 포함)이 가리킨다 — 1행 균등 칸도 중간 paraPr 없이 한 번에 파생한다."""
    md = (픽스처 / name).read_text(encoding="utf-8")
    if name.startswith("답항배치"):
        md = _1행_강제(md)
    before: set[str] = set()

    def 기록(doc):
        before.update(pp.get("id") for pp in _헤더(doc).iter(q("hh", "paraPr")))

    kit, doc, _, res = _조판(양식_hwpx, md, answer_key=False, doctor=기록)
    new = {pp.get("id") for pp in _헤더(doc).iter(q("hh", "paraPr"))} - before
    used = {el.get("paraPrIDRef") for s in doc.sections for el in s.element.iter() if el.get("paraPrIDRef")}
    assert new and new <= used, sorted(new - used)
    if name.startswith("답항배치"):
        assert res.layouts["1"] == "1행"


def test_그림은_줄이지_않고_넓으면_멈춘다(양식_hwpx, tmp_path):
    """(Task 30) 단 폭보다 넓은 그림은 오류(원래 크기와 함께 알린다), 원래 크기보다 좁게 넣으면 조판 note(경고)."""
    from PIL import Image

    Image.new("L", (600, 300), 255).save(tmp_path / "a.png")
    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8")
    head, rest = md.split("## 2.", 1)
    kit = load_kit(킷_디렉터리)

    def 조판(width):
        text = head + "## 2." + rest.replace("① 짧은 답지", f"![](a.png){{width={width}cm}}\n\n① 짧은 답지", 1)
        scan = scan_markdown(text)
        doc, prepared = prepare_document(양식_hwpx, kit)
        fill_slots(doc, kit, scan.front, question_count=len(scan.questions), total_points=sum(x.points for x in scan.questions))
        return compose(doc, scan, kit, answer_key=False, image_root=tmp_path)

    with pytest.raises(ValueError, match="단 폭.*원래 크기 5.1cm"):
        조판(12)
    assert [n for n in 조판(4).notes if "원래 크기 5.1cm" in n]
    assert not [n for n in 조판(5.1).notes if "원래 크기" in n]


코드_md = """## 1. [4.0점]
합성 코드 출력을 보고 옳은 것은?

```
합성값    3
길이       12
```

:::자료
설명 줄이다.
```
열A   0
열B  17
```
:::

① 가
*② 나
③ 다
④ 라
⑤ 마
"""


def test_코드_블록은_고정폭_왼쪽_정렬(양식_hwpx):
    """(Task 30) 코드 줄 = 문단 하나씩, 글자 그대로(공백), 굴림체(kit.code_font)·장평 100·자간 0, 왼쪽 정렬·들여쓰기 0.
    자료 박스 안 코드도 같다. 자간 맞춤 대상(fit.targets)에서 빠진다. 역변환은 ``` 펜스로 되돌린다."""
    from exam_kit.fit import targets
    from exam_kit.reverse import is_code, mono_char_prs, reverse_body, underlined_char_prs

    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8").split("## 1.")[0].replace("만점: 20", "만점: 4") + 코드_md
    kit, doc, prepared, res = _조판(양식_hwpx, md, answer_key=False)
    hdr = _헤더(doc)
    mono = mono_char_prs(doc)
    body_ps = [x for p in 최상위_문단(doc)[1:-1] for x in p.element.iter(q("hp", "p"))]  # 관리박스·꼬리(굴림체) 뺀 본문
    code_ps = [p for p in body_ps if is_code(p, mono)]
    assert ["".join(p.itertext()) for p in code_ps] == ["합성값    3", "길이       12", "열A   0", "열B  17"]
    font = {f.get("id"): f.get("face") for ff in hdr.iter(q("hh", "fontface")) if ff.get("lang") == "HANGUL"
            for f in ff.findall(q("hh", "font"))}
    for p in code_ps:
        cp = hdr.find(f".//{q('hh', 'charPr')}[@id='{p.find(q('hp', 'run')).get('charPrIDRef')}']")
        assert font[cp.find(q("hh", "fontRef")).get("hangul")] == "굴림체"
        assert set(cp.find(q("hh", "ratio")).attrib.values()) == {"100"} and set(cp.find(q("hh", "spacing")).attrib.values()) == {"0"}
        pp = _para_pr(doc, p.get("paraPrIDRef"))
        assert pp.find(q("hh", "align")).get("horizontal") == "LEFT"
    finalize_form(doc, kit, prepared)
    assert not [t for t in targets(doc, kit) if "합성값" in t.text or "열A" in t.text]
    ps = [p.element for p in 최상위_문단(doc)]
    heads = question_heads(doc)
    body = reverse_body(ps[1:-1], {h - 1 for h in heads}, underlined_char_prs(doc), mono=mono, boxes=kit.boxes)
    text = "\n".join(body)
    assert "```\n합성값    3\n길이       12\n```" in text and "```\n열A   0\n열B  17\n```" in text


def test_열_폭_넘칠_때는_가장_긴_낱말부터():
    """(Task 19) 칸 글이 다 들어가지 않으면 열마다 가장 긴 낱말 + 여백을 먼저 주고, 남는 폭을 모자란 만큼에 비례해 나눈다."""
    from exam_kit.compose import _글폭, column_widths  # noqa: F401

    row = ["가나", "가나다 가나다라", "가나다라 가나다라", "가 가나다라마바"]
    w = column_widths([row], 24000, 3000, pad=1000, m=_M)  # 글 폭 합 31108 > 24000 ≥ 가장 긴 낱말 합 21072
    assert sum(w) == 24000
    assert all(wi >= max(_글폭(t, _M) for t in text.split()) + 1000 for wi, text in zip(w, row)), w  # 가장 긴 낱말은 들어간다
    assert w[0] == min(w)  # 짧은 열은 제 낱말 폭만
    # 다 들어가면 예전처럼 비례(모든 칸이 제 글 폭 이상)
    w2 = column_widths([["가나", "다라"]], 20000, 3000, pad=1000, m=_M)
    assert w2 == [10000, 10000]


def test_낱말_단위_접기():
    """wrap_words — 낱말 사이에서만, 긴 낱말은 그대로, 두 칸 공백은 접지 않는 자리에서 그대로, `__…__`은 한 덩어리."""
    from exam_kit.compose import wrap_words

    assert wrap_words("가나 다라", 10000, _M) == "가나 다라"  # 들어가면 그대로
    assert wrap_words("가나다라마바사아자차카 타", 3000, _M) == "가나다라마바사아자차카\n타"  # 긴 낱말은 그대로(한글이 접는다)
    assert wrap_words("가나  다라 마바사아", 5500, _M) == "가나  다라\n마바사아"  # 두 칸은 줄 안에서 그대로
    assert wrap_words("가나다라 __마바 사아__ 자차", 5000, _M) == "가나다라\n__마바 사아__\n자차"  # 밑줄 안은 안 끊는다
    assert "\n" not in wrap_words("__가나 다라 마바 사아__", 3000, _M)  # 밑줄 하나뿐 — 끊을 자리가 없다


def test_답항표_균등과_글_길이(양식_hwpx):
    """(Task 19) 답항표 열: 모든 칸이 균등 칸에 들어가면 균등(G2), 아니면 글 길이에 맞춘다 — 접힌 칸이 있으면 행이 높아진다."""

    def 폭_높이(rows):
        md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8").split("## 1.")[0].replace("만점: 20", "만점: 4")
        md += "## 1. [4.0점]\n합성 발문?\n\n:::답항표 머리=\"가|나|다\"\n" + "\n".join(
            f"{'*' if i == 0 else ''}{m} {r}" for i, (m, r) in enumerate(zip("①②③④⑤", rows))) + "\n:::\n"
        _, doc, _, _ = _조판(양식_hwpx, md, answer_key=False)
        tbl = next(x for p in 최상위_문단(doc) for r in p.element.findall(q("hp", "run")) for x in r
                   if x.tag == q("hp", "tbl") and x.get("rowCnt") == "6")
        trs = tbl.findall(q("hp", "tr"))
        ws = [int(tc.find(q("hp", "cellSz")).get("width")) for tc in trs[0].findall(q("hp", "tc"))]
        hs = [int(tr.find(q("hp", "tc")).find(q("hp", "cellSz")).get("height")) for tr in trs]
        return ws, hs

    ws, hs = 폭_높이(["a | b | c"] * 5)
    assert ws[0] == _M.mark_col and max(ws[1:]) - min(ws[1:]) < 3 and len(set(hs)) == 1  # 균등, 한 줄
    ws, hs = 폭_높이(["가→나→다→라→마→바→사→아→자→차 | 가 | 나"] + ["가 | 나 | 다"] * 4)
    assert ws[1] > ws[2] and ws[1] > ws[3]  # 긴 칸이 넓다
    long_row = "가나다라마바사 아자차카타파하 가나다라마바사 아자차카타파하 가나다라마바사 | 가 | 나"
    ws, hs = 폭_높이([long_row] + ["가 | 나 | 다"] * 4)
    assert hs[1] > hs[2]  # 접힌 칸이 있는 행이 더 높다


def test_렌더_코드_블록은_열이_맞는다(양식_hwpx, 오라클, tmp_path):
    """(Task 30) 굴림체 고정폭 — `열A   0`의 0과 `열B  17`의 7은 같은 글자 칸(x)에 온다(공백 그대로·자간 0·장평 100).
    자료 박스 안 코드도 같다."""
    import pymupdf

    from exam_kit.render import render

    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8").split("## 1.")[0].replace("만점: 20", "만점: 4") + 코드_md
    kit, doc, prepared, _ = _조판(양식_hwpx, md, answer_key=False)
    finalize_form(doc, kit, prepared)
    out = tmp_path / "code.hwpx"
    doc.save_to_path(str(out))
    pdf = render(out, tmp_path / "r", oracle=오라클).pdf
    with pymupdf.open(str(pdf)) as d:
        lines = [(sp["font"], [(c["c"], c["bbox"][0]) for c in sp["chars"]])
                 for b in d[0].get_text("rawdict")["blocks"] for ln in b.get("lines", []) for sp in ln["spans"]]
    code = ["".join(c for c, _ in chars) for f, chars in lines if "Gulim" in f or "굴림" in f]
    assert any("열A" in t for t in code) and any("열B" in t for t in code), code

    def x_of(prefix, ch):
        chars = next(chars for f, chars in lines if ("Gulim" in f or "굴림" in f) and "".join(c for c, _ in chars).startswith(prefix))
        return next(x for c, x in chars if c == ch)

    assert abs(x_of("열A", "0") - x_of("열B", "7")) < 0.5  # 반각 칸 6번째(열=2칸, A·B=1칸, 공백 3·2칸)


def test_코드_블록_빈_줄은_빈_문단으로_남는다(양식_hwpx):
    """(m-3) 코드 속 빈 줄 = 고정폭 빈 문단 하나 — 줄 수가 그대로이고, 역변환도 빈 줄을 그대로 되돌린다(박스 안·밖)."""
    from exam_kit.reverse import is_code, mono_char_prs, reverse_body, underlined_char_prs

    빈줄_md = 코드_md.replace("합성값    3\n길이", "합성값    3\n\n길이").replace("열A   0\n열B", "열A   0\n\n열B")
    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8").split("## 1.")[0].replace("만점: 20", "만점: 4") + 빈줄_md
    kit, doc, prepared, res = _조판(양식_hwpx, md, answer_key=False)
    mono = mono_char_prs(doc)
    body_ps = [x for p in 최상위_문단(doc)[1:-1] for x in p.element.iter(q("hp", "p"))]
    assert ["".join(p.itertext()) for p in body_ps if is_code(p, mono)] == [
        "합성값    3", "", "길이       12", "열A   0", "", "열B  17"]
    finalize_form(doc, kit, prepared)
    ps = [p.element for p in 최상위_문단(doc)]
    text = "\n".join(reverse_body(ps[1:-1], {h - 1 for h in question_heads(doc)}, underlined_char_prs(doc), mono=mono, boxes=kit.boxes))
    assert "```\n합성값    3\n\n길이       12\n```" in text and "```\n열A   0\n\n열B  17\n```" in text
