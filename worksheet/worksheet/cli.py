"""학습지 hwpx 명령줄 도구."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from worksheet.checks import (
    check_answer_labels, check_empty_slots, check_markdown, check_package,
    check_slot_residue, preview_stats,
)
from worksheet.compose import compose as _compose
from worksheet.compose import output_format
from worksheet.kit import load_kit, seed_kit_path, validate_font_map, verify_kit
from worksheet.md import parse_sheet
from worksheet.skeleton import extract_skeleton


def _extract_kit(args: argparse.Namespace) -> int:
    source = Path(args.source)
    if not source.exists():
        # mkdir 앞에 둔다 — 원본이 없으면 대상 디렉터리조차 생기지 않아야 한다.
        raise ValueError(f"원본 hwpx 가 없다: {source}")
    root = Path(args.dest)
    root.mkdir(parents=True, exist_ok=True)

    # 스켈레톤을 뽑기 **전에** 그 킷을 다스리는 kit.json을 먼저 정한다 — font_map은
    # extract_skeleton이 바로 이번 호출에서 쓴다(자기 자신을 원본으로 쓰는 경로에서는
    # source == dest/skeleton.hwpx라, 스켈레톤을 덮어쓴 뒤에는 "옮기기 전" 글꼴을 다시
    # 읽을 수 없다). CLI 인자로 fontMap을 더 받지는 않는다 — kit.json에서만 정한다.
    kit_path = root / "kit.json"
    슬롯_인자 = {
        "school": args.school, "teacher": args.teacher,
        "subject": args.subject, "grade": args.grade,
    }
    if kit_path.exists() and not args.force:
        if any(슬롯_인자.values()):
            raise ValueError(
                f"kit.json 이 이미 있다: {kit_path} — "
                "슬롯 인자는 새 kit.json 을 쓸 때만 쓴다(--force)"
            )
        다스리는_kit = json.loads(kit_path.read_text(encoding="utf-8"))
        kit_json = "kept"
    else:
        다스리는_kit = json.loads(seed_kit_path().read_text(encoding="utf-8"))
        다스리는_kit["kit"] = root.name
        다스리는_kit["slots"] = 슬롯_인자
        kit_path.write_text(
            json.dumps(다스리는_kit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        kit_json = "written"

    # 여기서만 검사한다: dest에 kit.json이 이미 있던(kept) 경로는 load_kit()을 안 거치므로
    # fontMap의 형태(문자열→문자열, 자기 자신·연쇄 금지)를 아무도 안 본 채 그대로
    # extract_skeleton에 들어갈 뻔했다 — 값이 문자열이 아니면 header.xml에 hh:font를
    # 지으려 할 때 라이브러리의 TypeError가 트레이스백으로 새어 "손으로 쓴 입력은 한 줄
    # 오류로 알린다"는 이 파일의 계약을 깬다.
    font_map = 다스리는_kit.get("fontMap") or {}
    validate_font_map(font_map)

    보고 = extract_skeleton(source, root / "skeleton.hwpx", font_map=font_map)

    print(json.dumps({**보고, "kit_json": kit_json}, ensure_ascii=False))
    return 0


def _compose_cmd(args: argparse.Namespace) -> int:
    보고 = _compose(Path(args.md), Path(args.kit), Path(args.out))
    print(json.dumps(보고.__dict__, ensure_ascii=False))
    return 0 if 보고.validate_ok else 1


def _check_cmd(args: argparse.Namespace) -> int:
    # compose와 같은 방어 — 확장자를 알 수 없는 --out은 킷·md를 읽기도 전에 한 줄로
    # 거부한다. 이걸 건너뛰면 아래 check_package 등이 무조건 hwpx로 열려다 zipfile 등의
    # raw 예외를 그대로 새게 둔다(compose·check 두 진입점이 같은 위험을 같은 방식으로 막는다).
    output_format(Path(args.out))
    kit = load_kit(Path(args.kit))
    md_path = Path(args.md)
    sheet = parse_sheet(md_path.read_text(encoding="utf-8"))
    문제 = (
        verify_kit(kit)
        + check_markdown(sheet, kit, base_dir=md_path.parent)
        + check_answer_labels(sheet)
        + check_package(Path(args.out))
        + check_empty_slots(kit, grade=sheet.grade)
        + check_slot_residue(Path(args.out), kit.residue_markers)
    )
    print(json.dumps(
        {"문제": 문제, "미리보기": preview_stats(Path(args.out))},
        ensure_ascii=False, indent=2,
    ))
    return 0 if not 문제 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="worksheet")
    sub = parser.add_subparsers(dest="명령", required=True)

    p = sub.add_parser("extract-kit", help="원본 hwpx에서 킷을 뽑는다")
    p.add_argument("source")
    p.add_argument("dest")
    p.add_argument("--school", default="")
    p.add_argument("--teacher", default="")
    p.add_argument("--subject", default="")
    p.add_argument("--grade", default="")
    p.add_argument(
        "--force", action="store_true",
        help="있는 kit.json 도 씨앗+슬롯 인자로 다시 쓴다(기본은 있으면 건드리지 않는다)",
    )
    p.set_defaults(func=_extract_kit)

    c = sub.add_parser("compose", help="마크다운을 학습지(hwpx·docx)로 조판한다 — 출력 확장자로 형식을 고른다")
    c.add_argument("md")
    c.add_argument("--kit", required=True)
    c.add_argument("-o", "--out", required=True)
    c.set_defaults(func=_compose_cmd)

    k = sub.add_parser("check", help="[기계] 검사")
    k.add_argument("md")
    k.add_argument("--kit", required=True)
    k.add_argument("--out", "--hwpx", dest="out", required=True, help="조판 결과(.hwpx 또는 .docx)")
    k.set_defaults(func=_check_cmd)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError) as e:
        # 교사가 손으로 쓰는 입력(md·kit.json)의 오류는 트레이스백이 아니라 이 한 줄로
        # 알린다. 종료코드 2는 [기계] 검사 실패(1)와 구별된다 — 그 밖의 예외는 버그이므로
        # 여기서 안 잡고 그대로 트레이스백이 나게 둔다.
        print(f"오류: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
