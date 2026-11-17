from importlib.metadata import version

from packaging.version import Version

import exam_kit


def test_런타임_범위():
    # pyproject 핀(python-hwpx>=7.0,<8 · python-hwpx-automation>=8.0,<9)과 같게.
    assert Version("8.0") <= Version(version("python-hwpx-automation")) < Version("9")
    assert Version("7.0") <= Version(version("python-hwpx")) < Version("8")
    assert exam_kit.__version__ == "0.1.0"


def test_오라클_모듈이_import된다():
    from hwpx_automation.office.rendering.oracle import MacHancomOracle

    assert callable(MacHancomOracle)


def test_양식_픽스처(양식_hwpx):
    assert 양식_hwpx.suffix == ".hwpx" and 양식_hwpx.stat().st_size > 100_000
