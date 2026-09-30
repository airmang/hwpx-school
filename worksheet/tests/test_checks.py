import dataclasses
import json
import shutil
import unicodedata
import zipfile
from pathlib import Path

import pytest

from worksheet.checks import (
    check_answer_labels, check_empty_slots, check_hygiene, check_markdown,
    check_package, check_slot_residue, preview_stats,
)
from worksheet.cli import main as cli_main
from worksheet.compose import compose
from worksheet.kit import load_kit
from worksheet.md import parse_sheet

기본 = """---
kit: 시험킷
title: 제목
grade: 2학년
---

## 섹션

:::답칸 label="{첫째}" lines=1
:::

:::답칸 label="{둘째}" lines=1
:::
"""


def test_킷이_모르는_블록을_잡는다(킷_루트):
    kit = load_kit(킷_루트)
    sheet = parse_sheet(기본.replace(":::답칸", ":::없는블록", 1))
    문제 = check_markdown(sheet, kit)
    assert any("없는블록" in m for m in 문제)


def test_아는_블록만_있으면_잔존_0(킷_루트):
    kit = load_kit(킷_루트)
    sheet = parse_sheet(기본.format(첫째="가", 둘째="나"))
    assert check_markdown(sheet, kit) == []


def test_구조_노드를_펜스로_쓰면_M1이_잡는다(킷_루트):
    """M-1 통과는 '조판이 펜스 이름으로 거부하지 않는다'를 뜻해야 한다."""
    kit = load_kit(킷_루트)
    md = "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n:::정의빈칸\n■ 정의\n:::\n"
    문제 = check_markdown(parse_sheet(md), kit)
    assert any("펜스로 쓸 수 없는 블록: 정의빈칸" in m for m in 문제)


def test_구조_노드도_킷이_허용하지_않으면_잡는다(킷_루트):
    """(구조 노드 포함) — 발문도 정상 렌더러가 있지만 kit.blocks 대조에서는 예외가 아니다."""
    kit = load_kit(킷_루트)
    좁은_킷 = dataclasses.replace(kit, blocks=("정의빈칸", "답칸"))
    md = "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n> 발문 하나\n"
    문제 = check_markdown(parse_sheet(md), 좁은_킷)
    assert any("킷이 허용하지 않는 블록: 발문" in m for m in 문제)


def test_킷이_허용_안_하는_비교표는_멀쩡히_만들어도_잡는다(킷_루트):
    """허용 블록 대조(kit.blocks) — blocks=['정의빈칸','답칸']인 킷에 :::비교표가 오면."""
    kit = load_kit(킷_루트)
    좁은_킷 = dataclasses.replace(kit, blocks=("정의빈칸", "답칸"))
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ':::비교표 cols="가|나" rows="다"\n:::\n'
    )
    문제 = check_markdown(parse_sheet(md), 좁은_킷)
    assert any("킷이 허용하지 않는 블록: 비교표" in m for m in 문제)


def test_fence_problems_결과가_check_markdown에도_나온다(킷_루트):
    kit = load_kit(킷_루트)
    md = '---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n:::비교표 rows="가"\n:::\n'
    문제 = check_markdown(parse_sheet(md), kit)
    assert any("비교표 블록에 cols= 가 없다" in m for m in 문제)


def test_labelWidth가_너무_넓으면_M1이_킷의_본문_폭_기준으로_잡는다(킷_루트):
    """check_markdown(M-1)은 항상 kit이 있으므로 fence_problems의 상한 검사까지 본다."""
    kit = load_kit(킷_루트)
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ":::라벨설명 labelWidth=200cm\n[1] 가\n: 나\n:::\n"
    )
    문제 = check_markdown(parse_sheet(md), kit)
    assert any("너무 넓다" in m for m in 문제)


def test_모르는_속성도_check_markdown이_잡는다(킷_루트):
    kit = load_kit(킷_루트)
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ':::답칸 label="가" labelWidth=3cm\n:::\n'
    )
    문제 = check_markdown(parse_sheet(md), kit)
    assert any("답칸 블록이 모르는 속성: labelWidth" in m for m in 문제)


