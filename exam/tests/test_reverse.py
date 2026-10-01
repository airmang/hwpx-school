"""역변환(제출본 hwpx → md v2). 단위 테스트는 합성 XML만 — 실문항은 레포에 넣지 않는다.

제출본 테스트는 제출본이 있을 때만 돌고, 기대값도 제출본 자체(형광펜·누름틀)에서 뽑는다.
"""

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import lxml.etree as ET
import pytest
from hwpx.document import HwpxDocument

from _kits import kit_dir
from exam_kit import HC, HP
from exam_kit import reverse as reverse_mod
from exam_kit.kit import load_kit

_BOXES = load_kit(kit_dir()).boxes
from exam_kit.lint import errors, lint
from exam_kit.reverse import (
    _bin_items,
    classify_table,
    detect_matching,
    main,
    paragraph_text,
    picture_line,
    reverse,
    reverse_body,
    split_choices,
)
from exam_kit.scan import scan_markdown
from exam_kit.verify import extract_answers, question_heads

킷_디렉터리 = kit_dir()


def _p(xml_inner: str):
    return ET.fromstring(f'<hp:p xmlns:hp="{HP}" paraPrIDRef="0" styleIDRef="0">{xml_inner}</hp:p>')


def _run(text: str, cp: str = "8") -> str:
    return f'<hp:run charPrIDRef="{cp}"><hp:t>{text}</hp:t></hp:run>'


def _tc(row: int, col: int, paras: list[str], *, rs: int = 1, cs: int = 1) -> str:
    ps = "".join(f'<hp:p paraPrIDRef="0" styleIDRef="0">{_run(escape(t)) if t else ""}</hp:p>' for t in paras)
    return (f'<hp:tc><hp:subList>{ps}</hp:subList><hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
            f'<hp:cellSpan colSpan="{cs}" rowSpan="{rs}"/></hp:tc>')


def _tbl(rows: int, cols: int, trs: list[list[str]]):
    body = "".join(f"<hp:tr>{''.join(tr)}</hp:tr>" for tr in trs)
    return ET.fromstring(f'<hp:tbl xmlns:hp="{HP}" rowCnt="{rows}" colCnt="{cols}">{body}</hp:tbl>')


# --- 문단 글 -----------------------------------------------------------------


def test_paragraph_text_탭_밑줄_형광펜():
    assert paragraph_text(_p(_run("① ㄱ, ㄴ<hp:tab/>② ㄴ, ㄷ")), set()) == "① ㄱ, ㄴ\t② ㄴ, ㄷ"
    p = _p(_run("옳지 ") + _run("않은", "40") + _run(" 것은? [5.1점]"))
    assert paragraph_text(p, {"40"}) == "옳지 __않은__ 것은? [5.1점]"
    p = _p(_run('<hp:markpenBegin color="#FFFF00"/>④<hp:markpenEnd/> ㄱ, ㄴ, ㄷ'))
    assert paragraph_text(p, set()) == "*④ ㄱ, ㄴ, ㄷ"


def test_paragraph_text_밑줄_run_앞뒤_공백은_밑줄_밖으로():
    p = _p(_run("적절하지") + _run(" 않은 ", "40") + _run("것은?"))
    assert paragraph_text(p, {"40"}) == "적절하지 __않은__ 것은?"


def test_paragraph_text_흰_형광펜은_정답이_아니다():
    """제출본 12번처럼 정답을 고치며 남은 흰색 형광펜 — 노랑만 정답이다."""
    p = _p(_run('<hp:markpenBegin color="#FFFFFF"/>①<hp:markpenEnd/> ㄱ<hp:tab/>'
                '<hp:markpenBegin color="#ffff00"/>②<hp:markpenEnd/> ㄴ'))
    assert paragraph_text(p, set()) == "① ㄱ\t*② ㄴ"


