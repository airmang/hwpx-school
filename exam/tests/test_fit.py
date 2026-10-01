"""자간 맞춤(Task 28) — 대상 문단 · 파생 charPr · 가짜 측정으로 맞춤 루프 · settle 연결 · 실한컴."""

import io
import zipfile
from functools import partial
from pathlib import Path

import lxml.etree as ET
import pytest
from hwpx.document import HwpxDocument
from test_layout import _가짜_렌더, _마무리, _머리들, 픽스처

from _kits import kit_dir
from exam_kit import q
from exam_kit.fit import (
    Lines,
    Spacer,
    current_spacing,
    element_at,
    fit_spacing,
    para_text,
    read_lines,
    summary,
    tail_ratio,
    targets,
)
from exam_kit.kit import style_ids
from exam_kit.layout import settle as _settle
from exam_kit.verify import question_heads
from exam_kit.kit import load_kit

_M = load_kit(kit_dir()).metrics


# 이 파일의 settle은 모두 가짜 렌더라 균형 배치(⓪'')를 끈다 — 가짜 PDF의 줄은 묶음 높이를 뜻하지 않는다(test_layout과 같다).
settle = partial(_settle, balance=False)


def _charprs(doc) -> dict[str, bytes]:
    box = doc.headers[0].element.find(f".//{q('hh', 'charProperties')}")
    return {c.get("id"): ET.tostring(c, method="c14n") for c in box.findall(q("hh", "charPr"))}


def _spacing_of(doc, cid) -> dict[str, str]:
    c = doc.headers[0].element.find(f".//{q('hh', 'charPr')}[@id='{cid}']")
    return dict(c.find(q("hh", "spacing")).attrib)


def _used_charprs(doc) -> set[str]:
    return {el.get("charPrIDRef") for s in doc.sections for el in s.element.iter() if el.get("charPrIDRef")} | {
        el.get("charPrIDRef") for el in doc.headers[0].element.iter() if el.get("charPrIDRef")}


# ---- 대상 문단 -----------------------------------------------------------------

@pytest.fixture
def 견본(양식_hwpx):
    return _마무리(양식_hwpx, (픽스처 / "견본_전유형.md").read_text(encoding="utf-8"))


def test_대상_문단(견본):
    kit, doc = 견본
    ts = targets(doc, kit)
    heads = question_heads(doc)
    stems = [t for t in ts if t.role == "발문"]
    assert [t.key for t in stems] == [(h, -1) for h in heads] and [t.number for t in stems] == list(range(1, 11))
    # 세트 지문은 세트 첫 문항(7번) 묶음이다. 세트 자료 박스 줄도 7번
    [passage] = [t for t in ts if t.role == "지문"]
    assert passage.number == 7 and passage.text.startswith("[7∼8]")
    assert [t.number for t in ts if t.role == "자료" and t.text.startswith("어느 동아리가")] == [7]
    # 〈보기〉 항목·자료 줄은 박스 내용 셀 문단, 격자표·답항표 칸은 대상이 아니다
    assert [t.text.strip()[:2] for t in ts if t.role == "보기" and t.number == 10] == ["ㄱ.", "ㄴ.", "ㄷ."]
    ids = style_ids(doc)
    box_styles = {ids[kit.styles["box_guide"]][0], ids[kit.styles["box"]][0]}
    for t in ts:
        el = element_at(doc, t.key)
        assert para_text(el) == t.text
        if t.key[1] >= 0:
            assert el.get("styleIDRef") in box_styles, t
    assert not [t for t in ts if t.number == 10 and t.role == "자료"]  # 10번 자료는 격자표뿐(칸은 바탕글)
    assert not [t for t in ts if t.number == 6 and t.text.strip() in ("(가)", "강화", "지도")]  # 답항표 칸
    answers = [t for t in ts if t.role == "답지" and t.number == 1]
    assert len(answers) == 5  # 5행 답지 줄마다


# ---- 파생 charPr -----------------------------------------------------------------

def test_자간_charPr_파생·재사용·걷어내기(견본):
    kit, doc = 견본
    before = _charprs(doc)
    ts = targets(doc, kit)
    a, b = [t for t in ts if t.role == "답지"][:2]  # 같은 스타일 charPr 한 run
    base = element_at(doc, a.key).find(q("hp", "run")).get("charPrIDRef")
    sp = Spacer(doc)
    sp.set({a.key: -5, b.key: -5})
    after = _charprs(doc)
    new = set(after) - set(before)
    assert len(new) == 1  # 같은 (base, s)는 하나를 같이 쓴다
    [cid] = new
    assert _spacing_of(doc, cid) == dict.fromkeys(("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"), "-5")
    got, src = ET.fromstring(after[cid]), ET.fromstring(before[base])
    assert {k: v for k, v in got.attrib.items() if k != "id"} == {k: v for k, v in src.attrib.items() if k != "id"}
    assert [(x.tag, x.attrib) for x in got if not x.tag.endswith("spacing")] == \
           [(x.tag, x.attrib) for x in src if not x.tag.endswith("spacing")]
    assert {r.get("charPrIDRef") for r in element_at(doc, a.key).findall(q("hp", "run"))} == {cid}
    sp.set({})  # 되돌림: 원래 run·원래 charPr 목록 그대로(만든 것은 걷어 낸다)
    assert _charprs(doc) == before
    assert element_at(doc, a.key).find(q("hp", "run")).get("charPrIDRef") == base
    box = doc.headers[0].element.find(f".//{q('hh', 'charProperties')}")
    assert box.get("itemCnt") == str(len(before))
    sp.set({a.key: -3})
    assert set(_charprs(doc)) - set(before) <= _used_charprs(doc)  # 만든 것은 모두 쓰인다
    assert all(_charprs(doc)[k] == v for k, v in before.items())  # 양식 글자 모양은 그대로