def test_base_dir_없으면_그림_존재를_안_본다(킷_루트):
    kit = load_kit(킷_루트)
    md = "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n![](없는파일.png)\n"
    assert check_markdown(parse_sheet(md), kit) == []


def test_없는_그림_파일을_base_dir로_잡는다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    md = "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n![](없는파일.png)\n"
    문제 = check_markdown(parse_sheet(md), kit, base_dir=tmp_path)
    assert any("그림 파일이 없다: 없는파일.png" in m for m in 문제)


def test_PNG가_아닌_그림을_base_dir로_잡는다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    (tmp_path / "가짜.png").write_bytes(b"not a png at all")
    md = "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n![](가짜.png)\n"
    문제 = check_markdown(parse_sheet(md), kit, base_dir=tmp_path)
    assert any("PNG만 지원한다" in m and "가짜.png" in m for m in 문제)


# --- 칸 안 그림 — check_markdown(M-1)이 fence_problems에 넘기는 base_dir로 본문 그림 줄과
# 같은 세 가지(없는 파일·PNG 아님·형식 오류)를 본다. worksheet/blocks.py의 5개 블록 ×
# 6가지 칸 글자 매트릭스는 tests/test_blocks.py가 fence_problems를 직접 불러 이미
# 전수로 본다 — 여기서는 check_markdown이 그 결과를 그대로 옮기는지만 확인한다.


def test_칸_안_그림의_없는_파일을_check_markdown이_base_dir로_잡는다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ':::나란히 cols="가|나"\n![](없는파일.png)|둘째\n:::\n'
    )
    문제 = check_markdown(parse_sheet(md), kit, base_dir=tmp_path)
    assert any("그림 파일이 없다: 없는파일.png" in m for m in 문제)


def test_칸_안_그림의_PNG_아닌_파일을_check_markdown이_base_dir로_잡는다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    (tmp_path / "가짜.png").write_bytes(b"not a png at all")
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ':::나란히 cols="가|나"\n![](가짜.png)|둘째\n:::\n'
    )
    문제 = check_markdown(parse_sheet(md), kit, base_dir=tmp_path)
    assert any("PNG만 지원한다" in m and "가짜.png" in m for m in 문제)


def test_칸_안_그림_형식_오류를_check_markdown이_잡는다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ':::나란히 cols="가|나"\n![나쁜형식|둘째\n:::\n'
    )
    문제 = check_markdown(parse_sheet(md), kit, base_dir=tmp_path)
    assert any(
        "나란히 블록의 칸에 쓴 그림 줄을 읽을 수 없다" in m and "형식: ![](경로){width=8cm}" in m
        for m in 문제
    )


def test_base_dir_없으면_칸_안_그림_존재를_안_본다(킷_루트):
    """기존 호출·테스트 호환 — 형식 오류는 base_dir 없이도 본다(파일이 있어야 아는 게
    아니므로)."""
    kit = load_kit(킷_루트)
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ':::나란히 cols="가|나"\n![](없는파일.png)|둘째\n:::\n'
    )
    assert check_markdown(parse_sheet(md), kit) == []


# 엔진이 아예 모르는 이름이면 kit.blocks 대조는 의미가 없다 — 어떤 킷도 그릴 렌더러가
# 없는 이름을 "허용"할 수는 없다. 그래서 원인 하나에 문제 하나만 낸다(킷 허용 여부는
# 같이 보고하지 않는다).
def test_엔진이_모르는_이름은_킷_허용_여부를_같이_보고하지_않는다(킷_루트):
    kit = load_kit(킷_루트)
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ":::없는블록\n:::\n\n:::없는블록\n:::\n"
    )
    문제 = check_markdown(parse_sheet(md), kit)
    assert 문제 == ["엔진이 모르는 블록: 없는블록"]


