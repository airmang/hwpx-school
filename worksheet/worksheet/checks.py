"""[기계] 검사 — 결정적 사실만 본다. [의미] 판정은 여기서 하지 않는다."""

from __future__ import annotations

import re
import unicodedata
import zipfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from docx import Document
from hwpx import HwpxDocument, HwpxPackage
from hwpx.experimental import render_layout_preview

from worksheet.blocks import SPECS, STRUCTURAL, fence_problems, png_size, 그림_폭_문제
from worksheet.kit import DEFAULT_RESIDUE_MARKERS, Kit, effective_slots, parse_slot_fields
from worksheet.md import Fence, Figure, Heading, Sheet

_미리보기 = "Preview/PrvImage.png"
_미리보기_상한 = 1024  # 바이트. 빈 미리보기(1×1 PNG)는 69바이트, 실제 쪽 스냅샷은 수십 KB다.

# STRUCTURAL(이름 → 클래스)의 역표 — 이름 문자열을 여기서 다시 손으로 적지 않는다.
_구조_이름 = {cls: 이름 for 이름, cls in STRUCTURAL.items()}


def check_markdown(sheet: Sheet, kit: Kit, *, base_dir: Path | None = None) -> list[str]:
    """M-1 — 모든 노드가 엔진이 그릴 수 있고 킷이 허용하는 블록인가.

    M-1 통과는 "조판이 이 md 때문에 거부하지 않는다"를 뜻해야 한다(`compose()`가 조판
    직전에 이 함수 + `check_answer_labels`를 그대로 불러 이 성질을 고정한다). 그러려면
    네 가지를 다 봐야 한다:

    1. 펜스 이름이 구조 노드(정의빈칸·발문·그림칸) 자리인가 — 그 셋은 펜스가 아니라
       `■`·`>`·`![]()` 로 쓴다.
    2. 펜스 이름을 엔진이 아예 모르는가(`SPECS`에도 `STRUCTURAL`에도 없음).
    3. (구조 노드 포함) 이 이름을 킷이 허용하는가(`kit.blocks`) — 킷이 아는 이름인가와는
       별개 사실이다. 킷을 `blocks: ["정의빈칸","답칸"]`으로 좁혀도 `:::비교표`는 엔진이
       알아서 그냥 그려지던 구멍을 여기서 막는다.
    4. 펜스면 `fence_problems()`(모르는 속성·필수 속성·정수/길이 속성의 꼴과 범위·본문
       형식·칸 안 그림)까지 — kit을 넘기므로 길이 속성의 본문 폭 대비 상한도 여기서 본다.
       `base_dir`도 그대로 넘기므로(펜스 쪽) 칸 안 그림의 파일 존재·PNG 유효성도 여기서
       같이 본다 — `plan_node`도 같은 두 값을 `fence_problems`에 넘기므로 이 검사가
       초록불이면 칸 안 그림도 조판이 거부하지 않는다.
    5. 그림(본문 그림 줄, 구조 노드)이 본문 폭보다 넓지 않은가, `base_dir`가 주어지면 파일이
       실제로 있고 PNG인가.
    """
    문제: list[str] = []
    for node in sheet.nodes:
        if isinstance(node, Heading):
            continue

        if isinstance(node, Fence):
            이름 = node.name
            if 이름 in STRUCTURAL:
                문제.append(
                    f"펜스로 쓸 수 없는 블록: {이름} — 구조 노드는 펜스가 아니라 본문 문법으로 쓴다"
                )
            elif 이름 not in SPECS:
                # 엔진이 아예 모르는 이름이면 킷 허용 여부는 별개 사실이 아니다 — 어떤
                # 킷도 그릴 렌더러가 없는 이름을 "허용"할 수는 없다(원인 하나에 문제 하나만
                # 낸다). 다음 노드로 넘어간다 — fence_problems 도 이 이름엔 빈 리스트를
                # 내므로(SPECS에 없다) 어차피 더할 것이 없다.
                문제.append(f"엔진이 모르는 블록: {이름}")
                continue
        else:
            이름 = _구조_이름.get(type(node))
            if 이름 is None:
                raise TypeError(f"알 수 없는 노드: {type(node).__name__}")

        if 이름 not in kit.blocks:
            문제.append(f"킷이 허용하지 않는 블록: {이름}")

        if isinstance(node, Fence):
            문제 += fence_problems(node, kit=kit, base_dir=base_dir)

        if isinstance(node, Figure) and (폭_문제 := 그림_폭_문제(kit, node.width_mm, f"그림({node.path})")):
            문제.append(폭_문제)

        if isinstance(node, Figure) and base_dir is not None:
            경로 = Path(base_dir) / node.path
            if not 경로.is_file():
                # .exists() 가 아니라 .is_file() — 디렉터리를 가리키는 경로도 여기서 같은
                # 문구로 잡는다. 안 그러면 .exists()는 참을 주고 read_bytes()가
                # IsADirectoryError 트레이스백을 낸다.
                문제.append(f"그림 파일이 없다: {node.path}")
            else:
                try:
                    png_size(경로.read_bytes())
                except ValueError as e:
                    문제.append(f"{e}: {node.path}")

    return list(dict.fromkeys(문제))  # 같은 문제는 한 번만(순서 유지)


