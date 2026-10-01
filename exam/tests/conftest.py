import os
import shutil
from pathlib import Path

import pytest

루트 = Path(__file__).resolve().parents[1]
# 서식·제출본·학교 킷은 저장소 밖 사용자 로컬이다 — 환경변수로만 받는다(기본 경로 없음).
양식_기본 = 제출본_기본 = 학교B_양식_기본 = None


def _경로(env: str, 기본: Path | None) -> Path | None:
    v = os.environ.get(env) or (None if 기본 is None else str(기본))
    return Path(v) if v and Path(v).exists() else None


@pytest.fixture(scope="session")
def 양식_hwpx() -> Path:
    p = _경로("EXAM_FORM_PATH", 양식_기본)
    if p is None:
        pytest.skip("양식 hwpx 없음 — EXAM_FORM_PATH 로 지정")
    return p


@pytest.fixture(scope="session")
def 제출본_hwpx() -> Path:
    p = _경로("EXAM_SUBMITTED_PATH", 제출본_기본)
    if p is None:
        pytest.skip("제출본 hwpx 없음 — EXAM_SUBMITTED_PATH 로 지정")
    return p


@pytest.fixture(scope="session")
def 킷_루트() -> Path:
    from _kits import kit_dir

    return kit_dir()


@pytest.fixture(scope="session")
def 오라클():
    """이 PC의 실한컴(Windows COM 또는 macOS 한글 앱) — 엔진이 렌더에 쓰는 것과 같은 것(render._oracle)."""
    from exam_kit.render import RenderUnavailable, _oracle

    try:
        return _oracle()
    except RenderUnavailable:
        pytest.skip("실한컴 오라클 없음")


@pytest.fixture
def tmp_hwpx(tmp_path):
    def _f(name: str) -> Path:
        return tmp_path / name

    return _f


def pytest_collection_modifyitems(items):
    """실한컴 오라클 픽스처를 쓰는 테스트에 render 표지 — `-m "not render"`로 한컴 없이 돌린다."""
    for item in items:
        if "오라클" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.render)


@pytest.fixture(autouse=True)
def _한컴_잠금_격리(request, tmp_path_factory, monkeypatch):
    """실한컴 렌더 테스트(render 표지)가 아니면 공용 한컴 잠금 대신 테스트 전용 잠금 파일을 쓴다 — 가짜 오라클 테스트가
    다른 세션의 실제 렌더를 기다리거나 막지 않게. 실렌더 테스트는 upstream 공용 잠금을 그대로 쥔다."""
    if request.node.get_closest_marker("render") is None and request.node.get_closest_marker("real_lock") is None:
        import exam_kit.render as r

        path = tmp_path_factory.mktemp("잠금") / "hancom.lock"
        monkeypatch.setattr(r, "_lock_path", lambda: path)


@pytest.fixture(scope="session")
def 학교B_양식() -> Path:
    p = _경로("EXAM_FORM_B_PATH", 학교B_양식_기본)
    if p is None:
        pytest.skip("학교 B 양식 hwpx 없음 — EXAM_FORM_B_PATH 로 지정")
    return p