# ---- 가짜 측정 --------------------------------------------------------------------
# lines_fn이 저장된 hwpx를 열어 문단마다 자간을 읽고, "need[문단] 이상 줄이면 줄이 하나 준다"로 줄 수를 낸다.

짧은_끝 = "[3.0점]"   # 끝줄 폭 ÷ 가용 폭 ≈ 0.12 — 후보
긴_끝 = "가" * 20      # ≈ 0.7 — 후보 아님


def _가짜_측정(kit, spec: dict, calls: list | None = None, *, bad_text: bool = False):
    """spec: 키 → (처음 줄 수, 끝줄 글, 목적을 이루는 |s|[, 종류]). 종류 "줄"(기본): need 이상이면 줄 하나가 준다.
    "낱말": 첫 줄이 크게 벌어진 두 줄 문단 — need 이상이면 줄 시작이 한 글자 뒤로(줄 수 그대로). "낱말깨짐": need 이상이면
    줄 수가 준다(끌어올림이 아니다). "여유깨짐": 줄 당김인데 need + 1 이상이면 줄 시작이 바뀐다. spec 밖 대상 문단은 한 줄."""
    def lines_fn(path, work):
        d = HwpxDocument.open(str(path))
        out = {}
        for t in targets(d, kit):
            n, tail, need, *kind = spec.get(t.key, (1, "", 99))
            kind = kind[0] if kind else "줄"
            s = abs(current_spacing(d, t.key))
            text = para_text(element_at(d, t.key)) + ("?" if bad_text else "")
            if kind == "줄" or kind == "여유깨짐":
                got_n = n - 1 if s >= need else n
                cut = 4 + (1 if kind == "여유깨짐" and s >= need + 1 else 0)
                out[t.key] = Lines(got_n, tail, 30000, text, tuple(range(0, got_n * cut, cut)), (0,) * got_n)  # 벌어짐 없음
            elif kind == "낱말엉뚱":  # 가장 벌어진 줄은 0번인데, 자간을 주면 2번 줄 시작만 바뀐다
                cut = text.find(" ", text.find(" ") + 1) + 1
                out[t.key] = Lines(3, tail, 30000, text, (0, cut, cut + 3 + (1 if s >= need else 0)), (90000, 0, 0))
            else:
                moved = s >= need
                got_n = n - 1 if kind == "낱말깨짐" and moved else n
                cut = text.find(" ", text.find(" ") + 1) + 1  # 둘째 낱말 뒤 — 첫 줄에 공백이 둘
                out[t.key] = Lines(got_n, tail, 30000, text, (0, cut + (1 if kind == "낱말" and moved else 0))[:got_n],
                                   (90000,) * got_n)  # 가용 폭이 글보다 훨씬 커서 공백이 크게 벌어진 줄
        if calls is not None:
            calls.append({k: abs(current_spacing(d, k)) for k in spec})
        return out
    return lines_fn


def _저장(doc, path: Path):
    def save():
        doc.save_to_path(str(path))
        return path
    return save


def test_가짜_맞춤_가장_작은_자간과_역할_하한(견본, tmp_path):
    kit, doc = 견본
    before = _charprs(doc)
    ts = targets(doc, kit)
    s1, s2 = [t for t in ts if t.role == "발문"][:2]
    ans = next(t for t in ts if t.role == "답지")
    box = next(t for t in ts if t.role == "보기")
    loose = next(t for t in ts if t.role == "자료")
    spec = {s1.key: (2, 짧은_끝, 6),     # 발문 −6이면 한 줄
            ans.key: (3, 짧은_끝, 5),    # 답지 −5
            box.key: (2, 짧은_끝, 9),    # 〈보기〉 −9 필요 — 역할 하한 −7 밖: 짧은 끝줄이 아니다(알리지 않는다)
            s2.key: (2, 짧은_끝, 20),    # 발문 −20 필요 — 하한 −17까지 가도 못 당김 → failed
            loose.key: (2, 긴_끝, 1)}    # 끝줄이 길다 — 후보 아님(−1이면 당겨지더라도)
    calls: list = []
    res = fit_spacing(doc, kit, _저장(doc, tmp_path / "x.hwpx"), _가짜_측정(kit, spec, calls))
    assert {(t.key, s) for t, s in res.done} == {(s1.key, -7), (ans.key, -6)}  # 최소값(−6·−5) + 여유 1
    assert res.minimum == {s1.key: 6, ans.key: 5}
    assert [t.key for t, _ in res.failed] == [s2.key]
    assert res.rounds == 1 + 5 + 1 and len(calls) == res.rounds  # 처음 측정 + 이분 탐색(|하한| 17 → 5회) + 여유 확인
    assert all(c[loose.key] == 0 for c in calls)  # 후보가 아닌 문단은 건드린 적이 없다
    assert max(c[box.key] for c in calls) <= 7    # 역할 하한 밖으로 가 보지 않는다
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))  # 파일에 남은 것: 맞춘 문단만, 쓰이는 charPr만
    assert current_spacing(saved, s1.key) == -7 and current_spacing(saved, ans.key) == -6
    assert current_spacing(saved, s2.key) == current_spacing(saved, box.key) == current_spacing(saved, loose.key) == 0
    new = set(_charprs(saved)) - set(before)
    assert new and new <= _used_charprs(saved)
    assert all(_charprs(saved)[k] == v for k, v in before.items())
    assert summary(res.done)[s1.number].startswith("발문 −7")


