"""worksheet/skeleton.py 에서 복사·수정.

수행평가 양식 hwpx(원본)에서 본문을 비운 스켈레톤을 뽑는다.
"""

from __future__ import annotations

import os
import struct
import tempfile
import zlib
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.oxml.body import INLINE_OBJECT_NAMES
from hwpx.package import HwpxPackage

from assessment.ns import HH, HP

_OPF = "http://www.idpf.org/2007/opf/"
_OPF_NS = {"opf": _OPF}
_CONTENT_HPF = "Contents/content.hpf"
_고정_시각 = "1970-01-01T00:00:00Z"
# 이 도구는 유출 방지 도구다 — 안전하게 중립화하지 못한 원본은 파일이 아니라 예외로
# 끝나야 한다(fail closed). 사후조건이든 구조 거부든 원인은 전부 "원본의 구조" 이므로
# 예외 타입과 문구 앞머리를 하나로 통일한다.
_실패_머리말 = "스켈레톤을 안전하게 만들지 못했다"
# hp:tbl은 표 자체가 태그 이름이라 "인라인 개체"로 안 묶인다 — 별도로 더한다.
_금지된_로컬이름 = INLINE_OBJECT_NAMES | {"tbl"}

# 밑줄 답칸은 칸 아래 테두리로 그린다 — 밑줄 길이 = 칸 폭이라 글꼴과 무관하다(0.12 mm 검정).
# 양식 header 에 "아래 테두리만" 인 borderFill 이 흔히 없어서 추출이 이것을 보장한다.
_밑줄_테두리 = {"border_color": "#000000", "border_width": "0.12 mm", "active_borders": ("bottom",)}

# hh:fontface/@lang 7개 값 ↔ hh:fontRef·hh:charPr가 쓰는 속성 이름. 언어마다 글꼴 id
# 채번이 독립이라(HANGUL 목록의 id=3과 LATIN 목록의 id=3이 다른 글꼴일 수 있다), 글꼴을
# 옮기는 일은 이 7개 각각에 따로 적용해야 한다.
_FONTFACE_LANG_TO_ATTR = {
    "HANGUL": "hangul", "LATIN": "latin", "HANJA": "hanja", "JAPANESE": "japanese",
    "OTHER": "other", "SYMBOL": "symbol", "USER": "user",
}


def _q(tag: str) -> str:
    return f"{{{HP}}}{tag}"


def _hq(tag: str) -> str:
    return f"{{{HH}}}{tag}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _흰_png(폭: int = 1, 높이: int = 1) -> bytes:
    """1×1 흰 PNG — 미리보기 자리를 채우되 아무것도 드러내지 않는다."""
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * 폭 for _ in range(높이))

    def 청크(태그: bytes, 몸통: bytes) -> bytes:
        return (
            struct.pack(">I", len(몸통))
            + 태그
            + 몸통
            + struct.pack(">I", zlib.crc32(태그 + 몸통) & 0xFFFFFFFF)
        )

    머리 = struct.pack(">IIBBBBB", 폭, 높이, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + 청크(b"IHDR", 머리)
        + 청크(b"IDAT", zlib.compress(raw))
        + 청크(b"IEND", b"")
    )


def _bindata_item_ids(package: HwpxPackage) -> list[str]:
    """content.hpf 매니페스트에서 href가 BinData/로 시작하는 항목의 id 전부.

    정규식(`<opf:item id="..." href="BinData/`)으로 찾으면 id·href 속성 순서가 바뀐 문서에서
    0건 매치로 조용히 실패한다. `manifest_tree()`(6.4.0에 있다)로 실제 파싱된 매니페스트를
    순회해 속성 순서와 무관하게 찾는다.
    """
    manifest = package.manifest_tree().find("opf:manifest", _OPF_NS)
    if manifest is None:
        return []
    return [
        item.get("id")
        for item in manifest.findall("opf:item", _OPF_NS)
        if (item.get("href") or "").startswith("BinData/")
    ]


