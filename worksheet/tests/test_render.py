import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

import worksheet.render as 렌더_모듈
from _helpers import _png
from worksheet.compose import compose
from worksheet.render import (
    RenderError,
    RenderResult,
    RenderUnavailable,
    _gdocs_명령들,
    _잔존_쪽_PNG_지우기,
    _parse_result,
    _read_completed,
    _쪽_파일_정리,
    oracle_python,
    render_gdocs,
    render_hancom,
    render_libreoffice,
)

기본 = """---
kit: 시험킷
title: 렌더 확인
grade: 2학년
---

## 섹션

:::답칸 label="가" lines=1
:::
"""

# hwpx 불변 게이트 기준선(tests/test_hwpx_불변.py)과 같은 전체-블록 문서 — 실물 렌더 두 개를 나란히 본다.
_전체_블록 = """---
kit: 시험킷
title: 기준선 회차
grade: 2학년
keywordPage: true
---

## 첫 제목
교과서: 33-35P

> 발문 한 줄이다.

■ 정의: 빈칸이 [[8]] 들어간 줄

![](본문.png){width=5cm}

:::라벨설명 labelWidth=3cm
[1] 라벨 하나
: 설명 하나
[2] 라벨 둘
: ![](칸.png)
:::

:::용어카드 cols="가|나|다"
설명 가
![](칸.png){width=2cm}
설명 다
:::

## 둘째 제목

:::비교표 cols="왼쪽|오른쪽" rows="첫째|둘째"
값1|![](칸.png)
값3|값4
:::

:::데이터표 head="단계|값" rows=3
1|가
2|나
:::

:::답칸 label="답 쓰는 곳" lines=2
:::

:::강조박스 title="규칙"
한 줄
두 줄
:::

:::나란히 cols="예제 1|예제 2"
![](칸.png){width=4cm}|![](칸.png){width=4cm}
DFS 순서 :|DFS 순서 :
:::
"""


def _전체_블록_docx(폴더: Path, 킷_루트: Path) -> Path:
    (폴더 / "본문.png").write_bytes(_png(400, 200))
    (폴더 / "칸.png").write_bytes(_png(300, 120))
    md = 폴더 / "기준선.md"
    md.write_text(_전체_블록, encoding="utf-8")
    out = 폴더 / "기준선.docx"
    compose(md, 킷_루트, out)
    return out


# --- _gdocs_명령들 — 구글 문서 왕복이 쓰는 rclone 명령 목록, 순수 함수 -------------------


def test_구글_문서_왕복_명령은_전용_폴더만_쓰고_끝에_지운다(tmp_path):
    명령들 = _gdocs_명령들(tmp_path / "a.docx", "gdrive:_worksheet_render_tmp/abc", tmp_path / "a.pdf")
    올리기, 받기, 지우기 = 명령들
    assert 올리기[:2] == ["rclone", "copyto"] and "--drive-import-formats" in 올리기 and "docx" in 올리기
    assert 올리기[3].startswith("gdrive:_worksheet_render_tmp/abc/")
    assert 받기[:2] == ["rclone", "copyto"] and "--drive-export-formats" in 받기 and "pdf" in 받기
    assert 지우기 == ["rclone", "purge", "gdrive:_worksheet_render_tmp/abc"]


@pytest.mark.libreoffice
def test_LibreOffice_렌더가_PNG를_낸다(킷_루트, tmp_path):
    docx = _전체_블록_docx(tmp_path, 킷_루트)
    결과 = render_libreoffice(docx, tmp_path / "기준선.png")
    assert 결과.pages >= 1
    assert 결과.pngs[0].exists()