def test_가짜_이미_맞춘_문단은_다시_맞추지_않는다(견본, tmp_path):
    kit, doc = 견본
    s1 = targets(doc, kit)[0]
    spec = {s1.key: (2, 짧은_끝, 4)}
    fit_spacing(doc, kit, _저장(doc, tmp_path / "x.hwpx"), _가짜_측정(kit, spec))
    again = fit_spacing(doc, kit, _저장(doc, tmp_path / "x.hwpx"), _가짜_측정(kit, {s1.key: (1, 짧은_끝, 99)}))
    assert again.done == [] and again.rounds == 1 and current_spacing(doc, s1.key) == -5


def test_가짜_측정_글자가_다르면_멈춘다(견본, tmp_path):
    kit, doc = 견본
    with pytest.raises(ValueError, match="글자가 다르다"):
        fit_spacing(doc, kit, _저장(doc, tmp_path / "x.hwpx"), _가짜_측정(kit, {}, bad_text=True))


def test_줄_캐시_읽기(tmp_path):
    """최상위 문단 (i, −1), 그 안 문단 (i, j) — 줄 수 = lineseg 수, 끝줄 = 마지막 textpos부터."""
    sec = (f'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="{q("hp", "x")[1:].split("}")[0]}">'
           '<hp:p><hp:run><hp:t>첫 문단 글자</hp:t></hp:run><hp:linesegarray>'
           '<hp:lineseg textpos="0" horzsize="30000" vertsize="1100"/>'
           '<hp:lineseg textpos="2" horzsize="29000" vertsize="2500"/></hp:linesegarray></hp:p>'
           '<hp:p><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>칸<hp:tab/>글</hp:t></hp:run>'
           '<hp:linesegarray><hp:lineseg textpos="0" horzsize="100"/></hp:linesegarray></hp:p>'
           '</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p></hs:sec>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", sec)
    path = tmp_path / "x.hwpx"
    path.write_bytes(buf.getvalue())
    got = read_lines(path)
    assert got[(0, -1)] == Lines(2, "문단 글자", 29000, "첫 문단 글자", (0, 2), (30000, 29000), (1100, 2500))
    assert got[(0, -1)].extra(1100) == 1400  # 수식이 든 줄처럼 높아진 줄 — 글자 높이를 넘은 만큼
    assert got[(1, 0)] == Lines(1, "칸\t글", 100, "칸\t글", (0,), (100,), (0,))
    assert (1, -1) not in got  # 줄 캐시가 없는 문단은 뺀다


# ---- settle 연결 ------------------------------------------------------------------

def test_가짜_settle_자간_맞춤_뒤_재렌더(양식_hwpx, tmp_path):
    """⓪'이 문단을 당기면 재렌더하고, Settled에 문단·자간·측정 횟수가 남는다. 못 당긴 발문은 note."""
    kit, doc = _마무리(양식_hwpx, (픽스처 / "기본_5문항.md").read_text(encoding="utf-8"))
    ts = targets(doc, kit)
    s1, s2 = [t for t in ts if t.role == "발문"][:2]
    spec = {s1.key: (2, 짧은_끝, 3), s2.key: (2, 짧은_끝, 30)}
    한쪽 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 300), "꼬리": True}]
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=_가짜_렌더(kit, lambda d: 한쪽),
               lines_fn=lambda p, work: _가짜_측정(kit, spec)(p, work))
    assert [(t.key, v) for t, v in s.spacing] == [(s1.key, -4)] and s.measures == 1 + 5 + 1
    assert [n for n in s.notes if n.startswith("2번 발문 끝줄이 짧은데 자간 -17%까지 줄여도")], s.notes
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert current_spacing(saved, s1.key) == -4
    _, doc2 = _마무리(양식_hwpx, (픽스처 / "기본_5문항.md").read_text(encoding="utf-8"))
    off = settle(doc2, kit, tmp_path / "y.hwpx", tmp_path / "r2", render_fn=_가짜_렌더(kit, lambda d: 한쪽), fit=False)
    assert off.spacing == [] and off.measures == 0 and s.renders == off.renders + 1  # 맞춘 뒤 재렌더 한 번


# ---- 실한컴 --------------------------------------------------------------------------

한줄_넘는_md = """---
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
만점: 8
---

## 1. [4.0점]
다음 중 합성 문항의 두 설명으로 옳은 것만을 고른 것은?

*① 합성 답지 가
② 합성 답지 나
③ 합성 답지 다
④ 합성 답지 라
⑤ 합성 답지 마

## 2. [4.0점]
합성 문항 둘째 발문이다. 이 발문은 한 단 폭을 넘도록 일부러 길게 쓴 문장이라 끝줄에 낱말이 여럿 남도록 조금 더 이어 쓴다. 옳은 것은?

① 합성 답지 가
*② 합성 답지 나
③ 합성 답지 다
④ 합성 답지 라
⑤ 합성 답지 마
"""