def test_킷이_허용하지_않는_블록도_같은_문제는_한_번만_보고한다(킷_루트):
    """엔진은 아는 이름인데 킷이 안 허용하는 경우는 여전히 dedup만 확인한다."""
    kit = load_kit(킷_루트)
    좁은_킷 = dataclasses.replace(kit, blocks=("정의빈칸", "답칸"))
    md = (
        "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n"
        ':::비교표 cols="가|나" rows="다"\n:::\n\n:::비교표 cols="가|나" rows="다"\n:::\n'
    )
    문제 = check_markdown(parse_sheet(md), 좁은_킷)
    assert 문제.count("킷이 허용하지 않는 블록: 비교표") == 1


def test_구조_이름표에_없는_노드_타입은_TypeError로_거부한다(킷_루트):
    """_구조_이름[type(node)]의 bare KeyError 대신 읽을 수 있는 문구로 거부한다."""
    kit = load_kit(킷_루트)

    @dataclasses.dataclass(frozen=True)
    class _가짜노드:
        pass

    sheet = dataclasses.replace(
        parse_sheet(기본.format(첫째="가", 둘째="나")), nodes=(_가짜노드(),)
    )
    with pytest.raises(TypeError, match="알 수 없는 노드: _가짜노드"):
        check_markdown(sheet, kit)


def test_그림_경로가_디렉터리면_그림_파일이_없다로_잡는다(킷_루트, tmp_path):
    """.exists() 대신 .is_file()로 봐야 디렉터리 경로가 IsADirectoryError로 새지 않는다."""
    (tmp_path / "그림폴더").mkdir()
    kit = load_kit(킷_루트)
    md = "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n![](그림폴더)\n"
    문제 = check_markdown(parse_sheet(md), kit, base_dir=tmp_path)
    assert any("그림 파일이 없다: 그림폴더" in m for m in 문제)


def test_그림이_너무_짧은_PNG_조각이면_문제로_잡는다(킷_루트, tmp_path):
    """struct.error 가 트레이스백으로 새지 않고 [기계] 검사 문제로 잡힌다."""
    kit = load_kit(킷_루트)
    (tmp_path / "조각.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR")
    md = "---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n![](조각.png)\n"
    문제 = check_markdown(parse_sheet(md), kit, base_dir=tmp_path)
    assert any("PNG만 지원한다" in m and "조각.png" in m for m in 문제)


def test_중복_답칸_라벨을_잡는다():
    sheet = parse_sheet(기본.format(첫째="같은라벨", 둘째="같은라벨"))
    문제 = check_answer_labels(sheet)
    assert any("같은라벨" in m for m in 문제)
    assert check_answer_labels(parse_sheet(기본.format(첫째="가", 둘째="나"))) == []


def test_패키지_검증과_슬롯_잔존(킷_루트, tmp_path):
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="가", 둘째="나"), encoding="utf-8")
    out = tmp_path / "s.hwpx"
    compose(md, 킷_루트, out)

    assert check_package(out) == []
    assert check_slot_residue(out) == []


def test_슬롯_잔존을_잡는다(킷_루트, tmp_path):
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="《미정》", 둘째="TODO 채우기"), encoding="utf-8")
    out = tmp_path / "s.hwpx"
    compose(md, 킷_루트, out)

    문제 = check_slot_residue(out)
    assert any("《" in m for m in 문제)
    assert any("TODO" in m for m in 문제)


# --- M-3 보강 — 빈 슬롯 + residueMarkers + 전 섹션 --------------------------------------


def test_빈_슬롯_표준_킷은_넷_다_낸다():
    """슬롯이 전부 빈 kits/standard 는 4개를 다 낸다 — 그게 맞다(복사해서 채워 쓰는 씨앗)."""
    표준_킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"
    kit = load_kit(표준_킷)
    assert check_empty_slots(kit) == ["빈 슬롯: school, subject, teacher, grade"]


def test_빈_슬롯_슬롯이_다_차면_빈_리스트다(킷_루트):
    assert check_empty_slots(load_kit(킷_루트)) == []


def test_빈_슬롯_일부만_비면_그것만_처음_나온_순서로_댄다(킷_루트):
    kit = load_kit(킷_루트)
    반쯤_빈_킷 = dataclasses.replace(kit, slots={**kit.slots, "teacher": "", "grade": " "})
    assert check_empty_slots(반쯤_빈_킷) == ["빈 슬롯: teacher, grade"]