def test_LibreOffice_렌더는_고유_프로필로_soffice를_부른다(monkeypatch, tmp_path):
    """`-env:UserInstallation`이 없으면 이미 떠 있는(또는 동시에 도는) soffice 인스턴스의
    프로필 락에 걸려 변환이 조용히 멈출 수 있다 — 실제 soffice·pdftoppm 없이 명령 인자만
    본다(subprocess.run을 흉내 낸다)."""
    호출들 = []

    def 가짜_run(cmd, **kwargs):
        호출들.append(cmd)
        if cmd[0] == "soffice":
            outdir = Path(cmd[cmd.index("--outdir") + 1])
            docx = Path(cmd[-1])
            (outdir / (docx.stem + ".pdf")).write_bytes(b"%PDF-1.4")
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("worksheet.render.subprocess.run", 가짜_run)
    monkeypatch.setattr("worksheet.render._pdf_to_pngs", lambda pdf, out_png, dpi: (out_png,))

    docx = tmp_path / "가짜.docx"
    docx.write_bytes(b"")
    render_libreoffice(docx, tmp_path / "out.png")

    soffice_명령 = 호출들[0]
    assert soffice_명령[0] == "soffice"
    프로필_인자 = next(a for a in soffice_명령 if a.startswith("-env:UserInstallation="))
    프로필_경로 = Path(프로필_인자.removeprefix("-env:UserInstallation=file://"))
    출력_임시 = Path(soffice_명령[soffice_명령.index("--outdir") + 1])
    assert 프로필_경로.parent == 출력_임시  # 호출마다 새로 생기는 TemporaryDirectory 안이다
    assert 프로필_경로.name == "profile"


@pytest.mark.gdocs
def test_구글_문서_왕복_렌더가_PNG를_낸다(킷_루트, tmp_path):
    docx = _전체_블록_docx(tmp_path, 킷_루트)
    결과 = render_gdocs(docx, tmp_path / "기준선.png")
    assert 결과.pages >= 1
    assert 결과.pngs[0].exists()


@pytest.mark.parametrize("단계, 실패_인덱스", [("올리기", 0), ("받기", 1)])
def test_구글_문서_왕복_실패_메시지는_단계를_밝힌다(monkeypatch, tmp_path, 단계, 실패_인덱스):
    """실제 rclone·네트워크 없이(subprocess.run을 흉내 내) 올리기·받기 각각의 실패가
    메시지에 단계 이름으로 남는지만 본다. 지우기(purge)는 finally 에서 늘 불린다."""
    호출_순서 = []

    def 가짜_run(cmd, **kwargs):
        호출_순서.append(cmd)
        if len(호출_순서) - 1 == 실패_인덱스:
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": f"{단계} 에러"})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("worksheet.render.subprocess.run", 가짜_run)
    docx = tmp_path / "가짜.docx"
    docx.write_bytes(b"")
    with pytest.raises(RuntimeError, match=f"구글 문서 {단계} 실패"):
        render_gdocs(docx, tmp_path / "out.png")
    assert 호출_순서[-1][:2] == ["rclone", "purge"]  # finally 의 지우기는 실패해도 불린다


# --- _쪽_파일_정리 — pdftoppm 뒤 0-패딩 폭이 쪽수에 따라 달라도 쪽 순서대로 통일, 순수 함수 ---


def test_쪽_파일_정리는_패딩_없는_이름도_쪽_순서대로_세_자리로_통일한다(tmp_path):
    """1~9쪽짜리 문서는 pdftoppm이 패딩 없이 `-1`·`-2` … 로 낸다."""
    접두 = tmp_path / "r"
    (tmp_path / "r-1.png").write_bytes(b"first")
    (tmp_path / "r-2.png").write_bytes(b"second")
    결과 = _쪽_파일_정리(접두)
    assert [p.name for p in 결과] == ["r-001.png", "r-002.png"]
    assert 결과[0].read_bytes() == b"first"
    assert 결과[1].read_bytes() == b"second"


def test_쪽_파일_정리는_두_자리_패딩_이름도_쪽_순서대로_읽는다(tmp_path):
    """10쪽 이상짜리 문서는 pdftoppm이 `-01`·`-02` … 로 낸다 — 사전순이면 `-10`이 `-2`보다
    앞에 와 틀린다. 정수 비교(`_쪽_번호`)라야 맞는다."""
    접두 = tmp_path / "s"
    (tmp_path / "s-01.png").write_bytes(b"1")
    (tmp_path / "s-02.png").write_bytes(b"2")
    (tmp_path / "s-10.png").write_bytes(b"10")
    결과 = _쪽_파일_정리(접두)
    assert [p.name for p in 결과] == ["s-001.png", "s-002.png", "s-003.png"]
    assert [p.read_bytes() for p in 결과] == [b"1", b"2", b"10"]


