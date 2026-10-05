"""역변환 왕복 불변(exam_kit.roundtrip) — 합성 킷·합성 원고만(학교 킷 없이 돈다).

합성 원고를 합성 서식에 조판한 답 표시본을 '원안지'로 삼아: 원안지 → 원고 → 다시 조판 → 원고. 문항 글·정답·배점·
그림·수식이 그대로여야 한다(이슈 #8 합격 기준)."""

import re
import shutil
from pathlib import Path

import pytest
from exam_kit.kit import load_kit
from exam_kit.reverse import answer_table, reverse
from exam_kit.roundtrip import Counts, compare, main, rebuild, roundtrip
from exam_kit.scan import scan_markdown
from exam_kit.slots import read_text_slots

루트 = Path(__file__).resolve().parents[1]
킷 = 루트 / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"
픽스처 = Path(__file__).parent / "fixtures"


def _원안지(name: str, tmp_path: Path) -> Path:
    md = (픽스처 / name).read_text(encoding="utf-8")
    return rebuild(md, load_kit(킷), 서식, 픽스처, tmp_path / "원안지.hwpx")


@pytest.mark.parametrize("name", ["합성서식_6문항.md", "견본_전유형.md", "수식_합성.md", "답항배치_7문항.md"])
def test_왕복_불변(name, tmp_path):
    r = roundtrip(_원안지(name, tmp_path), load_kit(킷), 서식, tmp_path / "rt")
    assert r.same, r.diffs
    assert r.original == r.rebuilt and r.original.questions > 0


def test_수식_그림_답항표가_원고로_돌아온다(tmp_path):
    md = reverse(_원안지("견본_전유형.md", tmp_path), load_kit(킷), image_dir=tmp_path / "그림")
    s = scan_markdown(md, load_kit(킷).front_matter)
    assert s.errors == ()
    kinds = {b.kind for x in s.questions for b in x.blocks}
    assert {"보기", "자료", "표", "답항표", "그림"} <= kinds | {b.kind for st in s.sets for b in st.blocks}
    assert all(p.suffix == ".png" for p in (tmp_path / "그림").iterdir())
    md2 = reverse(_원안지("수식_합성.md", tmp_path), load_kit(킷), image_dir=tmp_path / "수식")
    assert md2.count("$") >= 2 * 50  # 수식 56개가 `$LaTeX$`로


def test_글자_번호는_원고_머리로만(tmp_path):
    """합성 서식은 글자 번호(`1. `) 양식 — 역변환 원고의 발문에 번호가 두 번 들어가지 않는다."""
    md = reverse(_원안지("합성서식_6문항.md", tmp_path), load_kit(킷), image_dir=tmp_path)
    body = md.split("---", 2)[2]
    assert "\n## 1. [" in body and "\n1. " not in body


def test_글자_자리_머리_값을_되읽는다(tmp_path):
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.open(str(_원안지("합성서식_6문항.md", tmp_path)))
    v = read_text_slots(doc, load_kit(킷))
    fm = scan_markdown((픽스처 / "합성서식_6문항.md").read_text(encoding="utf-8"), load_kit(킷).front_matter).front
    assert (v["학년도"], v["학기"], v["차"], v["학년"], v["과목"]) == (str(fm.학년도), str(fm.학기), str(fm.차),
                                                                    str(fm.학년), fm.과목)
    assert v["출제교사"] == fm.출제교사


def test_다른_곳은_자리만_알린다():
    md = (픽스처 / "합성서식_6문항.md").read_text(encoding="utf-8")
    a = scan_markdown(md, load_kit(킷).front_matter)
    first = next(x for x in a.questions if any(c.correct for c in x.choices))
    right = next(c.mark for c in first.choices if c.correct)
    wrong = next(m for m in "①②③④⑤" if m != right)
    b = scan_markdown(md.replace(f"*{right}", right, 1).replace(f"\n{wrong}", f"\n*{wrong}", 1), load_kit(킷).front_matter)
    c = Counts(6, 0, 0)
    diffs = compare(a, b, c, Counts(6, 1, 0))
    assert f"{first.number}번 정답" in diffs and "수식 수: 0 ≠ 1" in diffs
    assert all(len(d) < 40 for d in diffs)  # 문항 글은 넣지 않는다


