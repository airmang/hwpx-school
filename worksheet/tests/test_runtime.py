import hwpx
import worksheet


def test_런타임이_지원_범위다():
    """하드 고정(`==6.4.0`) 대신 범위 고정 — 사용자 방침(2026-09-21). 재현성은 `uv.lock`이,
    올릴 때의 회귀 검사는 로컬 전용 재현 테스트(`tests_local`)와 실한컴 렌더가 맡는다."""
    버전 = tuple(int(x) for x in hwpx.__version__.split("."))
    assert (6, 4) <= 버전 < (7, 0)
    assert worksheet.__version__ == "0.1.0"


def test_원본_픽스처가_존재한다(원본_hwpx):
    assert 원본_hwpx.exists()
    assert 원본_hwpx.suffix == ".hwpx"