def test_쪽_파일_정리는_이미_세_자리_패딩이면_그대로_둔다(tmp_path):
    """100쪽 이상짜리 문서는 pdftoppm이 이미 `-001` … 로 낸다 — 자기 자신으로 덮어쓰지 않는다."""
    접두 = tmp_path / "t"
    (tmp_path / "t-001.png").write_bytes(b"1")
    (tmp_path / "t-002.png").write_bytes(b"2")
    결과 = _쪽_파일_정리(접두)
    assert [p.name for p in 결과] == ["t-001.png", "t-002.png"]
    assert [p.read_bytes() for p in 결과] == [b"1", b"2"]


# --- _잔존_쪽_PNG_지우기 — 이전 실행이 같은 폴더에 남긴 쪽 PNG만 지운다, 순수 함수 -----------


def test_잔존_쪽_PNG_지우기는_쪽_번호_패턴만_지우고_그_밖은_남긴다(tmp_path):
    접두 = tmp_path / "r"
    (tmp_path / "r-1.png").write_bytes("쪽1".encode())
    (tmp_path / "r-002.png").write_bytes("쪽2".encode())
    안_지워질 = {
        "다른파일.png": "무관".encode(),
        "r.png": "대시_숫자_형태가_아니다".encode(),
        "r-표지.png": "숫자가_아닌_꼬리".encode(),
        "r-1.png.bak": "확장자가_다르다".encode(),
    }
    for 이름, 내용 in 안_지워질.items():
        (tmp_path / 이름).write_bytes(내용)

    _잔존_쪽_PNG_지우기(접두)

    assert not (tmp_path / "r-1.png").exists()
    assert not (tmp_path / "r-002.png").exists()
    for 이름, 내용 in 안_지워질.items():
        assert (tmp_path / 이름).read_bytes() == 내용


def test_이전_실행의_잔존_PNG는_이번_렌더_결과와_안_섞인다(tmp_path):
    """실측 재현: 이전 실행(13쪽, 이미 3자리로 정규화됨)이 남은 폴더에서 이번 렌더(3쪽,
    pdftoppm 무패딩 출력)를 하면 — 지우기 없이는 `_쪽_파일_정리`가 결과를 13개로 잘못 합치고
    일부 경로가 `FileNotFoundError`가 난다. 먼저 지우면 이번 3쪽만 남는다."""
    접두 = tmp_path / "r"
    for i in range(1, 14):
        (tmp_path / f"r-{i:03d}.png").write_bytes(f"옛{i}".encode())

    _잔존_쪽_PNG_지우기(접두)
    for i in range(1, 4):
        (tmp_path / f"r-{i}.png").write_bytes(f"새{i}".encode())

    결과 = _쪽_파일_정리(접두)

    assert len(결과) == 3
    assert all(p.exists() for p in 결과)
    assert [p.name for p in 결과] == ["r-001.png", "r-002.png", "r-003.png"]
    assert [p.read_bytes() for p in 결과] == [f"새{i}".encode() for i in range(1, 4)]


@pytest.mark.hancom
def test_실한컴_렌더가_PNG를_낸다(킷_루트, tmp_path):
    md = tmp_path / "r.md"
    md.write_text(기본, encoding="utf-8")
    hwpx = tmp_path / "r.hwpx"
    compose(md, 킷_루트, hwpx)

    결과 = render_hancom(hwpx, tmp_path / "r.png")
    assert 결과.pages >= 1
    assert 결과.pdf == (tmp_path / "r.pdf").resolve() and 결과.pdf.exists()
    assert [p.name for p in 결과.pngs] == [f"r-{i:03d}.png" for i in range(1, 결과.pages + 1)]
    assert 결과.pngs[0].exists()
    assert 결과.pngs[0].stat().st_size > 5_000