def test_조판기_답항표만_답항표로_읽는다():
    import lxml.etree as ET
    from exam_kit import HP

    def tbl(rows):
        trs = "".join("<hp:tr>" + "".join(
            f'<hp:tc><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>{t}</hp:t></hp:run>'
            f'</hp:p></hp:subList><hp:cellAddr colAddr="{c}" rowAddr="{r}"/><hp:cellSpan colSpan="1" rowSpan="1"/></hp:tc>'
            for c, t in enumerate(row)) + "</hp:tr>" for r, row in enumerate(rows))
        return ET.fromstring(f'<hp:tbl xmlns:hp="{HP}" rowCnt="{len(rows)}" colCnt="{len(rows[0])}">{trs}</hp:tbl>')

    rows = [["", "ㄱ", "ㄴ"]] + [[m, "가", "나"] for m in "①②③④⑤"]
    assert answer_table(tbl(rows), set()) == ['머리="ㄱ|ㄴ"'] + [f"{m} 가 | 나" for m in "①②③④⑤"]
    assert answer_table(tbl([["열", "값"], ["1", "2"]]), set()) is None  # 격자표
    assert answer_table(tbl([["x", "ㄱ", "ㄴ"]] + rows[1:]), set()) is None  # 머리행 첫 칸이 비지 않았다


def test_cli(tmp_path, capsys):
    src = _원안지("합성서식_6문항.md", tmp_path)
    assert main([str(src), "--kit", str(킷), "--form", str(서식), "--work", str(tmp_path / "rt")]) == 0
    out = capsys.readouterr().out
    assert "왕복 불변: 같다" in out and "원본: 문항 6" in out


def test_교사가_나눈_발문_문단은_조판에서도_나뉜다(tmp_path):
    """(10-01 결정) 빈 줄로 나눈 발문 문단 → 머리 문단 + 발문 이음 문단(배점은 마지막 문단 끝) — 왕복해도 문단 그대로."""
    from hwpx.document import HwpxDocument


    md = (픽스처 / "합성서식_6문항.md").read_text(encoding="utf-8")
    first = scan_markdown(md, load_kit(킷).front_matter).questions[0]
    stem = first.stem[0]
    md = md.replace(stem, "다음 조건을 만족시킨다.\n\n(가) 합성 조건 하나\n\n" + stem, 1)
    src = rebuild(md, load_kit(킷), 서식, 픽스처, tmp_path / "원안지.hwpx")
    texts = ["".join(t.text or "" for t in p.element.iter("{*}t")) for p in HwpxDocument.open(str(src)).sections[0].paragraphs]
    i = next(k for k, t in enumerate(texts) if "다음 조건을 만족시킨다." in t)
    assert texts[i + 1] == "(가) 합성 조건 하나" and texts[i + 2].startswith(stem) and texts[i + 2].endswith("점]")
    assert "점]" not in texts[i]  # 배점은 마지막 발문 문단 끝에만
    r = roundtrip(src, load_kit(킷), 서식, tmp_path / "rt")
    assert r.same, r.diffs
    back = scan_markdown((tmp_path / "rt" / "원고" / "원고.md").read_text(encoding="utf-8"), load_kit(킷).front_matter)
    assert back.questions[0].stem == ("다음 조건을 만족시킨다.", "(가) 합성 조건 하나", stem)


def _정답_없는_원고() -> str:
    return re.sub(r"(?m)^\*([①②③④⑤])", r"\1", (픽스처 / "합성서식_6문항.md").read_text(encoding="utf-8"))


def test_정답_표시_없는_초안도_왕복한다(tmp_path):
    """(10-01) 한/글 초안은 정답 형광펜이 아직 없는 것이 흔하다 — 조판·역변환·왕복이 멈추지 않고, 정답은 빈 것끼리 견주며 알린다."""
    src = rebuild(_정답_없는_원고(), load_kit(킷), 서식, 픽스처, tmp_path / "초안.hwpx")
    r = roundtrip(src, load_kit(킷), 서식, tmp_path / "rt")
    assert r.same, r.diffs
    assert r.notes and "정답 표시 없음 6문항" in r.notes[0]


def test_정답_표기_없음은_초안에서만_경고():
    from exam_kit.lint import lint

    md = _정답_없는_원고()
    codes = lambda **k: sorted({v.code for v in lint(md, **k) if v.code in ("E005", "W005")})
    assert codes() == ["E005"] and codes(draft=True) == ["W005"]
    two = (픽스처 / "합성서식_6문항.md").read_text(encoding="utf-8").replace("\n② ", "\n*② ", 1)
    assert "E005" in {v.code for v in lint(two, draft=True)}  # 정답 둘은 초안이어도 오류


