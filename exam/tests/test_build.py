import re
import subprocess
from pathlib import Path

import pytest
from _helpers import 최상위_문단
from hwpx.document import HwpxDocument

from _kits import kit_dir
from exam_kit import q
import pymupdf
from lxml import etree as ET

from exam_kit.build import (
    BuildResult,
    _clean,
    _reveal,
    add_answer_marks,
    build,
    git_ignored,
    main,
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
    doc.save_to_path(str(plain))
    k = HwpxDocument.open(str(plain))
    add_answer_marks(k, kit, res.answers)
    k.save_to_path(str(key))
    assert same_package(plain, key) == []
    t = next(t for t in k.sections[0].element.iter(q("hp", "t")) if (t.text or "").strip())
    t.text = t.text + "x"  # 형광펜 말고 글자 하나
    k.sections[0].mark_dirty()
    k.save_to_path(str(other))
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


def test_옛_산출물_정리는_다른_원고를_건드리지_않는다(tmp_path):
    mine = ["렌더/시험_문항지_p1.png", "렌더/시험_답표시본_p12.png", "대조/시험_vs_제출본_p3.png", "시험_문항지.hwpx"]
    others = ["렌더/시험_2_문항지_p1.png", "대조/시험_2_vs_제출본_p1.png", "시험_2_문항지.hwpx",
              "렌더/시험_문항지_p1_메모.png", "렌더/시험_메모.png"]
    _파일들(tmp_path, mine + others)
    _clean(tmp_path, "시험")
    assert not any((tmp_path / n).exists() for n in mine)
    assert all((tmp_path / n).exists() for n in others)


def test_옛_산출물_정리는_대괄호를_glob으로_읽지_않는다(tmp_path):
    mine = ["렌더/시험[1]_문항지_p1.png", "대조/시험[1]_vs_제출본_p2.png"]
    others = ["렌더/시험1_문항지_p1.png", "대조/시험1_vs_제출본_p2.png"]  # "시험[1]"을 glob으로 읽으면 여기에 맞는다
    _파일들(tmp_path, mine + others)
    _clean(tmp_path, "시험[1]")
    assert not any((tmp_path / n).exists() for n in mine)
    assert all((tmp_path / n).exists() for n in others)


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
    """앞 실행이 남긴 척하는 파일들 — build가 시작할 때 지워야 한다."""
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
    r = build(md, load_kit(킷_디렉터리), out, form_path=양식_hwpx, render_fn=_렌더_금지)
    assert r.blocked and r.문항지 is None and r.답표시본 is None
    assert not list(out.glob("*.hwpx")) and not any(p.exists() for p in olds)
    assert (out / "렌더" / "다른원고_문항지_p1.png").exists()  # 다른 원고의 산출물은 그대로
    text = r.보고.read_text(encoding="utf-8")
    assert "E003" in text and "조판하지 않았다" in text and "옛 보고" not in text and "진행 중" not in text


class _멈춤(Exception):
    pass


def test_lint_warn이면_경고로_두고_조판한다(양식_hwpx, tmp_path):
    md = _깨진_원고(tmp_path, "가장 적절한", "가장 적합한")  # E014 — 조판은 할 수 있는 규칙 오류
    out = tmp_path / "out"

    def 멈춤(hwpx, out_dir):
        raise _멈춤(hwpx)

    olds = _옛_산출물(out)
    with pytest.raises(_멈춤):
        build(md, load_kit(킷_디렉터리), out, form_path=양식_hwpx, lint_block=False, render_fn=멈춤)
    assert (out / "_렌더" / "시험_문항지.hwpx").exists()  # 조판·저장까지 갔다(렌더 루프 첫 렌더 직전)
    # 중간에 멈춘 실행: 옛 파일은 지워졌고, 반쯤 된 hwpx는 out_dir에 없고, 보고서는 '진행 중'
    assert not any(p.exists() for p in olds) and not list(out.glob("*.hwpx"))
    text = (out / "보고.md").read_text(encoding="utf-8")
    assert "진행 중" in text and "옛 보고" not in text


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

    md = _깨진_원고(tmp_path, "가장 적절한", "가장 적합한")
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
