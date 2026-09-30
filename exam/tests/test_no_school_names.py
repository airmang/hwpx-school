"""제품 저장소에는 특정 학교가 없다 — 학교 킷·학교 스킬·금칙어 목록은 사용자 로컬(09-30 결정).

금지 이름 = 로컬 킷 폴더(EXAM_KITS_DIR)의 킷 이름 앞부분 + 로컬 금칙어 파일(HWPX_FORBIDDEN_FILE, 한 줄에 하나).
이 이름이 저장소의 코드·테스트·문서·킷에 나오면 실패한다. 둘 다 없으면 건너뛴다.
"""

import os
import subprocess
from pathlib import Path

import pytest

저장소 = Path(__file__).resolve().parents[2]
_읽을_확장자 = {".py", ".md", ".json", ".toml", ".txt"}


def _금지_이름() -> set[str]:
    names: set[str] = set()
    kits = os.environ.get("EXAM_KITS_DIR")
    if kits and Path(kits).is_dir():
        names |= {d.name.split("-")[0] for d in Path(kits).iterdir() if (d / "kit.json").is_file()}
    words = os.environ.get("HWPX_FORBIDDEN_FILE")
    if words and Path(words).is_file():
        names |= {w.split("#", 1)[0].strip() for w in Path(words).read_text(encoding="utf-8").splitlines()}
    return {n for n in names if n}


def test_저장소에_학교_이름이_없다():
    금지 = _금지_이름()
    if not 금지:
        pytest.skip("EXAM_KITS_DIR·HWPX_FORBIDDEN_FILE(사용자 로컬) 없음")
    out = subprocess.run(["git", "ls-files", "-z"], cwd=저장소, capture_output=True, check=True).stdout
    걸림 = []
    for 조각 in out.split(b"\0"):
        rel = 조각.decode("utf-8")
        if not rel:
            continue
        f = 저장소 / rel
        이름_걸림 = [n for n in 금지 if n in rel]
        text = f.read_text(encoding="utf-8", errors="ignore") if f.suffix in _읽을_확장자 and f.is_file() else ""
        걸림 += [f"{rel}: {n}" for n in 금지 if n in text] + [f"{rel}(경로): {n}" for n in 이름_걸림]
    assert not 걸림, 걸림