def test_렌더_자간_맞춤으로_발문을_한_줄로(양식_hwpx, 오라클, tmp_path):
    """배점만 넘어가는 1번 발문(끝줄 `[4.0점]`, 렌더 실측)은 줄 하나를 당기고(가장 작은 자간 — 한 단계 덜 줄이면 두 줄),
    끝줄이 긴 2번은 그대로."""
    from exam_kit.fit import hancom_lines

    kit, doc = _마무리(양식_hwpx, 한줄_넘는_md)
    work = tmp_path / "m"

    def lines_fn(p, n):
        return hancom_lines(p, work / f"m{n}", oracle=오라클)

    out = tmp_path / "x.hwpx"
    res = fit_spacing(doc, kit, _저장(doc, out), lines_fn)
    s1, s2 = [t for t in targets(doc, kit) if t.role == "발문"]
    [copy] = (work / "m1").glob("*.hwpx")  # 측정 사본(이름은 겹치지 않게 붙는다)
    first = read_lines(copy)
    assert first[s1.key].n == 2 and first[s1.key].tail.strip() == "[4.0점]"
    assert first[s2.key].n >= 2 and tail_ratio(first[s2.key], _M) > kit.letter_spacing_tail  # 끝줄이 길다
    done = dict((t.key, v) for t, v in res.done)
    s, least = done[s1.key], res.minimum[s1.key]
    assert s in (-least, -least - 1) and -17 <= s < 0 and s2.key not in done and res.failed == []  # 최소값 + 여유 1
    now = hancom_lines(out, work / "확인", oracle=오라클)
    assert now[s1.key].n == 1 and now[s2.key].n == first[s2.key].n
    if least > 1:  # 가장 작은 자간 — 한 단계 덜 줄이면 두 줄
        Spacer(doc).set({s1.key: -(least - 1)})
        doc.save_to_path(str(out))
        assert hancom_lines(out, work / "덜", oracle=오라클)[s1.key].n == 2


def test_기준본과_줄_대조():
    """글자(공백·물결 무시)가 같은 기준본 문단을 문서 차례로 찾는다 — 없으면 None. 줄 시작은 '앞의 공백 아닌 글자 수'로."""
    from exam_kit.fit import Target, line_diff, norm_starts, same_lines

    ts = [Target((1, -1), 1, "발문", "다음 중 옳은 것은? [3.0점]"), Target((2, -1), 1, "답지", "① 가∼나 다라"),
          Target((3, -1), 1, "답지", "② 다")]
    ours = {(1, -1): Lines(2, "", 1, "다음 중 옳은 것은? [3.0점]", (0, 5)), (2, -1): Lines(2, "", 1, "① 가∼나 다라", (0, 6)),
            (3, -1): Lines(1, "", 1, "② 다", (0,))}
    ref = {(0, -1): Lines(1, "", 1, "머리", (0,)), (5, -1): Lines(2, "", 1, "다음 중  옳은 것은? [3.0점]", (0, 6)),
           (6, 2): Lines(2, "", 1, "① 가~나 다라", (0, 4))}
    rows = line_diff(ts, ours, ref)
    assert [(t.key, None if r is None else r.text) for t, _, r in rows] == \
        [((1, -1), "다음 중  옳은 것은? [3.0점]"), ((2, -1), "① 가~나 다라"), ((3, -1), None)]
    assert norm_starts(rows[0][1]) == norm_starts(rows[0][2]) == (0, 3)  # 공백 정리 차이는 무시한다
    assert same_lines(rows[0][1], rows[0][2]) and not same_lines(rows[1][1], rows[1][2]) and not same_lines(*rows[2][1:])


def test_가짜_낱말_끌어올림(견본, tmp_path):
    """줄 수는 그대로 두고 벌어진 줄에 낱말을 끌어올리는 가장 작은 자간(+ 여유 1). 줄 수가 바뀌면 버리고, 하한 −4 너머는
    가 보지 않는다. 벌어지지 않은 줄(가용 폭 = 글 폭)은 후보가 아니다."""
    kit, doc = 견본
    ts = targets(doc, kit)
    s1, s2, s3 = [t for t in ts if t.role == "발문"][:3]
    box = next(t for t in ts if t.role == "보기")
    spec = {s1.key: (2, 긴_끝, 2, "낱말"),       # −2에서 낱말이 올라온다 → −3(여유)
            s2.key: (2, 긴_끝, 2, "낱말깨짐"),   # −2에서 줄 수가 준다 — 끌어올림이 아니다
            s3.key: (2, 긴_끝, 6, "낱말"),       # −6 필요 — 하한 −4 밖
            box.key: (2, 긴_끝, 1)}             # 줄 당김 후보도 아니고(끝줄이 길다) 벌어지지도 않았다
    calls: list = []
    res = fit_spacing(doc, kit, _저장(doc, tmp_path / "x.hwpx"), _가짜_측정(kit, spec, calls))
    assert [(t.key, s) for t, s in res.done] == [(s1.key, -3)] and res.words == {s1.key}
    assert res.failed == [] and max(c[s3.key] for c in calls) == 4 and all(c[box.key] == 0 for c in calls)
    assert summary(res.done, res.words)[s1.number] == "발문 −3(낱말)"


def test_가짜_여유가_줄_시작을_바꾸면_최소값으로(견본, tmp_path):
    """여유 1을 더했더니 줄 시작이 바뀐다 → 최소값 그대로 둔다(보이는 조판은 최소값 때와 같아야 한다)."""
    kit, doc = 견본
    s1 = targets(doc, kit)[0]
    res = fit_spacing(doc, kit, _저장(doc, tmp_path / "x.hwpx"), _가짜_측정(kit, {s1.key: (3, 짧은_끝, 6, "여유깨짐")}))
    assert [(t.key, s) for t, s in res.done] == [(s1.key, -6)] and res.minimum == {s1.key: 6}


