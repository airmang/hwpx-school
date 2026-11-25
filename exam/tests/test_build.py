import dataclasses
import os
import re
import subprocess
from functools import partial
from pathlib import Path

import pytest
from _helpers import 최상위_문단
from hwpx.document import HwpxDocument
from test_layout import _가짜_렌더, _머리들

from _kits import kit_dir
from exam_kit import q
import pymupdf
from lxml import etree as ET

from exam_kit.build import (
    BuildResult,
    _old_outputs,
    _reveal,
    add_answer_marks,
    build,
    git_ignored,
    main,
    publish,
    same_layout,
    same_package,
    write_report,
)
from exam_kit.compose import compose
from exam_kit.geometry import ColumnLayout, PageLayout
from exam_kit.kit import load_kit
from exam_kit.prepare import finalize_form, prepare_document
from exam_kit.scan import scan_markdown
from exam_kit.slots import fill_slots
from exam_kit.verify import errors, extract_answers, question_heads, verify_document

킷_디렉터리 = kit_dir()
픽스처 = Path(__file__).resolve().parent / "fixtures"
견본 = 픽스처 / "견본_전유형.md"
견본_정답 = {str(i): m for i, m in zip(range(1, 11), "②④①⑤③②④①④③")}


def _조판(양식_hwpx, *, answer_key: bool):
    kit = load_kit(킷_디렉터리)
    scan = scan_markdown(견본.read_text(encoding="utf-8"))
    doc, prepared = prepare_document(양식_hwpx, kit)
    fill_slots(doc, kit, scan.front, question_count=len(scan.questions),
               total_points=sum(x.points for x in scan.questions))
    prepared = prepared.refresh(doc)
    res = compose(doc, scan, kit, answer_key=answer_key, image_root=픽스처)
    finalize_form(doc, kit, prepared)
    return kit, doc, res


def _형광펜_자리(doc) -> list[tuple[int, str, str, bool]]:
    """(최상위 문단 인덱스, 원문자, 뒤따르는 글, 칸 안인가) — 형광펜마다."""
    out = []
    for i, p in enumerate(최상위_문단(doc)):
        for m in p.element.iter(q("hp", "markpenBegin")):
            end = m.getnext()
            in_cell = any(a.tag == q("hp", "tc") for a in m.iterancestors())
            out.append((i, m.tail, end.tail or "", in_cell))
    return out


# ---- 답 표시본 = 문항지 + 형광펜 ------------------------------------------------

def test_형광펜_더하기는_조판_형광펜과_같은_자리(양식_hwpx):
    kit, plain, res = _조판(양식_hwpx, answer_key=False)
    _, keyed, _ = _조판(양식_hwpx, answer_key=True)
    body = "".join(plain.sections[0].element.itertext())
    add_answer_marks(plain, kit, res.answers)
    assert _형광펜_자리(plain) == _형광펜_자리(keyed)
    assert any(cell for *_, cell in _형광펜_자리(plain))  # 답항표(칸 안) 문항 포함
    assert "".join(plain.sections[0].element.itertext()) == body  # 형광펜은 글자를 바꾸지 않는다
    assert extract_answers(plain) == 견본_정답
    fs = verify_document(plain, kit, expect_answers=견본_정답, answer_key=True, draft=False)
    assert {f.code for f in errors(fs)} & {"M8", "M11"} == set(), fs


def test_형광펜_자리가_없으면_멈춘다(양식_hwpx):
    kit, doc, res = _조판(양식_hwpx, answer_key=False)
    with pytest.raises(ValueError, match="3번"):
        add_answer_marks(doc, kit, {**res.answers, "3": "㉠"})
    with pytest.raises(ValueError, match="4번 정답이 없다"):
        add_answer_marks(doc, kit, {k: v for k, v in res.answers.items() if k != "4"})


def test_빈_형광펜은_정답이_아니다(양식_hwpx):
    kit, doc, _ = _조판(양식_hwpx, answer_key=False)
    t = next(최상위_문단(doc)[question_heads(doc)[0]].element.iter(q("hp", "t")))
    ET.SubElement(t, q("hp", "markpenBegin"), {"color": "#FFFF00"})  # tail 없음
    assert extract_answers(doc) == {}


def test_두_판_꾸러미_대조(양식_hwpx, tmp_path):
    kit, doc, res = _조판(양식_hwpx, answer_key=False)
    plain, key, other = tmp_path / "p.hwpx", tmp_path / "k.hwpx", tmp_path / "o.hwpx"
    doc.save(str(plain))
    k = HwpxDocument.open(str(plain))
    add_answer_marks(k, kit, res.answers)
    k.save(str(key))
    assert same_package(plain, key) == []
    t = next(t for t in k.sections[0].element.iter(q("hp", "t")) if (t.text or "").strip())
    t.text = t.text + "x"  # 형광펜 말고 글자 하나
    k.sections[0].mark_dirty()
    k.save(str(other))
    assert same_package(plain, other) == ["Contents/section0.xml가 다르다(형광펜을 빼고도)"]