# --- _parse_result — 서브프로세스 stdout(JSON 마지막 줄) → RenderResult, 순수 함수 -------


def test_parse_result은_1쪽_결과를_읽는다():
    stdout = json.dumps({"pages": 1, "pngs": ["/tmp/r-001.png"], "pdf": "/tmp/r.pdf"})
    결과 = _parse_result(stdout)
    assert 결과 == RenderResult(pages=1, pngs=(Path("/tmp/r-001.png"),), pdf=Path("/tmp/r.pdf"))


def test_parse_result은_3쪽_결과를_읽는다():
    stdout = json.dumps({
        "pages": 3,
        "pngs": ["/tmp/r-001.png", "/tmp/r-002.png", "/tmp/r-003.png"],
        "pdf": "/tmp/r.pdf",
    })
    결과 = _parse_result(stdout)
    assert 결과.pages == 3
    assert 결과.pngs == (
        Path("/tmp/r-001.png"), Path("/tmp/r-002.png"), Path("/tmp/r-003.png"),
    )
    assert 결과.pdf == Path("/tmp/r.pdf")


def test_parse_result은_앞에_잡음_줄이_섞여도_마지막_JSON_줄만_읽는다():
    stdout = "폰트를 불러오는 중...\n경고: 임시 폰트로 대체\n" + json.dumps(
        {"pages": 1, "pngs": ["/tmp/r-001.png"], "pdf": "/tmp/r.pdf"}
    )
    결과 = _parse_result(stdout)
    assert 결과.pages == 1
    assert 결과.pngs == (Path("/tmp/r-001.png"),)


def test_parse_result은_JSON이_없으면_RuntimeError():
    with pytest.raises(RuntimeError, match="실한컴 렌더 실패"):
        _parse_result("그냥 텍스트\n또 다른 줄\n")


def test_parse_result은_빈_stdout도_RuntimeError():
    with pytest.raises(RuntimeError, match="실한컴 렌더 실패"):
        _parse_result("")


# --- 형태는 맞지만 내용이 틀린 JSON도 RuntimeError(bare KeyError/TypeError 대신) ---


def test_parse_result은_JSON이_dict가_아니면_RuntimeError():
    with pytest.raises(RuntimeError, match="실한컴 렌더 결과를 읽을 수 없다"):
        _parse_result(json.dumps([1, 2, 3]))


def test_parse_result은_필요한_키가_없으면_RuntimeError():
    with pytest.raises(RuntimeError, match="실한컴 렌더 결과를 읽을 수 없다"):
        _parse_result(json.dumps({"foo": 1}))


def test_parse_result은_pngs_개수가_pages와_다르면_RuntimeError():
    stdout = json.dumps({"pages": 2, "pngs": ["/tmp/r-001.png"], "pdf": "/tmp/r.pdf"})
    with pytest.raises(RuntimeError, match="실한컴 렌더 결과를 읽을 수 없다"):
        _parse_result(stdout)


# --- oracle_python — HWPX_ORACLE_PY가 있으면 그 인터프리터, 없으면 이 프로젝트의 것 --------


def test_oracle_python은_HWPX_ORACLE_PY가_있으면_그_경로를_쓴다(monkeypatch, tmp_path):
    가짜_파이썬 = tmp_path / "python"
    가짜_파이썬.write_text("", encoding="utf-8")
    monkeypatch.setenv("HWPX_ORACLE_PY", str(가짜_파이썬))
    assert oracle_python() == 가짜_파이썬


def test_oracle_python은_HWPX_ORACLE_PY가_없는_파일이면_거부한다(monkeypatch, tmp_path):
    monkeypatch.setenv("HWPX_ORACLE_PY", str(tmp_path / "없는파일"))
    with pytest.raises(FileNotFoundError):
        oracle_python()


# --- 공개 render-pdf 호출(#18) — 플러그인 캐시·생성형 스크립트 없이 ------------------------