def test_가짜_settle_자간이_배치를_바꾼다(양식_hwpx, tmp_path):
    """(M-8) 자간 맞춤 전 렌더는 2쪽, 맞춘 뒤는 1쪽 — 뒤 단계·총쪽수·Settled가 맞춘 뒤 렌더를 쓴다."""
    kit, doc = _마무리(양식_hwpx, (픽스처 / "기본_5문항.md").read_text(encoding="utf-8"))
    s1 = targets(doc, kit)[0]
    spec = {s1.key: (2, 짧은_끝, 3)}
    한쪽 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 300), "꼬리": True}]
    두쪽 = [{1: _머리들(200, 400, 600), 2: _머리들(150)}, {1: _머리들(120), "꼬리": True}]
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r",
               render_fn=_가짜_렌더(kit, lambda d: 한쪽 if current_spacing(d, s1.key) else 두쪽),
               lines_fn=lambda p, work: (Path(work).mkdir(parents=True), _가짜_측정(kit, spec)(p, work))[1])  # 측정 사본 폴더 흉내
    assert s.render.page_count == 1 and s.first_pages == 2 and not s.pages_added
    assert {f.field_id: f.value for f in HwpxDocument.open(str(tmp_path / "x.hwpx")).list_form_fields()}[
        kit.slots["총쪽수"]] == "1"
    assert not [n for n in s.notes if "꼬리" in n or "넘겼다" in n], s.notes
    assert sorted(p.name for p in (tmp_path / "r" / "자간").iterdir()) == [f"m{s.measures}"]  # 측정 사본은 마지막 것만(M-7)


def test_가짜_그대로_둔_접힘이_자간으로_풀리면_note를_고친다(양식_hwpx, tmp_path):
    """(M-6) 눌러 둔 1행이 ⓪에서 접혀 '그대로 둔다' note가 남았는데, ⓪' 자간 맞춤이 그 줄을 당겨 최종 렌더에서 풀렸다."""
    from test_layout import _답지_쪽

    from exam_kit.layout import choice_layouts
    from exam_kit.scan import scan_markdown

    md = (픽스처 / "답항배치_7문항.md").read_text(encoding="utf-8").replace("## 1. [3.0점]", "## 1. [3.0점] {답항=1행}", 1)
    kit, doc = _마무리(양식_hwpx, md)
    assert choice_layouts(doc, kit)[0] == ("1행", 1)
    row = next(t for t in targets(doc, kit) if t.role == "답지" and t.number == 1)
    scan = scan_markdown(md)
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", scan=scan,
               render_fn=_가짜_렌더(kit, lambda d: _답지_쪽(d, kit, 접힘=set() if current_spacing(d, row.key) else {0})),
               lines_fn=lambda p, work: _가짜_측정(kit, {row.key: (2, 짧은_끝, 2)})(p, work))
    [note] = [n for n in s.notes if n.startswith("1번 답지가 ")]
    assert "그대로 둔다" in note and note.endswith("최종 렌더에서는 풀렸다(자간 맞춤 뒤)")


보기_md = 한줄_넘는_md.split("## 1.")[0].replace("만점: 8", "만점: 4") + """## 1. [4.0점]
<보기>에서 옳은 것만을 고른 것은?

:::보기
ㄱ. 합성 보기 첫째 항목은 한 줄을 넘도록 길게 써서 둘째 줄이 내어쓰기 자리에서 시작하는지 본다.
ㄴ. 둘째 항목은 짧다.
:::

*① ㄱ
② ㄴ
③ ㄱ, ㄴ
④ 없음
⑤ 모두
"""


def test_렌더_보기_항목_자리는_제출본_다수_기하(양식_hwpx, 오라클, tmp_path):
    """〈보기〉 항목 = 제출본 교사 다수 기하(Task 29 판정): 기호 ㄱ·ㄴ(텍스트 층) x = 단 왼끝 + 7.13pt(앞 공백 판 12.41에서
    공백 한 칸만큼 왼쪽), 둘째 줄 첫 글리프 = 단 왼끝 + 26.9~27.6pt(내어쓰기 1950 — 앞 판 2500보다 5.5pt 왼쪽). G3d 렌더 실측 ±0.5pt."""
    from exam_kit.geometry import boxes, column_lefts, hancom_windows_pdf
    from exam_kit.render import render

    kit, doc = _마무리(양식_hwpx, 보기_md)
    out = tmp_path / "b.hwpx"
    doc.save_to_path(str(out))
    pdf = render(out, tmp_path / "r", oracle=오라클).pdf
    import pymupdf

    cl = column_lefts(kit)[0]
    with pymupdf.open(str(pdf)) as d:
        page = d[0]
        if hancom_windows_pdf(pdf):  # Windows 한컴 PDF는 ㄱ·ㄴ도 보이는 Type3 글자다(macOS는 HCRBatang 텍스트 층) — 같은 펜 자리 x0
            type3 = {f[3] for f in page.get_fonts() if f[2] == "Type3"}

            def 기호_글꼴(sp) -> bool:
                return sp["font"] in type3 and sp.get("alpha", 255) > 0
        else:

            def 기호_글꼴(sp) -> bool:
                return sp["font"].startswith("HCRBatang")
        xs = [ch["bbox"][0] - cl for b in page.get_text("rawdict")["blocks"] for ln in b.get("lines", [])
              for sp in ln["spans"] if 기호_글꼴(sp) for ch in sp["chars"] if ch["c"] in "ㄱㄴ"
              and ch["bbox"][0] < cl + 20]
    assert len(xs) >= 2 and all(abs(x - 7.13) <= 0.5 for x in xs), xs
    [box] = [b for b in boxes(pdf, kit) if b.titled]
    assert len(box.lines) >= 2 and 26.9 - 0.5 <= box.lines[1][2] <= 27.6 + 0.5, box.lines