def test_split_choices():
    assert split_choices("① ㄱ\t② ㄴ \t③ ㄱ, ㄷ") == ["① ㄱ", "② ㄴ", "③ ㄱ, ㄷ"]
    assert split_choices("*④ ㄴ, ㄷ\t⑤ ㄱ, ㄴ, ㄷ") == ["*④ ㄴ, ㄷ", "⑤ ㄱ, ㄴ, ㄷ"]
    assert split_choices("① 가  *② 나") == ["① 가", "*② 나"]  # 탭 없이 공백으로 이은 답지


def test_detect_matching():
    lines = ["       ㄱ                 ㄴ                  ㄷ",
             "*①    가나             다라 마           바사 아",
             "②    가나             다라 마            자 차",
             "③    가나              카타               파",
             "④    하거              너더\t   러머",
             "⑤    하거              버서              자 차"]
    head, rows = detect_matching(lines)
    assert head == ["ㄱ", "ㄴ", "ㄷ"]
    assert rows[0] == ["*①", "가나", "다라 마", "바사 아"] and len(rows) == 5
    assert rows[3] == ["④", "하거", "너더", "러머"]  # 공백 사이에 탭이 섞여도
    assert detect_matching(["① a", "② b"]) is None
    assert detect_matching(["(가)  (나)"] + [f"{m}  a  b" for m in "①②③④⑤"])[0] == ["(가)", "(나)"]


# --- 표 분류 -----------------------------------------------------------------


def test_classify_table_보기():
    e = ""
    tbl = _tbl(4, 5, [
        [_tc(0, 0, [e], cs=2), _tc(0, 2, ["< 보 기 >"], rs=2), _tc(0, 3, [e], cs=2)],
        [_tc(1, 0, [e], cs=2), _tc(1, 3, [e], cs=2)],
        [_tc(2, 0, [e]), _tc(2, 1, ["", " ㄱ. 가는 나다.", "ㄴ. 라는 마다."], cs=3), _tc(2, 4, [e])],
        [_tc(3, 0, [e], cs=5)],
    ])
    assert classify_table(tbl, set(), boxes=_BOXES) == ("보기", ["ㄱ. 가는 나다.", "ㄴ. 라는 마다."])


def test_classify_table_보기_항목_이어진_줄은_앞_항목에_붙인다():
    tbl = _tbl(4, 5, [
        [_tc(0, 0, [""], cs=2), _tc(0, 2, ["< 보 기 >"], rs=2), _tc(0, 3, [""], cs=2)],
        [_tc(1, 0, [""], cs=2), _tc(1, 3, [""], cs=2)],
        [_tc(2, 0, [""]), _tc(2, 1, ["ㄱ. 가는", "나다.", "ㄴ. 라"], cs=3), _tc(2, 4, [""])],
        [_tc(3, 0, [""], cs=5)],
    ])
    assert classify_table(tbl, set(), boxes=_BOXES)[1] == ["ㄱ. 가는 나다.", "ㄴ. 라"]


def test_classify_table_자료():
    tbl = _tbl(3, 3, [
        [_tc(0, 0, [""], cs=3)],
        [_tc(1, 0, [""]), _tc(1, 1, ["가나다 ( ㄱ ) 라마.", "바사."]), _tc(1, 2, [""])],
        [_tc(2, 0, [""], cs=3)],
    ])
    assert classify_table(tbl, set(), boxes=_BOXES) == ("자료", ["가나다 ( ㄱ ) 라마.", "바사."])


def test_classify_table_격자표():
    tbl = _tbl(3, 3, [
        [_tc(0, 0, ["가"]), _tc(0, 1, ["나"]), _tc(0, 2, ["다"])],
        [_tc(1, 0, ["1"]), _tc(1, 1, ["2"]), _tc(1, 2, ["3"])],
        [_tc(2, 0, ["4"]), _tc(2, 1, ["5"]), _tc(2, 2, ["6"])],
    ])
    # 3×3이라도 자료 박스 모양(0행 병합·가운데 내용 칸)이 아니면 격자표
    assert classify_table(tbl, set(), boxes=_BOXES) == ("표", ["| 가 | 나 | 다 |", "|---|---|---|", "| 1 | 2 | 3 |", "| 4 | 5 | 6 |"])