def _scrub_opaque_metadata(package: HwpxPackage) -> None:
    """**모든** opf:meta를 이름과 무관하게 일반 규칙으로 세척한다.

    이름을 나열해 지우는 블랙리스트 방식(lastsaveby·description·date 셋만 등)은 다른 학교
    원본에만 있는 한컴 자체 필드(이름을 모르는 opf:meta)가 있으면 존재 자체를 몰라 조용히
    새어나간다. 그래서 opf:meta를 전부 순회해, 이름에 "Date"가 든 항목(CreatedDate·
    ModifiedDate)은 고정 시각으로, 그 밖은 전부 빈 값으로 덮는다 — 이름을 몰라도 세척한다.
    opf:title은 별도 요소(opf:meta가 아니다)라 이 함수가 손대지 않는다
    — 호출자가 `set_document_metadata(title=...)`로 고정 제목을 준다.
    """
    tree = package.manifest_tree()
    metadata = tree.find("opf:metadata", _OPF_NS)
    if metadata is None:
        return
    for meta in metadata.findall("opf:meta", _OPF_NS):
        이름 = meta.get("name") or ""
        meta.text = _고정_시각 if "Date" in 이름 else None
    package.set_xml(_CONTENT_HPF, tree)


def _charpr_글꼴_스냅샷(header) -> dict[tuple[str, str], str | None]:
    """`(charPr id, 언어 속성)` → 그 순간 가리키는 글꼴 이름.

    글꼴을 옮기기 **전**(원본 그대로)과 저장해 다시 연 **뒤**(옮긴 결과) 두 시점에 같은
    함수로 찍어, "바꾸기 전 이름을 font_map으로 옮긴 것 == 바뀐 뒤 이름"을 모든
    charPr×언어에 대해 확인하는 사후조건(`_글꼴_사후조건_확인`)의 재료로 쓴다.
    """
    id_to_face: dict[str, dict[str, str]] = {}
    for fontface in header.findall(f".//{_hq('fontface')}"):
        attr = _FONTFACE_LANG_TO_ATTR.get(fontface.get("lang", ""))
        if attr is None:  # pragma: no cover - 방어적: 7개 밖의 lang 값은 실측된 적이 없다
            continue
        id_to_face[attr] = {
            font.get("id"): font.get("face") for font in fontface.findall(_hq("font"))
        }

    스냅샷: dict[tuple[str, str], str | None] = {}
    for charpr in header.findall(f".//{_hq('charPr')}"):
        cid = charpr.get("id")
        fontref = charpr.find(_hq("fontRef"))
        if cid is None or fontref is None:
            continue
        for attr in _FONTFACE_LANG_TO_ATTR.values():
            스냅샷[(cid, attr)] = id_to_face.get(attr, {}).get(fontref.get(attr))
    return 스냅샷


