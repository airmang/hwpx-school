import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

import assessment.render as 렌더_모듈
from assessment.compose import compose
from assessment.render import RenderError, RenderUnavailable, _read_completed, oracle_python, render_hancom
from test_hwpx import MD


@pytest.mark.hancom
def test_실한컴_두_파일_렌더(킷_루트, tmp_path):
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", 킷_루트, tmp_path / "a.hwpx")
    for path in (r.student, r.answers):
        결과 = render_hancom(path, tmp_path / f"{path.stem}.png")
        assert 결과.pages >= 1 and all(p.exists() for p in 결과.pngs)
        assert [p.name for p in 결과.pngs] == [f"{path.stem}-{i:03d}.png" for i in range(1, 결과.pages + 1)]


# --- 공개 render-pdf 호출(#18) — worksheet와 같은 계약 --------------------------------------


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


def test_render_hancom은_공개_render_pdf_명령을_부른다(플러그인_없는_집, monkeypatch, tmp_path):
    잡힌: list = []

    def 가짜_run(명령, **kw):
        잡힌.append(명령)
        접두 = 명령[명령.index("--png") + 1]
        줄 = json.dumps({"ok": True, "pdf": 명령[5], "pages": 1, "pngs": [f"{접두}-001.png"], "backend": "mac"})
        return subprocess.CompletedProcess(명령, 0, stdout=줄 + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", 가짜_run)
    결과 = render_hancom(tmp_path / "a.hwpx", tmp_path / "a.png")
    명령 = 잡힌[0]
    assert 명령[:4] == [sys.executable, "-m", "hwpx_automation.office.rendering", "render-pdf"]
    assert 명령[명령.index("--backend") + 1] == "auto" and "--json" in 명령
    assert [p.name for p in 결과.pngs] == ["a-001.png"]
    assert 결과.pdf == (tmp_path / "a.pdf").resolve()


def test_read_completed는_한컴이_없으면_RenderUnavailable():
    줄 = json.dumps({"ok": False, "error": "hancom-unavailable", "message": "합성 사유", "backend": None})
    with pytest.raises(RenderUnavailable):
        _read_completed(3, 줄, "")


def test_실제_render_pdf는_구조_전용이면_RenderUnavailable(킷_루트, 플러그인_없는_집, monkeypatch, tmp_path):
    """`HWPX_ORACLE_STRUCTURAL_ONLY=1`이면 render-pdf는 한컴을 찾지도 띄우지도 않고 종료 코드 3으로
    끝난다 — 입력 hwpx 검사와 pymupdf 확인([oracle] extra)은 실제로 돈다."""
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", 킷_루트, tmp_path / "a.hwpx")
    monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", "1")
    with pytest.raises(RenderUnavailable) as 잡힘:
        render_hancom(r.student, tmp_path / "s.png")
    assert 잡힘.value.code == "hancom-unavailable"


def test_실제_render_pdf는_없는_입력을_RenderError로_낸다(플러그인_없는_집, monkeypatch, tmp_path):
    monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", "1")
    with pytest.raises(RenderError) as 잡힘:
        render_hancom(tmp_path / "없는.hwpx", tmp_path / "r.png")
    assert 잡힘.value.code == "input-missing"