def test_grade를_주면_킷의_grade_슬롯이_비어도_빈_슬롯으로_안_센다():
    """회차(md)의 grade 가 킷의 grade 슬롯을 덮는다. 표준 킷은 넷 다 비었지만
    grade="3학년"을 주면 그 슬롯만 빠진 셋만 남는다."""
    표준_킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"
    kit = load_kit(표준_킷)
    assert check_empty_slots(kit, grade="3학년") == ["빈 슬롯: school, subject, teacher"]


def test_슬롯_잔존은_모든_section_xml을_본다(킷_루트, tmp_path):
    """M-3 은 section0.xml 고정이 아니라 Contents/section*.xml 전부를 본다."""
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="가", 둘째="나"), encoding="utf-8")
    out = tmp_path / "s.hwpx"
    compose(md, 킷_루트, out)
    assert check_slot_residue(out) == []  # 채운 뒤에는 section0에도 잔존이 없다

    with zipfile.ZipFile(out, "a") as z:
        z.writestr("Contents/section1.xml", "<hp:p>TODO 다음 섹션에만 있는 잔존</hp:p>")

    문제 = check_slot_residue(out)
    assert any("TODO" in m for m in 문제)


def test_슬롯_잔존_마커는_킷마다_바꿀_수_있다(킷_루트, tmp_path):
    """정보 교과 코드의 '# TODO'와 국어식 《책 제목》은 킷의 residueMarkers 로 갈린다."""
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="금칙표시", 둘째="나"), encoding="utf-8")
    out = tmp_path / "s.hwpx"
    compose(md, 킷_루트, out)

    assert check_slot_residue(out) == []  # 기본 마커(《》TODO TBD)엔 안 걸린다
    문제 = check_slot_residue(out, markers=("금칙표시",))
    assert any("금칙표시" in m for m in 문제)


def test_슬롯_잔존은_디코드_실패한_섹션을_문제로_낸다(킷_루트, tmp_path):
    """errors="ignore" 대신 엄격 디코드로 읽는다 — 실패하면 조용히 건너뛰지 않고 문제로 낸다."""
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="가", 둘째="나"), encoding="utf-8")
    out = tmp_path / "s.hwpx"
    compose(md, 킷_루트, out)

    with zipfile.ZipFile(out, "a") as z:
        z.writestr("Contents/section9.xml", b"\x80\x81\x82\x83")  # UTF-8이 아니다

    문제 = check_slot_residue(out)
    assert any("슬롯 검사를 하지 못했다" in m and "section9.xml" in m for m in 문제)