@pytest.fixture
def 플러그인_없는_집(monkeypatch, tmp_path):
    """hwpx 플러그인을 설치하지 않은 사용자 — 홈에 플러그인 캐시가 없고 HWPX_ORACLE_PY도 없다."""
    집 = tmp_path / "home"
    집.mkdir()
    monkeypatch.setenv("HOME", str(집))
    monkeypatch.setenv("USERPROFILE", str(집))
    monkeypatch.delenv("HWPX_ORACLE_PY", raising=False)
    return 집


def test_렌더_모듈은_플러그인_캐시와_사설_오라클을_쓰지_않는다():
    소스 = inspect.getsource(렌더_모듈)
    for 금지 in (".hwpx-mcp-runtime", "plugins/cache", "MacHancomOracle", "python -c", '"-c"'):
        assert 금지 not in 소스, 금지


def test_oracle_python은_플러그인이_없어도_이_프로젝트의_인터프리터를_쓴다(플러그인_없는_집):
    assert oracle_python() == Path(sys.executable)


def _성공_줄(명령: list[str], pages: int) -> str:
    접두 = 명령[명령.index("--png") + 1]
    return json.dumps({
        "ok": True,
        "pdf": 명령[5],
        "pages": pages,
        "pngs": [f"{접두}-{i:03d}.png" for i in range(1, pages + 1)],
        "backend": "windows",
    })