def _글꼴_한쌍_다시가리키기(header, src_face: str, dst_face: str) -> tuple[int, bool]:
    """`header`(hh:head 전체 element)에서 `src_face` → `dst_face` 매핑 하나를 7개 언어
    각각에 적용한다. `(실제로 다시 가리킨 fontRef 속성 수, 무엇이든 바뀌었는가)`를 돌려준다
    — 후자는 charPr 리다이렉트가 0건이어도 글꼴 목록 자체는 바뀌는 경우(그 글꼴을 쓰는
    charPr이 하나도 없을 때)까지 포함해 `header.mark_dirty()`를 부를지 판단하는 신호다.

    언어마다:
    ① src의 id를 찾는다 — 그 목록에 없으면 이 언어는 건너뛴다(오류 아님 — 다른 학교
       양식에 표준 씨앗의 fontMap이 딸려 와도 무해해야 한다).
    ② dst의 id를 찾거나, 없으면 목록 끝에 새로 더한다.
    ③ 이 언어를 쓰는 모든 charPr의 fontRef를 src→dst로 다시 가리킨다.
    ④ src의 hh:font 항목을 지우고, 남은 항목의 id를 **문서 순서대로** 0부터 다시
       붙인다(원래 id 값이 아니라 남은 요소의 상대 순서 기준이다 — 그래서 id가 애초에
       0..N-1 연속이 아니었어도 항상 안전하다). 그 변화를 이 언어의 모든 fontRef 값에
       반영하고 fontCnt를 맞춘다 — 공개 스켈레톤에 사용자가 갖지 못한 글꼴의 흔적을
       남기지 않는다.
    """
    charprs = header.findall(f".//{_hq('charPr')}")
    바뀐_참조_수 = 0
    무언가_바뀜 = False

    for fontface in header.findall(f".//{_hq('fontface')}"):
        attr = _FONTFACE_LANG_TO_ATTR.get(fontface.get("lang", ""))
        if attr is None:  # pragma: no cover - 방어적: 7개 밖의 lang 값은 실측된 적이 없다
            continue

        fonts = fontface.findall(_hq("font"))
        face_to_id = {f.get("face"): f.get("id") for f in fonts}
        if src_face not in face_to_id:
            continue
        무언가_바뀜 = True
        src_id = face_to_id[src_face]

        if dst_face in face_to_id:
            dst_id = face_to_id[dst_face]
        else:
            dst_id = str(len(fonts))
            새_font = fontface.makeelement(
                _hq("font"),
                {"id": dst_id, "face": dst_face, "type": "TTF", "isEmbedded": "0"},
            )
            fontface.append(새_font)
            fonts = fontface.findall(_hq("font"))  # 새 항목을 포함해 다시 읽는다

        for charpr in charprs:
            fontref = charpr.find(_hq("fontRef"))
            if fontref is not None and fontref.get(attr) == src_id:
                fontref.set(attr, dst_id)
                바뀐_참조_수 += 1

        src_element = next(f for f in fonts if f.get("id") == src_id)
        남은_것 = [f for f in fonts if f is not src_element]
        새_id = {f.get("id"): str(idx) for idx, f in enumerate(남은_것)}

        fontface.remove(src_element)
        for f in 남은_것:
            f.set("id", 새_id[f.get("id")])
        fontface.set("fontCnt", str(len(남은_것)))

        for charpr in charprs:
            fontref = charpr.find(_hq("fontRef"))
            if fontref is None:
                continue
            현재 = fontref.get(attr)
            if 현재 in 새_id:
                fontref.set(attr, 새_id[현재])

    return 바뀐_참조_수, 무언가_바뀜


def _글꼴_옮기기(doc: HwpxDocument, font_map: dict[str, str]) -> tuple[int, dict]:
    """`font_map`(`{원래 글꼴: 바꿀 글꼴}`)을 header.xml에 적용한다.

    `(re-point한 fontRef 속성 수, 적용 전 (charPr id, 언어)→글꼴이름 스냅샷)`을 돌려준다 —
    스냅샷은 적용 **전** 상태를 담아야 하므로 이 함수 맨 앞, 어떤 언어의 fontface도 아직
    안 건드린 시점에 찍는다(그래야 사후조건이 "바꾸기 전"을 정확히 안다).
    """
    header_part = doc.parts.headers[0]
    header = header_part.element
    이전_스냅샷 = _charpr_글꼴_스냅샷(header)

    바뀐_참조_수 = 0
    무언가_바뀜 = False
    for src_face, dst_face in font_map.items():
        부분_카운트, 부분_바뀜 = _글꼴_한쌍_다시가리키기(header, src_face, dst_face)
        바뀐_참조_수 += 부분_카운트
        무언가_바뀜 = 무언가_바뀜 or 부분_바뀜

    if 무언가_바뀜:
        header_part.mark_dirty()

    return 바뀐_참조_수, 이전_스냅샷


