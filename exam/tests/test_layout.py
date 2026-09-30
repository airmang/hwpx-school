from dataclasses import replace
from functools import partial
from pathlib import Path

import pymupdf
import pytest
from _helpers import 최상위_문단, 텍스트
from hwpx.document import HwpxDocument
from test_geometry import _글리프, _머리

from _kits import kit_dir
from exam_kit.compose import case_prev, compose
from exam_kit.geometry import (
    ColumnLayout,
    PageLayout,
    body_bottom,
    column_lefts,
    separator_x,
    splits,
    tail_box_top,
)
from exam_kit.kit import load_kit
from exam_kit.layout import (
    DIST_SAFETY,
    group_starts,
    head_places,
    set_break,
    tail_problem,
)
from exam_kit.layout import settle as _settle
from exam_kit.prepare import finalize_form, prepare_document
from exam_kit.render import RenderResult
from exam_kit.scan import scan_markdown
from exam_kit.slots import fill_slots
from exam_kit.verify import question_heads, verify_render

킷_디렉터리 = kit_dir()
픽스처 = Path(__file__).resolve().parent / "fixtures"

# 이 파일의 루프 테스트(분할·꼬리·간격·접힘)는 자간 맞춤(⓪')·균형 배치(⓪'')를 끈다 — 실렌더 테스트의 배치 수치가 자간 없는 조판으로
# 잰 값이고, 가짜 렌더 테스트는 한컴 측정을 부르면 안 된다. 자간 맞춤은 test_fit에서 따로 본다.
settle = partial(_settle, fit=False, balance=False)

# 실측 길이의 합성 발문·답지(test_verify의 옛 M10 소재) — 문항 수로 마지막 쪽 오른쪽 단을 비우거나 채운다.
# 렌더 실측(09-23): 10문항 = 2쪽 왼쪽 단에서 끝남(오른쪽 단 빔), 14문항 = 2쪽 오른쪽 단이 꼬리 박스 자리까지 참.
_발문 = [
    "인공지능 모델의 성능을 평가할 때 고려해야 할 점으로 가장 적절한 것은?",
    "다음은 어느 학교의 학생 데이터를 이용해 분류 모델을 만드는 과정을 설명한 글이다. 이 과정에서 학습 데이터와 테스트 데이터를 나누는 까닭으로 가장 적절한 것은?",
    "탐색 알고리즘에서 휴리스틱 함수의 값이 실제 비용보다 항상 크지 않을 때 보장되는 성질을 설명한 것으로 가장 적절한 것은?",
    "k-최근접 이웃 알고리즘에 대한 설명으로 적절하지 않은 것은?",
]
_답지 = [
    "데이터의 양이 많을수록 항상 성능이 좋아진다.",
    "학습에 쓰지 않은 데이터로 평가해야 새로운 데이터에 대한 성능을 가늠할 수 있다.",
    "정확도만으로는 집단별 오류의 차이를 알 수 없으므로 정밀도와 재현율을 함께 살펴본다.",
    "모델이 복잡할수록 과적합의 위험이 줄어든다.",
    "특징의 단위가 다르면 거리 계산이 한쪽 특징에 치우칠 수 있다.",
]


def 합성_md(n: int) -> str:
    head = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8").split("---")[1].replace("만점: 20", f"만점: {4 * n}")
    out = [f"---{head}---", ""]
    for k in range(1, n + 1):
        out += [f"## {k}. [4.0점]", _발문[k % 4], ""]
        out += [f"{'*' if i == k % 5 else ''}{m} {_답지[(k + i) % 5]}" for i, m in enumerate("①②③④⑤")]
        out.append("")
    return "\n".join(out)


def _마무리(양식_hwpx, md: str):
    kit = load_kit(킷_디렉터리)
    scan = scan_markdown(md)
    doc, prepared = prepare_document(양식_hwpx, kit)
    fill_slots(doc, kit, scan.front, question_count=len(scan.questions),
               total_points=sum(x.points for x in scan.questions))
    prepared = prepared.refresh(doc)
    compose(doc, scan, kit, answer_key=False, image_root=픽스처)
    finalize_form(doc, kit, prepared)
    return kit, doc


# ---- 문서 쪽 ----------------------------------------------------------------

def test_묶음_첫_문단(양식_hwpx):
    _, doc = _마무리(양식_hwpx, (픽스처 / "기본_5문항.md").read_text(encoding="utf-8"))
    assert group_starts(doc) == question_heads(doc)  # 세트 없음 — 묶음 첫 문단 = 머리
    md = (픽스처 / "견본_전유형.md").read_text(encoding="utf-8")
    _, doc = _마무리(양식_hwpx, md)
    ps = 최상위_문단(doc)
    heads, starts = question_heads(doc), group_starts(doc)
    sets = [k for k, (h, s) in enumerate(zip(heads, starts)) if h != s]
    assert sets, "견본_전유형에 세트가 있다"
    for k in sets:
        assert 텍스트(ps[starts[k]].element).startswith("[")  # 세트 첫 문항의 묶음은 세트 머리 `[a∼b]`부터
    set_break(doc, starts[1], "column")
    assert (ps[starts[1]].element.get("columnBreak"), ps[starts[1]].element.get("pageBreak")) == ("1", "0")
    set_break(doc, starts[1], "page")
    assert (ps[starts[1]].element.get("columnBreak"), ps[starts[1]].element.get("pageBreak")) == ("0", "1")


def _쪽(page, *cols, tail=None):
    return PageLayout(page, tuple(ColumnLayout(page, i, 100.0, b, tuple(h), bool(h) if b else None)
                                  for i, (b, h) in enumerate(cols, 1)), tail)


def test_꼬리_자리_판정():
    kit = load_kit(킷_디렉터리)
    top = tail_box_top(kit)
    box = (371.3, top, 680.5, top + 89.8)
    limit = top - kit.tailbox["room"] / 100
    assert tail_problem([_쪽(1, (900.0, [300.0]), (None, []), tail=box)], kit) is None           # 오른쪽 단 빔
    assert tail_problem([_쪽(1, (900.0, [300.0]), (limit - 1, [120.0]), tail=box)], kit) is None  # 여유까지 비어 있음
    assert "침범" in tail_problem([_쪽(1, (900.0, [300.0]), (limit + 1, [120.0]), tail=box)], kit)
    assert "빈 쪽" in tail_problem([_쪽(1, (900.0, [300.0]), (930.0, [120.0])), _쪽(2, (None, []), (None, []), tail=box)], kit)
    with pytest.raises(ValueError, match="꼬리 박스를 찾지 못했다"):  # 문항을 옮길 일이 아니다(양식·측정 문제)
        tail_problem([_쪽(1, (900.0, [300.0]), (None, []))], kit)
    assert head_places([_쪽(1, (900.0, [300.0, 500.0]), (800.0, [120.0]))]) == [(1, 1), (1, 1), (1, 2)]