def test_불일치_까닭_분류():
    """줄 대조 불일치를 두 파일의 문단 속성으로 가른다. 〈보기〉는 어긋난 첫 줄 시작 k에 맞는 자리(k = 1: 첫 줄 글 시작 x,
    k ≥ 2: 내어쓰기 x)가 두 판에서 다를 때만 설명된다 — 그 밖은 '설명 없음'."""
    from exam_kit.fit import BOX_CAUSE, FORM_BOX, Target, Traits, mismatch_cause

    글 = "가나다라마바사아자차카타파하"
    두줄, 두줄_다름 = Lines(2, "", 1, 글, (0, 5)), Lines(2, "", 1, 글, (0, 6))
    세줄, 세줄_셋째다름 = Lines(3, "", 1, 글, (0, 5, 9)), Lines(3, "", 1, 글, (0, 5, 10))
    엔진 = Traits(0, -1950, False, (0,))
    보기 = Target((1, 0), 6, "보기", "가")
    양식 = Traits(0, -2500, True, (0,))
    assert mismatch_cause(보기, 두줄, 두줄_다름, 엔진, 양식, m=_M) == f"{FORM_BOX}: 첫 줄 x 534(엔진 0)"
    교사 = Traits(0, -1888, False, (0,))
    assert mismatch_cause(보기, 세줄, 세줄_셋째다름, 엔진, 교사, m=_M) == f"{BOX_CAUSE}: 내어쓰기 x 1888(엔진 1950)"
    # 둘째 줄 시작이 다른데 첫 줄 자리는 같다(내어쓰기만 다르다) — 설명이 안 된다
    assert mismatch_cause(보기, 두줄, 두줄_다름, 엔진, 교사, m=_M).startswith("설명 없음")
    답지 = Target((2, -1), 8, "답지", "가")
    assert mismatch_cause(답지, 세줄, Lines(3, "", 1, 글, (0, 6, 10)), 엔진,
                          Traits(1000, -1600, False, (-4, 0)), m=_M).startswith("제출본 손 자간이 문단 일부 run에만(-4)")
    assert "문서화된 예외" in mismatch_cause(답지, 두줄, 세줄, Traits(1000, -1600, False, (-6,)),
                                         Traits(1000, -1600, False, (0,)), m=_M)
    assert mismatch_cause(답지, 두줄, 두줄_다름, 엔진, 엔진, m=_M) == "설명 없음"
    assert mismatch_cause(답지, 두줄, None, 엔진, None, m=_M).startswith("설명 없음")


def test_벌어짐은_탭_줄을_빼고_줄마다():
    """(M-b) 탭 배치형 답지 줄은 벌어짐이 아니라 칸 — 0. 줄마다 값이 나오고 gap_ratio는 그 최댓값."""
    from exam_kit.fit import gap_ratio, line_gaps

    ln = Lines(3, "", 1, "가 나 다\t라 마 바 사 아", (0, 6, 9), (30000, 30000, 30000))
    gaps = line_gaps(ln, _M)
    assert len(gaps) == 2 and gaps[0] == 0.0 and gaps[1] > 0 and gap_ratio(ln, _M) == gaps[1]


def test_측정은_한_번_더_해_본다(tmp_path):
    """(M-a) 한컴 저장이 한 번 실패하면 한 번 더 — 두 번 실패하면 RenderUnavailable."""
    from exam_kit.fit import hancom_lines
    from exam_kit.render import RenderUnavailable

    src = _꾸러미(tmp_path / "a.hwpx")

    class 오라클:
        def __init__(self, 실패):
            self.실패, self.호출 = 실패, 0

        def refresh_document(self, path):
            self.호출 += 1
            return self.호출 > self.실패

    o = 오라클(1)
    assert hancom_lines(src, tmp_path / "m", oracle=o) == {} and o.호출 == 2
    names = [p.name for p in (tmp_path / "m").iterdir()]
    assert len(names) == 2 and len(set(names)) == 2  # (m-1) 재시도는 새 무작위 이름의 새 사본으로
    with pytest.raises(RenderUnavailable, match="2회"):
        hancom_lines(src, tmp_path / "m2", oracle=오라클(2))

def test_가짜_끌어올림은_벌어진_줄_다음_줄이_움직여야(견본, tmp_path):
    """(M-c) 가장 벌어진 줄 i 다음 줄(i+1)의 시작이 뒤로 가야 끌어올림 — 다른 줄만 바뀌면 성공이 아니다."""
    kit, doc = 견본
    s1 = [t for t in targets(doc, kit) if t.role == "발문"][0]
    res = fit_spacing(doc, kit, _저장(doc, tmp_path / "x.hwpx"), _가짜_측정(kit, {s1.key: (3, 긴_끝, 1, "낱말엉뚱")}))
    assert res.done == [] and res.rounds == 1 + 4  # −1 ~ −4를 다 재 보고 그만둔다


# ---- Task 29 후속: 나눔 지시 · 박스 높이 · 두 관점 대조 ----------------------------------------

def _나눔(doc, k):
    from exam_kit.layout import group_starts

    el = 최상위(doc)[group_starts(doc)[k]].element
    return el.get("columnBreak"), el.get("pageBreak")


def 최상위(doc):
    return list(doc.sections[0].paragraphs)


def test_나눔_지시는_묶음_첫_문단에(양식_hwpx):
    """{단나눔}은 문항 머리에 단 나눔, 세트 첫 문항의 {쪽나눔}은 세트 머리(묶음 첫 문단)에 쪽 나눔."""
    md = (픽스처 / "견본_전유형.md").read_text(encoding="utf-8")
    md = md.replace("## 3. [10.5점]", "## 3. [10.5점] {단나눔}").replace("### 7. [9.5점]", "### 7. [9.5점] {쪽나눔}")
    kit, doc = _마무리(양식_hwpx, md)
    assert _나눔(doc, 2) == ("1", "0") and _나눔(doc, 6) == ("0", "1") and _나눔(doc, 1) == ("0", "0")
    from exam_kit.layout import group_starts

    assert 최상위(doc)[group_starts(doc)[6]].element.findtext(f".//{q('hp', 't')}").startswith("[7∼8]")  # 세트 머리