# ---- 두 판 배치 대조 -------------------------------------------------------------

def _쪽(page: int, heads1, heads2) -> PageLayout:
    cols = tuple(ColumnLayout(page, c, 99.2, 500.0, tuple(h), True) for c, h in ((1, heads1), (2, heads2)))
    return PageLayout(page, cols, None)


def test_두_판_배치_대조():
    a = [_쪽(1, [300.0, 400.0], [100.0]), _쪽(2, [100.0], [])]
    assert same_layout(a, [_쪽(1, [300.2, 400.0], [100.0]), _쪽(2, [100.0], [])]) == []
    moved = same_layout(a, [_쪽(1, [300.0, 401.0], [100.0]), _쪽(2, [100.0], [])])
    assert len(moved) == 1 and "2번" in moved[0]
    assert same_layout(a, [_쪽(1, [300.0, 400.0], [100.0, 500.0])])  # 쪽 수·배치가 다르다


# ---- 보고서 ----------------------------------------------------------------------

def test_보고서는_확인_필요와_쪽_추가를_드러낸다(tmp_path):
    r = BuildResult(보고=tmp_path / "보고.md", blocked=False, 문항지=tmp_path / "a_문항지.hwpx",
                    답표시본=tmp_path / "a_답표시본.hwpx", page_count=3, pages=(2, 3), draft=True,
                    notes=["조판: 9번 {답항=3행} — 추정 폭이 칸을 넘는다", "렌더: 14번을 다음 쪽으로 넘겼다"])
    write_report(r, md_path=tmp_path / "a.md", compare=tmp_path / "제출본.hwpx")
    text = r.보고.read_text(encoding="utf-8")
    banner = text.split("## ")[0]
    assert text.splitlines()[0].startswith("# ") and "단계:" in banner and "초안: **예**" in banner
    assert "## 확인 필요 (3)" in text and "9번 {답항=3행}" in text
    assert "- **[쪽 추가] 최종 쪽수가 첫 렌더 본문 기준보다 늘었다: 2쪽 → 3쪽" in text  # note 글귀가 아니라 쪽수로
    for p in ("a_문항지.hwpx", "a.md", "제출본.hwpx"):
        assert f'`{_reveal(tmp_path / p)}`' in text
    assert "검증 완료" not in text


def test_쪽_추가는_글귀가_아니라_쪽수로(tmp_path):
    r = BuildResult(보고=tmp_path / "보고.md", blocked=False, 문항지=tmp_path / "a.hwpx", 답표시본=tmp_path / "b.hwpx",
                    pages=(2, 2), notes=["렌더: … (쪽 추가: 최후 수단)"])
    text = write_report(r, md_path=tmp_path / "a.md").read_text(encoding="utf-8")
    assert "[쪽 추가] 최종" not in text and "**[" not in text and "초안: 아니오" in text


def test_규칙_오류를_넘기고_조판했으면_맨_앞에_알린다(tmp_path, capsys):
    from exam_kit.lint import Violation

    r = BuildResult(보고=tmp_path / "보고.md", blocked=False, 문항지=tmp_path / "a.hwpx", 답표시본=tmp_path / "b.hwpx",
                    lint=[Violation("E016", "E", 3, "3번 부정어에 __밑줄__ 없음"), Violation("W019", "W", 3, "…")],
                    notes=["렌더: 무엇"])
    text = write_report(r, md_path=tmp_path / "a.md").read_text(encoding="utf-8")
    first = text.split("## 확인 필요 (2)")[1].strip().splitlines()[0]
    assert first == "- **[규칙 오류 무시] 규칙 오류 1건을 --lint-warn으로 넘기고 조판했다**"
    r.blocked = True  # 막혔으면 넘긴 것이 아니다
    assert "[규칙 오류 무시]" not in write_report(r, md_path=tmp_path / "a.md").read_text(encoding="utf-8")


def _파일들(root: Path, names: list[str]) -> None:
    for n in names:
        (root / n).parent.mkdir(parents=True, exist_ok=True)
        (root / n).write_bytes(b"x")


def _폴더(root: Path) -> dict:
    """폴더 안 모든 것 — 상대 경로 → 바이트(폴더는 None). 호출 앞뒤를 견준다."""
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None) for p in sorted(root.rglob("*"))}


def _바뀐(before: dict, after: dict) -> list[str]:
    """목록이 같은지 보고(다르면 실패), 바이트가 달라진 파일 이름만."""
    assert list(after) == list(before), sorted(set(after) ^ set(before))
    return [k for k in after if after[k] != before[k]]


