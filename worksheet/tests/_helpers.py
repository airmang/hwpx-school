"""tests/ 안에서 여러 파일이 같이 쓰는 잡다한 헬퍼.

`conftest.py`에 두지 않는 이유: 로컬 전용 스위트를 같이 수집하는 실행에서는 이 디렉터리
말고도 `conftest.py`를 갖는 디렉터리가 하나 더 있다. 둘 다 `__init__.py`가 없는 채로 같은
pytest 세션에서 수집되면 두 `conftest.py`가 같은 맨 모듈 이름 `conftest`를 다투게 되어
`from conftest import ...`가 엉뚱한 쪽을 가리킬 수 있다. `_helpers`는 이 디렉터리에만 있는
이름이라 이 충돌이 없다.
"""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_LANG_TO_ATTR = {
    "HANGUL": "hangul", "LATIN": "latin", "HANJA": "hanja", "JAPANESE": "japanese",
    "OTHER": "other", "SYMBOL": "symbol", "USER": "user",
}
# 장식 글꼴을 심을 기본 charPr — 본문(0)과 표준 킷의 headline. 번호는 kit.json 에서 읽는다.
_제목_charpr = str(json.loads(
    (Path(__file__).resolve().parents[1] / "kits" / "standard" / "kit.json").read_text(encoding="utf-8")
)["styles"]["charPr"]["headline"])
_장식_대상_charpr = ("0", _제목_charpr)


def _png(width: int, height: int) -> bytes:
    """단색 PNG — 그림칸처럼 크기가 중요하지 않은 자리에 쓴다."""
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def _금칙장식체_심기(
    source: Path,
    dest: Path,
    *,
    face: str = "금칙장식체",
    대상_charpr_ids: tuple[str, ...] = _장식_대상_charpr,
) -> None:
    """`source`(정상 스켈레톤) 사본의 header.xml 7개 fontface 목록 **중간**에 합성 글꼴
    `face`를 끼워 넣고, `대상_charpr_ids`의 charPr이 7개 언어 전부에서 그 글꼴을 가리키게
    만든 '더러운' 원본을 `dest`에 쓴다. `대상_charpr_ids`를 빈 튜플로 주면 아무 charPr도
    가리키지 않는 글꼴을 목록에만 끼운 상태를 만들 수 있다(그 글꼴을 쓰는 charPr이 하나도
    없어도 목록 자체는 바뀌는 경우를 재현하는 용도).

    `dest`를 다시 `source`로 삼아 이어 부르면(서로 다른 `face`로) 서로 다른 두 글꼴을 같은
    header에 독립적으로 심을 수 있다 — 매번 그 시점의 header 상태를 있는 그대로 읽어
    적용하므로, 먼저 심은 글꼴이 있어도 새로 셈해 안전하다.

    끝이 아니라 중간에 끼우는 이유: 글꼴 remap이 id를 0부터 다시 붙이는 renumbering을
    실제로 겪게 하려면, 끼운 자리 **뒤**에 있던 기존 글꼴이 있어야 한다 — 끝에 붙이면
    그 글꼴을 지워도 다른 글꼴의 id가 하나도 안 밀려 renumbering이 공허해진다. 끼우는
    동안 뒤쪽 기존 항목의 id를 밀 때, **그 항목을 참조하던 다른 모든 charPr의 fontRef도
    같이 밀어야** 한다 — 안 그러면 id는 유효해도 엉뚱한 글꼴을 가리키게 되어(값이 겹친
    자리가 우연히 다른 글꼴이 됨) 이 픽스처 자체가 내적으로 모순된 상태가 된다.
    """
    with zipfile.ZipFile(source) as zin:
        parts = [(info, zin.read(info.filename)) for info in zin.infolist()]
    header_idx = next(
        i for i, (info, _) in enumerate(parts) if info.filename == "Contents/header.xml"
    )
    root = ET.fromstring(parts[header_idx][1])

    charprs = root.findall(f".//{_HH}charPr")
    새_id_by_lang: dict[str, str] = {}

    for fontface in root.findall(f".//{_HH}fontface"):
        lang = fontface.get("lang")
        attr = _LANG_TO_ATTR[lang]
        fonts = fontface.findall(f"{_HH}font")
        n = len(fonts)
        끼울_위치 = n // 2

        for f in fonts[끼울_위치:]:
            f.set("id", str(int(f.get("id")) + 1))
        for charpr in charprs:
            fontref = charpr.find(f"{_HH}fontRef")
            if fontref is None:
                continue
            현재 = fontref.get(attr)
            if 현재 is not None and int(현재) >= 끼울_위치:
                fontref.set(attr, str(int(현재) + 1))

        새_font = fontface.makeelement(
            f"{_HH}font",
            {"id": str(끼울_위치), "face": face, "type": "TTF", "isEmbedded": "0"},
        )
        fontface.insert(끼울_위치, 새_font)
        fontface.set("fontCnt", str(n + 1))
        새_id_by_lang[lang] = str(끼울_위치)

    for charpr_id in 대상_charpr_ids:
        charpr = root.find(f".//{_HH}charPr[@id='{charpr_id}']")
        fontref = charpr.find(f"{_HH}fontRef")
        for lang, attr in _LANG_TO_ATTR.items():
            fontref.set(attr, 새_id_by_lang[lang])

    새_header_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(dest, "w") as zout:
        for i, (info, data) in enumerate(parts):
            zout.writestr(info, 새_header_bytes if i == header_idx else data)


def _charpr_글꼴이름_전부(hwpx_path: Path) -> dict[tuple[str, str], str | None]:
    """`(charPr id, 언어 속성)` → 그 순간 가리키는 글꼴 이름 — 엔진 코드를 안 부르고
    XML에서 직접 다시 계산한다(글꼴 remap의 핵심 단언을 독립적으로 검증하는 데 쓴다).
    """
    with zipfile.ZipFile(hwpx_path) as z:
        root = ET.fromstring(z.read("Contents/header.xml"))

    id_to_face_by_attr: dict[str, dict[str, str]] = {}
    for fontface in root.findall(f".//{_HH}fontface"):
        attr = _LANG_TO_ATTR[fontface.get("lang")]
        id_to_face_by_attr[attr] = {
            f.get("id"): f.get("face") for f in fontface.findall(f"{_HH}font")
        }

    결과: dict[tuple[str, str], str | None] = {}
    for charpr in root.findall(f".//{_HH}charPr"):
        cid = charpr.get("id")
        fontref = charpr.find(f"{_HH}fontRef")
        if cid is None or fontref is None:
            continue
        for attr in _LANG_TO_ATTR.values():
            결과[(cid, attr)] = id_to_face_by_attr.get(attr, {}).get(fontref.get(attr))
    return 결과