def test_check_서브커맨드는_빈_슬롯과_슬롯_잔존을_잇는다(킷_루트, tmp_path, capsys):
    """cli check 이 check_empty_slots(kit)·check_slot_residue(hwpx, kit.residue_markers)를
    둘 다 실제로 부르는지 각각 확인한다 — 잔존 반쪽은 킷의 residueMarkers 를 기본값이
    아닌 값으로 바꿔, cli 가 기본 마커로 되돌아가면 이 단언이 깨지게 만든다."""
    표준_킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"
    md = tmp_path / "s.md"
    md.write_text(
        '---\nkit: standard\ntitle: t\n---\n\n## 섹션\n\n:::답칸 label="가" lines=1\n:::\n',
        encoding="utf-8",
    )
    out = tmp_path / "s.hwpx"
    compose(md, 표준_킷, out)

    코드 = cli_main(["check", str(md), "--kit", str(표준_킷), "--hwpx", str(out)])
    보고 = json.loads(capsys.readouterr().out)

    assert 코드 == 1
    assert any("빈 슬롯" in m for m in 보고["문제"])

    마커_킷 = tmp_path / "마커킷"
    shutil.copytree(킷_루트, 마커_킷)  # 킷_루트는 슬롯이 이미 다 차 있다 — 빈 슬롯 쪽과 겹치지 않는다
    데이터 = json.loads((마커_킷 / "kit.json").read_text(encoding="utf-8"))
    데이터["residueMarkers"] = ["금칙표시"]
    (마커_킷 / "kit.json").write_text(
        json.dumps(데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md잔존 = tmp_path / "잔존.md"
    md잔존.write_text(
        '---\nkit: 시험킷\ntitle: t\n---\n\n## 섹션\n\n:::답칸 label="금칙표시" lines=1\n:::\n',
        encoding="utf-8",
    )
    out잔존 = tmp_path / "잔존.hwpx"
    compose(md잔존, 마커_킷, out잔존)

    코드 = cli_main(["check", str(md잔존), "--kit", str(마커_킷), "--hwpx", str(out잔존)])
    보고 = json.loads(capsys.readouterr().out)

    assert 코드 == 1
    assert any("금칙표시" in m and "슬롯 잔존" in m for m in 보고["문제"])


def test_위생은_없는_경로에서_fail_open이_아니라_문제를_낸다(tmp_path):
    """경로가 아예 없으면 rglob이 빈 리스트를 내, 그대로 두면 "금칙어 잔존 0"으로 읽힌다
    — fail open이다. 오타 난 --dest가 그 자리다."""
    없는_경로 = tmp_path / "없는디렉터리"
    assert not 없는_경로.exists()
    문제 = check_hygiene(없는_경로, ["금칙고"])
    assert any("경로가 없다" in m for m in 문제)


def test_배포_위생은_금칙어를_잡는다(킷_루트):
    문제 = check_hygiene(킷_루트, ["시험고", "김교사"])
    assert 문제, "시험킷에는 합성 금칙어가 있어야 한다(슬롯이 채워져 있으므로)"


def test_배포_위생은_파일_하나도_검사한다(tmp_path):
    """단일 파일을 디렉터리처럼 훑으면 조용히 통과한다 — 거짓 통과가 검사 없음보다 나쁘다."""
    파일 = tmp_path / "SKILL.md"
    파일.write_text("시험고등학교 김교사T 양식", encoding="utf-8")

    문제 = check_hygiene(파일, ["시험고", "김교사"])
    assert len(문제) == 2
    assert all("SKILL.md" in m for m in 문제)
    assert check_hygiene(파일, ["없는말"]) == []


def test_미리보기_그림이_남은_hwpx를_잡는다(원본_hwpx, 킷_루트):
    """쪽 스냅샷은 글자 검사가 못 보는 유출 통로다 — 크기로 잡는다."""
    assert any("미리보기 그림" in m for m in check_hygiene(원본_hwpx, []))
    assert not any("미리보기 그림" in m for m in check_hygiene(킷_루트 / "skeleton.hwpx", []))


# --- M-5 check_hygiene — 전 부품·NFC 정규화·fail closed ---------------------------------
# 합성 금칙어로만 검사한다("금칙고"·"김금칙") — 실제 학교·교사 이름은 tests_local 몫이다.

_표준_스켈레톤 = Path(__file__).resolve().parents[1] / "kits" / "standard" / "skeleton.hwpx"


def _hwpx_변형(원본: Path, dest: Path, 바꿀_멤버: dict[str, bytes]) -> Path:
    """원본 hwpx를 복사하되 지정한 멤버만 새 내용으로 덮어쓰거나 새로 추가한다."""
    with zipfile.ZipFile(원본) as src, zipfile.ZipFile(dest, "w") as out:
        for 이름 in src.namelist():
            if 이름 not in 바꿀_멤버:
                out.writestr(이름, src.read(이름))
        for 이름, 데이터 in 바꿀_멤버.items():
            out.writestr(이름, 데이터)
    return dest


def test_위생은_PrvText에만_있는_금칙어를_잡는다(tmp_path):
    사본 = _hwpx_변형(
        _표준_스켈레톤, tmp_path / "a.hwpx", {"Preview/PrvText.txt": "금칙고 텍스트".encode()}
    )
    문제 = check_hygiene(사본, ["금칙고"])
    assert any("금칙고" in m and "Preview/PrvText.txt" in m for m in 문제)


def test_위생은_header_xml에만_있는_금칙어를_잡는다(tmp_path):
    with zipfile.ZipFile(_표준_스켈레톤) as z:
        원본_헤더 = z.read("Contents/header.xml")
    사본 = _hwpx_변형(
        _표준_스켈레톤, tmp_path / "b.hwpx",
        {"Contents/header.xml": 원본_헤더 + "김금칙".encode()},
    )
    문제 = check_hygiene(사본, ["김금칙"])
    assert any("김금칙" in m and "Contents/header.xml" in m for m in 문제)


def test_위생은_section1_xml에만_있는_금칙어를_잡는다(tmp_path):
    """section0.xml 고정이 아니라 hwpx 안 모든 부품을 본다."""
    사본 = _hwpx_변형(
        _표준_스켈레톤, tmp_path / "c.hwpx", {"Contents/section1.xml": "금칙고".encode()}
    )
    문제 = check_hygiene(사본, ["금칙고"])
    assert any("금칙고" in m and "Contents/section1.xml" in m for m in 문제)


def test_위생은_settings_xml에만_있는_금칙어를_잡는다(tmp_path):
    """header.xml·section1.xml과 같은 '그 밖의 멤버' 경로 — 특정 파일 이름을 하드코딩하지
    않는다는 것을 한 번 더 확인한다(옛 코드는 section0.xml·content.hpf 둘만 하드코딩했다)."""
    with zipfile.ZipFile(_표준_스켈레톤) as z:
        원본_설정 = z.read("settings.xml")
    사본 = _hwpx_변형(
        _표준_스켈레톤, tmp_path / "e.hwpx", {"settings.xml": 원본_설정 + "금칙고".encode()}
    )
    문제 = check_hygiene(사본, ["금칙고"])
    assert any("금칙고" in m and "settings.xml" in m for m in 문제)


def test_위생은_디렉터리_이름의_금칙어를_상대경로_전체에서_본다(tmp_path):
    (tmp_path / "금칙고폴더").mkdir()
    (tmp_path / "금칙고폴더" / "깨끗한파일.md").write_text("아무 내용도 없다", encoding="utf-8")

    문제 = check_hygiene(tmp_path, ["금칙고"])
    assert any("금칙고" in m and "금칙고폴더" in m for m in 문제)


def test_위생은_NFD로_저장된_본문도_NFC로_맞춰_잡는다(tmp_path):
    """맥에서 붙여넣은 글은 NFD로 들어온다 — 정규화 없이 그냥 in 검색하면 못 찾는다."""
    파일 = tmp_path / "nfd.md"
    파일.write_bytes(unicodedata.normalize("NFD", "금칙고 텍스트").encode("utf-8"))

    문제 = check_hygiene(파일, ["금칙고"])  # forbidden 은 평범한(NFC) 문자열로 준다
    assert any("금칙고" in m for m in 문제)


def test_위생은_UTF16_BOM_텍스트도_읽는다(tmp_path):
    파일 = tmp_path / "u16.txt"
    파일.write_bytes("금칙고 텍스트".encode("utf-16"))  # 기본이 BOM을 붙인다

    문제 = check_hygiene(파일, ["금칙고"])
    assert any("금칙고" in m for m in 문제)


def test_위생은_못_읽는_바이너리_파일을_조용히_통과시키지_않는다(tmp_path):
    파일 = tmp_path / "이상한.bin"
    파일.write_bytes(b"\x80\x81\x82\x83\x84")  # UTF-8도 아니고 BOM도 없어 UTF-16도 아니다

    문제 = check_hygiene(파일, [])
    assert 문제 == ["검사하지 못한 파일: 이상한.bin"]


def test_위생은_BinData_멤버를_항상_그림으로_보고한다(tmp_path):
    """그림 속 글자는 기계가 못 읽는다 — 통과가 아니라 문제다(forbidden이 비어도 낸다)."""
    사본 = _hwpx_변형(
        _표준_스켈레톤, tmp_path / "d.hwpx", {"BinData/image1.png": b"\x89PNG\r\n\x1a\n\x00\x00"}
    )
    문제 = check_hygiene(사본, [])
    assert any("검사하지 못한 파일(그림): " in m and "BinData/image1.png" in m for m in 문제)


def test_위생은_깨끗한_표준_킷에는_빈_리스트다():
    표준_킷_루트 = Path(__file__).resolve().parents[1] / "kits" / "standard"
    assert check_hygiene(표준_킷_루트, ["금칙고", "김금칙"]) == []


def test_docx_도_패키지_검사와_슬롯_잔존_검사를_받는다(킷_루트, tmp_path):
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="《미정》", 둘째="TODO 채우기"), encoding="utf-8")
    out = tmp_path / "s.docx"
    compose(md, 킷_루트, out)
    assert check_package(out) == []
    문제 = check_slot_residue(out)
    assert any("《" in m for m in 문제) and any("TODO" in m for m in 문제)