def test_간격_기본은_distribute():
    import inspect

    from exam_kit import build

    assert inspect.signature(settle).parameters["gap"].default == "distribute"  # G2 판정(09-26)
    assert inspect.signature(build.build).parameters["gap"].default is None  # 없으면 킷 habits.json의 gap_mode
    kit = load_kit(킷_디렉터리)
    assert (kit.gap_mode, kit.pack) == ("distribute", "balanced")  # G2·G4 판정(검수 교사 단 바닥 맞춤)
    assert kit.question_gap_min == 880  # 반 줄 — 간격 줄이기 켬


def test_간격_이름_검사(양식_hwpx, tmp_path):
    kit, doc = _마무리(양식_hwpx, (픽스처 / "기본_5문항.md").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="gap"):
        settle(doc, kit, tmp_path / "x.hwpx", tmp_path, gap="even")


# ---- 실한컴 렌더 --------------------------------------------------------------

def _굳힘(양식_hwpx, n: int, tmp_path, gap: str, 오라클):
    from exam_kit.render import render

    kit, doc = _마무리(양식_hwpx, 합성_md(n))
    out = tmp_path / f"합성_{n}_{gap}.hwpx"
    s = settle(doc, kit, out, tmp_path / f"r_{n}_{gap}", gap=gap,
               render_fn=lambda h, d: render(h, d, oracle=오라클))
    return kit, doc, out, s


def _총쪽수(doc, kit) -> str:
    return {f.field_id: f.value for f in doc.list_form_fields()}[kit.slots["총쪽수"]]


def test_렌더_오른쪽_단이_빈_경우(양식_hwpx, 오라클, tmp_path):
    kit, doc, out, s = _굳힘(양식_hwpx, 10, tmp_path, "fixed", 오라클)
    last = s.layout[-1]
    assert s.render.page_count == 2 and s.notes == []
    assert last.columns[-1].bottom is None and last.tail_box is not None  # 마지막 문항은 왼쪽 단에서 끝나고 박스는 오른쪽 단
    assert splits(s.render.pdf, kit) == []
    assert _총쪽수(doc, kit) == "2"
    assert verify_render(s.render, HwpxDocument.open(str(out)), kit, expected_pages=2) == []  # M10


def test_렌더_짧은_1쪽(양식_hwpx, 오라클, tmp_path):
    """Task 13 발견: 1쪽에 다 들어가는 문항 — 빈 2쪽 없이 1쪽 오른쪽 단 아래에 박스."""
    kit, doc, out, s = _굳힘(양식_hwpx, 3, tmp_path, "fixed", 오라클)
    assert s.render.page_count == 1 and s.notes == [] and _총쪽수(doc, kit) == "1"
    assert verify_render(s.render, HwpxDocument.open(str(out)), kit, expected_pages=1) == []


def test_렌더_오른쪽_단이_찬_경우(양식_hwpx, 오라클, tmp_path):
    """14문항: 그냥 두면 한글이 닻을 3쪽으로 밀어 빈 3쪽에 박스만 앉는다 → 14번을 3쪽으로 넘기고 경고."""
    kit, doc, out, s = _굳힘(양식_hwpx, 14, tmp_path, "fixed", 오라클)
    assert s.renders >= 2 and s.render.page_count == 3
    assert [n for n in s.notes if "14번" in n and "쪽 추가" in n], s.notes
    assert s.first_pages == 2 and s.pages_added  # 첫 렌더는 이미 3쪽(박스만 앉은 빈 3쪽) — 본문 기준 2쪽 → 3쪽
    assert head_places(s.layout)[-1] == (3, 1) and not any(p.blank for p in s.layout)
    assert splits(s.render.pdf, kit) == [] and _총쪽수(doc, kit) == "3"
    assert verify_render(s.render, HwpxDocument.open(str(out)), kit, expected_pages=3) == []
    assert {f.code for f in verify_render(s.render, HwpxDocument.open(str(out)), kit, expected_pages=4)} == {"M10"}


def test_렌더_간격_나눔(양식_hwpx, 오라클, tmp_path):
    """distribute: 배치(문항 → 쪽·단)는 fixed와 같고, 마지막 내용 단을 뺀 단은 끝이 본문 하단 근처로 맞춰진다.
    단, 꼬리 자리 때문에 14번을 3쪽으로 넘겨 보낸 2쪽 오른쪽 단(11·12·13번)은 고정 간격 — 머리 자리가 fixed와 같다(G2)."""
    kit, _, _, fixed = _굳힘(양식_hwpx, 14, tmp_path, "fixed", 오라클)
    kit, _, out, s = _굳힘(양식_hwpx, 14, tmp_path, "distribute", 오라클)
    assert head_places(s.layout) == head_places(fixed.layout) and s.render.page_count == 3
    last = max((c.page, c.col) for p in s.layout for c in p.columns if c.bottom is not None)
    moved = (2, 2)
    assert [k + 1 for k, pl in enumerate(head_places(s.layout)) if pl == moved] == [11, 12, 13]
    for p in s.layout:
        for c in p.columns:
            if (c.page, c.col) == moved:
                want = fixed.layout[c.page - 1].columns[c.col - 1].heads
                assert all(abs(a - b) < 0.5 for a, b in zip(c.heads, want)) and len(c.heads) == len(want), (c.heads, want)
            elif c.bottom is not None and (c.page, c.col) != last and len(c.heads) > 1:
                assert body_bottom(kit) - DIST_SAFETY - 6 < c.bottom <= body_bottom(kit), (c.page, c.col, c.bottom)
    assert verify_render(s.render, HwpxDocument.open(str(out)), kit, expected_pages=3) == []


# 한 줄짜리 5행 답지 — 합성 14번(답지 7줄)이 5줄이 되어 2쪽 오른쪽 단이 꼬리 자리를 9.3pt 넘친다(맨 위 간격 0 뒤 렌더 실측
# 아래끝 862.1 vs 한계 847.0 — 15.1pt). 그 단의 줄일 수 있는 양은 3 × 8.8 = 26.4pt.
_한줄_답지 = ("데이터의 양이 많을수록 항상 성능이 좋아진다.", "모델이 복잡할수록 과적합의 위험이 줄어든다.",
            "특징의 단위가 다르면 거리 계산이 치우친다.", "학습 데이터와 평가 데이터는 나누어 쓴다.", "정밀도와 재현율을 함께 살펴본다.")