def test_옛_산출물은_이_원고_것만_고른다(tmp_path):
    mine = ["렌더/시험_문항지_p1.png", "렌더/시험_답표시본_p12.png", "대조/시험_vs_제출본_p3.png", "시험_문항지.hwpx"]
    others = ["렌더/시험_2_문항지_p1.png", "대조/시험_2_vs_제출본_p1.png", "시험_2_문항지.hwpx",
              "렌더/시험_문항지_p1_메모.png", "렌더/시험_메모.png", "보고.md", "_렌더/시험_문항지.hwpx"]
    _파일들(tmp_path, mine + others)
    before = _폴더(tmp_path)
    assert sorted(_old_outputs(tmp_path, "시험")) == sorted(tmp_path / n for n in mine)
    assert _폴더(tmp_path) == before  # 찾기만 한다 — 지우지 않는다


def test_옛_산출물_고르기는_대괄호를_glob으로_읽지_않는다(tmp_path):
    mine = ["렌더/시험[1]_문항지_p1.png", "대조/시험[1]_vs_제출본_p2.png"]
    others = ["렌더/시험1_문항지_p1.png", "대조/시험1_vs_제출본_p2.png"]  # "시험[1]"을 glob으로 읽으면 여기에 맞는다
    _파일들(tmp_path, mine + others)
    assert sorted(_old_outputs(tmp_path, "시험[1]")) == sorted(tmp_path / n for n in mine)


# ---- 한 묶음 게시 ---------------------------------------------------------------

def _새_묶음(stage: Path, out: Path, names: list[str]) -> dict[Path, Path]:
    for n in names:
        (stage / n).parent.mkdir(parents=True, exist_ok=True)
        (stage / n).write_bytes(b"new")
    return {out / n: stage / n for n in names}


def test_게시는_옛_것을_치우고_새_것을_넣는다(tmp_path):
    out, stage, backup = tmp_path / "out", tmp_path / "stage", tmp_path / "이전"
    _파일들(out, ["a_문항지.hwpx", "a_답표시본.hwpx", "렌더/a_문항지_p1.png", "렌더/a_문항지_p2.png", "렌더/b_문항지_p1.png"])
    names = ["a_문항지.hwpx", "a_답표시본.hwpx", "렌더/a_문항지_p1.png", "대조/a_vs_제출본_p1.png"]
    publish(_새_묶음(stage, out, names), _old_outputs(out, "a"), backup)
    after = _폴더(out)
    assert all(after[n] == b"new" for n in names)
    assert "렌더/a_문항지_p2.png" not in after  # 쪽이 줄면 옛 쪽 PNG는 남지 않는다
    assert after["렌더/b_문항지_p1.png"] == b"x"  # 다른 원고의 것은 그대로
    assert not [p for p in stage.rglob("*") if p.is_file()]  # 복사가 아니라 옮김(os.replace)
    assert sorted(p.read_bytes() for p in backup.iterdir()) == [b"x"] * 4  # 옛 것은 backup에 — 부르는 쪽이 지운다


def test_게시가_도중에_실패하면_옛_것을_되돌린다(tmp_path, monkeypatch):
    """둘째 판 자리가 막혀 있으면(Windows: 한/글에 열려 있는 파일) 첫째 판만 새 것인 폴더를 남기지 않는다."""
    import exam_kit.build as B

    out, stage = tmp_path / "out", tmp_path / "stage"
    _파일들(out, ["a_문항지.hwpx", "a_답표시본.hwpx", "렌더/a_문항지_p1.png", "렌더/a_문항지_p2.png"])
    new = _새_묶음(stage, out, ["a_문항지.hwpx", "a_답표시본.hwpx", "렌더/a_문항지_p1.png", "대조/a_vs_제출본_p1.png"])
    before = _폴더(out)
    real = os.replace

    def 막힘(src, dst):
        if Path(dst) == out / "a_답표시본.hwpx" and stage in Path(src).parents:
            raise PermissionError("다른 프로그램이 쓰고 있다")
        return real(src, dst)

    monkeypatch.setattr(B.os, "replace", 막힘)
    with pytest.raises(PermissionError):
        publish(new, _old_outputs(out, "a"), tmp_path / "이전")
    assert _폴더(out) == before  # 목록도 바이트도 그대로(새로 만든 폴더 대조/도 없다)


# ---- 규칙 검사 차단 --------------------------------------------------------------

def _깨진_원고(tmp_path, old: str = "[8.5점]", new: str = "[8점]") -> Path:
    md = tmp_path / "시험.md"
    text = 견본.read_text(encoding="utf-8")
    assert old in text
    md.write_text(text.replace(old, new, 1), encoding="utf-8")
    (tmp_path / "그림.png").write_bytes((픽스처 / "그림.png").read_bytes())
    return md


def _렌더_금지(hwpx, out_dir):
    raise AssertionError("렌더까지 가면 안 된다")


