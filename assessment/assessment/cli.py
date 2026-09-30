"""compose / check. 종료코드 0 통과 · 1 검사 문제(JSON) · 2 입력 오류(한 줄)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from assessment.blocks import InputError, plan_sheet
from assessment.checks import check_answers, check_sheet, check_student
from assessment.compose import compose, output_paths
from assessment.kit import load_kit
from assessment.md import MdError, parse_sheet


def _출력(데이터: dict) -> None:
    print(json.dumps(데이터, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="assessment")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compose")
    c.add_argument("md", type=Path)
    c.add_argument("--kit", type=Path, required=True)
    c.add_argument("-o", "--out", type=Path, required=True)
    k = sub.add_parser("check")
    k.add_argument("md", type=Path)
    k.add_argument("--kit", type=Path, required=True)
    k.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    try:
        sheet = parse_sheet(a.md.read_text(encoding="utf-8"))
        kit = load_kit(a.kit)
    except (MdError, ValueError, OSError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    if sheet.kit != kit.name:
        print(f"오류: 킷 이름이 다르다: md={sheet.kit} 킷={kit.name}", file=sys.stderr)
        return 2
    문제 = check_sheet(sheet, base_dir=a.md.parent)
    if a.cmd == "compose":
        if 문제:
            _출력({"문제": 문제})
            return 1
        try:
            r = compose(a.md, a.kit, a.out)
        except InputError as e:
            print(f"오류: {e}", file=sys.stderr)
            return 2
        except ValueError as e:
            _출력({"문제": str(e).splitlines()})
            return 1
        except OSError as e:
            print(f"오류: 파일을 쓰지 못했다: {e}", file=sys.stderr)
            return 2
        _출력({"student": str(r.student), "answers": str(r.answers), "items": r.items, "memos": r.memos, "문제": []})
        return 0
    if a.out is not None:
        try:
            학생, 정답 = output_paths(a.out)
            문제 += check_student(학생, sheet) + check_answers(정답, sheet)
        except ValueError as e:
            print(f"오류: {e}", file=sys.stderr)
            return 2
        except OSError as e:
            경로 = getattr(e, "filename", None) or a.out
            print(f"오류: 산출물이 없다: {경로} — 먼저 compose 한다", file=sys.stderr)
            return 2
    elif not 문제:
        # --out 이 없으면 산출물이 없으니 파일 검사 대신 계획을 한 번 돌려 그림 폭
        # 같은, 문항 트리만으로는 못 잡는 입력 오류를 compose 전에 미리 잡는다.
        try:
            plan_sheet(sheet, kit, base_dir=a.md.parent, answers=False)
        except InputError as e:
            print(f"오류: {e}", file=sys.stderr)
            return 2
    _출력({"문제": 문제})
    return 1 if 문제 else 0


if __name__ == "__main__":
    sys.exit(main())
