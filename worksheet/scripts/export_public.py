"""엔진 실행에 필요한 경로만 <dest>로 복사하고 금칙어 위생을 검사한다(엔진만 따로 묶어 낼 때).

    uv run --python 3.13 python scripts/export_public.py <dest> --forbidden <금칙어 파일>

`git ls-files`로 이 프로젝트가 추적하는 파일만 고르므로 `__pycache__`·잡파일이 못 낀다.
학교 킷은 저장소에 없고, `재현`·`tests_local`·`scripts`는 애초에 목록에 없다.
금칙어(학교·사람 이름 등)는 저장소에 두지 않는다 — 한 줄에 하나씩 쓴 로컬 파일을 --forbidden으로 준다.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from worksheet.checks import check_hygiene

PROJECT_ROOT = Path(__file__).resolve().parents[1]

공개_경로 = [
    "SKILL.md", "README.md", "pyproject.toml", "uv.lock",
    "references", "worksheet", "kits/standard", "tests",
]
허용_확장자 = {".py", ".md", ".json", ".toml", ".lock", ".hwpx"}


def load_forbidden(path: Path) -> list[str]:
    """금칙어 파일(한 줄에 하나, # 뒤는 주석) — 목록 자신은 저장소 밖에 둔다."""
    words = [ln.split("#", 1)[0].strip() for ln in Path(path).read_text(encoding="utf-8").splitlines()]
    words = [w for w in words if w]
    if not words:
        raise ValueError(f"금칙어 파일이 비었다: {path}")
    return words


def public_files() -> list[Path]:
    """공개 경로 아래 git이 추적하는 파일만 — 프로젝트 기준 상대 경로로 낸다.

    `-z`로 받아 `\\0`으로 자른다 — 한글 경로가 이스케이프된 채로 나오는 것을 피한다.
    """
    보고 = subprocess.run(
        ["git", "ls-files", "-z", "--", *공개_경로],
        cwd=PROJECT_ROOT, capture_output=True, check=True,
    )
    return [Path(조각.decode("utf-8")) for 조각 in 보고.stdout.split(b"\0") if 조각]


def export(dest: Path) -> list[Path]:
    """공개 파일을 작업 트리에서 <dest>로 복사한다(위생 검사는 main()이 한다).

    `git ls-files`가 파일 목록만 낼 뿐 내용은 작업 트리에서 읽으므로, 커밋 전 수정본도
    그대로 복사된다.
    """
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"<dest>가 비어 있지 않다: {dest} — 덮어쓰기 사고를 막으려고 거부한다")

    파일들 = public_files()
    안맞는_확장자 = [p for p in 파일들 if p.suffix not in 허용_확장자]
    if 안맞는_확장자:
        raise ValueError(
            "공개 경로에 위생 검사가 못 읽는 확장자 파일이 있다"
            f"(허용: {sorted(허용_확장자)}): {[str(p) for p in 안맞는_확장자]}"
        )

    dest.mkdir(parents=True, exist_ok=True)
    복사됨: list[Path] = []
    for 상대경로 in 파일들:
        대상 = dest / 상대경로
        대상.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / 상대경로, 대상)
        복사됨.append(대상)
    return 복사됨


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export_public")
    parser.add_argument("dest", help="빈 디렉터리(없으면 새로 만든다)")
    parser.add_argument("--forbidden", required=True, type=Path,
                        help="금칙어 파일(한 줄에 하나) — 학교·사람 이름 등. 저장소 밖에 둔다")
    args = parser.parse_args(argv)

    금칙어 = load_forbidden(args.forbidden)
    파일들 = export(Path(args.dest))
    문제 = check_hygiene(Path(args.dest), 금칙어)
    if 문제:
        for 줄 in 문제:
            print(줄)
        return 1
    print(f"금칙어 잔존 0 (파일 {len(파일들)}개)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