def _옛_산출물(out: Path, stem: str = "시험") -> list[Path]:
    """앞 실행이 남긴 척하는 파일들 — 거부되거나 중간에 멈춘 build는 그대로 둬야 한다."""
    olds = [out / f"{stem}_문항지.hwpx", out / f"{stem}_답표시본.hwpx", out / "렌더" / f"{stem}_문항지_p3.png",
            out / "대조" / f"{stem}_vs_제출본_p4.png", out / "_렌더" / "문항지" / "r9" / "x.pdf"]
    for p in olds:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"old")
    (out / "보고.md").write_text("옛 보고 — 기계 잔존 0", encoding="utf-8")
    (out / "렌더" / "다른원고_문항지_p1.png").write_bytes(b"keep")
    return olds


def test_규칙_오류면_조판하지_않는다(양식_hwpx, tmp_path):
    md = _깨진_원고(tmp_path)
    out = tmp_path / "out"
    olds = _옛_산출물(out)
    before = _폴더(out)
    r = build(md, load_kit(킷_디렉터리), out, form_path=양식_hwpx, render_fn=_렌더_금지)
    assert r.blocked and r.문항지 is None and r.답표시본 is None
    # 거부: 앞선 산출물(두 판·렌더·대조·작업 폴더)과 다른 원고의 것은 그대로, 임시 파일도 없다 — 바뀐 것은 보고서뿐
    assert _바뀐(before, _폴더(out)) == ["보고.md"] and all(p.read_bytes() == b"old" for p in olds)
    text = r.보고.read_text(encoding="utf-8")
    assert "E003" in text and "조판하지 않았다" in text and "옛 보고" not in text and "진행 중" not in text
    assert "앞선 조판" in text and "`시험_문항지.hwpx`" in text  # 남아 있는 두 판이 이번 원고의 것이 아니라고 적는다


class _멈춤(Exception):
    pass


def test_lint_warn이면_경고로_두고_조판한다(양식_hwpx, tmp_path):
    md = _깨진_원고(tmp_path, "이유로 알맞은", "이유로 적합한")  # E014 — 조판은 할 수 있는 규칙 오류
    out = tmp_path / "out"

    seen = []

    def 멈춤(hwpx, out_dir):
        seen.append((Path(hwpx).is_file(), Path(hwpx).parent.name, Path(hwpx).parent.parent))
        raise _멈춤(hwpx)

    olds = _옛_산출물(out)
    before = _폴더(out)
    with pytest.raises(_멈춤):
        build(md, load_kit(킷_디렉터리), out, form_path=양식_hwpx, lint_block=False, render_fn=멈춤)
    assert seen == [(True, "_렌더_새", out)]  # 조판·저장까지 갔다(렌더 루프 첫 렌더 직전) — 새 판은 임시 작업 폴더에서 만든다
    # 중간에 멈춘 실행: 옛 산출물은 그대로이고, 반쯤 된 hwpx도 임시 작업 폴더도 남지 않고, 보고서는 '진행 중'
    assert _바뀐(before, _폴더(out)) == ["보고.md"] and all(p.read_bytes() == b"old" for p in olds)
    text = (out / "보고.md").read_text(encoding="utf-8")
    assert "진행 중" in text and "옛 보고" not in text and "앞선 조판" in text


# ---- 거부·실패한 조판은 앞선 산출물을 그대로 둔다(끝까지 간 조판 뒤) ------------------------------

합성_킷 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"  # 이 묶음은 학교 킷이 있어도 합성 킷·합성 서식으로 돈다
합성_서식 = 합성_킷 / "synthetic_form.hwpx"
합성_원고 = 픽스처 / "합성서식_6문항.md"


def _가짜_조판(monkeypatch):
    """한컴 없이 끝까지 가는 build의 (킷, render_fn). 렌더는 문항 수만큼 머리를 그린 합성 PDF(test_layout._가짜_렌더)에
    쪽 PNG 한 장을 붙인 것이고, 킷의 렌더 판정은 그 PDF에 맞춰 곡선 글리프로 둔다. 자간 맞춤(한컴 측정)은 끈다."""
    import exam_kit.build as B
    from exam_kit.layout import settle

    kit = load_kit(합성_킷)
    kit = dataclasses.replace(kit, render={**kit.render, "glyphs": "curves"})

    def 쪽(doc):
        n = len(question_heads(doc))
        left = n - n // 2
        ys = [150 + 120 * i for i in range(left)]
        return [{1: _머리들(*ys), 2: _머리들(*ys[:n - left]), "꼬리": True}]

    base = _가짜_렌더(kit, 쪽)

    def render_fn(hwpx, out_dir):
        rr = base(hwpx, out_dir)
        png = Path(out_dir) / "p1.png"
        png.write_bytes(b"png of " + Path(hwpx).name.encode("utf-8"))
        return dataclasses.replace(rr, pages=[png])

    monkeypatch.setattr(B, "settle", partial(settle, fit=False))
    return kit, render_fn


