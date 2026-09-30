from importlib.metadata import version

from packaging.version import Version

import exam_kit


def test_런타임_범위():
    assert Version(version("python-hwpx-automation")) >= Version("7.2.0")
    assert Version(version("python-hwpx-automation")) < Version("8")
    assert Version(version("python-hwpx")) >= Version("6.5.0")
    assert exam_kit.__version__ == "0.1.0"


def test_오라클_모듈이_import된다():
    from hwpx_automation.office.rendering.oracle import MacHancomOracle

    assert callable(MacHancomOracle)


def test_양식_픽스처(양식_hwpx):
    assert 양식_hwpx.suffix == ".hwpx" and 양식_hwpx.stat().st_size > 100_000