def 짧은_끝_md(n: int) -> str:
    """합성_md(n)에서 마지막 문항 답지만 한 줄짜리로(5행 그대로)."""
    head = 합성_md(n).rsplit(f"## {n}. [4.0점]", 1)[0]
    return head + f"## {n}. [4.0점]\n{_발문[n % 4]}\n\n" + "\n".join(
        f"{'*' if i == n % 5 else ''}{m} {t}" for i, (m, t) in enumerate(zip("①②③④⑤", _한줄_답지))) + "\n"


def test_렌더_간격_줄이기로_쪽을_지킨다(양식_hwpx, 오라클, tmp_path):
    """G2(하한 880): 14문항에서 14번 답지만 한 줄짜리로 — 2쪽 오른쪽 단이 꼬리 자리를 조금(< 줄일 수 있는 양) 넘친다.
    그 단의 간격을 줄여 2쪽을 지킨다(넘기지 않는다). 하한을 끄면(1760) 같은 원고가 3쪽이 된다."""
    from exam_kit.render import render

    def 굳힘(kit, tag):
        _, doc = _마무리(양식_hwpx, 짧은_끝_md(14))
        out = tmp_path / f"{tag}.hwpx"
        return doc, out, settle(doc, kit, out, tmp_path / f"r_{tag}", render_fn=lambda h, d: render(h, d, oracle=오라클))

    kit = load_kit(킷_디렉터리)
    _, _, off = 굳힘(replace(kit, question_gap_min=kit.question_gap), "끔")
    assert off.render.page_count == 3 and off.pages_added, off.notes  # 줄이기 없이는 쪽 추가
    doc, out, s = 굳힘(kit, "켬")
    assert s.render.page_count == 2 and not s.pages_added, s.notes
    assert [n for n in s.notes if "2쪽 오른쪽 단 문항 간격을 1760 → " in n] and not [n for n in s.notes if "넘겼다" in n]
    saved = HwpxDocument.open(str(out))
    right = [k for k, pl in enumerate(head_places(s.layout)) if pl == (2, 2)]
    gaps = [_간격(saved, k) for k in right]
    assert gaps[0] == 0 and all(kit.question_gap_min <= g < kit.question_gap for g in gaps[1:]), gaps
    assert tail_problem(s.layout, kit) is None and splits(s.render.pdf, kit) == []
    assert verify_render(s.render, saved, kit, expected_pages=2) == []


# ---- 가짜 렌더로 루프 분기 -----------------------------------------------------
# render_fn이 저장된 hwpx 상태(나눔·간격·총쪽수)를 읽고 그에 맞는 합성 PDF를 낸다 — 루프가 고친 것이 파일에
# 닿았는지까지 본다(되돌림이 저장 안 되면 다음 렌더가 여전히 '넘친' PDF를 낸다).


def _가짜_pdf(path: Path, kit, pages) -> Path:
    """pages: [{1: [("머리"|"줄", y), …], 2: […], "꼬리": bool}] — 머리 = `N.` 줄, 줄 = 답지 줄(왼여백 10.5)."""
    doc = pymupdf.open()
    lefts, sx = column_lefts(kit), separator_x(kit)
    for spec in pages:
        page = doc.new_page(width=kit.page["width"] / 100, height=kit.page["height"] / 100)
        page.draw_line((sx, 99.2), (sx, 960), width=0.5)
        for col in (1, 2):
            for kind, y, *xs in spec.get(col, []):
                if kind == "머리":
                    _머리(page, lefts[col - 1], y)
                else:  # 줄: 답지 자리(dx 10.5)에 글리프 하나, xs가 있으면 그 dx들에(탭 칸 원문자)
                    for x in (xs[0] if xs else [10.5]):
                        _글리프(page, lefts[col - 1] + x, y)
        if spec.get("꼬리"):
            x0, top = lefts[1], tail_box_top(kit)
            x1, bot = x0 + kit.tailbox["width"] / 100, top + kit.tailbox["height"] / 100
            for a, b in (((x0, top), (x1, top)), ((x0, bot), (x1, bot)), ((x0, top), (x0, bot)), ((x1, top), (x1, bot))):
                page.draw_line(a, b, width=0.36)
    doc.save(str(path))
    return path


def _가짜_렌더(kit, choose):
    """choose(저장된 문서) → 쪽 명세. 호출마다 새 PDF."""
    def render_fn(hwpx, out_dir):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pages = choose(HwpxDocument.open(str(hwpx)))
        pdf = _가짜_pdf(out_dir / "fake.pdf", kit, pages)
        return RenderResult(pdf=pdf, pages=[], page_count=len(pages), seconds=0.0, hwpx_sha256="")
    return render_fn


def _머리들(*ys):
    return [("머리", y) for y in ys]


def _나눔(doc, k: int) -> tuple[str, str]:
    el = 최상위_문단(doc)[group_starts(doc)[k]].element
    return el.get("columnBreak"), el.get("pageBreak")


def _간격(doc, k: int) -> int:
    return case_prev(doc.headers[0], 최상위_문단(doc)[group_starts(doc)[k]].element.get("paraPrIDRef"))


@pytest.fixture
def 다섯(양식_hwpx):
    return _마무리(양식_hwpx, (픽스처 / "기본_5문항.md").read_text(encoding="utf-8"))


def test_가짜_머리_수가_다르면_멈춘다(다섯, tmp_path):
    kit, doc = 다섯
    fake = _가짜_렌더(kit, lambda d: [{1: _머리들(200, 400), 2: _머리들(150, 300), "꼬리": True}])
    with pytest.raises(ValueError, match="문항 머리 4개 ≠ 문서의 문항 5개"):
        settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=fake)


def test_가짜_분할_해소_단_나눔(다섯, tmp_path):
    """3번이 1쪽 1단에서 2단으로 이어진다 → 3번 묶음 첫 문단에 단 나눔."""
    kit, doc = 다섯
    나뉨 = [{1: _머리들(200, 400, 600), 2: [("줄", 120)] + _머리들(300, 500), "꼬리": True}]
    풀림 = [{1: _머리들(200, 400), 2: _머리들(120, 300, 500), "꼬리": True}]
    fake = _가짜_렌더(kit, lambda d: 풀림 if _나눔(d, 2) == ("1", "0") else 나뉨)
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", gap="fixed", render_fn=fake)  # 간격 나눔은 따로 본다
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert s.notes == [] and _나눔(saved, 2) == ("1", "0")
    assert _간격(saved, 2) == 0  # 단 맨 위 문항은 위 간격 0
    assert _간격(saved, 3) == kit.question_gap  # 단 안 문항은 그대로