def _온전한_원고(tmp_path, 원고: Path = 견본) -> Path:
    md = tmp_path / "시험.md"
    md.write_text(원고.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "그림.png").write_bytes((픽스처 / "그림.png").read_bytes())
    return md


def _한_번_조판(tmp_path, monkeypatch):
    """끝까지 간 조판 한 번 + 그 뒤 손본 문항지(교사가 한/글에서 고쳐 저장한 척) — (킷, render_fn, 원고, out)."""
    kit, render_fn = _가짜_조판(monkeypatch)
    md, out = _온전한_원고(tmp_path), tmp_path / "out"
    first = build(md, kit, out, form_path=합성_서식, render_fn=render_fn, pack="greedy")
    assert not first.blocked and first.문항지 == out / "시험_문항지.hwpx" and first.답표시본 == out / "시험_답표시본.hwpx"
    assert extract_answers(HwpxDocument.open(str(first.답표시본))) == 견본_정답
    assert [p.name for p in first.pngs["문항지"]] == ["시험_문항지_p1.png"] and all(p.is_file() for p in first.pngs["문항지"])
    assert (out / "_렌더").is_dir() and not (out / "_렌더_새").exists()  # 작업 폴더는 끝까지 간 뒤 제 이름으로
    first.문항지.write_bytes(first.문항지.read_bytes() + b"<!-- hand-finished -->")
    return kit, render_fn, md, out


def test_거부한_조판은_앞선_산출물을_그대로_둔다(tmp_path, monkeypatch):
    """조판 → 손봄 → 원고를 고치다 규칙 오류 → 다시 조판이 거부된다. 앞선 두 판·렌더·작업 폴더는 바이트까지 그대로이고
    폴더 목록도 같다(임시 파일 없음). 보고서만 이번 실행(거부)을 적는다."""
    kit, _, md, out = _한_번_조판(tmp_path, monkeypatch)
    before = _폴더(out)
    assert {"시험_문항지.hwpx", "시험_답표시본.hwpx", "렌더/시험_문항지_p1.png", "렌더/시험_답표시본_p1.png",
            "_렌더/시험_문항지.hwpx", "보고.md"} <= set(before)
    _깨진_원고(tmp_path)  # 같은 원고(시험.md)에 배점 합 오류
    r = build(md, kit, out, form_path=합성_서식, render_fn=_렌더_금지, pack="greedy")
    assert r.blocked and r.문항지 is None and r.답표시본 is None
    assert _바뀐(before, _폴더(out)) == ["보고.md"]
    text = r.보고.read_text(encoding="utf-8")
    assert "조판하지 않았다" in text and "앞선 조판" in text and "`시험_문항지.hwpx`" in text and "`시험_답표시본.hwpx`" in text


def test_거부한_조판은_CLI에서도_앞선_두_판을_알린다(tmp_path, monkeypatch, capsys):
    _, _, md, out = _한_번_조판(tmp_path, monkeypatch)
    before = _폴더(out)
    _깨진_원고(tmp_path)
    assert main([str(md), "--kit", str(합성_킷), "--form", str(합성_서식), "--out", str(out)]) == 1
    printed = capsys.readouterr().out
    assert "조판하지 않았다" in printed and "앞선 조판" in printed and "시험_문항지.hwpx" in printed
    assert _바뀐(before, _폴더(out)) == ["보고.md"]


def test_멈춘_조판은_앞선_산출물을_그대로_둔다(tmp_path, monkeypatch):
    """조판 → 손봄 → 다시 조판이 렌더 도중 예외로 멈춘다. 앞선 산출물은 그대로이고 임시 작업 폴더는 남지 않는다."""
    kit, render_fn, md, out = _한_번_조판(tmp_path, monkeypatch)
    before = _폴더(out)
    calls = []

    def 둘째에_멈춤(hwpx, out_dir):
        calls.append(hwpx)
        if len(calls) == 2:
            raise _멈춤(hwpx)
        return render_fn(hwpx, out_dir)

    with pytest.raises(_멈춤):
        build(md, kit, out, form_path=합성_서식, render_fn=둘째에_멈춤, pack="greedy")
    assert _바뀐(before, _폴더(out)) == ["보고.md"]
    text = (out / "보고.md").read_text(encoding="utf-8")
    assert "진행 중" in text and "앞선 조판" in text