def _글꼴_사후조건_확인(
    saved: HwpxDocument,
    font_map: dict[str, str],
    이전_글꼴: dict[tuple[str, str], str | None],
) -> None:
    """저장한 스켈레톤을 다시 열어 font_map 적용이 실제로 먹혔고 다른 참조를 안 틀어뜨렸는지
    확인한다 — fail closed, `_사후조건_확인`과 같은 예외 타입·문구 앞머리를 쓴다.

    ① 어떤 fontface 에도 font_map의 원래 글꼴 이름이 남아 있지 않다.
    ② 모든 fontRef 값이 그 언어 목록의 유효한 id다(0 ≤ 값 < fontCnt, id가 0..N-1 연속,
       fontCnt가 실제 항목 수와 같다).
    ③ 모든 charPr × 언어에 대해, 옮기기 **전** 가리키던 글꼴 이름을 font_map으로 옮긴
       값이 옮긴 **뒤** 가리키는 이름과 같다 — 다른 글꼴 참조가 id 재부여로 틀어지지
       않았다는 증명이고, font_map 적용의 핵심 단언이다.
    """
    header = saved.parts.headers[0].element
    원래_글꼴들 = set(font_map)
    유효_범위: dict[str, int] = {}

    for fontface in header.findall(f".//{_hq('fontface')}"):
        lang = fontface.get("lang", "")
        fonts = fontface.findall(_hq("font"))
        얼굴들 = {f.get("face") for f in fonts}
        남은 = 원래_글꼴들 & 얼굴들
        if 남은:
            raise ValueError(
                f"{_실패_머리말}: font_map의 원래 글꼴이 저장 뒤에도 남아 있다"
                f"({lang}) — {sorted(남은)}"
            )

        ids = [f.get("id") or "" for f in fonts]
        try:
            id값들 = sorted(int(i) for i in ids)
        except ValueError:
            id값들 = None
        if id값들 != list(range(len(fonts))) or fontface.get("fontCnt") != str(len(fonts)):
            raise ValueError(
                f"{_실패_머리말}: {lang} fontface의 id가 0..N-1 연속이 아니거나 fontCnt가 "
                f"실제 항목 수와 다르다 — id={ids}, fontCnt={fontface.get('fontCnt')!r}"
            )

        attr = _FONTFACE_LANG_TO_ATTR.get(lang)
        if attr is not None:
            유효_범위[attr] = len(fonts)

    for charpr in header.findall(f".//{_hq('charPr')}"):
        fontref = charpr.find(_hq("fontRef"))
        if fontref is None:
            continue
        for attr, fontcnt in 유효_범위.items():
            값 = fontref.get(attr)
            if 값 is None or not 값.isdigit() or not (0 <= int(값) < fontcnt):
                raise ValueError(
                    f"{_실패_머리말}: charPr {charpr.get('id')}의 fontRef {attr}={값!r}가 "
                    f"유효한 id 범위(0..{fontcnt - 1})를 벗어난다"
                )

    이후_글꼴 = _charpr_글꼴_스냅샷(header)
    if set(이전_글꼴) != set(이후_글꼴):
        raise ValueError(f"{_실패_머리말}: font_map 적용 전후 charPr×언어 집합이 달라졌다")
    for 키, 이전_이름 in 이전_글꼴.items():
        기대 = font_map.get(이전_이름, 이전_이름)
        실제 = 이후_글꼴[키]
        if 기대 != 실제:
            raise ValueError(
                f"{_실패_머리말}: charPr×언어 {키}의 글꼴이 font_map과 다르게 바뀌었다 — "
                f"이전={이전_이름!r} 기대={기대!r} 실제={실제!r}"
            )


def _밑줄_borderFill_더하기(doc: HwpxDocument) -> int:
    """아래 테두리만 SOLID 인 borderFill 을 header 에 보장하고 그 id 를 돌려준다.

    `ensure_border_fill` 은 같은 정의가 있으면 그 id 를, 없으면 (기존 최대 id + 1) 로 새로
    만든다 — 같은 원본이면 늘 같은 id 가 나온다(결정적). kit.json `borderFill.underline` 이
    이 id 를 가리킨다.
    """
    return int(doc.oxml.ensure_border_fill(**_밑줄_테두리))


def _밑줄_borderFill_확인(saved: HwpxDocument, bid: int) -> None:
    header = saved.parts.headers[0].element
    bf = next((e for e in header.iter(_hq("borderFill")) if e.get("id") == str(bid)), None)
    if bf is None:
        raise ValueError(f"{_실패_머리말}: 밑줄 borderFill {bid} 이 저장 뒤 header 에 없다")
    변 = {}
    for 이름 in ("left", "right", "top", "bottom"):
        e = bf.find(_hq(f"{이름}Border"))
        변[이름] = None if e is None else (e.get("type"), e.get("width"), e.get("color"))
    기대 = ("SOLID", _밑줄_테두리["border_width"], _밑줄_테두리["border_color"])
    if 변["bottom"] != 기대 or any(변[k] is None or 변[k][0] != "NONE" for k in ("left", "right", "top")):
        raise ValueError(f"{_실패_머리말}: 밑줄 borderFill {bid} 이 아래 테두리만이 아니다 — {변}")