def test_가짜_분할_해소_쪽_나눔(다섯, tmp_path):
    """5번이 1쪽 2단에서 2쪽 1단으로 이어진다 → 쪽 경계라 쪽 나눔."""
    kit, doc = 다섯
    나뉨 = [{1: _머리들(200, 400), 2: _머리들(150, 400, 700)}, {1: [("줄", 120)], "꼬리": True}]
    풀림 = [{1: _머리들(200, 400), 2: _머리들(150, 400)}, {1: _머리들(120), "꼬리": True}]
    fake = _가짜_렌더(kit, lambda d: 풀림 if _나눔(d, 4) == ("0", "1") else 나뉨)
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=fake)
    assert s.notes == [] and _나눔(HwpxDocument.open(str(tmp_path / "x.hwpx")), 4) == ("0", "1")


def test_가짜_분할_못_푸는_긴_문항(다섯, tmp_path):
    """1번이 1단 맨 위에서 시작해 2단으로 넘친다(단보다 긴 문항) — 나눔을 넣지 않고 알린다, 최종 재검사도 남긴다."""
    kit, doc = 다섯
    fake = _가짜_렌더(kit, lambda d: [{1: _머리들(200), 2: [("줄", 120)] + _머리들(300, 400, 500, 600), "꼬리": True}])
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=fake)
    assert [n for n in s.notes if "1번 문항이 한 단보다 길어" in n]
    assert [n for n in s.notes if "최종 렌더에 문항 분할" in n]
    assert _나눔(HwpxDocument.open(str(tmp_path / "x.hwpx")), 0) == ("0", "0")


_침범_y = 850.0  # 줄 글리프 아래끝 859 > 자리 한계(856.84 − 9.8 = 847.04), 윗선 위에서 시작


def test_가짜_꼬리_자리를_못_만드는_한_문항(양식_hwpx, tmp_path):
    kit, doc = _마무리(양식_hwpx, 합성_md(1))
    fake = _가짜_렌더(kit, lambda d: [{2: _머리들(500) + [("줄", _침범_y)], "꼬리": True}])
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=fake)
    assert [n for n in s.notes if "꼬리 박스 자리를 만들 수 없다" in n]
    assert [n for n in s.notes if "최종 렌더의 꼬리 박스가 제자리가 아니다" in n]


def test_가짜_꼬리_3회_소진과_줄이기_실패(다섯, tmp_path):
    kit, doc = 다섯
    fake = _가짜_렌더(kit, lambda d: [{1: _머리들(200, 400, 600), 2: _머리들(150, 500) + [("줄", _침범_y)], "꼬리": True}])
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=fake)
    assert [n for n in s.notes if "3회 안에 만들지 못했다" in n]
    assert [n for n in s.notes if n.startswith("꼬리 박스 자리가 없어 5번을")]  # 같은 문항은 한 번만 적는다
    assert not [n for n in s.notes if "줄였다" in n]
    assert [n for n in s.notes if "모자라 줄이지 않았다" in n]  # 줄 아래끝 기준 넘침 12pt > 한 문항 8.8pt


def test_가짜_꼬리_박스를_못_찾으면_멈춘다(다섯, tmp_path):
    kit, doc = 다섯
    fake = _가짜_렌더(kit, lambda d: [{1: _머리들(200, 400, 600), 2: _머리들(150, 500)}])
    with pytest.raises(ValueError, match="꼬리 박스를 찾지 못했다"):
        settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=fake)


def test_가짜_꼬리_간격_줄이기(다섯, tmp_path):
    """킷 하한 880(G2): 오른쪽 단 5번 위 간격을 줄여 쪽을 지킨다. 넘친 단만 줄인다 — 왼쪽 단은 나눔이 박혀 있어
    줄여도 오른쪽 단이 당겨지지 않는다(fixed로 돌려 왼쪽 단 간격이 그대로인지 본다)."""
    kit, doc = 다섯
    assert kit.question_gap_min == 880
    넘침 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 500) + [("줄", _침범_y - 5)], "꼬리": True}]
    맞음 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 495) + [("줄", 800)], "꼬리": True}]
    fake = _가짜_렌더(kit, lambda d: 맞음 if _간격(d, 4) < kit.question_gap else 넘침)
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", gap="fixed", render_fn=fake)
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert [n for n in s.notes if "1쪽 오른쪽 단 문항 간격을 1760 → " in n] and not [n for n in s.notes if "넘겼다" in n]
    assert kit.question_gap_min <= _간격(saved, 4) < kit.question_gap
    assert _간격(saved, 1) == _간격(saved, 2) == kit.question_gap  # 왼쪽 단은 그대로
    assert _간격(saved, 3) == 0  # 단 맨 위는 줄이기 뒤에도 0


def test_가짜_넘침이_줄일_양보다_크면_렌더_없이_넘긴다(다섯, tmp_path):
    """줄 아래끝 기준 넘침 16.0pt > 줄일 수 있는 양(문항 하나 × 8.8pt) — 줄인 간격으로 렌더하지 않고 알린 뒤 넘긴다.
    (가짜 글리프는 박스 윗선 위에서 시작해야 단 내용으로 잰다 — y 854 → 아래끝 863.0, 한계 856.84 − 9.8)"""
    kit, doc = 다섯
    넘침 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 500) + [("줄", 854)], "꼬리": True}]
    넘김 = [{1: _머리들(200, 400, 600), 2: _머리들(150)}, {1: _머리들(120), "꼬리": True}]
    본_간격: set[int] = set()

    def choose(d):
        본_간격.add(_간격(d, 4))
        return 넘김 if _나눔(d, 4) == ("0", "1") else 넘침

    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", gap="fixed", render_fn=_가짜_렌더(kit, choose))
    assert 본_간격 <= {0, kit.question_gap}  # 줄인 간격이 렌더에 간 적이 없다
    assert [n for n in s.notes if "16.0pt 넘쳐" in n and "모자라 줄이지 않았다" in n], s.notes
    assert [n for n in s.notes if n.startswith("꼬리 박스 자리가 없어 5번을")]


