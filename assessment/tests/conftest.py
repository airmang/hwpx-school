import os
from pathlib import Path

import pytest

루트 = Path(__file__).resolve().parents[1]
킷 = 루트 / "kits" / "standard"


@pytest.fixture(scope="session")
def 킷_루트() -> Path:
    return 킷


@pytest.fixture(scope="session")
def 원본_경로() -> Path:
    """자기 양식으로도 추출을 확인하고 싶으면 `ASSESSMENT_FORM_PATH` 에 그 hwpx 경로를 준다.

    없으면 건너뛴다 — 공개 테스트는 `합성_원본`(tests/test_skeleton.py)만으로 돈다.
    """
    값 = os.environ.get("ASSESSMENT_FORM_PATH")
    if not 값:
        pytest.skip("ASSESSMENT_FORM_PATH 가 비어 있다 — 실제 양식 추출 검사를 건너뛴다")
    원본 = Path(값)
    if not 원본.exists():
        pytest.skip(f"ASSESSMENT_FORM_PATH 의 파일이 없다: {원본}")
    return 원본
