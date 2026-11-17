"""원본 학습지 hwpx에서 본문을 비운 스켈레톤을 뽑는다."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from worksheet.ns import HH


_CONTENT_HPF = "Contents/content.hpf"
_고정_시각 = "1970-01-01T00:00:00Z"
# 이 도구는 유출 방지 도구다 — 안전하게 중립화하지 못한 원본은 파일이 아니라 예외로
# 끝나야 한다(fail closed). 사후조건이든 구조 거부든 원인은 전부 "원본의 구조" 이므로
# 예외 타입과 문구 앞머리를 하나로 통일한다.
_실패_머리말 = "스켈레톤을 안전하게 만들지 못했다"


_LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")


def _bindata_items(doc: HwpxDocument) -> list[str]:
    """이진 항목 가운데 파트가 `BinData/` 아래인 것의 매니페스트 id 전부(`doc.media.images`)."""
    return [item.item_id for item in doc.media.images if item.href.startswith("BinData/")]


def _scrub_metadata(doc: HwpxDocument, title: str) -> None:
    """content.hpf 메타데이터를 세척한다: 제목은 고정 제목, 이름을 모르는 것까지 **모든** opf:meta를 — 이름에 "Date"가
    든 항목(CreatedDate·ModifiedDate)은 고정 시각으로, 그 밖은 빈 값으로(`doc.parts.clear_document_metadata`).
    이름을 나열해 지우는 블랙리스트 방식은 다른 학교 원본에만 있는 한컴 자체 필드를 놓친다."""
    doc.parts.set_document_metadata(
        title=title, creator="", subject="", keyword="",
        created_date=_고정_시각, modified_date=_고정_시각,
    )
    doc.parts.clear_document_metadata(keep=("title", "language"), timestamp=_고정_시각)


def _charpr_글꼴_스냅샷(doc: HwpxDocument) -> dict[tuple[str, str], str | None]:
    """`(charPr id, 언어 속성)` → 그 순간 가리키는 글꼴 이름(`doc.styles.font_face`).

    글꼴을 옮기기 **전**(원본 그대로)과 저장해 다시 연 **뒤**(옮긴 결과) 두 시점에 같은
    함수로 찍어, "바꾸기 전 이름을 font_map으로 옮긴 것 == 바뀐 뒤 이름"을 모든
    charPr×언어에 대해 확인하는 사후조건(`_글꼴_사후조건_확인`)의 재료로 쓴다.
    fontRef가 없는 글자 모양은 넣지 않는다.
    """
    스냅샷: dict[tuple[str, str], str | None] = {}
    for cid, style in doc.styles.char_properties.items():
        if "fontRef" not in style.child_attributes:
            continue
        for lang in _LANGS:
            스냅샷[(str(cid), lang.lower())] = doc.styles.font_face(cid, lang)
    return 스냅샷


def _글꼴_옮기기(doc: HwpxDocument, font_map: dict[str, str]) -> tuple[int, dict]:
    """`font_map`(`{원래 글꼴: 바꿀 글꼴}`)을 header.xml에 적용한다.

    `(re-point한 fontRef 속성 수, 적용 전 (charPr id, 언어)→글꼴이름 스냅샷)`을 돌려준다 —
    스냅샷은 적용 **전** 상태를 담아야 하므로 이 함수 맨 앞, 어떤 언어의 fontface도 아직
    안 건드린 시점에 찍는다(그래야 사후조건이 "바꾸기 전"을 정확히 안다).

    교체는 항목마다 core의 `doc.styles.replace_font`가 7개 언어에 한다: 원래 글꼴이 없는
    언어는 건너뛰고(다른 학교 양식에 표준 씨앗의 fontMap이 딸려 와도 무해해야 한다), 바꿀
    글꼴을 찾거나 끝에 더하고, fontRef를 옮기고, 원래 글꼴을(같은 이름이 여러 번 선언됐으면
    모두) 지운 뒤 id를 문서 순서대로 0..N-1로 다시 매기고 fontCnt를 맞춘다. 항목은
    `font_map` 순서대로 적용한다 — 자기 자신·연쇄는 `kit.validate_font_map`이 이미 막는다.
    """
    이전_스냅샷 = _charpr_글꼴_스냅샷(doc)

    바뀐_참조_수 = 0
    for src_face, dst_face in font_map.items():
        try:
            보고 = doc.styles.replace_font(src_face, dst_face)
        except HwpxValueError as exc:
            raise ValueError(
                f"{_실패_머리말}: font_map 항목 '{src_face}' → '{dst_face}'를 적용할 수 없다 — {exc}"
            ) from exc
        바뀐_참조_수 += 보고.repointed

    return 바뀐_참조_수, 이전_스냅샷


def _글꼴_사후조건_확인(
    saved: HwpxDocument,
    font_map: dict[str, str],
    이전_글꼴: dict[tuple[str, str], str | None],
) -> None:
    """저장한 스켈레톤을 다시 열어 font_map 적용이 실제로 먹혔고 다른 참조를 안 틀어뜨렸는지
    확인한다 — fail closed, `_사후조건_확인`과 같은 예외 타입·문구 앞머리를 쓴다.

    ① 어떤 언어 글꼴 목록에도 font_map의 원래 글꼴 이름이 남아 있지 않다.
    ② 모든 fontRef 값이 그 언어 목록의 유효한 id다(0 ≤ 값 < 글꼴 수, id가 0..N-1 연속).
       (fontCnt는 core `replace_font`가 맞추고, 공개 읽기로는 보지 않는다.)
    ③ 모든 charPr × 언어에 대해, 옮기기 **전** 가리키던 글꼴 이름을 font_map으로 옮긴
       값이 옮긴 **뒤** 가리키는 이름과 같다 — 다른 글꼴 참조가 id 재부여로 틀어지지
       않았다는 증명이고, font_map 적용의 핵심 단언이다.
    """
    원래_글꼴들 = set(font_map)
    유효_범위: dict[str, int] = {}

    # fontCnt와 '블록은 있는데 글꼴이 0개'는 공개 읽기(styles.fonts)로 보이지 않아 저장한 헤더 파트를 읽는다(옛 판 조건 그대로).
    헤더 = saved.package.get_xml(saved.package.header_paths()[0])
    fontcnt_of = {ff.get("lang", ""): ff.get("fontCnt") for ff in 헤더.iter(f"{{{HH}}}fontface")}
    for lang in _LANGS:
        if lang not in fontcnt_of:  # 그 언어 목록이 없다
            continue
        fonts = saved.styles.fonts(lang)
        남은 = 원래_글꼴들 & {f.face for f in fonts.values()}
        if 남은:
            raise ValueError(
                f"{_실패_머리말}: font_map의 원래 글꼴이 저장 뒤에도 남아 있다"
                f"({lang}) — {sorted(남은)}"
            )
        ids = list(fonts)
        try:
            id값들 = sorted(int(i) for i in ids)
        except ValueError:
            id값들 = None
        if id값들 != list(range(len(fonts))) or fontcnt_of[lang] != str(len(fonts)):
            raise ValueError(
                f"{_실패_머리말}: {lang} fontface의 id가 0..N-1 연속이 아니거나 fontCnt가 "
                f"실제 항목 수와 다르다 — id={ids}, fontCnt={fontcnt_of[lang]!r}"
            )
        유효_범위[lang.lower()] = len(fonts)

    for cid, style in saved.styles.char_properties.items():
        fontref = style.child_attributes.get("fontRef")
        if fontref is None:
            continue
        for attr, fontcnt in 유효_범위.items():
            값 = fontref.get(attr)
            if 값 is None or not 값.isdigit() or not (0 <= int(값) < fontcnt):
                raise ValueError(
                    f"{_실패_머리말}: charPr {cid}의 fontRef {attr}={값!r}가 "
                    f"유효한 id 범위(0..{fontcnt - 1})를 벗어난다"
                )

    이후_글꼴 = _charpr_글꼴_스냅샷(saved)
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


def _사후조건_확인(
    saved: HwpxDocument,
    *,
    font_map: dict[str, str] | None = None,
    이전_글꼴: dict[tuple[str, str], str | None] | None = None,
) -> None:
    """저장한 스켈레톤을 다시 열어 본문·BinData 세척이 실제로 먹혔는지 확인한다.

    fail closed — 셋 중 하나라도 어기면 조용히 깨진 채(또는 유출된 채) 배포될 수 있으므로
    조용히 넘어가지 않고 `ValueError`를 낸다(사후조건도 원인은 원본의 구조이므로 구조 거부와
    같은 예외 타입·문구 앞머리를 쓴다):

    ① `validate().ok` — 패키지 자체가 깨지지 않았는가.
    ② `BinData/` 로 시작하는 부품이 실제로 0개인가.
    ③ `content.hpf`에 `BinData/` 문자열이 아예 없는가 — ①·②를 다 통과해도, 물리 부품은
       지워졌는데 매니페스트에 낡은 참조만 남는 경우(예: 항목 id를 못 찾아 매니페스트에서만
       못 지웠을 때)가 있다. 실측: 그 상태에서도 `validate().ok`는 참이고 BinData 부품
       개수는 0이다 — ③만이 이 경우를 잡는다.
    `font_map`을 줬으면(비어 있지 않으면) 추가로 `_글꼴_사후조건_확인`을 부른다 — 글꼴을
    안 옮긴 호출(`font_map=None`)은 이 자리에서 header.xml을 아예 안 본다.

    호출자(`extract_skeleton`)가 이 함수를 **임시 경로**에 저장한 결과에 대고 불러야
    한다 — 실패해도 `dest`에는 아무것도 쓰이지 않도록.
    """
    검증 = saved.validate()
    if not 검증.ok:
        raise ValueError(f"{_실패_머리말}: 검증을 통과하지 못했다 — {list(검증.errors)}")
    남은_bindata = [n for n in saved.package.part_names() if n.startswith("BinData/")]
    if 남은_bindata:
        raise ValueError(f"{_실패_머리말}: BinData 부품이 남아 있다 — {남은_bindata}")
    if "BinData/" in saved.package.get_text(_CONTENT_HPF):
        raise ValueError(f"{_실패_머리말}: content.hpf에 BinData/ 참조가 남아 있다")
    if font_map:
        _글꼴_사후조건_확인(saved, font_map, 이전_글꼴 or {})


def extract_skeleton(
    source: Path,
    dest: Path,
    *,
    title: str = "학습지 양식 스켈레톤",
    font_map: dict[str, str] | None = None,
) -> dict[str, int]:
    doc = HwpxDocument.open(source)
    if len(doc.sections) > 1:
        raise ValueError(
            f"{_실패_머리말}: 섹션이 둘 이상인 원본은 지원하지 않는다: {len(doc.sections)}개"
        )
    section = doc.sections[0]
    if not section.paragraphs:
        raise ValueError(f"{_실패_머리말}: 본문 문단이 없다: {source}")

    # 본문 비우기는 core의 clear_body가 한다: 첫 문단 첫 run의 secPr(쪽 설정)과 첫 문단
    # run들의 ctrl(단·머리말·꼬리말·쪽 번호)만 남기고 나머지 문단·글자·표·그림·도형과 줄
    # 캐시를 지운다. ctrl은 머리말·꼬리말도 담는 범용 컨테이너라, 남기는 secPr·ctrl **안쪽**에
    # 글자·표·개체가 있으면(다른 학교 원본의 머리말에 든 학교명·교사명 같은) 지우지 않고
    # 통째로 거부한다("raise") — 무엇을 지워도 되는지 이 함수가 판단할 만큼 확신할 수
    # 없어서다. 거부는 아무것도 바꾸기 전에 일어난다.
    try:
        보고 = section.clear_body(on_control_content="raise")
    except HwpxValueError as exc:
        if exc.code == "section-clear-no-section-properties":
            raise ValueError(
                f"{_실패_머리말}: 첫 문단 첫 run에 secPr이 없다 — 원본 구조가 예상과 다르다"
            ) from exc
        if exc.code == "section-clear-control-content":
            raise ValueError(
                f"{_실패_머리말}: 첫 문단의 컨트롤 안에 내용이 있다"
                f"(머리말·꼬리말일 수 있다) — {', '.join(exc.context['tags'])}"
            ) from exc
        raise
    first_run_stripped = 보고.stripped_run_children

    package = doc.package
    for item_id in _bindata_items(doc):
        package.remove_manifest_item(item_id)
    for name in [n for n in package.part_names() if n.startswith("BinData/")]:
        package.delete(name)

    _scrub_metadata(doc, title)
    # 미리보기 글(Preview/PrvText.txt)은 OPF 매니페스트에 없어 위 메타데이터 세척에 딸려 오지
    # 않는다 — 원본 저장 시점의 본문 미리보기가 그대로 남아 학교·교사 실명이 샌다. 미리보기 그림은
    # 원본 1쪽의 **스냅샷**이라 학교 로고·교사명이 그대로 보인다(check_hygiene 은 텍스트만 본다).
    # container.xml 이 루트파일로 선언해 지울 수는 없으니 글은 비우고 그림은 1×1 흰 그림으로 바꾼다.
    doc.parts.clear_preview()

    fonts_remapped = 0
    이전_글꼴: dict[tuple[str, str], str | None] = {}
    if font_map:
        fonts_remapped, 이전_글꼴 = _글꼴_옮기기(doc, font_map)

    # save(dest)를 바로 부르면, 그 뒤 사후조건이 실패했을 때 dest에 이미
    # "중립처럼 보이지만 아닌" 완전한 zip이 남는다. 같은 디렉터리의 임시 경로에 먼저 쓰고,
    # 사후조건까지 통과한 뒤에만 os.replace로 원자적 교체한다 — 실패하면 임시 파일을 지우고
    # 그대로 다시 던진다(기존 dest가 있었다면 손대지 않은 채 그대로 남는다).
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, 임시_경로_문자열 = tempfile.mkstemp(
        prefix=dest.name + ".", suffix=".tmp.hwpx", dir=str(dest.parent),
    )
    os.close(fd)
    임시_경로 = Path(임시_경로_문자열)
    try:
        doc.save(임시_경로)
        saved = HwpxDocument.open(임시_경로)
        _사후조건_확인(saved, font_map=font_map, 이전_글꼴=이전_글꼴)
    except BaseException:
        임시_경로.unlink(missing_ok=True)
        raise
    os.replace(임시_경로, dest)

    return {
        "paragraphs": len(saved.sections[0].paragraphs),
        "border_fills": len(saved.styles.border_fills),
        "char_prs": len(saved.styles.char_properties),
        "para_prs": len(saved.styles.paragraph_properties),
        "bin_data": sum(
            1 for n in saved.package.part_names() if n.startswith("BinData/")
        ),
        "parts": len(saved.package.part_names()),
        "first_run_stripped": first_run_stripped,
        "fonts_remapped": fonts_remapped,
    }
