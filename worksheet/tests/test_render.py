import json
from pathlib import Path

import pytest

from _helpers import _png
from worksheet.compose import compose
from worksheet.render import (
    RenderResult,
    _gdocs_명령들,
    _잔존_쪽_PNG_지우기,
    _parse_result,
    _pick,
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
def test_오라클_런타임을_찾는다():
    """이 머신의 플러그인 캐시에 의존한다 — 다른 머신·CI의 기본 실행에서는 실패한다."""
    assert oracle_python().exists()


@pytest.mark.hancom
def test_실한컴_렌더가_PNG를_낸다(킷_루트, tmp_path):
    md = tmp_path / "r.md"
    md.write_text(기본, encoding="utf-8")
    hwpx = tmp_path / "r.hwpx"
    compose(md, 킷_루트, hwpx)

    결과 = render_hancom(hwpx, tmp_path / "r.png")
    assert 결과.pages >= 1
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


# --- _pick — 후보 경로 중 버전이 가장 높은 것(사전순이 아니라 숫자 비교) -------------------


def test_pick은_버전을_사전순이_아니라_숫자로_비교한다():
    """사전순 문자열 비교로는 '2.10.0' < '2.2.0'이 된다 — 진짜로는 2.10.0이 더 높은 버전이다."""
    낮음 = Path("/x/hwpx-plugin/2.2.0/.hwpx-mcp-runtime/envs/e/gen-1/bin/python")
    높음 = Path("/x/hwpx-plugin/2.10.0/.hwpx-mcp-runtime/envs/e/gen-1/bin/python")
    assert _pick([낮음, 높음]) == 높음
    assert _pick([높음, 낮음]) == 높음  # 순서를 바꿔도 결과가 같다


def test_pick은_후보가_하나면_그것을_돌려준다():
    유일 = Path("/x/hwpx-plugin/1.0.0/.hwpx-mcp-runtime/envs/e/gen-1/bin/python")
    assert _pick([유일]) == 유일


# --- 버전 조각이 숫자가 아니어도(프리릴리스 접미사 등) 안 터진다 --------------------


def test_pick은_숫자가_아닌_버전_조각에서_안_터진다():
    """'2.10.0-beta'처럼 마지막 조각이 숫자로 안 읽히면 `int()`가 ValueError를 던진다 —
    0으로 치고 원본 문자열을 보조 키로 써서 그래도 결정적으로 고른다(터지지만 않으면 된다;
    어느 쪽이 "더 높다"인지는 이 테스트가 못박지 않는다)."""
    프리릴리스 = Path("/x/hwpx-plugin/2.10.0-beta/.hwpx-mcp-runtime/envs/e/gen-1/bin/python")
    정식 = Path("/x/hwpx-plugin/2.2.0/.hwpx-mcp-runtime/envs/e/gen-1/bin/python")
    결과 = _pick([프리릴리스, 정식])
    assert 결과 in (프리릴리스, 정식)


# --- oracle_python — HWPX_ORACLE_PY 환경변수가 glob보다 우선 -----------------------------


def test_oracle_python은_HWPX_ORACLE_PY가_있으면_그_경로를_쓴다(monkeypatch, tmp_path):
    가짜_파이썬 = tmp_path / "python"
    가짜_파이썬.write_text("", encoding="utf-8")
    monkeypatch.setenv("HWPX_ORACLE_PY", str(가짜_파이썬))
    assert oracle_python() == 가짜_파이썬


def test_oracle_python은_HWPX_ORACLE_PY가_없는_파일이면_거부한다(monkeypatch, tmp_path):
    monkeypatch.setenv("HWPX_ORACLE_PY", str(tmp_path / "없는파일"))
    with pytest.raises(FileNotFoundError):
        oracle_python()