def test_가짜_넘겨_보낸_단은_간격을_나누지_않는다(다섯, tmp_path):
    """distribute: 꼬리 자리 때문에 5번을 2쪽으로 넘기면 1쪽 오른쪽 단(3·4번)은 고정 간격으로 둔다 — 빈자리가 단 아래로
    모인다(G2). 다른 단(1쪽 왼쪽 단)은 나눈다."""
    kit, doc = 다섯
    넘침 = [{1: _머리들(200, 400), 2: _머리들(150, 400, 700) + [("줄", _침범_y)], "꼬리": True}]  # 줄여 봐도 가짜는 그대로 넘친다
    넘김 = [{1: _머리들(200, 400), 2: _머리들(150, 400)}, {1: _머리들(120), "꼬리": True}]
    fake = _가짜_렌더(kit, lambda d: 넘김 if _나눔(d, 4) == ("0", "1") else 넘침)
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=fake)  # 기본 = distribute
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert [n for n in s.notes if n.startswith("꼬리 박스 자리가 없어 5번을")], s.notes
    assert head_places(s.layout) == [(1, 1), (1, 1), (1, 2), (1, 2), (2, 1)]
    assert _간격(saved, 3) == kit.question_gap  # 넘겨 보낸 단: 고정
    assert _간격(saved, 1) > kit.question_gap   # 다른 단: 나눔


def test_가짜_꼬리_간격_줄이기_실패는_되돌린다(다섯, tmp_path):
    """줄인 간격으로도 넘치면 되돌린 뒤(파일까지) 넘긴다 — 넘김 렌더가 본 5번 간격이 원래 값이어야 한다."""
    kit, doc = 다섯
    넘침 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 500) + [("줄", _침범_y - 5)], "꼬리": True}]  # 줄일 만한 넘침
    넘김 = [{1: _머리들(200, 400, 600), 2: _머리들(150)}, {1: _머리들(120), "꼬리": True}]
    본: list[tuple[tuple[str, str], int]] = []

    def choose(d):
        본.append((_나눔(d, 4), _간격(d, 4)))
        return 넘김 if _나눔(d, 4) == ("0", "1") else 넘침

    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", gap="fixed", render_fn=_가짜_렌더(kit, choose))
    assert [n for n in s.notes if "넘겼다" in n] and not [n for n in s.notes if "줄였다" in n]
    assert [g for _, g in 본 if kit.question_gap_min <= g < kit.question_gap]  # 줄여 본 렌더가 있었다
    first_move = next(g for br, g in 본 if br == ("0", "1"))
    assert first_move == kit.question_gap  # 되돌림이 파일에 닿은 뒤 넘겼다


def test_가짜_간격_나눔_되돌림이_파일에_닿는다(다섯, tmp_path):
    """나눈 간격이 배치를 바꾸면(넘침) 되돌린다 — 되돌림이 저장되지 않으면 마지막 렌더가 여전히 넘친 배치다(C1)."""
    kit, doc = 다섯
    원래 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 300), "꼬리": True}]
    넘침 = [{1: _머리들(200, 400), 2: _머리들(120, 150, 300), "꼬리": True}]

    def choose(d):
        return 넘침 if any(_간격(d, k) > kit.question_gap for k in range(5)) else 원래

    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", gap="distribute", render_fn=_가짜_렌더(kit, choose))
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert [n for n in s.notes if "되돌렸다" in n]
    assert head_places(s.layout) == [(1, 1)] * 3 + [(1, 2)] * 2
    assert all(_간격(saved, k) <= kit.question_gap for k in range(5))


def test_가짜_총쪽수를_채웠더니_쪽이_바뀜(다섯, tmp_path):
    kit, doc = 다섯
    한쪽 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 300), "꼬리": True}]
    두쪽 = [{1: _머리들(200, 400, 600), 2: _머리들(150)}, {1: _머리들(120), "꼬리": True}]

    def choose(d):
        return 두쪽 if _총쪽수(d, kit) == "1" else 한쪽

    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=_가짜_렌더(kit, choose))
    assert [n for n in s.notes if "총쪽수를 1로 채웠더니 렌더 쪽수가 2로 바뀌었다" in n]
    assert s.first_pages == 1 and s.pages_added  # 글귀가 아니라 쪽수로 — build가 [쪽 추가]를 이것으로 가린다


# ---- 접힌 답지(fix 2) ----------------------------------------------------------

def _답지_쪽(doc, kit, *, 접힘: set[int] = frozenset(), 어긋남: set[int] = frozenset()):
    """문서의 배치형대로 답지 줄을 그린 한 쪽(두 단) — 접힘 문항은 줄 하나 더, 어긋남 문항은 둘째 칸 원문자를 비킨다."""
    from exam_kit.compose import Samples, _Composer, 배치형
    from exam_kit.layout import choice_layouts

    c = _Composer(doc, kit, Samples(None, None, None), answer_key=False)
    lays = choice_layouts(doc, kit)
    cols: dict[int, list] = {1: [], 2: []}
    col, y = 1, 200.0
    for k in range(len(question_heads(doc))):
        rows = []
        if k in lays:
            kind, _ = lays[k]
            role, per_row = 배치형[kind]
            starts = c.slots(role, max(per_row))
            for cnt in per_row:
                xs = [st / 100 + 0.55 for st in starts[:cnt]]
                if k in 어긋남 and cnt > 1:
                    xs[1] -= 20
                rows.append(("줄", 0, xs))
            if k in 접힘:
                rows.append(("줄", 0))
        else:
            rows = [("줄", 0)] * 5
        need = 17.6 * (len(rows) + 2)
        if y + need > 900:
            col, y = 2, 120.0
        cols[col].append(("머리", y))
        for i, r in enumerate(rows, 1):
            cols[col].append((r[0], y + 17.6 * (i + 1), *r[2:]))
        y += need
    return [{1: cols[1], 2: cols[2], "꼬리": True}]


@pytest.fixture
def 배치(양식_hwpx):
    md = (픽스처 / "답항배치_7문항.md").read_text(encoding="utf-8")
    kit = load_kit(킷_디렉터리)
    scan = scan_markdown(md)  # 누름 없는 원고 — 루프가 접힌 1번을 느슨한 형으로 다시 쓸 수 있다
    doc, prepared = prepare_document(양식_hwpx, kit)
    fill_slots(doc, kit, scan.front, question_count=7, total_points=sum(x.points for x in scan.questions))
    prepared = prepared.refresh(doc)
    # 1번은 1행으로 조판해 둔다(자동 선택은 1행을 고르지 않는다 — G3 ③)
    compose(doc, scan_markdown(md.replace("## 1. [3.0점]", "## 1. [3.0점] {답항=1행}", 1)), kit, answer_key=True)
    finalize_form(doc, kit, prepared)
    return kit, doc, scan