def test_render_hancom은_공개_render_pdf_명령을_부른다(플러그인_없는_집, monkeypatch, tmp_path):
    잡힌: dict = {}

    def 가짜_run(명령, **kw):
        잡힌["명령"], 잡힌["kw"] = 명령, kw
        return subprocess.CompletedProcess(명령, 0, stdout="잡음 줄\n" + _성공_줄(명령, 2) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", 가짜_run)
    hwpx = tmp_path / "in.hwpx"
    결과 = render_hancom(hwpx, tmp_path / "out" / "r.png", dpi=96, timeout=120)

    명령 = 잡힌["명령"]
    assert 명령[:4] == [sys.executable, "-m", "hwpx_automation.office.rendering", "render-pdf"]
    assert 명령[4:6] == [str(hwpx.resolve()), str((tmp_path / "out" / "r.pdf").resolve())]
    assert 명령[명령.index("--png") + 1] == str((tmp_path / "out" / "r").resolve())
    assert 명령[명령.index("--dpi") + 1] == "96"
    assert 명령[명령.index("--backend") + 1] == "auto"
    assert 명령[명령.index("--timeout") + 1] == "120"
    assert "--json" in 명령
    assert 잡힌["kw"]["timeout"] > 120  # 바깥 기한은 render-pdf 자기 예산보다 길다
    assert (tmp_path / "out").is_dir()
    assert 결과.pages == 2
    assert [p.name for p in 결과.pngs] == ["r-001.png", "r-002.png"]
    assert 결과.pdf == (tmp_path / "out" / "r.pdf").resolve()


def test_render_hancom은_HWPX_ORACLE_PY_인터프리터로도_같은_공개_진입점을_부른다(monkeypatch, tmp_path):
    다른_파이썬 = tmp_path / "render-env" / "python.exe"
    다른_파이썬.parent.mkdir()
    다른_파이썬.write_text("", encoding="utf-8")
    monkeypatch.setenv("HWPX_ORACLE_PY", str(다른_파이썬))
    잡힌: list = []

    def 가짜_run(명령, **kw):
        잡힌.append(명령)
        return subprocess.CompletedProcess(명령, 0, stdout=_성공_줄(명령, 1), stderr="")

    monkeypatch.setattr(subprocess, "run", 가짜_run)
    render_hancom(tmp_path / "in.hwpx", tmp_path / "r.png")
    assert 잡힌[0][:4] == [str(다른_파이썬), "-m", "hwpx_automation.office.rendering", "render-pdf"]


def test_render_hancom은_시간_초과를_RuntimeError로_낸다(플러그인_없는_집, monkeypatch, tmp_path):
    def 가짜_run(명령, **kw):
        raise subprocess.TimeoutExpired(명령, kw["timeout"])

    monkeypatch.setattr(subprocess, "run", 가짜_run)
    with pytest.raises(RuntimeError, match="시간 초과"):
        render_hancom(tmp_path / "in.hwpx", tmp_path / "r.png", timeout=5)


# --- _read_completed — render-pdf의 종료 코드·JSON 결과를 읽는다, 순수 함수 ---------------


def _실패_줄(코드: str, 메시지: str = "합성 사유") -> str:
    return json.dumps({"ok": False, "error": 코드, "message": 메시지, "backend": None})


def test_read_completed는_한컴이_없으면_RenderUnavailable():
    with pytest.raises(RenderUnavailable) as 잡힘:
        _read_completed(3, _실패_줄("hancom-unavailable", "no Hancom reachable"), "")
    assert 잡힘.value.code == "hancom-unavailable"
    assert "no Hancom reachable" in str(잡힘.value)
    assert isinstance(잡힘.value, RuntimeError)  # 기존 호출자의 `except RuntimeError`가 그대로 잡는다


def test_read_completed는_렌더_실패_코드를_RenderError로_낸다():
    with pytest.raises(RenderError) as 잡힘:
        _read_completed(1, _실패_줄("hancom-refused"), "")
    assert 잡힘.value.code == "hancom-refused"
    assert not isinstance(잡힘.value, RenderUnavailable)


def test_read_completed는_결과_줄_없이_끝나면_stderr를_담는다():
    with pytest.raises(RuntimeError, match="종료 코드 1.*No module named"):
        _read_completed(1, "", "No module named hwpx_automation")


def test_read_completed는_결과_줄_없이_코드_3이면_RenderUnavailable():
    with pytest.raises(RenderUnavailable):
        _read_completed(3, "", "합성 사유")


def test_read_completed는_0이_아닌_코드의_성공_줄을_믿지_않는다():
    줄 = json.dumps({"ok": True, "pdf": "/t/r.pdf", "pages": 1, "pngs": ["/t/r-001.png"], "backend": "mac"})
    with pytest.raises(RuntimeError, match="종료 코드 1"):
        _read_completed(1, 줄, "")


def test_read_completed는_성공_줄을_RenderResult로_읽는다():
    줄 = json.dumps({"ok": True, "pdf": "/t/r.pdf", "pages": 1, "pngs": ["/t/r-001.png"], "backend": "mac"})
    assert _read_completed(0, 줄, "") == RenderResult(pages=1, pngs=(Path("/t/r-001.png"),), pdf=Path("/t/r.pdf"))


# --- 진짜 공개 명령을 한컴 없이 돌린다 — [oracle] extra가 이 프로젝트에 깔려 있어야 지난다 ---


def test_실제_render_pdf는_구조_전용이면_RenderUnavailable(킷_루트, 플러그인_없는_집, monkeypatch, tmp_path):
    """`HWPX_ORACLE_STRUCTURAL_ONLY=1`이면 render-pdf는 한컴을 찾지도 띄우지도 않고 종료 코드 3과
    `hancom-unavailable` 결과 줄로 끝난다. 그 앞 단계(입력 hwpx 검사·pymupdf 확인)는 실제로 돈다."""
    md = tmp_path / "r.md"
    md.write_text(기본, encoding="utf-8")
    hwpx = tmp_path / "r.hwpx"
    compose(md, 킷_루트, hwpx)
    monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", "1")

    with pytest.raises(RenderUnavailable) as 잡힘:
        render_hancom(hwpx, tmp_path / "r.png")
    assert 잡힘.value.code == "hancom-unavailable"
    assert not (tmp_path / "r.pdf").exists()


def test_실제_render_pdf는_없는_입력을_RenderError로_낸다(플러그인_없는_집, monkeypatch, tmp_path):
    monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", "1")
    with pytest.raises(RenderError) as 잡힘:
        render_hancom(tmp_path / "없는.hwpx", tmp_path / "r.png")
    assert 잡힘.value.code == "input-missing"
