"""학교 킷은 제품 저장소에 없다 — 각 사용자가 자기 학교를 등록해 로컬에 만든다(skills/exam/references/학교-등록.md).

킷이 필요한 테스트는 환경변수로 받은 킷 폴더로만 돈다. 없으면 그 모듈(또는 픽스처)을 건너뛴다.
"""

import os
from pathlib import Path

import pytest

누름틀_킷 = "EXAM_KIT_PATH"     # 누름틀 양식 킷(엔진 회귀의 첫 기준) — 서식은 EXAM_FORM_PATH
글자자리_킷 = "EXAM_KIT_B_PATH"  # 글자 자리 양식 킷(누름틀 없는 서식) — 서식은 EXAM_FORM_B_PATH


def kit_dir(env: str = 누름틀_킷) -> Path:
    p = os.environ.get(env)
    if not p or not (Path(p) / "kit.json").is_file():
        pytest.skip(f"학교 킷 없음 — {env}로 킷 폴더를 지정(학교 킷은 저장소 밖 사용자 로컬)", allow_module_level=True)
    return Path(p)