def _docx_인가(path: Path) -> bool:
    """`output_format()`(확장자 규칙의 단일 출처)에 위임한다 — 대소문자 무관, 모르는
    확장자는 (여기서도) 거부한다. 지연 임포트: `worksheet.compose`가 이 모듈(checks)을
    가져오므로, 모듈 최상단에서 서로 가져오면 순환 임포트가 된다(호출 시점에는 두 모듈
    다 이미 로드가 끝나 있으므로 함수 안 임포트는 안전하다).
    """
    from worksheet.compose import output_format

    return output_format(path) == "docx"


def check_package(path: Path) -> list[str]:
    """M-2 — 패키지 검증. hwpx 는 validate(), docx 는 python-docx 로 다시 열고 필수 부품을 본다.

    repair_hwpx가 필요 없어야 한다(hwpx).
    """
    if _docx_인가(path):
        try:
            Document(str(path))
            with zipfile.ZipFile(path) as z:
                없는 = [n for n in ("[Content_Types].xml", "word/document.xml") if n not in z.namelist()]
                깨진 = z.testzip()
        except Exception as e:  # noqa: BLE001 — 어떤 이유로든 열리지 않으면 그것이 검사 결과다
            return [f"docx 를 열 수 없다: {e}"]
        return [f"docx 필수 부품이 없다: {n}" for n in 없는] + ([f"docx 부품이 깨졌다: {깨진}"] if 깨진 else [])
    보고 = HwpxDocument.open(path).validate()
    return [] if 보고.ok else [f"패키지 검증 실패: {e}" for e in 보고.errors]


def check_empty_slots(kit: Kit, *, grade: str | None = None) -> list[str]:
    """M-3 보강 — 머리띠(`furniture.band`)가 참조하는 슬롯 중 킷에 없거나 빈 것.

    `kits/standard`처럼 슬롯이 전부 빈 씨앗 킷은 참조되는 슬롯 넷을 전부 낸다 — 그게
    맞다: 씨앗은 복사해서 슬롯을 채워 쓰라고 있는 것이라 "슬롯이 비어 있다"가 정상 진단이다.

    `grade`(회차의 학년)를 주면 `worksheet.kit.effective_slots`로 킷의 `grade` 슬롯을
    덮은 값을 기준으로 본다 — 킷 자체는 `grade` 슬롯이 비어 있어도 회차(md)가 `grade`를
    주면 그 슬롯은 "빈 슬롯"으로 세지 않는다. 자리표시자는 `worksheet.kit.parse_slot_fields`
    (`load_kit`의 킷 스키마 검사와 같은 함수)로 읽는다.
    """
    band = kit.furniture["band"]
    슬롯 = effective_slots(kit, grade=grade)
    이름들: list[str] = []
    for 줄 in (*band["teacherLines"], *band["nameLines"]):
        for 필드 in parse_slot_fields(줄):
            if 필드 not in 이름들:
                이름들.append(필드)

    빈것 = [이름 for 이름 in 이름들 if not 슬롯.get(이름, "").strip()]
    return [f"빈 슬롯: {', '.join(빈것)}"] if 빈것 else []