# --- 그림 --------------------------------------------------------------------


def test_picture_line_원래_폭_cm():
    pic = ET.fromstring(
        f'<hp:pic xmlns:hp="{HP}" xmlns:hc="{HC}"><hc:img binaryItemIDRef="BIN0001"/>'
        f'<hp:sz width="17008" height="10205"/></hp:pic>')
    assert picture_line(pic, "그림_05_1.png") == "![](그림_05_1.png){width=6cm}"
    pic.find(f"{{{HP}}}sz").set("width", "14173")
    assert picture_line(pic, "a.png") == "![](a.png){width=5cm}"


# --- 조용히 버리지 않는다(fail-loud) --------------------------------------------


def _pic(bid: str = "BIN0001", width: int = 17008) -> str:
    return (f'<hp:pic xmlns:hc="{HC}"><hc:img binaryItemIDRef="{bid}"/>'
            f'<hp:sz width="{width}" height="100"/></hp:pic>')


def _tc_xml(row: int, col: int, inner: str, *, cs: int = 1) -> str:
    return (f'<hp:tc><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0">{inner}</hp:p></hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="{cs}" rowSpan="1"/></hp:tc>')


def _자료_xml(inner: str) -> str:
    return (f'<hp:tbl rowCnt="3" colCnt="3"><hp:tr>{_tc_xml(0, 0, "", cs=3)}</hp:tr>'
            f'<hp:tr>{_tc_xml(1, 0, "")}{_tc_xml(1, 1, inner)}{_tc_xml(1, 2, "")}</hp:tr>'
            f'<hp:tr>{_tc_xml(2, 0, "", cs=3)}</hp:tr></hp:tbl>')


def test_classify_table_병합_칸_격자표는_오류():
    tbl = _tbl(2, 2, [[_tc(0, 0, ["제목"], cs=2)], [_tc(1, 0, ["a"]), _tc(1, 1, ["b"])]])
    with pytest.raises(ValueError, match="병합 칸"):
        classify_table(tbl, set(), boxes=_BOXES)


def test_classify_table_3x3_제목행_병합_격자는_자료가_아니다():
    """0행 병합 + (1,1)이 있어도 레일·2행에 글이 있으면 자료 박스가 아니다(글을 잃지 않는다)."""
    tbl = _tbl(3, 3, [
        [_tc(0, 0, ["표 제목"], cs=3)],
        [_tc(1, 0, ["a"]), _tc(1, 1, ["b"]), _tc(1, 2, ["c"])],
        [_tc(2, 0, ["d"]), _tc(2, 1, ["e"]), _tc(2, 2, ["f"])],
    ])
    with pytest.raises(ValueError, match="병합 칸"):
        classify_table(tbl, set(), boxes=_BOXES)


def test_classify_table_자료_안의_격자표():
    grid = ('<hp:run charPrIDRef="8"><hp:tbl rowCnt="1" colCnt="2"><hp:tr>'
            f'{_tc_xml(0, 0, _run("x"))}{_tc_xml(0, 1, _run("y"))}</hp:tr></hp:tbl></hp:run>')
    tbl = ET.fromstring(f'<hp:tbl xmlns:hp="{HP}"' + _자료_xml(grid)[len("<hp:tbl"):])
    assert classify_table(tbl, set(), boxes=_BOXES) == ("자료", ["| x | y |", "|---|---|"])


@pytest.mark.parametrize("inner", [
    '<hp:run charPrIDRef="8">' + _pic() + "</hp:run>",
    '<hp:run charPrIDRef="8"><hp:tbl rowCnt="1" colCnt="1"><hp:tr>'
    + _tc_xml(0, 0, _run("x")) + "</hp:tr></hp:tbl></hp:run>",
])
def test_classify_table_그림_표가_든_격자표는_오류(inner):
    tbl = ET.fromstring(f'<hp:tbl xmlns:hp="{HP}" rowCnt="1" colCnt="2"><hp:tr>'
                        f'{_tc_xml(0, 0, inner)}{_tc_xml(0, 1, _run("b"))}</hp:tr></hp:tbl>')
    with pytest.raises(ValueError, match="그림·표가 든 표"):
        classify_table(tbl, set(), boxes=_BOXES)


