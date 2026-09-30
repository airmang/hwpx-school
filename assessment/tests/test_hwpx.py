import os
import struct
import zipfile
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from assessment.backends.hwpx import HwpxWriter
from assessment.blocks import InputError
from assessment.compose import compose, output_paths
from assessment.kit import load_kit
from assessment.ns import HP

MD = """---
kit: standard
title: 인공지능 기초 수행평가(A)
score: 25점/기본점수 10점
total: 4
---

## 용어를 쓰시오 {총 2점}
:::제시문
그래프는 ( 가 )(와) ( 나 )(으)로 이루어진다.
:::
:::답칸 (가) | (나)
:::정답
(가) 노드
(나) 간선
:::

## 순서를 쓰시오. {각 1점, 총 2점}
> (단, 왼쪽부터 탐색한다.)
:::표답칸
BFS
DFS
:::
:::단나눔
:::서술칸 3줄
:::정답
BFS: A-B-C
:::
"""


@pytest.fixture(scope="module")
def 산출(킷_루트, tmp_path_factory):
    d = tmp_path_factory.mktemp("out")
    (d / "a.md").write_text(MD, encoding="utf-8")
    report = compose(d / "a.md", 킷_루트, d / "a.hwpx")
    return report


def _섹션(path: Path) -> ET.Element:
    with zipfile.ZipFile(path) as z:
        return ET.fromstring(z.read("Contents/section0.xml"))


def test_두_파일(산출):
    assert 산출.student.name == "a_학생용.hwpx" and 산출.answers.name == "a_정답용.hwpx"
    assert 산출.items == 2 and 산출.memos == 2


def test_output_paths():
    assert output_paths(Path("/x/시험(A).hwpx")) == (Path("/x/시험(A)_학생용.hwpx"), Path("/x/시험(A)_정답용.hwpx"))


def test_학생용에는_메모가_없고_정답용에는_문항수만큼(산출):
    for path, 기대 in ((산출.student, 0), (산출.answers, 2)):
        메모 = [e for e in _섹션(path).iter(f"{{{HP}}}fieldBegin") if e.get("type") == "MEMO"]
        assert len(메모) == 기대


def test_머리_1단_본문_2단_순서(산출):
    문단 = _섹션(산출.student).findall(f"{{{HP}}}p")
    # 제목 글은 markpenBegin 의 tail 에 있다 — t.text 가 아니라 itertext 로 읽는다.
    글 = ["".join("".join(t.itertext()) for t in p.iter(f"{{{HP}}}t")) for p in 문단]
    assert 글[0].startswith("인공지능 기초 수행평가(A)")
    assert "학번" in 글[1]
    assert [c.get("colCount") for c in 문단[2].iter(f"{{{HP}}}colPr")] == ["2"]
    assert 글[3].startswith("1. 용어를 쓰시오")


def test_단나눔은_다음_문단의_columnBreak(산출):
    문단 = _섹션(산출.student).findall(f"{{{HP}}}p")
    assert sum(1 for p in 문단 if p.get("columnBreak") == "1") == 1


def test_제목_형광펜(산출, 킷_루트):
    xml = zipfile.ZipFile(산출.student).read("Contents/section0.xml").decode()
    색 = load_kit(킷_루트).furniture["titleMarkpen"]
    assert f'markpenBegin color="{색}"' in xml and "markpenEnd" in xml


def test_검사_문제가_있으면_조판하지_않는다(킷_루트, tmp_path):
    (tmp_path / "b.md").write_text(MD.replace("total: 4", "total: 9"), encoding="utf-8")
    with pytest.raises(ValueError, match="배점 합계"):
        compose(tmp_path / "b.md", 킷_루트, tmp_path / "b.hwpx")
    assert not list(tmp_path.glob("*.hwpx"))