def check_slot_residue(
    path: Path, markers: Sequence[str] = DEFAULT_RESIDUE_MARKERS
) -> list[str]:
    """M-3 — 미치환 슬롯·TODO 잔존. hwpx 는 매니페스트의 구역과 `Contents/section*.xml` 전부(section0 고정 아님),
    docx 는 `word/document.xml`·`word/header*.xml`·`word/footer*.xml` 를 본다.

    본문 부품은 항상 UTF-8(OWPML 표준·OOXML 둘 다)이라 엄격 디코드로 읽는다 — 실패하면
    조용히 건너뛰지 않고 `슬롯 검사를 하지 못했다`를 문제로 낸다: `errors="ignore"`로
    조용히 넘기면 읽지 못한 부품을 "잔존 없음"으로 착각하는 거짓 통과가 된다. 읽지 못한
    부품이 있어도 나머지 부품은 계속 본다.

    docx 본문 글자는 런 경계에서 `<w:t>` 로 쪼개질 수 있다("TODO"가 "TO"·"DO" 두 런에
    걸치는 식) — 태그가 섞인 원문 그대로 찾으면 쪼개진 낱말을 놓치므로, `<w:t…>` 안
    글자만 뽑아 이어 붙인 문자열에서 찾는다. 잇는 것은 한 문단(`<w:p>`) 안까지다 — 문단 사이를
    이어 붙이면 앞 칸 끝과 뒤 칸 첫머리가 마커처럼 붙는 거짓 양성이 난다.
    """
    조각들: list[str] = []
    문제: list[str] = []
    if _docx_인가(path):
        with zipfile.ZipFile(path) as 꾸러미:
            부품들 = sorted(
                n for n in 꾸러미.namelist()
                if n == "word/document.xml"
                or (n.startswith("word/header") and n.endswith(".xml"))
                or (n.startswith("word/footer") and n.endswith(".xml"))
            )
            for n in 부품들:
                try:
                    내용 = 꾸러미.read(n).decode("utf-8")
                except UnicodeDecodeError:
                    문제.append(f"슬롯 검사를 하지 못했다: {n}")
                    continue
                # 문단 안에서만 잇고 문단 사이는 끊는다 — 한 칸 끝과 다음 칸 첫머리가 마커로 붙지 않게
                조각들.append("\n".join(
                    "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", 문단))
                    for 문단 in re.findall(r"<w:p(?:\s[^>]*)?>.*?</w:p>", 내용, flags=re.S)
                ))
    else:
        꾸러미 = HwpxPackage.open(path)
        # 매니페스트가 밝힌 구역에 더해, 매니페스트 밖에 끼어든 구역 부품도 본다
        부품들 = sorted(
            set(꾸러미.section_paths())
            | {n for n in 꾸러미.part_names() if n.startswith("Contents/section") and n.endswith(".xml")}
        )
        for n in 부품들:
            try:
                조각들.append(꾸러미.get_text(n))
            except UnicodeDecodeError:
                문제.append(f"슬롯 검사를 하지 못했다: {n}")
    xml = " ".join(조각들)
    문제 += [f"슬롯 잔존 {흔적!r} {xml.count(흔적)}건" for 흔적 in markers if 흔적 in xml]
    return 문제


def check_answer_labels(sheet: Sheet) -> list[str]:
    """M-4 — 답칸 라벨 유일·누락 없음."""
    라벨들 = [
        node.attrs.get("label", "").strip()
        for node in sheet.nodes
        if isinstance(node, Fence) and node.name == "답칸"
    ]
    문제 = ["라벨 없는 답칸이 있다"] if any(not 라 for 라 in 라벨들) else []
    문제 += [
        f"답칸 라벨 중복: {라벨} ({횟수}회)"
        for 라벨, 횟수 in Counter(라 for 라 in 라벨들 if 라).items()
        if 횟수 > 1
    ]
    return 문제