def test_classify_table_박스_안의_박스는_오류():
    inner = '<hp:run charPrIDRef="8">' + _자료_xml(_run("안")) + "</hp:run>"
    tbl = ET.fromstring(f'<hp:tbl xmlns:hp="{HP}"' + _자료_xml(inner)[len("<hp:tbl"):])
    with pytest.raises(ValueError, match="박스 안에 자료"):
        classify_table(tbl, set(), boxes=_BOXES)


def test_paragraph_text_노랑_형광펜이_낱말에_있으면_오류():
    with pytest.raises(ValueError, match="정답 표시가 모호"):
        paragraph_text(_p(_run('가<hp:markpenBegin color="#FFFF00"/>중요<hp:markpenEnd/>')), set())


@pytest.mark.parametrize("inner", [
    '<hp:run charPrIDRef="8"><hp:rect/></hp:run>',
    '<hp:run charPrIDRef="8"><hp:t>a<hp:hyphen/>b</hp:t></hp:run>',
])
def test_paragraph_text_모르는_요소는_오류(inner):
    with pytest.raises(ValueError, match="모르는 요소"):
        paragraph_text(_p(inner), set())


def test_paragraph_text_형광펜_뒤_공백·run_경계를_건넌다():
    p = _p(_run('<hp:markpenBegin color="#FFFF00"/> ① 가<hp:markpenEnd/>'))
    assert paragraph_text(p, set()) == "*① 가"
    p = _p(_run('가<hp:tab/><hp:markpenBegin color="#FFFF00"/>') + _run("② 나<hp:markpenEnd/>"))
    assert paragraph_text(p, set()) == "가\t*② 나"


def test_paragraph_text_글_없는_컨트롤은_건너뛴다():
    ctrl = '<hp:ctrl><hp:fieldBegin id="1"/><hp:bookmark name="b"/><hp:colPr/><hp:pageNum/><hp:pageHiding/></hp:ctrl>'
    p = _p(f'<hp:run charPrIDRef="8">{ctrl}<hp:t>가</hp:t></hp:run>' + _run('나<hp:markpenEnd/>')
           + '<hp:run charPrIDRef="8"><hp:ctrl><hp:fieldEnd/></hp:ctrl></hp:run>')
    assert paragraph_text(p, set()) == "가나"


@pytest.mark.parametrize("inner", ["<hp:footNote/>", "<hp:endNote/>", "<hp:newNum/>", "<hp:fieldBegin/><hp:footNote/>"])
def test_paragraph_text_글을_싣는_컨트롤은_오류(inner):
    with pytest.raises(ValueError, match="run 안의 컨트롤"):
        paragraph_text(_p(f'<hp:run charPrIDRef="8"><hp:ctrl>{inner}</hp:ctrl><hp:t>가</hp:t></hp:run>'), set())


@pytest.mark.parametrize("tag", ["insertBegin", "deleteBegin"])
def test_paragraph_text_변경_추적은_오류(tag):
    with pytest.raises(ValueError, match="모르는 요소"):
        paragraph_text(_p(_run(f"가<hp:{tag}/>나")), set())


def test_split_choices_답지_속_원문자는_자르지_않는다():
    assert split_choices("③ ④번 과정이 먼저다.") == ["③ ④번 과정이 먼저다."]
    assert split_choices("① 두 값은 같다\t② ③과 같다") == ["① 두 값은 같다", "② ③과 같다"]


def test_matching_머리_변형():
    rows = [f"{m}    가    나    다" for m in "①②③④⑤"]
    for head, want in (("㉠   ㉡   ㉢", ["㉠", "㉡", "㉢"]), ("(A)  (B)  (C)", ["(A)", "(B)", "(C)"]),
                       ("ㄱ ㄴ ㄷ", ["ㄱ", "ㄴ", "ㄷ"])):
        assert detect_matching([head] + rows)[0] == want