def test_열려_있는_옛_산출물은_렌더_전에_알린다(tmp_path, monkeypatch):
    """Windows: 앞선 문항지가 다른 프로그램(한/글)에 열려 있으면 끝에 바꿔 넣을 수 없다 — 긴 렌더를 돌리기 전에 멈추고
    그대로 둔다(제자리 이름 바꾸기로 알아본다)."""
    import exam_kit.build as B

    kit, _, md, out = _한_번_조판(tmp_path, monkeypatch)
    before = _폴더(out)
    real = os.rename

    def 열림(src, dst):
        if Path(src).name == "시험_문항지.hwpx":
            raise PermissionError(13, "다른 프로세스가 파일을 쓰고 있다")
        return real(src, dst)

    monkeypatch.setattr(B.os, "rename", 열림)
    with pytest.raises(PermissionError, match="열려 있어"):
        build(md, kit, out, form_path=합성_서식, render_fn=_렌더_금지, pack="greedy")
    assert _바뀐(before, _폴더(out)) == ["보고.md"]


def test_게시가_막힌_조판은_앞선_산출물을_그대로_둔다(tmp_path, monkeypatch):
    """다시 조판이 끝까지 갔지만 답 표시본 자리를 바꿀 수 없다(열려 있는 파일) — 문항지만 새 것인 폴더를 남기지 않는다."""
    import exam_kit.build as B

    kit, render_fn, md, out = _한_번_조판(tmp_path, monkeypatch)
    before = _폴더(out)
    real = os.replace

    def 막힘(src, dst):
        if Path(dst) == out / "시험_답표시본.hwpx" and Path(src).name == "시험_답표시본.hwpx":
            raise PermissionError("다른 프로그램이 쓰고 있다")
        return real(src, dst)

    monkeypatch.setattr(B.os, "replace", 막힘)
    with pytest.raises(PermissionError):
        build(md, kit, out, form_path=합성_서식, render_fn=render_fn, pack="greedy")
    assert _바뀐(before, _폴더(out)) == ["보고.md"]


def test_다시_조판이_끝까지_가면_옛_것과_바꾼다(tmp_path, monkeypatch):
    kit, render_fn, md, out = _한_번_조판(tmp_path, monkeypatch)
    손본 = (out / "시험_문항지.hwpx").read_bytes()
    _파일들(out, ["렌더/시험_문항지_p9.png", "대조/시험_vs_제출본_p1.png", "렌더/다른원고_문항지_p1.png", "_렌더/옛_작업.txt"])
    r = build(md, kit, out, form_path=합성_서식, render_fn=render_fn, pack="greedy")
    after = _폴더(out)
    assert not r.blocked and after["시험_문항지.hwpx"] != 손본 and after["시험_문항지.hwpx"] == after["_렌더/시험_문항지.hwpx"]
    assert after["시험_답표시본.hwpx"] == after["_렌더/시험_답표시본.hwpx"]
    assert extract_answers(HwpxDocument.open(str(r.문항지))) == {}
    assert "렌더/시험_문항지_p9.png" not in after and "대조/시험_vs_제출본_p1.png" not in after  # 이 원고의 옛 쪽은 남지 않는다
    assert after["렌더/다른원고_문항지_p1.png"] == b"x"
    assert "_렌더/옛_작업.txt" not in after and not [k for k in after if k.startswith("_렌더_새") or "_게시" in k or "_이전" in k]
    assert "진행 중" not in after["보고.md"].decode("utf-8") and "기계 잔존" in after["보고.md"].decode("utf-8")


def test_작업_폴더를_못_바꿔도_조판은_끝난다(tmp_path, monkeypatch):
    """앞 실행의 _렌더/를 다 지우지 못해 이름을 못 바꾸면(열려 있는 pdf 등) 그 위에 겹쳐 넣는다 — 두 판은 이미 게시됐다."""
    import exam_kit.build as B

    kit, render_fn, md, out = _한_번_조판(tmp_path, monkeypatch)
    _파일들(out, ["_렌더/열려_있는.pdf"])
    real_rmtree = B.shutil.rmtree
    monkeypatch.setattr(B.shutil, "rmtree", lambda p, **kw: None if Path(p) == out / "_렌더" else real_rmtree(p, **kw))
    r = build(md, kit, out, form_path=합성_서식, render_fn=render_fn, pack="greedy")
    after = _폴더(out)
    assert not r.blocked and after["시험_문항지.hwpx"] == after["_렌더/시험_문항지.hwpx"] and "_렌더/열려_있는.pdf" in after
    assert not [k for k in after if k.startswith("_렌더_새")] and "진행 중" not in after["보고.md"].decode("utf-8")


