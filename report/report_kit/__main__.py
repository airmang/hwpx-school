"""uv run python -m report_kit register|roles|make …"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import make, register, roles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="report_kit")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("register", help="자리표시 견본 → 킷")
    p.add_argument("template")
    p.add_argument("kit")
    p = sub.add_parser("roles", help="킷의 역할과 칸")
    p.add_argument("kit")
    p = sub.add_parser("make", help="계획 JSON → 문서")
    p.add_argument("plan")
    p.add_argument("--kit", required=True)
    p.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)

    if args.command == "register":
        out = register(args.template, args.kit)
    elif args.command == "roles":
        out = roles(args.kit)
    else:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        out = make(plan, args.kit, args.output)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