def test_가짜_접힌_답지는_느슨한_형으로(배치, tmp_path):
    """1번(1행)이 접히고 2번(2행) 칸이 어긋난다 → 1번 2행, 2번 3행으로 다시 쓰고, 정답 형광펜은 그대로."""
    from exam_kit.layout import choice_layouts
    from exam_kit.verify import extract_answers

    kit, doc, scan = 배치
    before = extract_answers(doc)

    def choose(d):
        lays = choice_layouts(d, kit)
        return _답지_쪽(d, kit, 접힘={0} if lays.get(0, ("",))[0] == "1행" else set(),
                         어긋남={1} if lays.get(1, ("",))[0] == "2행" else set())

    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=_가짜_렌더(kit, choose), scan=scan)
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    lays = choice_layouts(saved, kit)
    assert lays[0] == ("2행", 2) and lays[1] == ("3행", 3)
    assert [n for n in s.notes if n.startswith("1번 답지가 1행에서") and "2행으로" in n]
    assert [n for n in s.notes if n.startswith("2번 답지가 2행에서") and "3행으로" in n]
    assert extract_answers(saved) == before
    assert not [n for n in s.notes if "최종 렌더에 접힌" in n]


def test_가짜_눌러_둔_형은_알리기만(배치, tmp_path):
    from dataclasses import replace as dreplace

    from exam_kit.layout import choice_layouts

    kit, doc, scan = 배치
    qs = list(scan.questions)
    qs[0] = dreplace(qs[0], override="1행")
    forced = dreplace(scan, questions=tuple(qs))
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", scan=forced,
               render_fn=_가짜_렌더(kit, lambda d: _답지_쪽(d, kit, 접힘={0})))
    assert choice_layouts(HwpxDocument.open(str(tmp_path / "x.hwpx")), kit)[0] == ("1행", 1)
    assert [n for n in s.notes if "눌러 둔 형({답항=1행})" in n] and len([n for n in s.notes if n.startswith("1번")]) == 1


def test_렌더_견본_접힌_답지를_풀고_남기지_않는다(양식_hwpx, 오라클, tmp_path):
    """견본_전유형 9번은 {답항=3행}으로 눌러 칸을 넘친다(조판 note). 누름을 뺀 원고로 settle → 5행으로 다시 쓰고 접힘 0."""
    from exam_kit.layout import choice_layouts, wrapped_choices
    from exam_kit.render import render

    md = (픽스처 / "견본_전유형.md").read_text(encoding="utf-8")
    kit, doc = _마무리(양식_hwpx, md)
    assert choice_layouts(doc, kit)[8] == ("3행", 3)
    free = scan_markdown(md.replace("## 9. [10.5점] {답항=3행}", "## 9. [10.5점]"))
    s = settle(doc, kit, tmp_path / "c.hwpx", tmp_path / "r", scan=free,
               render_fn=lambda h, d: render(h, d, oracle=오라클))
    saved = HwpxDocument.open(str(tmp_path / "c.hwpx"))
    assert [n for n in s.notes if n.startswith("9번 답지가 3행에서") and "5행으로" in n], s.notes
    assert 8 not in choice_layouts(saved, kit)
    assert wrapped_choices(saved, s.render.pdf, kit) == []
    assert verify_render(s.render, saved, kit, expected_pages=s.render.page_count) == []


# ---- fix 3: 맨 위 간격을 뺀 뒤에 꼬리 판단 · scan 대조 · 마지막 답지 줄 보호 ---------------------

def test_가짜_맨_위_간격을_빼면_들어가는_넘침은_넘기지_않는다(다섯, tmp_path):
    """오른쪽 단이 꼬리 자리를 ~10pt 넘치지만, 그 단 맨 위 4번의 위 간격(17.6pt)을 빼면 들어간다 → 넘기지 않는다."""
    kit, doc = 다섯
    한계 = tail_box_top(kit) - kit.tailbox["room"] / 100  # 847.04
    넘침 = [{1: _머리들(200, 400, 600), 2: _머리들(150, 500) + [("줄", 한계 + 10 - 10)], "꼬리": True}]  # 아래끝 = 한계 + 10pt
    맞음 = [{1: _머리들(200, 400, 600), 2: _머리들(132.4, 482.4) + [("줄", 한계 + 10 - 10 - 17.6)], "꼬리": True}]
    fake = _가짜_렌더(kit, lambda d: 맞음 if _간격(d, 3) == 0 else 넘침)
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=fake)
    assert not [n for n in s.notes if "넘겼다" in n or "꼬리" in n], s.notes
    assert s.render.page_count == 1 and s.first_pages == 1 and not s.pages_added


def test_원고와_문서가_다르면_멈춘다(배치, 다섯, tmp_path):
    from exam_kit.compose import relayout_choices

    kit, doc, scan = 배치
    _, 다른_doc = 다섯
    with pytest.raises(ValueError, match="문항 7개 ≠ 문서 문항 5개"):
        settle(다른_doc, kit, tmp_path / "x.hwpx", tmp_path / "r", scan=scan, render_fn=_가짜_렌더(kit, lambda d: []))
    with pytest.raises(ValueError, match="1번 답지가 원고와 다르다"):
        relayout_choices(doc, kit, replace(scan.questions[1], number="1"), "3행", answer_key=True)  # 2번 답지로 1번을 덮으려 한다


def test_답지_다시_쓰기는_마지막_줄_보호를_따른다(배치):
    """마지막 답지 줄의 keepWithNext는 원래 줄을 따른다(세트 안 문항처럼 뒤와 묶여 있던 줄이면 그대로 묶인다)."""
    from exam_kit.compose import choice_paragraphs, derive_para_pr, relayout_choices

    kit, doc, scan = 배치
    header = doc.headers[0]

    def 마지막_keep(n):
        el = 최상위_문단(doc)[choice_paragraphs(doc, kit, n)[-1]].element
        pp = header.element.find(f".//{{*}}paraPr[@id='{el.get('paraPrIDRef')}']")
        return pp.find("{*}breakSetting").get("keepWithNext")

    relayout_choices(doc, kit, scan.questions[0], "3행", answer_key=True)
    assert 마지막_keep(1) == "0"
    last = 최상위_문단(doc)[choice_paragraphs(doc, kit, 2)[-1]].element  # 2번 마지막 줄을 뒤와 묶인 줄로 바꿔 둔다
    last.set("paraPrIDRef", derive_para_pr(header, last.get("paraPrIDRef"),
                                            break_setting={"keep_with_next": True, "keep_lines": True}))
    relayout_choices(doc, kit, scan.questions[1], "3행", answer_key=True)
    assert 마지막_keep(2) == "1"


def test_가짜_간격_나눔은_상한까지(다섯, tmp_path):
    """(Task 30) distribute가 문항 하나에 더하는 간격은 kit.gap_extra_max까지 — 넘는 몫은 단 아래에 남긴다."""
    kit, doc = 다섯
    kit = replace(kit, gap_extra_max=1000)
    원래 = [{1: _머리들(200, 300, 400), 2: _머리들(150, 250), "꼬리": True}]  # 1쪽 1단 아래가 크게 빈다
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", gap="distribute", render_fn=_가짜_렌더(kit, lambda d: 원래))
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert _간격(saved, 1) == _간격(saved, 2) == kit.question_gap + 1000, s.notes