def test_깨진_docx_는_패키지_검사에_걸린다(tmp_path):
    나쁜 = tmp_path / "x.docx"
    나쁜.write_bytes(b"not a zip")
    assert check_package(나쁜) and check_package(나쁜)[0].startswith("docx 를 열 수 없다")


def test_docx_슬롯_잔존은_런_경계에서_쪼개진_마커도_잡는다(킷_루트, tmp_path):
    """check_slot_residue의 docx 분기는 파트별로 `<w:t>` 글자만 이어 붙인 뒤 찾는다 —
    "TODO"가 런 경계에서 "TO"·"DO" 두 런으로 쪼개져도(현재 DocxWriter는 이렇게 쓰지
    않지만) 놓치지 않아야 한다. 원문 그대로(태그 포함) 찾으면 이 사례를 놓친다."""
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="가", 둘째="나"), encoding="utf-8")
    out = tmp_path / "s.docx"
    compose(md, 킷_루트, out)
    assert check_slot_residue(out) == []  # 손대기 전에는 잔존이 없다

    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    쪼개짐 = xml.replace(
        "</w:body>",
        "<w:p><w:r><w:t>TO</w:t></w:r><w:r><w:t>DO</w:t></w:r></w:p></w:body>",
        1,
    )
    assert 쪼개짐 != xml, "치환 대상(</w:body>)이 실제로 있어야 이 테스트가 뭘 확인하는지 보장된다"

    쪼개진_out = _hwpx_변형(out, tmp_path / "쪼개짐.docx", {"word/document.xml": 쪼개짐.encode("utf-8")})
    문제 = check_slot_residue(쪼개진_out)
    assert any("TODO" in m for m in 문제)