def test_작은_수정은_두_판을_한_묶음으로_게시한다(tmp_path, monkeypatch):
    """patch의 게시도 build.publish — 답 표시본 자리가 막히면 문항지만 새 것인 폴더를 남기지 않고, 풀리면 두 판이 함께 선다."""
    import exam_kit.build as B
    from exam_kit.patch import patch

    kit, render_fn = _가짜_조판(monkeypatch)
    md, v1, v2 = _온전한_원고(tmp_path, 합성_원고), tmp_path / "v1", tmp_path / "v2"
    build(md, kit, v1, form_path=합성_서식, render_fn=render_fn, pack="greedy")
    text = md.read_text(encoding="utf-8")
    assert "다음은 탐색 방법에 대한 설명이다." in text
    md.write_text(text.replace("다음은 탐색 방법에 대한 설명이다.", "다음은 여러 탐색 방법에 대한 설명이다.", 1), encoding="utf-8")
    _파일들(v2, ["시험_문항지.hwpx", "시험_답표시본.hwpx"])  # 이 폴더에 앞서 낸 두 판(b"x")
    before = {k: v for k, v in _폴더(v2).items() if not k.startswith("_작업")}
    real = os.replace

    def 막힘(src, dst):
        if Path(dst) == v2 / "시험_답표시본.hwpx" and Path(src).name == "시험_답표시본.hwpx":
            raise PermissionError("다른 프로그램이 쓰고 있다")
        return real(src, dst)

    monkeypatch.setattr(B.os, "replace", 막힘)
    with pytest.raises(PermissionError):
        patch(md, v1, kit, form=합성_서식, out_dir=v2, render_fn=render_fn)
    after = _폴더(v2)
    assert {k: v for k, v in after.items() if not k.startswith("_작업")} == before
    assert not [k for k in after if "_게시" in k or "_이전" in k]
    monkeypatch.setattr(B.os, "replace", real)
    r = patch(md, v1, kit, form=합성_서식, out_dir=v2, render_fn=render_fn)
    assert not r.rebuild and r.changed == ["1번 문단 1"]
    after = _폴더(v2)
    assert r.문항지 == v2 / "시험_문항지.hwpx" and after["시험_문항지.hwpx"] == after["_작업/시험_문항지.hwpx"] != b"x"
    assert after["시험_답표시본.hwpx"] == after["_작업/시험_답표시본.hwpx"] != b"x"
    assert not [k for k in after if "_게시" in k or "_이전" in k]


