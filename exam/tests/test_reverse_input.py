"""역변환 입력·멈춤·머리 값 — 학교 킷 없이 도는 테스트(합성 문서만).

.hwp 열기(source.open_source), 그림 PNG 통일(as_png), 쪽 어림(page_guess), 멈춤 위치(ReverseStop), 머리 값 풀기(resolve_front)."""

import io

import lxml.etree as ET
import pytest
from exam_kit import HP
from exam_kit import source as source_mod
from exam_kit.reverse import ReverseStop, as_png, page_guess, resolve_front, reverse_body
from exam_kit.source import SourceError, open_source
from hwpx.document import HwpxDocument
from hwpx.hwp5.errors import Hwp5ConversionReport
from PIL import Image


def _p(inner: str = "", vertpos: int | None = None):
    seg = "" if vertpos is None else f'<hp:linesegarray><hp:lineseg textpos="0" vertpos="{vertpos}"/></hp:linesegarray>'
    return ET.fromstring(f'<hp:p xmlns:hp="{HP}" paraPrIDRef="0" styleIDRef="0">{inner}{seg}</hp:p>')


def _run(text: str) -> str:
    return f'<hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run>'


# ---- 입력 ------------------------------------------------------------------------------------


def test_원안지는_hwp나_hwpx만(tmp_path):
    with pytest.raises(SourceError, match="hwp 또는 .hwpx"):
        open_source(tmp_path / "a.docx", tmp_path)


def _가짜_hwp(monkeypatch, report: Hwp5ConversionReport):
    """HwpxDocument.open이 .hwp를 받으면 이 report를 단 합성 문서를 낸다(.hwpx 사본은 진짜로 연다)."""
    real = HwpxDocument.open

    def fake(path, *a, **k):
        if str(path).endswith(".hwp"):
            doc = HwpxDocument.new()
            doc._hwp5_report = report
            return doc
        return real(path, *a, **k)

    monkeypatch.setattr(source_mod.HwpxDocument, "open", staticmethod(fake))


def test_hwp_바꾸지_못한_내용이_있으면_멈춘다(tmp_path, monkeypatch):
    _가짜_hwp(monkeypatch, Hwp5ConversionReport.of({"chart": 2}, {}))
    with pytest.raises(SourceError, match=r"chart 2.*한/글에서 hwpx로 저장"):
        open_source(tmp_path / "원안지.hwp", tmp_path / "work")


def test_hwp_자리_없는_데이터는_알림으로_남고_변환_사본을_연다(tmp_path, monkeypatch):
    _가짜_hwp(monkeypatch, Hwp5ConversionReport.of({}, {"summaryInfo": 1}))
    src = open_source(tmp_path / "원안지.hwp", tmp_path / "work")
    assert src.hwpx == tmp_path / "work" / "원안지_변환.hwpx" and src.hwpx.is_file()
    assert src.notes and "summaryInfo 1" in src.notes[0]


# ---- 그림 --------------------------------------------------------------------------------------


def _image(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (30, 20), (200, 10, 10)).save(buf, fmt)
    return buf.getvalue()


def test_그림은_PNG로_통일한다():
    png = as_png(_image("BMP"), ".bmp")
    assert png.startswith(b"\x89PNG")
    with Image.open(io.BytesIO(png)) as im:
        assert im.size == (30, 20)  # 크기 그대로(무손실)
    assert as_png(b"\x89PNG-as-is", ".PNG") == b"\x89PNG-as-is"  # PNG는 손대지 않는다
    assert as_png(_image("JPEG"), ".jpg").startswith(b"\x89PNG")
    with pytest.raises(ValueError, match="PNG로 바꿀 수 없다"):
        as_png(b"not an image", ".wmf")


# ---- 쪽 어림·멈춤 위치 ---------------------------------------------------------------------------


def test_쪽_어림은_줄_배치가_줄어드는_곳을_새_단으로_센다():
    ps = [_p(vertpos=y) for y in (0, 900, 40, 500)] + [_p()] + [_p(vertpos=10)]
    assert page_guess(ps, 2) == [1, 1, 1, 1, 1, 2]  # 2단: 셋째 단(=2쪽) — 줄 캐시 없는 문단은 앞 쪽을 잇는다
    assert page_guess(ps, 1) == [1, 1, 2, 2, 2, 3]


def test_멈춤은_문항_쪽_문단_글을_알린다():
    head = _p(_run("가는? [1.0점]"), vertpos=0)
    choices = [_p(_run(f"{m} 답"), vertpos=100 * (i + 1)) for i, m in enumerate("①②③④⑤")]
    stray = _p(_run("덧붙인 글"), vertpos=20)  # 새 단 — 2단이면 1쪽, 1단이면 2쪽
    paras = [head, *choices, stray]
    with pytest.raises(ReverseStop) as e:
        reverse_body(paras, {0}, set(), pages=page_guess(paras, 1))
    stop = e.value
    assert (stop.question, stop.page, stop.paragraph, stop.snippet) == (1, 2, 6, "덧붙인 글")
    assert "답지 뒤에 본문" in stop.reason and str(stop).startswith("약 2쪽 · 1번 문항 · 문단 6:")


def test_문항_앞_내용도_자리를_알린다():
    paras = [_p(_run("떠도는 글")), _p(_run("가는? [1.0점]"))]
    with pytest.raises(ReverseStop) as e:
        reverse_body(paras, {1}, set())
    assert e.value.question is None and e.value.paragraph == 0 and "문항 앞" in str(e.value)


# ---- 머리 값 -----------------------------------------------------------------------------------

_필수 = ("양식", "학년도", "학년", "학기", "차", "과목", "시행", "출제교사")


def _읽음(**over):
    base = {"양식": "합성", "학년도": "2026", "학년": "1", "학기": "1", "차": "2", "과목": "수학", "과목코드": None,
            "시행": "__.__.(_) _교시", "대상": "1학년 1반~5반", "인쇄": "__매 * _묶음", "출제교사": "김출제", "대상_반": "1반~5반"}
    base.update(over)
    return base


def test_머리_값을_읽으면_그대로_쓴다():
    lines = resolve_front(_읽음(), {}, _필수)
    assert lines[0] == "---" and "과목: 수학" in lines and "대상: 1학년 1반~5반" in lines
    assert not any(x.startswith(("과목코드", "대상_반")) for x in lines)  # 못 읽은 선택 키·내부 키는 안 쓴다


def test_못_읽은_필수_머리_값은_무엇을_줄지_알리고_멈춘다():
    with pytest.raises(ReverseStop, match=r"학년, 과목.*--front 학년=… 과목=…"):
        resolve_front(_읽음(학년=None, 과목=None, 대상=None), {}, _필수)


def test_준_머리_값이_이기고_대상은_준_학년으로_다시_짓는다():
    lines = resolve_front(_읽음(학년=None, 과목=None, 대상=None), {"학년": "3", "과목": "기하"}, _필수)
    assert "학년: 3" in lines and "과목: 기하" in lines and "대상: 3학년 1반~5반" in lines


def test_모르는_머리_키는_멈춘다():
    with pytest.raises(ReverseStop, match="모르는 머리 키"):
        resolve_front(_읽음(), {"학급": "3"}, _필수)