# --- 문단 흐름(reverse_body) — 합성 문단 ---------------------------------------


def _head(text: str) -> str:
    return _run(text)


def _choices5(star: str = "③") -> list[str]:
    return [_run((f'<hp:markpenBegin color="#FFFF00"/>{m}<hp:markpenEnd/>' if m == star else m) + f" 답 {i}")
            for i, m in enumerate("①②③④⑤", 1)]


def _body(*inners: str):
    return [_p(x) for x in inners]


def test_reverse_body_세트와_그림(tmp_path):
    paras = _body(
        _run("[1∼2] 다음 글을 읽고 물음에 답하시오."),
        '<hp:run charPrIDRef="8">' + _자료_xml(_run("지문 글.")) + "</hp:run>",
        _head("가는 무엇인가? [50.0점]"),
        '<hp:run charPrIDRef="8">' + _pic() + "</hp:run>",
        *_choices5("①"),
        _head("나는 무엇인가? [50.0점]"),
        *_choices5("⑤"),
    )
    heads = {2, 9}
    md = reverse_body(paras, heads, set(), bins={"BIN0001": (".png", b"PNGDATA")}, image_dir=tmp_path, boxes=_BOXES)
    assert md[:5] == ["## 1~2. 세트", "다음 글을 읽고 물음에 답하시오.", "", ":::자료", "지문 글."]
    assert "### 1. [50.0점]" in md and "### 2. [50.0점]" in md
    assert "![](그림_01_1.png){width=6cm}" in md and (tmp_path / "그림_01_1.png").read_bytes() == b"PNGDATA"
    assert "*① 답 1" in md and "*⑤ 답 5" in md
    s = scan_markdown("---\n양식: x\n학년도: 2026\n학년: 2\n학기: 1\n차: 1\n과목: x\n과목코드: 1\n"
                      "시행: 4.22.(수) 3교시\n대상: 2학년 1반~2반\n인쇄: 1매 * 1묶음\n출제교사: x\n---\n" + "\n".join(md))
    assert s.errors == () and [q.set_rng for q in s.questions] == [("1", "2"), ("1", "2")]


def test_reverse_body_BinData_없으면_오류(tmp_path):
    paras = _body(_head("가? [1.0점]"), '<hp:run charPrIDRef="8">' + _pic("BIN0009") + "</hp:run>", *_choices5())
    with pytest.raises(ValueError, match="BIN0009"):
        reverse_body(paras, {0}, set(), bins={}, image_dir=tmp_path)


def test_reverse_body_답지_뒤_본문은_오류():
    with pytest.raises(ValueError, match="답지 뒤에 본문"):
        reverse_body(_body(_head("가? [1.0점]"), *_choices5(), _run("덧붙인 글")), {0}, set())


def test_reverse_body_첫_문항_앞_내용은_오류():
    with pytest.raises(ValueError, match="문항 앞에 내용"):
        reverse_body(_body(_run("떠도는 글"), _head("가? [1.0점]"), *_choices5()), {1}, set())


def test_reverse_body_짝짓기_열맞춤_실패는_오류():
    rows = [_run(f"{m}    가    나    다") for m in "①②③④"] + [_run("⑤    가    나")]
    with pytest.raises(ValueError, match="5행 열 맞춤"):
        reverse_body(_body(_head("가? [1.0점]"), _run("ㄱ    ㄴ    ㄷ"), *rows), {0}, set())


def test_reverse_body_머리_없는_열맞춤_답지는_오류():
    rows = [_run(f"{m}    가    나    다") for m in "①②③④⑤"]
    with pytest.raises(ValueError, match="열을 맞춘 답지"):
        reverse_body(_body(_head("가? [1.0점]"), _run("머리가 아닌 줄"), *rows), {0}, set())