def test_두번째_패스가_실패하면_임시파일도_안_남고_기존_쌍도_그대로(킷_루트, tmp_path, monkeypatch):
    """Minor-1: 2번째 패스(정답용) 실패는 새 학생용을 남기지도, 기존 쌍을 건드리지도 않는다."""
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    out = tmp_path / "a.hwpx"
    이전 = compose(tmp_path / "a.md", 킷_루트, out)
    이전_학생_바이트 = 이전.student.read_bytes()
    이전_정답_바이트 = 이전.answers.read_bytes()

    원래_save = HwpxWriter.save
    호출_수 = {"n": 0}

    def _두번째에_실패(self, path):
        호출_수["n"] += 1
        if 호출_수["n"] == 2:
            raise RuntimeError("일부러 실패")
        원래_save(self, path)

    monkeypatch.setattr(HwpxWriter, "save", _두번째에_실패)
    with pytest.raises(RuntimeError, match="일부러 실패"):
        compose(tmp_path / "a.md", 킷_루트, out)

    assert 이전.student.read_bytes() == 이전_학생_바이트
    assert 이전.answers.read_bytes() == 이전_정답_바이트
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [이전.student.name, 이전.answers.name, "a.md"]
    )


def test_정답_교체만_실패하면_기존_쌍이_그대로다(킷_루트, tmp_path, monkeypatch):
    """§8: 마지막 os.replace 두 번(학생·정답)도 전부-아니면-전무 — 기존 쌍이 있던 경우."""
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    out = tmp_path / "a.hwpx"
    이전 = compose(tmp_path / "a.md", 킷_루트, out)
    이전_학생_바이트 = 이전.student.read_bytes()
    이전_정답_바이트 = 이전.answers.read_bytes()

    원래_replace = os.replace

    def _정답만_실패(src, dst):
        if Path(dst) == 이전.answers:
            raise OSError("일부러 실패")
        원래_replace(src, dst)

    monkeypatch.setattr(os, "replace", _정답만_실패)
    with pytest.raises(OSError, match="일부러 실패"):
        compose(tmp_path / "a.md", 킷_루트, out)

    assert 이전.student.read_bytes() == 이전_학생_바이트
    assert 이전.answers.read_bytes() == 이전_정답_바이트
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [이전.student.name, 이전.answers.name, "a.md"]
    )


def test_정답_교체만_실패하면_기존_쌍이_없을_땐_아무것도_안_남는다(킷_루트, tmp_path, monkeypatch):
    """§8: 기존 쌍이 없던 최초 compose 에서 정답 교체만 실패하면 새 학생용도 남지 않는다."""
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    out = tmp_path / "a.hwpx"
    학생, 정답 = output_paths(out)

    원래_replace = os.replace

    def _정답만_실패(src, dst):
        if Path(dst) == 정답:
            raise OSError("일부러 실패")
        원래_replace(src, dst)

    monkeypatch.setattr(os, "replace", _정답만_실패)
    with pytest.raises(OSError, match="일부러 실패"):
        compose(tmp_path / "a.md", 킷_루트, out)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md"]


def test_단나눔_뒤에_아무것도_없이_저장하면_InputError(킷_루트, tmp_path):
    """§8: :::단나눔 뒤에 문단이 하나도 없이 save() 하면 InputError(cli 는 이걸로 종료코드 2)."""
    from assessment.plan import ColumnBreakPlan

    w = HwpxWriter(load_kit(킷_루트))
    w.draw(ColumnBreakPlan())
    with pytest.raises(InputError, match="단나눔 뒤에 아무 내용이 없다"):
        w.save(tmp_path / "x.hwpx")
    assert not (tmp_path / "x.hwpx").exists()


def test_조판_성공하면_기존_쌍을_교체한다(킷_루트, tmp_path):
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    out = tmp_path / "a.hwpx"
    첫 = compose(tmp_path / "a.md", 킷_루트, out)
    첫_학생_바이트 = 첫.student.read_bytes()

    다른_MD = MD.replace("용어를 쓰시오", "용어를 다시 쓰시오")
    (tmp_path / "a.md").write_text(다른_MD, encoding="utf-8")
    둘째 = compose(tmp_path / "a.md", 킷_루트, out)

    assert 둘째.student.read_bytes() != 첫_학생_바이트
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [둘째.student.name, 둘째.answers.name, "a.md"]
    )


def _header(path: Path) -> ET.Element:
    with zipfile.ZipFile(path) as z:
        return ET.fromstring(z.read("Contents/header.xml"))