def test_출력_폴더가_git_무시_대상이_아니면_알린다(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("무시/\n", encoding="utf-8")
    (tmp_path / "무시").mkdir()
    (tmp_path / "보임").mkdir()
    assert git_ignored(tmp_path / "무시") is True
    assert git_ignored(tmp_path / "보임") is False


def test_git_밖이면_모른다(tmp_path):
    assert git_ignored(tmp_path) is None


# ---- CLI 끝까지(실한컴 렌더 — 두 판·보고서·대조 PNG) -------------------------------

def test_CLI_끝까지_실렌더(양식_hwpx, 제출본_hwpx, 오라클, tmp_path, capsys):
    out = tmp_path / "out"
    rc = main([str(견본), "--kit", str(킷_디렉터리), "--form", str(양식_hwpx), "--out", str(out),
               "--compare", str(제출본_hwpx)])
    printed = capsys.readouterr().out
    문항지, 답표시본, 보고 = out / "견본_전유형_문항지.hwpx", out / "견본_전유형_답표시본.hwpx", out / "보고.md"
    assert 문항지.exists() and 답표시본.exists() and 보고.exists()
    assert extract_answers(HwpxDocument.open(str(답표시본))) == 견본_정답
    assert extract_answers(HwpxDocument.open(str(문항지))) == {}
    text = 보고.read_text(encoding="utf-8")
    assert "기계 잔존 0" in text and "검증 완료" not in text
    assert "- 두 판 배치: 같다" in text and "  - M8 " not in text  # 두 판 글자·배치 대조 잔존 없음
    assert "9번" in text.split("## 확인 필요")[1].split("## ")[0]  # 눌러 둔 {답항=3행} 넘침 note
    assert "| 문항 | 쪽 | 단 | 답지 배치형 | 자간 |" in text and re.search(r"\| (발문|답지|보기|자료) −\d+", text)  # 자간 맞춤이 돌았다
    assert "자간 측정" in text
    # 자간 맞춤 뒤 박스 셀을 실제 줄 수로 줄인다 — 〈보기〉 박스 아랫여백이 보통값(≈11.6pt, 한 줄 빈 박스는 20.4pt)
    from exam_kit.geometry import boxes

    last = max((out / "_렌더" / "문항지").glob("r*"), key=lambda d: int(d.name[1:]))
    bs = [b for b in boxes(next(last.glob("*.pdf")), load_kit(킷_디렉터리)) if b.titled]
    # 네 줄 이상은 아랫여백이 보통값, 세 줄 이하는 양식 견본 높이(6336)라 더 넓되 위아래가 고르다
    assert bs and all((b.bottom_gap < 13.0 or len(b.lines) <= 3) and abs(b.bottom_gap - b.top_gap) < 2.0 for b in bs), \
        [(len(b.lines), round(b.top_gap, 1), round(b.bottom_gap, 1)) for b in bs]
    pages = sorted((out / "렌더").glob("견본_전유형_문항지_p*.png"))
    compare = sorted((out / "대조").glob("*.png"))
    assert pages and len(compare) >= len(pages)
    assert all(f'"{p.resolve()}"' in text for p in compare)
    widths = {pymupdf.Pixmap(str(p)).width for p in compare}
    assert len(widths) == 1  # 쪽 수가 달라도(엔진 2 · 제출본 4) 빈 칸을 남겨 폭이 같다
    assert not list((out / "_렌더").glob("*.hwpx")) or 문항지.read_bytes() == (out / "_렌더" / 문항지.name).read_bytes()
    assert "확인 필요" in printed and rc == 0


def test_보고서_단계_줄은_stage로(tmp_path):
    """(Task 19) build --stage — 보고서 맨 위 단계 줄을 바꾼다(없으면 엔진 STAGE)."""
    from exam_kit.build import STAGE, BuildResult, main, write_report

    r = BuildResult(보고=tmp_path / "보고.md", blocked=True, stage="원고 미확정 — 합성 단계")
    assert "> 단계: 원고 미확정 — 합성 단계" in write_report(r, md_path=tmp_path / "a.md").read_text(encoding="utf-8")
    r = BuildResult(보고=tmp_path / "보고2.md", blocked=True)
    assert f"> 단계: {STAGE}" in write_report(r, md_path=tmp_path / "a.md").read_text(encoding="utf-8")

    with pytest.raises(SystemExit):  # 옵션이 있는지만(필수 인자 없이 도움말로 끝난다)
        main(["--help"])


def test_단_나눔_pack은_settle의_balance로(양식_hwpx, tmp_path, monkeypatch):
    """(Task 30) build --pack — balanced면 균형 배치(⓪''), greedy면 앞에서부터 흐르는 대로(상한·꼬리·지시는 그대로)."""
    import exam_kit.build as b

    md = _깨진_원고(tmp_path, "이유로 알맞은", "이유로 적합한")
    seen = []

    def 가짜_settle(*args, balance=True, **kw):
        seen.append(balance)
        raise _멈춤()

    monkeypatch.setattr(b, "settle", 가짜_settle)
    for pack in ("balanced", "greedy"):
        with pytest.raises(_멈춤):
            build(md, load_kit(킷_디렉터리), tmp_path / pack, form_path=양식_hwpx, lint_block=False,
                  render_fn=_렌더_금지, pack=pack)
    assert seen == [True, False]
    with pytest.raises(ValueError, match="pack"):
        build(md, load_kit(킷_디렉터리), tmp_path / "x", form_path=양식_hwpx, lint_block=False,
              render_fn=_렌더_금지, pack="first-fit")


def test_보고서의_파일_열기_명령은_OS에_맞다(tmp_path, monkeypatch):
    """macOS는 open(-R), Windows는 explorer(/select,) — 선생님이 보고서의 명령을 그대로 붙여 쓴다."""
    import exam_kit.build as B

    p = tmp_path / "a_문항지.hwpx"
    monkeypatch.setattr(B.sys, "platform", "darwin")
    assert B._reveal(p) == f'open -R "{p.resolve()}"' and B._open(p) == f'open "{p.resolve()}"'
    monkeypatch.setattr(B.sys, "platform", "win32")
    assert B._reveal(p) == f'explorer /select,"{p.resolve()}"' and B._open(p) == f'explorer "{p.resolve()}"'


def test_두_판_배치_대조는_Windows_형광펜_밀림만_봐준다():
    """drift > 0(Windows 한/글 PDF): 답 표시본 머리가 그 단에서 앞선 머리 수 × drift + tol까지 아래로 밀려도 같다.
    위로 밀리거나, 단이 바뀌거나, 허용보다 더 밀리면 다르다."""
    def 판(*ys, col=1):
        return [PageLayout(1, (ColumnLayout(1, col, 60.0, 900.0, ys, True),), None)]

    plain = 판(100.0, 300.0, 500.0)
    key = 판(100.0, 300.6, 501.0)  # 앞선 정답 줄 1·2개만큼 밀림(0.6·1.0)
    assert len(same_layout(plain, key)) == 2  # macOS 기준(±0.5)으로는 다르다
    assert same_layout(plain, key, drift=0.4) == []  # 허용: 0.9 · 1.3
    assert len(same_layout(plain, 판(100.0, 300.0, 501.4), drift=0.4)) == 1  # 1.4 > 1.3
    assert len(same_layout(plain, 판(100.0, 299.3, 500.0), drift=0.4)) == 1  # 위로 0.7
    assert len(same_layout(plain, 판(100.0, 300.0, 500.0, col=2), drift=0.4)) == 3  # 단이 다르다