def _보존_run_안의_금지_태그(run) -> list[str]:
    """보존하는 첫 run(secPr·ctrl)의 서브트리 전체에서 글자·표·그림·도형 자손을 찾는다.

    ctrl은 머리말·꼬리말도 담는 범용 컨테이너다 — ctrl **자체**만 보존 대상인지 보는 것으로는
    부족하다: 그 안쪽까지 봐야 한다. 다른 학교 원본이 머리말에 학교명·교사명을 넣어 뒀다면 바로 이
    자리(첫 문단 첫 run의 ctrl 안)에 있다. 찾은 태그를 처음 나온 순서·중복 없이
    `hp:` 접두사를 붙여 돌려준다 — 빈 리스트면 안전하다는 뜻이다.
    """
    찾음: list[str] = []
    for 자손 in run.iter():
        if 자손 is run:
            continue
        이름 = _local_name(자손.tag)
        if 이름 == "t":
            if not (자손.text or "").strip():
                continue
        elif 이름 not in _금지된_로컬이름:
            continue
        태그 = f"hp:{이름}"
        if 태그 not in 찾음:
            찾음.append(태그)
    return 찾음


def _사후조건_확인(
    saved: HwpxDocument,
    *,
    font_map: dict[str, str] | None = None,
    이전_글꼴: dict[tuple[str, str], str | None] | None = None,
    밑줄_borderFill: int | None = None,
) -> None:
    """저장한 스켈레톤을 다시 열어 본문·BinData 세척이 실제로 먹혔는지 확인한다.

    fail closed — 하나라도 어기면 조용히 깨진 채(또는 유출된 채) 배포될 수 있으므로
    조용히 넘어가지 않고 `ValueError`를 낸다:

    ① 검증 — 패키지 자체가 깨지지 않았는가.
    ② 문단 정확히 2개.
    ③ P0에 secPr이 있다.
    ④ P1(2단 전환 문단)에 colPr colCount=2가 있다.
    ⑤ `hp:t`(글자) 0개.
    ⑥ fieldBegin(메모·필드) 0개.
    ⑦ `BinData/` 로 시작하는 부품이 실제로 0개인가 — 물리 부품·매니페스트 참조 둘 다.
    ⑧ (`밑줄_borderFill` 을 줬으면) 그 borderFill 이 아래 테두리만 SOLID 인가.

    `font_map`을 줬으면(비어 있지 않으면) 추가로 `_글꼴_사후조건_확인`을 부른다 — 글꼴을
    안 옮긴 호출(`font_map=None`)은 이 자리에서 header.xml을 아예 안 본다.
    """
    검증 = saved.validate()
    if not 검증.ok:
        raise ValueError(f"{_실패_머리말}: 검증을 통과하지 못했다 — {list(검증.errors)}")

    section = saved.sections[0]
    element = section.element
    paragraphs = element.findall(_q("p"))
    if len(paragraphs) != 2:
        raise ValueError(
            f"{_실패_머리말}: 문단이 정확히 2개가 아니다 — {len(paragraphs)}개"
        )
    if not paragraphs[0].findall(f".//{_q('secPr')}"):
        raise ValueError(f"{_실패_머리말}: 첫 문단에 secPr이 없다")
    colPr목록 = paragraphs[1].findall(f".//{_q('colPr')}")
    if [c.get("colCount") for c in colPr목록] != ["2"]:
        raise ValueError(
            f"{_실패_머리말}: 두 번째 문단에 colPr colCount=2가 없다 — "
            f"{[c.get('colCount') for c in colPr목록]}"
        )
    if element.findall(f".//{_q('t')}"):
        raise ValueError(f"{_실패_머리말}: 스켈레톤에 hp:t(글자)가 남아 있다")
    if element.findall(f".//{_q('fieldBegin')}"):
        raise ValueError(f"{_실패_머리말}: 스켈레톤에 fieldBegin이 남아 있다")

    남은_bindata = [n for n in saved.package.part_names() if n.startswith("BinData/")]
    if 남은_bindata:
        raise ValueError(f"{_실패_머리말}: BinData 부품이 남아 있다 — {남은_bindata}")
    if "BinData/" in saved.package.get_text(_CONTENT_HPF):
        raise ValueError(f"{_실패_머리말}: content.hpf에 BinData/ 참조가 남아 있다")
    if font_map:
        _글꼴_사후조건_확인(saved, font_map, 이전_글꼴 or {})
    if 밑줄_borderFill is not None:
        _밑줄_borderFill_확인(saved, 밑줄_borderFill)