def test_docx_슬롯_잔존은_문단을_건너_이어_붙이지_않는다(킷_루트, tmp_path):
    """한 문단(칸) 끝의 "TO"와 다음 문단 첫머리의 "DO"는 마커가 아니다 — 문단마다 끊어 본다."""
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="가", 둘째="나"), encoding="utf-8")
    out = tmp_path / "s.docx"
    compose(md, 킷_루트, out)
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    두_문단 = xml.replace(
        "</w:body>",
        "<w:p><w:r><w:t>STO</w:t></w:r></w:p><w:p><w:r><w:t>DOG</w:t></w:r></w:p></w:body>",
        1,
    )
    assert 두_문단 != xml
    변형 = _hwpx_변형(out, tmp_path / "두문단.docx", {"word/document.xml": 두_문단.encode("utf-8")})
    assert check_slot_residue(변형) == []

def test_미리보기_통계를_낸다(킷_루트, tmp_path):
    md = tmp_path / "s.md"
    md.write_text(기본.format(첫째="가", 둘째="나"), encoding="utf-8")
    out = tmp_path / "s.hwpx"
    compose(md, 킷_루트, out)

    통계 = preview_stats(out)
    assert 통계["pages_estimate"] >= 1
    assert 209 < 통계["width_mm"] < 211
    assert 296 < 통계["height_mm"] < 298
    assert 통계["layout_tables"] >= 3