def test_역변환은_정답_없는_문항을_알린다(tmp_path, capsys):
    from exam_kit.reverse import main as reverse_main

    src = rebuild(_정답_없는_원고(), load_kit(킷), 서식, 픽스처, tmp_path / "초안.hwpx")
    reverse_main([str(src), "--kit", str(킷), "--out", str(tmp_path / "md" / "원고.md")])
    assert "정답 표시(노랑 형광펜) 없음 6문항" in capsys.readouterr().out


def test_그림_단_왼쪽_정렬도_왕복한다(tmp_path):
    """(#7-3) `{width=… align=left indent=…}` — 조판은 단 왼쪽(+ 띄움), 역변환은 그 자리를 되살린다. 정렬도 왕복 불변에 든다."""
    from hwpx.document import HwpxDocument

    md = (픽스처 / "견본_전유형.md").read_text(encoding="utf-8")
    line = next(ln for ln in md.splitlines() if ln.startswith("![](그림.png)"))
    md = md.replace(line, line.replace("cm}", "cm align=left indent=1.5cm}"), 1)
    s = scan_markdown(md, load_kit(킷).front_matter)
    pic = next(b for x in s.questions for b in x.blocks if b.kind == "그림")
    assert (pic.attrs["align"], pic.attrs["indent_cm"]) == ("left", 1.5)
    src = rebuild(md, load_kit(킷), 서식, 픽스처, tmp_path / "원안지.hwpx")
    doc = HwpxDocument.open(str(src))
    para = next(p.element for p in doc.sections[0].paragraphs if p.element.find(".//{*}pic") is not None)
    pp = next(e for e in doc.oxml.headers[0].element.iter("{*}paraPr") if e.get("id") == para.get("paraPrIDRef"))
    assert pp.find("{*}align").get("horizontal") == "LEFT"
    r = roundtrip(src, load_kit(킷), 서식, tmp_path / "rt")
    assert r.same, r.diffs
    back = (tmp_path / "rt" / "원고" / "원고.md").read_text(encoding="utf-8")
    assert "align=left indent=1.5cm}" in back


def test_떠_있는_그림의_자리를_읽는다():
    """원안지 실물: 떠 있는 그림(treatAsChar=0)은 hp:pos의 가로 정렬·띄움으로, 글자처럼 취급한 그림은 문단 모양으로."""
    import lxml.etree as ET
    from exam_kit import HP
    from exam_kit.reverse import picture_line, picture_place

    def pic(tac: str, h: str = "LEFT", off: int = 9046):
        return ET.fromstring(f'<hp:pic xmlns:hp="{HP}"><hp:pos treatAsChar="{tac}" horzRelTo="COLUMN" horzAlign="{h}" '
                             f'horzOffset="{off}"/><hp:sz width="11386"/></hp:pic>')

    para = ET.fromstring(f'<hp:p xmlns:hp="{HP}" paraPrIDRef="7"/>')
    assert picture_place(pic("0"), para, {}) == ("left", 9046)
    assert picture_place(pic("0", "CENTER"), para, {}) == ("center", 0)
    assert picture_place(pic("1"), para, {"7": ("CENTER", 0)}) == ("center", 0)
    assert picture_place(pic("1"), para, {"7": ("JUSTIFY", 1417)}) == ("left", 1417)
    assert picture_line(pic("0"), "a.png", ("left", 9046)) == "![](a.png){width=4.02cm align=left indent=3.19cm}"
    with pytest.raises(ValueError, match="RIGHT"):
        picture_place(pic("0", "RIGHT"), para, {})


def test_BMP_그림은_회색조_PNG로_들어간다(tmp_path):
    """(#7-3) 원고 그림이 BMP(실제 원안지에서 꺼낸 그림 등)여도 조판은 회색조 PNG 사본을 넣는다."""
    import io
    import zipfile

    from PIL import Image

    root = tmp_path / "원고"
    shutil.copytree(픽스처, root)
    with Image.open(root / "그림.png") as im:
        im.convert("RGB").save(root / "그림.bmp")
    md = (root / "견본_전유형.md").read_text(encoding="utf-8").replace("](그림.png)", "](그림.bmp)")
    src = rebuild(md, load_kit(킷), 서식, root, tmp_path / "원안지.hwpx")
    with zipfile.ZipFile(src) as z:
        bins = [n for n in z.namelist() if n.startswith("BinData/")]
        assert bins and all(n.endswith(".png") for n in bins)
        with Image.open(io.BytesIO(z.read(bins[0]))) as im:
            assert im.mode == "L"