def test_단_나눔_균형():
    """(Task 30) pack_columns — 넘침 없이, 쪽수 최소가 먼저, 그다음 그 쪽들의 모든 단(비는 단 포함)이 고르게.
    단 한계 100, 간격 0."""
    from exam_kit.layout import pack_columns

    top = lambda j: 0.0  # noqa: E731
    # 한 쪽 두 단: 60+30 | 30+60+10 (남는 10·0) — 한 쪽이 최소
    assert pack_columns([60, 30, 30, 60, 10], 0.0, top, 100, 100, {}) == [0, 0, 1, 1, 1]
    # 두 쪽 네 단: 앞 세 단에 몰고(90·90·20) 넷째 단을 비우는 대신 네 단에 고르게(50·40·50·60)
    assert pack_columns([50, 40, 50, 40, 20], 0.0, top, 100, 100, {}) == [0, 1, 2, 3, 3]
    assert pack_columns([55, 50, 45, 40, 35, 30], 0.0, top, 100, 100, {}) == [0, 1, 2, 2, 3, 3]
    # 나눔 지시: 3번 묶음(인덱스 2)은 {쪽나눔} — 새 쪽 왼쪽 단(2)에서. 지시로 비는 오른쪽 단도 빈 단으로 세므로
    # (m-1) 앞 두 묶음은 두 단에 나눈다(10·10 | 빈 단보다 10 | 10이 고르다)
    assert pack_columns([10, 10, 10], 0.0, top, 100, 100, {2: "page"}) == [0, 1, 2]
    # 단나눔 지시: 2번 묶음(인덱스 1)은 단 맨 위 — 오른쪽 단(1)에서
    assert pack_columns([10, 10, 10], 0.0, top, 100, 100, {1: "column"}) == [0, 1, 1]
    # 큰 n에서도 재귀 한도와 상관없다(표를 뒤에서 채운다) — 한 단에 둘씩
    assert pack_columns([50.0] * 400, 0.0, top, 100, 100, {}) == [k // 2 for k in range(400)]
    # 꼬리 자리: 마지막 묶음이 오른쪽 단이면 한계 60 — 넘치면 다음 쪽 왼쪽 단으로(오른쪽 단을 비운다)
    assert pack_columns([90, 70], 0.0, top, 100, 60, {}) == [0, 2]
    # 간격: 두 묶음 사이에 gap
    assert pack_columns([50, 45, 10], 10.0, top, 100, 100, {}) == [0, 1, 1]


# ---- 균형 배치 루프(⓪'') — 가짜 렌더 ---------------------------------------------
# 가짜 렌더는 저장된 문서의 나눔을 따라 머리를 놓는다: 나눔이 없으면 한 단에 셋까지 흐르고, 단 나눔이면 다음 단, 쪽 나눔이면
# 다음 쪽 왼쪽 단. follow=False면 나눔을 무시하고 늘 자연 흐름(높이 추정이 틀린 경우).


def _흐름(doc, follow: bool = True) -> list[int]:
    cols, col, n = [], 0, 0
    for k in range(len(group_starts(doc))):
        c, p = _나눔(doc, k) if follow else ("0", "0")
        if k and p == "1":
            col, n = col + 1 + (col + 1) % 2, 0
        elif k and (c == "1" or n == 3):
            col, n = col + 1, 0
        cols.append(col)
        n += 1
    return cols


def _흐름_렌더(kit, follow: bool = True):
    def choose(doc):
        cols = _흐름(doc, follow)
        pages = [{} for _ in range(max(cols) // 2 + 1)]
        for j in sorted(set(cols)):
            pages[j // 2][j % 2 + 1] = _머리들(*[200 + 200 * i for i in range(cols.count(j))])
        pages[-1]["꼬리"] = True
        return pages
    return _가짜_렌더(kit, choose)


def _균형_루프(kit, doc, tmp_path, fake):
    from exam_kit.layout import _Loop

    loop = _Loop(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", fake)
    loop.pin_directed()
    return loop


def test_가짜_균형_계획을_박고_자리가_맞으면_끝(다섯, tmp_path, monkeypatch):
    """(I-1 a) 계획 ≠ 자연 흐름 → 나눔을 박고 재렌더, 자리가 계획과 같으면 balanced에 남긴다."""
    from exam_kit.layout import _Loop

    kit, doc = 다섯
    monkeypatch.setattr(_Loop, "plan_columns", lambda self, rr, lay: [0, 0, 1, 1, 1])
    loop = _균형_루프(kit, doc, tmp_path, _흐름_렌더(kit))
    rr, lay = loop.render()
    assert _흐름(doc) == [0, 0, 0, 1, 1]  # 자연 흐름은 계획과 다르다
    rr, lay = loop.balance(rr, lay)
    want = [(1, 1), (1, 1), (1, 2), (1, 2), (1, 2)]
    assert head_places(lay) == want and loop.balanced == want and loop.notes == []
    assert loop.n == 2  # 첫 렌더 + 박은 뒤 한 번
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert [_나눔(saved, k) for k in range(5)] == [("0", "0"), ("0", "0"), ("1", "0"), ("0", "0"), ("0", "0")]


def test_가짜_균형_두_번_어긋나면_원래대로(다섯, tmp_path, monkeypatch):
    """(I-1 b) 렌더 자리가 두 번 다 계획과 다르면 박은 나눔을 거두고 루프 시작 전 나눔으로 되돌린다 — 지시 나눔은 그대로, note."""
    from exam_kit.layout import _Loop

    kit, doc = 다섯
    set_break(doc, group_starts(doc)[1], "column")  # 원고 지시({단나눔})로 들어온 나눔 — pin_directed가 붙든다
    monkeypatch.setattr(_Loop, "plan_columns", lambda self, rr, lay: [0, 1, 2, 2, 3])
    loop = _균형_루프(kit, doc, tmp_path, _흐름_렌더(kit, follow=False))
    set_break(doc, group_starts(doc)[3], "page")  # 앞 단계가 박은(지시 아닌) 나눔 — 되돌림의 '원래'
    before = [_나눔(doc, k) for k in range(5)]
    rr, lay = loop.render()
    rr, lay = loop.balance(rr, lay)
    assert loop.balanced is None
    assert [n for n in loop.notes if "두 번 다 달라 원래 흐름으로" in n]
    assert loop.n == 3  # 첫 렌더 + 박은 뒤 한 번(둘째 계획이 같아 다시 박을 것 없음 = 둘째 어긋남) + 되돌린 뒤 한 번
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert [_나눔(saved, k) for k in range(5)] == before == [
        ("0", "0"), ("1", "0"), ("0", "0"), ("0", "1"), ("0", "0")]


def test_가짜_균형은_단나눔_지시를_지킨다(양식_hwpx, tmp_path, monkeypatch):
    """(I-1 c) 원고 {단나눔}은 계획의 제약(brk)으로 넘어가고, 박은 뒤에도 파일에 남는다."""
    import exam_kit.layout as L
    from exam_kit.geometry import Extent

    md = (픽스처 / "기본_5문항.md").read_text(encoding="utf-8")
    kit, doc = _마무리(양식_hwpx, md.replace("## 4. [3.0점] {답항=5행}", "## 4. [3.0점] {답항=5행} {단나눔}"))
    assert _나눔(doc, 3) == ("1", "0")

    def 높이(pdf, kit, set_first=frozenset()):  # 묶음 다섯, 150pt씩 — 지시가 없으면 한 단(셋)·두 단으로도 담긴다
        lay = L.measure(pdf, kit)
        return [Extent(((p, c, y - 2.0, y + 148.0),)) for (p, c), y in
                zip(head_places(lay), [h for pg in lay for col in pg.columns for h in col.heads])]

    seen = []
    real = L.pack_columns

    def 엿보기(h, gap, top, limit, tail_limit, brk):
        seen.append(dict(brk))
        return real(h, gap, top, limit, tail_limit, brk)

    monkeypatch.setattr(L, "group_extents", 높이)
    monkeypatch.setattr(L, "pack_columns", 엿보기)
    s = _settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", fit=False, render_fn=_흐름_렌더(kit))
    assert seen and all(b == {3: "column"} for b in seen)
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert _나눔(saved, 3) == ("1", "0"), s.notes
    assert head_places(s.layout)[3] != head_places(s.layout)[2]  # 4번은 단 맨 위


def test_가짜_균형_둘째_계획이_없으면_되돌린다(다섯, tmp_path, monkeypatch):
    """박은 뒤 자리가 어긋났는데 둘째 계획이 None(잴 수 없음·담을 수 없음)이면 박은 나눔을 거두고 note."""
    from exam_kit.layout import _Loop

    kit, doc = 다섯
    plans = iter([[0, 0, 1, 1, 1], None])
    monkeypatch.setattr(_Loop, "plan_columns", lambda self, rr, lay: next(plans))
    loop = _균형_루프(kit, doc, tmp_path, _흐름_렌더(kit, follow=False))
    rr, lay = loop.render()
    rr, lay = loop.balance(rr, lay)
    assert loop.balanced is None and [n for n in loop.notes if "원래 흐름으로" in n]
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert [_나눔(saved, k) for k in range(5)] == [("0", "0")] * 5


# ---- 단 아래 맞춤(Task 31) — 검토 교사 "문제를 끝에 맞추도록" ------------------------------


def _단(s, p, c):
    return s.layout[p - 1].columns[c - 1]


def test_가짜_마지막_쪽_왼쪽_단도_아래에_맞춘다(다섯, tmp_path):
    """마지막 쪽 왼쪽 단(머리 둘)도 나눈다 — 마지막 문항 끝이 단 한계(본문 하단 − DIST_SAFETY)에 닿는 간격.
    한 문항 단(1쪽 오른쪽 단)은 위에 붙인 채(간격 0)로 둔다."""
    kit, doc = 다섯
    두쪽 = [{1: _머리들(200, 400), 2: _머리들(150)}, {1: _머리들(120, 300), "꼬리": True}]
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=_가짜_렌더(kit, lambda d: 두쪽))
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert head_places(s.layout) == [(1, 1), (1, 1), (1, 2), (2, 1), (2, 1)], s.notes
    slack = body_bottom(kit) - _단(s, 2, 1).bottom - DIST_SAFETY
    assert _간격(saved, 4) == kit.question_gap + int(slack * 100)  # 마지막 쪽 왼쪽 단
    assert _간격(saved, 1) > kit.question_gap                          # 1쪽 왼쪽 단
    assert _간격(saved, 2) == 0                                        # 한 문항 단 — 늘리지 않는다


def test_가짜_꼬리_단은_꼬리_박스_위까지(다섯, tmp_path):
    """마지막 쪽 오른쪽 단은 꼬리 박스 위 여유(_limit)에 맞춘다 — 본문 하단이 아니라. 문항 사이 둘에 고르게."""
    from exam_kit.layout import _limit

    kit, doc = 다섯
    한쪽 = [{1: _머리들(200, 400), 2: _머리들(150, 300, 450), "꼬리": True}]
    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", render_fn=_가짜_렌더(kit, lambda d: 한쪽))
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    slack = _limit(kit) - _단(s, 1, 2).bottom - DIST_SAFETY
    assert _간격(saved, 3) == _간격(saved, 4) == kit.question_gap + int(slack * 100 / 2), s.notes
    assert _limit(kit) < body_bottom(kit)
    left = body_bottom(kit) - _단(s, 1, 1).bottom - DIST_SAFETY
    assert _간격(saved, 1) == kit.question_gap + int(left * 100)  # 왼쪽 단은 본문 하단까지


def test_가짜_간격_나눔이_분할을_만들면_되돌린다(다섯, tmp_path):
    """(Task 31 I-1) 나눈 간격으로 1쪽 왼쪽 단의 2번이 오른쪽 단으로 이어지면(머리 자리는 그대로) 되돌리고 한 줄 더 남겨 다시 —
    가짜는 간격이 늘면 늘 나뉘므로 끝내 고정 간격으로 되돌린다."""
    kit, doc = 다섯
    원래 = [{1: _머리들(200, 400), 2: _머리들(150, 300, 450), "꼬리": True}]
    나뉨 = [{1: _머리들(200, 400), 2: [("줄", 120)] + _머리들(150, 300, 450), "꼬리": True}]

    def choose(d):
        return 나뉨 if any(_간격(d, k) > kit.question_gap for k in range(5)) else 원래

    s = settle(doc, kit, tmp_path / "x.hwpx", tmp_path / "r", gap="distribute", render_fn=_가짜_렌더(kit, choose))
    saved = HwpxDocument.open(str(tmp_path / "x.hwpx"))
    assert [n for n in s.notes if "고정 간격으로 되돌렸다" in n], s.notes
    assert all(_간격(saved, k) <= kit.question_gap for k in range(5))
    assert not splits(s.render.pdf, kit)