def test_가짜_지시된_나눔은_루프가_바꾸지_않는다(양식_hwpx, tmp_path):
    """3번 {쪽나눔} — 렌더가 3번을 1쪽 오른쪽 단 맨 위에 두어도(가짜) 루프의 흐름 고정(단 나눔)이 쪽 나눔을 덮지 않는다."""
    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8").replace("## 3. [4.5점] {답항=5행}", "## 3. [4.5점] {답항=5행} {쪽나눔}")
    kit, doc = _마무리(양식_hwpx, md)
    assert _나눔(doc, 2) == ("0", "1")
    한쪽 = [{1: _머리들(200, 400), 2: _머리들(120, 300, 500), "꼬리": True}]
    settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=_가짜_렌더(kit, lambda d: 한쪽), fit=False)
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert _나눔(saved, 2) == ("0", "1")  # 지시 그대로(흐름 고정이라면 단 나눔으로 바꿨을 자리)
    assert _나눔(saved, 3) == ("0", "0")


def test_박스_높이는_잰_줄_수로(양식_hwpx):
    """resize_boxes: 내용 행 높이 = (줄 수 합 − 1) × 피치 + _M.box_extra(_box와 같은 식) — 줄 수가 줄면 박스도 준다."""
    from exam_kit.compose import resize_boxes

    kit, doc = _마무리(양식_hwpx, (픽스처 / "박스_4문항.md").read_text(encoding="utf-8"))
    items = [t for t in targets(doc, kit) if t.role == "보기" and t.number == 1]
    assert len(items) == 2
    i = items[0].key[0]
    tbl = next(x for r in 최상위(doc)[i].element.findall(q("hp", "run")) for x in r if x.tag == q("hp", "tbl"))
    before = int(tbl.find(q("hp", "sz")).get("height"))

    def 줄(n):
        return {t.key: Lines(n, "", 1, t.text) for t in items}

    assert resize_boxes(doc, kit, 줄(1)) == 0  # 조판(한 줄씩 → 견본 높이 6336)과 같다 — 그대로
    assert resize_boxes(doc, kit, 줄(2)) == 1  # 두 줄씩이면 늘린다
    cells = [tc for tc in tbl.iter(q("hp", "tc")) if tc.find(q("hp", "cellAddr")).get("rowAddr") == "2"]
    pitch = _M.line_pitch[160]  # (보기)박스안내용 줄간격 160%
    want = (4 - 1) * pitch + _M.box_extra
    assert {int(tc.find(q("hp", "cellSz")).get("height")) for tc in cells} == {want}
    assert int(tbl.find(q("hp", "sz")).get("height")) == before - kit.box_min_height + want
    assert resize_boxes(doc, kit, {}) == 0  # 잰 줄이 없으면 건드리지 않는다


def test_두_관점_대조_저장_캐시(견본):
    """diff_rows: 새 조판 기준(①)과 같고 저장 캐시(②)와만 다른 문단은 '제출본 저장 줄 캐시(출제 PC 배치)'."""
    from exam_kit.fit import CACHE_CAUSE, Traits, diff_rows

    kit, doc = 견본
    ts = targets(doc, kit)
    t = next(x for x in ts if x.role == "발문")
    ours = {x.key: Lines(1, "", 1, x.text, (0,)) for x in ts} | {t.key: Lines(2, "", 1, t.text, (0, 10))}
    ref_key = {x.key: (x.key[0] + 100, x.key[1]) for x in ts}
    fresh = {ref_key[x.key]: v for x, v in ((x, ours[x.key]) for x in ts)}
    cached = dict(fresh) | {ref_key[t.key]: Lines(2, "", 1, t.text, (0, 8))}
    tr = {k: Traits(0, 0, False, (0,)) for k in list(ours) + list(fresh)}
    rows1 = diff_rows(doc, kit, ours, tr, fresh, tr)
    rows2 = diff_rows(doc, kit, ours, tr, cached, tr, fresh)
    assert all(c == "" for *_, c in rows1)
    assert [(x.key, c.split(" — ")[0]) for x, _, _, c in rows2 if c] == [(t.key, CACHE_CAUSE)]


def _꾸러미(path, *, mimetype_first=True, header='<hh:head xmlns:hh="h"/>'):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        items = [("mimetype", "application/hwp+zip", zipfile.ZIP_STORED),
                 ("Contents/header.xml", header, zipfile.ZIP_DEFLATED),
                 ("Contents/section0.xml", '<hs:sec xmlns:hs="s"/>', zipfile.ZIP_DEFLATED)]
        for name, data, how in (items if mimetype_first else items[1:] + items[:1]):
            z.writestr(zipfile.ZipInfo(name), data, compress_type=how)
    return path


def test_꾸러미_검사(tmp_path):
    """(m-2) 한컴에 넘기기 전: zip 무결성·첫 항목 무압축 mimetype·section0·header 파싱 — 어기면 ValueError, 한컴을 부르지 않는다."""
    from exam_kit.fit import hancom_lines
    from exam_kit.render import check_package

    check_package(_꾸러미(tmp_path / "ok.hwpx"))
    for name, kw in (("순서", {"mimetype_first": False}), ("헤더", {"header": "<hh:head"})):
        with pytest.raises(ValueError, match="한컴에 넘길 수 없는"):
            check_package(_꾸러미(tmp_path / f"{name}.hwpx", **kw))
    (tmp_path / "반쪽.hwpx").write_bytes((tmp_path / "ok.hwpx").read_bytes()[:40])
    with pytest.raises(ValueError, match="한컴에 넘길 수 없는"):
        check_package(tmp_path / "반쪽.hwpx")

    class 부르면_안_됨:
        def refresh_document(self, path):
            raise AssertionError("검사 전에 한컴을 불렀다")

    with pytest.raises(ValueError):
        hancom_lines(tmp_path / "반쪽.hwpx", tmp_path / "m", oracle=부르면_안_됨())