def extract_skeleton(
    source: Path,
    dest: Path,
    *,
    title: str = "수행평가 양식 스켈레톤",
    font_map: dict[str, str] | None = None,
) -> dict[str, int]:
    doc = HwpxDocument.open(source)
    if len(doc.sections) > 1:
        raise ValueError(
            f"{_실패_머리말}: 섹션이 둘 이상인 원본은 지원하지 않는다: {len(doc.sections)}개"
        )
    section = doc.sections[0]
    element = section.element

    paragraphs = element.findall(_q("p"))
    if len(paragraphs) < 3 or not paragraphs[2].findall(f".//{_q('colPr')}[@colCount='2']"):
        raise ValueError(
            f"{_실패_머리말}: 원본 구조가 예상과 다르다 — 세 번째 문단에 2단 정의가 없다"
        )
    first = paragraphs[0]
    if not first.findall(f".//{_q('secPr')}"):
        raise ValueError(f"{_실패_머리말}: 첫 문단에 secPr이 없다 — 원본 구조가 예상과 다르다")

    runs = first.findall(_q("run"))
    첫_run, 나머지_run = runs[0], runs[1:]
    for run in 나머지_run:
        first.remove(run)

    # 보존하는 첫 run에 secPr·ctrl 말고 글자(hp:t)·표·그림·도형이 같이 들어 있으면 그대로
    # 새 나갔다 — 화이트리스트(secPr·ctrl만 남긴다)로 나머지 자식을 전부 지운다.
    보존할_자식 = {_q("secPr"), _q("ctrl")}
    first_run_stripped = 0
    for child in list(첫_run):
        if child.tag not in 보존할_자식:
            첫_run.remove(child)
            first_run_stripped += 1

    # 보존한 secPr·ctrl **안쪽**까지 본다. ctrl은 머리말·꼬리말도 담는 범용
    # 컨테이너라, 위 화이트리스트만으로는 그 안에 든 내용을 놓친다. 여기서 걸리면
    # 자동으로 지우지 않고 통째로 거부한다 — 무엇을 지워도 되는지 이 함수가 판단할 만큼
    # 확신할 수 없어서다.
    금지_태그 = _보존_run_안의_금지_태그(첫_run)
    if 금지_태그:
        raise ValueError(
            f"{_실패_머리말}: 첫 문단의 컨트롤 안에 내용이 있다"
            f"(머리말·꼬리말일 수 있다) — {', '.join(금지_태그)}"
        )

    for cache in first.findall(_q("linesegarray")):
        first.remove(cache)

    # 세 번째 문단(P2)은 남긴다 — 1단→2단 전환을 이루는 colPr을 담은 hp:run 하나만
    # 남기고(그 run 안에서도 hp:ctrl 외 자식 제거) linesegarray를 지운다. 나머지
    # 문단(P1, P3 이후)은 전부 지운다.
    전환_문단 = paragraphs[2]
    전환_runs = 전환_문단.findall(_q("run"))
    전환_run = next(
        r for r in 전환_runs if r.findall(f".//{_q('colPr')}[@colCount='2']")
    )
    for run in 전환_runs:
        if run is not 전환_run:
            전환_문단.remove(run)
    보존할_전환_자식 = {_q("ctrl")}
    for child in list(전환_run):
        if child.tag not in 보존할_전환_자식:
            전환_run.remove(child)

    # 첫 문단과 같은 이유로 전환 run의 ctrl **안쪽**까지 본다 — colPr만 있어야 할
    # 자리에 표·그림·도형이 같이 실려 있으면 그대로 새 나간다. 여기서 걸리면 자동으로
    # 지우지 않고 통째로 거부한다.
    금지_태그 = _보존_run_안의_금지_태그(전환_run)
    if 금지_태그:
        raise ValueError(
            f"{_실패_머리말}: 2단 전환 문단(세 번째 문단)의 컨트롤 안에 내용이 있다"
            f" — {', '.join(금지_태그)}"
        )

    for cache in 전환_문단.findall(_q("linesegarray")):
        전환_문단.remove(cache)

    for paragraph in paragraphs[1:]:
        if paragraph is not 전환_문단:
            element.remove(paragraph)
    section.mark_dirty()

    package = doc.package
    for item_id in _bindata_item_ids(package):
        package.remove_manifest_item(item_id)
    for name in [n for n in package.part_names() if n.startswith("BinData/")]:
        package.delete(name)

    package.set_document_metadata(
        title=title, creator="", subject="", keyword="",
        created_date=_고정_시각, modified_date=_고정_시각,
    )
    _scrub_opaque_metadata(package)
    # Preview/PrvText.txt는 OPF 매니페스트에 없어 위 메타데이터 세척에 딸려 오지
    # 않는다 — 원본 저장 시점의 본문 미리보기가 그대로 남아 학교·교사 실명이 샌다.
    if package.has_part("Preview/PrvText.txt"):
        package.write("Preview/PrvText.txt", "")
    # 미리보기 그림은 원본 1쪽의 **스냅샷**이라 학교 로고·교사명이 그대로 보인다.
    # check_hygiene 은 텍스트만 보므로 이것을 못 잡는다 — 위생 검사가 통과한 채로
    # 공개물에 실릴 수 있다. container.xml 이 루트파일로 선언해 지울 수는 없으니 비운다.
    if package.has_part("Preview/PrvImage.png"):
        package.set_part("Preview/PrvImage.png", _흰_png())

    fonts_remapped = 0
    이전_글꼴: dict[tuple[str, str], str | None] = {}
    if font_map:
        fonts_remapped, 이전_글꼴 = _글꼴_옮기기(doc, font_map)
    밑줄_borderFill = _밑줄_borderFill_더하기(doc)

    # save_to_path(dest)를 바로 부르면, 그 뒤 사후조건이 실패했을 때 dest에 이미
    # "중립처럼 보이지만 아닌" 완전한 zip이 남는다. 같은 디렉터리의 임시 경로에 먼저 쓰고,
    # 사후조건까지 통과한 뒤에만 os.replace로 원자적 교체한다 — 실패하면 임시 파일을 지우고
    # 그대로 다시 던진다(기존 dest가 있었다면 손대지 않은 채 그대로 남는다).
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, 임시_경로_문자열 = tempfile.mkstemp(
        prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent),
    )
    os.close(fd)
    임시_경로 = Path(임시_경로_문자열)
    try:
        doc.save_to_path(임시_경로)
        saved = HwpxDocument.open(임시_경로)
        _사후조건_확인(saved, font_map=font_map, 이전_글꼴=이전_글꼴, 밑줄_borderFill=밑줄_borderFill)
    except BaseException:
        임시_경로.unlink(missing_ok=True)
        raise
    os.replace(임시_경로, dest)

    return {
        "paragraphs": len(saved.sections[0].element.findall(_q("p"))),
        "border_fills": len(saved.styles.border_fills),
        "char_prs": len(saved.styles.char_properties),
        "para_prs": len(saved.styles.paragraph_properties),
        "bin_data": sum(
            1 for n in saved.package.part_names() if n.startswith("BinData/")
        ),
        "parts": len(saved.package.part_names()),
        "first_run_stripped": first_run_stripped,
        "fonts_remapped": fonts_remapped,
        "underline_border_fill": 밑줄_borderFill,
    }
