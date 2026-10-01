"""Windows 시험(시험용 브랜치) — 이 PC에서 엔진이 처음부터 끝까지 도는지 합성 원고로만 본다.

    uv run python tools/windows_try.py --out <결과 폴더> [--kit <학교 킷 폴더> --form <학교 양식 hwpx>]

1. 환경: 이 PC의 한/글 자동화(COM)를 찾는지, 렌더 오라클이 한/글 저장(refresh_document — 자간 맞춤이 쓴다)을 하는지.
2. 합성 킷 + 합성 수학 원고 — 학교 파일 없이 돈다.
3. 학교 킷 + 학교 양식 + 합성 견본 원고(견본_전유형) — --kit·--form을 줄 때만.
4. 학교 킷 + 학교 양식 + 합성 수학 원고(머리를 견본 원고의 머리로, `답항: 1행부터`) — --kit·--form을 줄 때만.
학교 킷과 양식은 저장소 밖(사용자 로컬)이라 경로를 인자로만 받는다. 조판마다 끝 코드(0 = 두 판 기계 잔존 0)와
보고서 경로를 찍는다. 결과 폴더는 저장소 밖에 둔다. 끝 코드 0 = 모두 0.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

EXAM = Path(__file__).resolve().parents[1]
FIX = EXAM / "tests" / "fixtures"
SYNTH = EXAM / "kits" / "synthetic"


def 환경() -> bool:
    from exam_kit.render import RenderUnavailable, _oracle

    try:
        o = _oracle()
    except RenderUnavailable as e:
        print(f"[환경] 한/글 자동화를 찾지 못했다 — {e}", flush=True)
        return False
    saves = hasattr(o, "refresh_document")
    print(f"[환경] 렌더 오라클 {type(o).__name__} · 한/글 저장(refresh_document) {'있다' if saves else '없다 — 상류가 옛 판이다'}",
          flush=True)
    return saves


def 조판(name: str, md: Path, kit: Path, form: Path, out: Path) -> int:
    cmd = [sys.executable, "-W", "ignore", "-m", "exam_kit.build", str(md), "--kit", str(kit), "--form", str(form),
           "--out", str(out / name)]
    print(f"[{name}] 조판 시작 — {md.name}", flush=True)
    t0 = time.time()
    code = subprocess.run(cmd, cwd=EXAM, env=dict(os.environ, PYTHONIOENCODING="utf-8")).returncode
    print(f"[{name}] 끝 코드 {code} ({time.time() - t0:.0f}초) — 보고서 {out / name / '보고.md'}", flush=True)
    return code


def 학교_수학_원고(out: Path) -> Path:
    """합성 수학 원고의 머리를 합성 견본 원고(누름틀 결재란 양식 머리)의 것으로 바꾸고 `답항: 1행부터`를 더한다."""
    head = (FIX / "견본_전유형.md").read_text(encoding="utf-8").split("\n## 1.")[0].rstrip()
    body = (FIX / "수식_합성.md").read_text(encoding="utf-8").split("---\n", 2)[2]
    md = out / "수식_학교양식.md"
    md.write_text(head[:-3] + "만점: 45\n답항: 1행부터\n---\n" + body, encoding="utf-8")
    return md


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Windows 시험 — 합성 원고로 엔진 끝까지")
    ap.add_argument("--out", type=Path, required=True, help="결과 폴더(저장소 밖)")
    ap.add_argument("--kit", type=Path, help="학교 킷 폴더(kit.json이 든 폴더, 저장소 밖)")
    ap.add_argument("--form", type=Path, help="학교 원안지 양식 hwpx(저장소 밖)")
    a = ap.parse_args(argv)
    if (a.kit is None) != (a.form is None):
        ap.error("--kit과 --form은 함께 준다")
    if a.kit is not None and not (a.kit / "kit.json").is_file():
        ap.error(f"킷 폴더에 kit.json이 없다: {a.kit}")
    if a.form is not None and not a.form.is_file():
        ap.error(f"양식 파일이 없다: {a.form}")
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not 환경():
        return 3
    codes = {"합성킷_수식": 조판("합성킷_수식", FIX / "수식_합성.md", SYNTH, SYNTH / "synthetic_form.hwpx", out)}
    if a.kit is not None:
        kit, form = a.kit.resolve(), a.form.resolve()
        codes["학교_견본"] = 조판("학교_견본", FIX / "견본_전유형.md", kit, form, out)
        codes["학교_수식"] = 조판("학교_수식", 학교_수학_원고(out), kit, form, out)
    print("\n결과: " + " · ".join(f"{k} {v}" for k, v in codes.items()) + " (0 = 두 판 기계 잔존 0)", flush=True)
    return 0 if all(v == 0 for v in codes.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
