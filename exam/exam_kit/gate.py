"""엔진 회귀 게이트 — 기준 산출물과 새 산출물(같은 이름의 hwpx)이 같은지 본다.

    uv run python -m exam_kit.gate <기준 폴더> <새 폴더>     # 끝 코드 0 = 전부 같다

엔진이나 python-hwpx를 바꾸면 등록된 모든 학교의 기준 산출물로 이 비교를 돌린다(skills/exam/SKILL.md 엔진 회귀).
같다고 보는 차이는 둘뿐이고, 나머지는 zip 항목 목록까지 바이트로 같아야 한다.
- 문단 id(`<hp:p id>`)와 그림 instid — python-hwpx가 빌드마다 바꾼다.
- paraPr의 id와 개수 — 내용이 같으면 같은 paraPr다. python-hwpx 6.6.0부터 같은 내용의 paraPr를 새로 만들지 않고
  재사용해서, 개수가 줄고 뒤 id가 당겨진다(내용의 집합은 같다). 그래서 header의 paraPr는 내용의 집합으로 견주고,
  paraPrIDRef(본문·스타일)는 가리키는 paraPr의 내용으로 바꿔 견준다.
"""

from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

import lxml.etree as ET

from . import q

_P_ID = re.compile(rb'(<hp:p\b[^>]*?\bid=")\d+(")')
_INSTID = re.compile(rb'(\binstid=")\d+(")')
_PARA_REF = re.compile(rb'(\bparaPrIDRef=")([^"]*)(")')
HEADER = "Contents/header.xml"


def para_keys(header: bytes) -> dict[str, str]:
    """paraPr id → 내용 열쇠(id를 뺀 정규형 XML의 sha1 앞 12자)."""
    out = {}
    for pp in ET.fromstring(header).iter(q("hh", "paraPr")):
        c = deepcopy(pp)
        c.attrib.pop("id", None)
        out[pp.get("id")] = hashlib.sha1(ET.tostring(c, method="c14n")).hexdigest()[:12]
    return out


def _refs(data: bytes, keys: dict[str, str]) -> bytes:
    """paraPrIDRef="N" → paraPrIDRef="pp-<내용 열쇠>"(모르는 id는 그대로 보이게 `?N`)."""
    return _PARA_REF.sub(lambda m: m.group(1) + ("pp-" + keys.get(m.group(2).decode(), "?" + m.group(2).decode())).encode()
                         + m.group(3), data)


def normalize_header(header: bytes) -> tuple[bytes, frozenset[str]]:
    """(paraPr 목록을 비우고 paraPrIDRef를 내용 열쇠로 바꾼 header, paraPr 내용 열쇠의 집합)."""
    keys = para_keys(header)
    root = ET.fromstring(header)
    for box in root.iter(q("hh", "paraProperties")):
        for pp in box.findall(q("hh", "paraPr")):
            box.remove(pp)
        box.attrib.pop("itemCnt", None)
    return _refs(ET.tostring(root), keys), frozenset(keys.values())


def normalize_part(data: bytes, keys: dict[str, str]) -> bytes:
    """본문 XML(section·masterpage 등) — 문단 id·그림 instid를 0으로, paraPrIDRef를 내용 열쇠로."""
    return _refs(_INSTID.sub(rb"\g<1>0\g<2>", _P_ID.sub(rb"\g<1>0\g<2>", data)), keys)


def compare(a: Path, b: Path) -> list[str]:
    """두 hwpx의 다른 곳(빈 목록 = 같다)."""
    with zipfile.ZipFile(a) as za, zipfile.ZipFile(b) as zb:
        na, nb = za.namelist(), zb.namelist()
        if sorted(na) != sorted(nb):
            return [f"zip 항목이 다르다: {sorted(set(na) ^ set(nb))}"]
        ka, kb = para_keys(za.read(HEADER)), para_keys(zb.read(HEADER))
        out = []
        for n in sorted(na):
            x, y = za.read(n), zb.read(n)
            if n == HEADER:
                (x, sx), (y, sy) = normalize_header(x), normalize_header(y)
                if sx != sy:
                    out.append(f"{n}: paraPr 내용이 다르다(기준에만 {len(sx - sy)}가지 · 새 것에만 {len(sy - sx)}가지)")
            elif n.startswith("Contents/") and n.endswith(".xml"):
                x, y = normalize_part(x, ka), normalize_part(y, kb)
            if x != y:
                out.append(n)
        return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="엔진 회귀 게이트 — 기준 폴더와 새 폴더의 같은 이름 hwpx 비교")
    ap.add_argument("base", type=Path, help="기준 산출물 폴더")
    ap.add_argument("new", type=Path, help="새 산출물 폴더")
    args = ap.parse_args(argv)
    names = sorted(p.name for p in args.base.glob("*.hwpx"))
    if not names:
        print(f"기준 폴더에 hwpx가 없다: {args.base}")
        return 2
    bad = 0
    for name in names:
        other = args.new / name
        diffs = ["새 폴더에 없다"] if not other.is_file() else compare(args.base / name, other)
        bad += bool(diffs)
        print(f"{name}: {'같다' if not diffs else '다르다 — ' + '; '.join(diffs)}")
    extra = sorted({p.name for p in args.new.glob("*.hwpx")} - set(names))
    if extra:
        print(f"기준에 없는 새 hwpx(보지 않았다): {extra}")
    print("전부 같다" if not bad else f"다른 파일 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