def test_박스는_양식_견본_높이_밑으로_가지_않는다(양식_hwpx):
    """(I-1) 한 줄짜리 항목 셋 — 조판도 resize_boxes도 내용 행을 kit.box_min_height(양식 견본 내용 셀 6336) 밑으로 두지 않는다."""
    from exam_kit.compose import resize_boxes

    kit, doc = _마무리(양식_hwpx, (픽스처 / "박스_4문항.md").read_text(encoding="utf-8"))
    assert kit.box_min_height == 6336
    items = [t for t in targets(doc, kit) if t.role == "보기" and t.number == 1]
    i = items[0].key[0]
    tbl = next(x for r in 최상위(doc)[i].element.findall(q("hp", "run")) for x in r if x.tag == q("hp", "tbl"))
    rows = [tc for tc in tbl.iter(q("hp", "tc")) if tc.find(q("hp", "cellAddr")).get("rowAddr") == "2"]
    heights = {int(tc.find(q("hp", "cellSz")).get("height")) for tc in rows}
    assert heights == {6336}  # 추정(두 줄 = 3781)보다 견본 높이가 크다
    assert resize_boxes(doc, kit, {t.key: Lines(1, "", 1, t.text) for t in items}) == 0
    assert {int(tc.find(q("hp", "cellSz")).get("height")) for tc in rows} == {6336}


def test_양식_검사는_견본_박스_높이를_킷과_대조한다(양식_hwpx):
    from dataclasses import replace as dreplace

    from exam_kit.kit import load_kit, verify_kit

    kit = load_kit(kit_dir())
    assert not [m for m in verify_kit(kit, form_path=양식_hwpx) if "box_min_height" in m]
    assert [m for m in verify_kit(dreplace(kit, box_min_height=6000), form_path=양식_hwpx) if "box_min_height" in m]


표_넘침_md = 한줄_넘는_md.split("## 1.")[0] + """## 1. [4.0점]
합성 표를 보고 옳은 것은?

:::자료
| 구분 | 합성 누적 점수 | 첫째 모둠 결과 | 둘째 모둠 결과 | 셋째 모둠 결과 |
|---|---:|---:|---:|---:|
| 가 | 31 | 17 | 23 | 29 |
:::

*① 가
② 나
③ 다
④ 라
⑤ 마

## 2. [4.0점]
합성 답항표를 고른 것은?

:::답항표 머리="거친 칸|남은 칸|값"
① 가→나→다 | 가→다 | 3
② 가→나→다→라→마→바 | 가→라→바 | 12
*③ 가→나→라→바 | 가→라→바 | 7
④ 가→다→라→마→바 | 가→다→바 | 7
⑤ 가→나→다→라→바 | 가→다→바 | 15
:::
"""


def test_렌더_넘치는_표는_낱말_사이에서만_접힌다(양식_hwpx, 오라클, tmp_path):
    """(Task 19) 칸 글이 다 들어가지 않는 표 — 열마다 가장 긴 낱말을 먼저 주어, 칸 글이 접히면 띄어쓰기 자리에서만 접힌다.
    답항표는 긴 칸이 접히지 않게 글 길이에 맞춘다(전에는 균등 칸이라 긴 화살표 줄이 두 줄로 접혔다). 합성 글만 쓴다."""
    from exam_kit.fit import hancom_lines

    kit, doc = _마무리(양식_hwpx, 표_넘침_md)
    out = tmp_path / "t.hwpx"
    doc.save_to_path(str(out))
    lines = hancom_lines(out, tmp_path / "m", oracle=오라클)
    cells = []
    ps = 최상위(doc)
    for i, p in list(enumerate(ps))[1:-1]:  # 관리박스(첫 문단)·꼬리 박스(끝 문단)는 양식 표 — 뺀다
        for tbl in (x for r in p.element.findall(q("hp", "run")) for x in r if x.tag == q("hp", "tbl")):
            for j, sub in enumerate(list(p.element.iter(q("hp", "p")))[1:]):
                if any(a is tbl for a in sub.iterancestors(q("hp", "tbl"))) and para_text(sub).strip():
                    cells.append(lines[(i, j)])
    assert cells
    for ln in cells:  # 접힌 줄은 모두 띄어쓰기 뒤에서 시작한다(낱말 한가운데서 접히지 않았다)
        assert all(ln.text[s - 1] in " \n" for s in ln.starts[1:]), (ln.text, ln.starts)
    assert any(ln.n > 1 for ln in cells if "→" not in ln.text)  # 넘치는 표라 실제로 접힌 칸이 있다(가지 확인)
    answer = [ln for ln in cells if "→" in ln.text]
    assert answer and all(ln.n == 1 for ln in answer)  # 답항표 칸은 한 줄

    tbl = next(x for p in 최상위(doc) for r in p.element.findall(q("hp", "run")) for x in r
               if x.tag == q("hp", "tbl") and x.get("rowCnt") == "6")
    ws = [int(tc.find(q("hp", "cellSz")).get("width")) for tc in tbl.find(q("hp", "tr")).findall(q("hp", "tc"))]
    assert ws[0] == _M.mark_col and ws[1] > ws[3]  # 긴 첫째 칸이 짧은 값 칸보다 넓다