def _글자_읽기(데이터: bytes) -> str | None:
    """UTF-8 엄격 디코드 → 실패하면 BOM 있는 UTF-16 → 그것도 실패하면 None.

    호출자는 None을 "검사하지 못한 파일"로 만든다 — `errors="ignore"`로 읽으면 못 읽은
    파일도 조용히 통과하므로 그렇게 하지 않는다. BOM이 없으면 UTF-16을 시도하지 않는다
    (임의 바이너리가 우연히
    native-endian UTF-16으로 잘못 풀리는 것을 막는다).
    """
    try:
        return 데이터.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if 데이터[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return 데이터.decode("utf-16")
        except UnicodeDecodeError:
            pass
    return None


def _금칙어_본문_문제(텍스트: str | None, 위치: str, 금칙어_정규화: Sequence[str]) -> list[str]:
    if 텍스트 is None:
        return [f"검사하지 못한 파일: {위치}"]
    정규화 = unicodedata.normalize("NFC", 텍스트)
    return [f"금칙어 {말!r}: {위치}" for 말 in 금칙어_정규화 if 말 in 정규화]


def check_hygiene(root: Path, forbidden: Sequence[str]) -> list[str]:
    """M-5 — 배포본 금칙어. 파일 하나든 디렉터리든 받는다. fail closed.

    `Path(파일).rglob("*")` 는 빈 리스트라, 단일 파일을 디렉터리처럼 훑으면 금칙어가 있어도
    조용히 통과한다. 이 검사는 공개 배포본에 학교·교사 이름이 새는 것을 막는 **유일한 기계
    검사**이므로 거짓 통과가 검사 없음보다 나쁘다.

    본문·경로·금칙어 모두 NFC로 정규화한 뒤 비교한다 — 맥에서 붙여넣은 글과 파일 이름은
    NFD로 들어온다. hwpx(`zipfile.is_zipfile` — 확장자 무관)는 **모든 멤버**를 본다:
    `Preview/PrvImage.png`(쪽 스냅샷)는 글자 검사로 못 보는 그림 유출 통로라 크기로 보고,
    `BinData/`의 그림은 글자를 읽을 수 없으므로 항상 "검사하지 못한 파일(그림)"이다 —
    통과가 아니라 문제다. 그 밖의 멤버·비 zip 파일은 글자를 읽어 검색하고, 못 읽으면(둘
    다 실패) 마찬가지로 문제로 낸다.

    `root` 가 아예 없으면 `rglob("*")`가 조용히 빈 리스트를 내, 그대로 두면 "금칙어 잔존
    0"으로 읽힌다 — fail **open**이다: 파일을 하나도 못 본 것뿐인데 통과로 보이는, 검사
    없음보다 나쁜 거짓 통과다. 오타 난 `--dest`가 그 자리다. 여기서도 fail closed로
    문제를 낸다.
    """
    뿌리 = Path(root)
    if not 뿌리.exists():
        return [f"검사할 수 없다 — 경로가 없다: {뿌리}"]
    대상 = [뿌리] if 뿌리.is_file() else sorted(p for p in 뿌리.rglob("*") if p.is_file())
    금칙어_정규화 = [unicodedata.normalize("NFC", 말) for 말 in forbidden]
    문제: list[str] = []

    for 경로 in 대상:
        이름 = 경로.name if 뿌리.is_file() else str(경로.relative_to(뿌리))
        정규화_이름 = unicodedata.normalize("NFC", 이름)
        문제 += [f"금칙어 {말!r}(경로): {이름}" for 말 in 금칙어_정규화 if 말 in 정규화_이름]

        if zipfile.is_zipfile(경로):
            with zipfile.ZipFile(경로) as 꾸러미:
                for 멤버 in sorted(꾸러미.namelist()):
                    위치 = f"{이름}!{멤버}"
                    정규화_멤버 = unicodedata.normalize("NFC", 멤버)
                    문제 += [
                        f"금칙어 {말!r}(경로): {위치}" for 말 in 금칙어_정규화 if 말 in 정규화_멤버
                    ]

                    if 멤버 == _미리보기:
                        # 쪽 스냅샷은 금칙어가 **그림으로** 들어 있을 수 있다. 글자 검사로는
                        # 못 보므로 크기로 잡는다 — extract_skeleton 이 심는 빈 미리보기는
                        # 69바이트다.
                        if len(꾸러미.read(멤버)) > _미리보기_상한:
                            문제.append(
                                f"미리보기 그림이 비어 있지 않다: {이름} — "
                                "쪽 스냅샷은 글자 검사가 못 보는 유출 통로다"
                            )
                        continue
                    if 멤버.startswith("BinData/"):
                        문제.append(f"검사하지 못한 파일(그림): {위치}")
                        continue

                    문제 += _금칙어_본문_문제(_글자_읽기(꾸러미.read(멤버)), 위치, 금칙어_정규화)
        else:
            문제 += _금칙어_본문_문제(_글자_읽기(경로.read_bytes()), 이름, 금칙어_정규화)

    return 문제


def preview_stats(path: Path) -> dict[str, object]:
    """M-6 — 레이아웃 미리보기 계수(실한컴이 아니라 headless 레이아웃).

    `pages_estimate` 는 **근사값**이다 — 실측으로, 키워드면 문서를 프리뷰는 1쪽, 실한컴은
    2쪽으로 센 적이 있다. 쪽수·쪽 나눔의 권위는 M-7(실한컴, `worksheet.render.RenderResult.
    pages`)에 있다. `layout_tables`·`layout_paragraphs`는 이 헤드리스 레이아웃이 쪽마다 센
    표·문단 수의 합이다 — `ComposeReport.tables`·`.paragraphs`(문서 모델 객체 수)와 이름이
    비슷해도 다른 것을 센다: 이쪽은 레이아웃 결과(쪽에 실제로 배치된 표·문단), 저쪽은 문서
    모델 자체의 객체 수다.

    docx 는 이 헤드리스 레이아웃이 없다 — `pages_estimate`가 None인 근사 없음 그 자체를
    낸다(실물 렌더로 본다).
    """
    if _docx_인가(path):
        return {
            "pages_estimate": None,
            "note": "docx 는 근사 레이아웃이 없다 — 실물 렌더(LibreOffice·Word·구글 문서)로 본다",
        }
    preview = render_layout_preview(Path(path))
    첫쪽 = preview.pages[0]
    return {
        "pages_estimate": len(preview.pages),
        "width_mm": round(첫쪽.width_mm, 2),
        "height_mm": round(첫쪽.height_mm, 2),
        "layout_tables": sum(p.table_count for p in preview.pages),
        "layout_paragraphs": sum(p.paragraph_count for p in preview.pages),
        "warnings": list(preview.warnings),
    }