def test_reverse_body_답지가_다섯이_아니면_오류():
    with pytest.raises(ValueError, match="다섯 개가 아니다"):
        reverse_body(_body(_head("가? [1.0점]"), *_choices5()[:4]), {0}, set())


def test_bin_items(tmp_path):
    f = tmp_path / "x.hwpx"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("Contents/content.hpf", '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest>'
                   '<opf:item id="BIN0001" href="BinData/BIN0001.png"/><opf:item id="s" href="Contents/section0.xml"/>'
                   "</opf:manifest></opf:package>")
        z.writestr("BinData/BIN0001.png", b"IMG")
    assert _bin_items(f) == {"BIN0001": (".png", b"IMG")}


def test_main_scan_오류면_0이_아니다(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(reverse_mod, "open_source", lambda p, w: reverse_mod.Source(None, p, p))  # 원안지 열기는 건너뛴다
    monkeypatch.setattr(reverse_mod, "reverse", lambda *a, **k: "---\n양식: x\n학년도: 2026\n학년: 2\n학기: 1\n차: 1\n"
                        "과목: x\n과목코드: 1\n시행: 4.22.(수) 3교시\n대상: 2학년 1반~2반\n인쇄: 1매 * 1묶음\n"
                        "출제교사: x\n---\n떠도는 글\n")
    assert reverse_mod.main(["x.hwpx", "--kit", str(킷_디렉터리), "--out", str(tmp_path / "o.md")]) == 1
    assert "scan 오류" in capsys.readouterr().out


# --- 제출본 (있을 때만) ---------------------------------------------------------


def test_제출본_역변환(제출본_hwpx, tmp_path):
    kit = load_kit(킷_디렉터리)
    md = reverse(제출본_hwpx, kit, image_dir=tmp_path)
    s = scan_markdown(md)
    assert s.errors == (), s.errors[:3]
    doc = HwpxDocument.open(str(제출본_hwpx))
    assert len(s.questions) == len(question_heads(doc))
    got = {q.number: next(c.mark for c in q.choices if c.correct) for q in s.questions}
    assert got == extract_answers(doc)  # 형광펜(노랑) 정답 그대로
    kinds = {b.kind for q in s.questions for b in q.blocks}
    assert {"보기", "자료", "표", "답항표"} <= kinds
    assert abs(sum(q.points for q in s.questions) - s.front.만점) < 1e-9
    v = {f.field_id: f.value for f in doc.list_form_fields()}
    assert s.front.시행_분해() == {k: v[kit.slots[k]] for k in ("월", "일", "요일", "교시")}
    assert s.front.과목 == v[kit.slots["과목"]]
    e = errors(lint(md, md_dir=tmp_path))
    assert not [x for x in e if x.code in ("E001", "E002", "E003", "E004", "E005", "E006", "E009", "E010")], e[:5]


def test_cli_출력_폴더를_만든다(tmp_path, monkeypatch):
    monkeypatch.setattr(reverse_mod, "open_source", lambda p, w: reverse_mod.Source(None, p, p))  # 원안지 열기는 건너뛴다
    monkeypatch.setattr(reverse_mod, "reverse", lambda *a, **k: "---\n양식: x\n학년도: 2026\n학년: 2\n학기: 1\n차: 1\n"
                        "과목: x\n과목코드: 1\n시행: 4.22.(수) 3교시\n대상: 2학년 1반~2반\n인쇄: 1매 * 1묶음\n"
                        "출제교사: x\n---\n")
    out = tmp_path / "새" / "폴더" / "o.md"
    assert reverse_mod.main(["x.hwpx", "--kit", str(킷_디렉터리), "--out", str(out)]) == 0
    assert out.exists()


def test_cli(제출본_hwpx, tmp_path, capsys):
    out = tmp_path / "역변환.md"
    assert main([str(제출본_hwpx), "--kit", str(킷_디렉터리), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith(f"---\n양식: {킷_디렉터리.name}\n")
    assert "문항" in capsys.readouterr().out