def test_답칸_밑줄은_칸_아래_테두리다(산출):
    """밑줄은 칸 아래 테두리(칸 폭 = 밑줄 길이, 글꼴 무관) — 공백 채움·글자 밑줄이 없다."""
    from assessment.ns import HH
    헤더 = _header(산출.student)
    칸들 = [tc for tc in _섹션(산출.student).iter(f"{{{HP}}}tc") if "".join(tc.itertext()).strip() in ("(가)", "(나)")]
    assert len(칸들) == 2
    for 칸 in 칸들:
        assert "".join(칸.itertext()) in ("(가)", "(나)")  # 공백 채움 없음
        bf = 헤더.find(f".//{{{HH}}}borderFill[@id='{칸.get('borderFillIDRef')}']")
        변 = {s: bf.find(f"{{{HH}}}{s}Border").get("type") for s in ("left", "right", "top", "bottom")}
        assert 변 == {"left": "NONE", "right": "NONE", "top": "NONE", "bottom": "SOLID"}
        for run in 칸.iter(f"{{{HP}}}run"):
            cp = 헤더.find(f".//{{{HH}}}charPr[@id='{run.get('charPrIDRef')}']")
            assert cp.find(f"{{{HH}}}underline").get("type") == "NONE"
    # 답칸 사이 틈 칸은 테두리가 없다 — 밑줄이 칸마다 끊어져 보인다.
    행 = [tc for tr in _섹션(산출.student).iter(f"{{{HP}}}tr") for tc in [list(tr.iter(f"{{{HP}}}tc"))] if any("".join(c.itertext()) == "(가)" for c in tc)][0]
    assert len(행) == 3
    틈 = 헤더.find(f".//{{{HH}}}borderFill[@id='{행[1].get('borderFillIDRef')}']")
    assert all(틈.find(f"{{{HH}}}{s}Border").get("type") == "NONE" for s in ("left", "right", "top", "bottom"))


def test_표_바깥_여백은_킷_값(산출, 킷_루트):
    """표 바깥 여백은 킷 값(사방) — python-hwpx 기본값 0 이면 표 둘레 간격이 좁다."""
    값 = str(load_kit(킷_루트).furniture["tableOutMargin"])
    for path in (산출.student, 산출.answers):
        여백 = [t.find(f"{{{HP}}}outMargin") for t in _섹션(path).iter(f"{{{HP}}}tbl")]
        assert 여백 and all(
            m is not None and [m.get(k) for k in ("left", "right", "top", "bottom")] == [값] * 4 for m in 여백
        )


def _png(w: int, h: int) -> bytes:
    def c(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + c(b"IDAT", zlib.compress(raw)) + c(b"IEND", b"")


def test_그림_캡션_왼쪽_정렬(킷_루트, tmp_path):
    """caption=left 면 캡션 문단만 킷의 caption_left — 그림 문단은 role 대로 가운데(center)."""
    (tmp_path / "a.png").write_bytes(_png(200, 100))
    md = """---
kit: standard
title: 그림 시험
total: 2
---

## 그림 문제 {2점}
![캡션 줄](a.png){caption=left}
:::정답
답
:::
"""
    (tmp_path / "a.md").write_text(md, encoding="utf-8")
    r = compose(tmp_path / "a.md", 킷_루트, tmp_path / "a.hwpx")
    k = load_kit(킷_루트)
    칸 = next(tc for tc in _섹션(r.student).iter(f"{{{HP}}}tc") if list(tc.iter(f"{{{HP}}}pic")))
    문단들 = list(칸.iter(f"{{{HP}}}p"))
    그림_문단, 캡션_문단 = 문단들
    assert 그림_문단.get("paraPrIDRef") == str(k.para_pr["center"])
    assert 캡션_문단.get("paraPrIDRef") == str(k.para_pr["caption_left"])
    assert "".join(캡션_문단.itertext()) == "캡션 줄"


def test_그림_캡션_기본은_가운데_정렬(킷_루트, tmp_path):
    """caption= 을 안 쓰면 캡션도 그림과 같이 role 대로 가운데(center)."""
    (tmp_path / "a.png").write_bytes(_png(200, 100))
    md = """---
kit: standard
title: 그림 시험
total: 2
---

## 그림 문제 {2점}
![캡션 줄](a.png)
:::정답
답
:::
"""
    (tmp_path / "a.md").write_text(md, encoding="utf-8")
    r = compose(tmp_path / "a.md", 킷_루트, tmp_path / "a.hwpx")
    k = load_kit(킷_루트)
    칸 = next(tc for tc in _섹션(r.student).iter(f"{{{HP}}}tc") if list(tc.iter(f"{{{HP}}}pic")))
    문단들 = list(칸.iter(f"{{{HP}}}p"))
    assert all(p.get("paraPrIDRef") == str(k.para_pr["center"]) for p in 문단들)


def test_병합_머리_표의_colSpan_rowSpan(킷_루트, tmp_path):
    """`<`·`^` 병합이 hwpx 칸 병합(cellSpan)으로 — 가려진 칸은 없고, 세로 병합 칸 높이는 두 행 합."""
    md = """---
kit: standard
title: 병합 시험
total: 2
---

## 혼동 행렬을 채우시오 {2점}
| 답칸 1-① | 예측 | < |
| ^ | 예측 양성 | 예측 음성 |
|---|---|---|
| 실제 양성 |  |  |
| 실제 음성 |  |  |
:::정답
답
:::
"""
    (tmp_path / "a.md").write_text(md, encoding="utf-8")
    r = compose(tmp_path / "a.md", 킷_루트, tmp_path / "a.hwpx")
    k = load_kit(킷_루트)
    표 = next(t for t in _섹션(r.student).iter(f"{{{HP}}}tbl") if "예측 양성" in "".join(t.itertext()))
    assert (표.get("rowCnt"), 표.get("colCnt")) == ("4", "3")
    행들 = 표.findall(f"{{{HP}}}tr")
    assert [len(tr.findall(f"{{{HP}}}tc")) for tr in 행들] == [2, 2, 3, 3]

    def 칸(tc):
        sp, sz, ad = (tc.find(f"{{{HP}}}{x}") for x in ("cellSpan", "cellSz", "cellAddr"))
        return ("".join(tc.itertext()), (ad.get("rowAddr"), ad.get("colAddr")), (sp.get("rowSpan"), sp.get("colSpan")), sz)

    답칸, 예측 = (칸(tc) for tc in 행들[0].findall(f"{{{HP}}}tc"))
    w = k.furniture["widths"]
    assert 답칸[:3] == ("답칸 1-①", ("0", "0"), ("2", "1"))
    assert 답칸[3].get("width") == str(w["dataLabel"])
    assert 답칸[3].get("height") == str(2 * k.furniture["rowHeight"]["auto"])
    assert 예측[:3] == ("예측", ("0", "1"), ("1", "2"))
    assert 예측[3].get("width") == str(w["box"] - w["dataLabel"])
    assert [칸(tc)[0] for tc in 행들[1].findall(f"{{{HP}}}tc")] == ["예측 양성", "예측 음성"]


def test_나란히와_문항_밖_안내(킷_루트, tmp_path):
    """최상위 안내 상자 + 나란히 2칸·3칸 — 한 행 N칸 표, 칸마다 그림 하나."""
    for n in "abc":
        (tmp_path / f"{n}.png").write_bytes(_png(200, 100))
    md = """---
kit: standard
title: 나란히 시험
total: 1
---

:::안내
시험 전 안내 글
:::
:::나란히
![가](a.png)
![나](b.png){caption=left}
:::
## 문제 {1점}
:::나란히
![](a.png)
![](b.png)
![](c.png)
:::
:::정답
답
:::
"""
    (tmp_path / "a.md").write_text(md, encoding="utf-8")
    r = compose(tmp_path / "a.md", 킷_루트, tmp_path / "a.hwpx")
    뿌리 = _섹션(r.student)
    그림표 = [t for t in 뿌리.iter(f"{{{HP}}}tbl") if list(t.iter(f"{{{HP}}}pic"))]
    assert [(t.get("rowCnt"), t.get("colCnt")) for t in 그림표] == [("1", "2"), ("1", "3")]
    assert [len(list(t.iter(f"{{{HP}}}pic"))) for t in 그림표] == [2, 3]
    assert [len(list(t.iter(f"{{{HP}}}tc"))) for t in 그림표] == [2, 3]
    글 = "".join(뿌리.itertext())
    assert "시험 전 안내 글" in 글 and 글.index("시험 전 안내 글") < 글.index("1. 문제")
