from pathlib import Path

from hwpx.document import HwpxDocument

from _kits import kit_dir
from exam_kit.kit import load_kit, sha256, style_ids, verify_kit

킷_디렉터리 = kit_dir()


def test_kit_json_로드():
    kit = load_kit(킷_디렉터리)
    assert kit.name == 킷_디렉터리.name  # 킷 이름 = 킷 폴더 이름
    assert kit.page["width"] == 72852 and kit.page["height"] == 103180
    assert kit.columns == {"count": 2, "gap": 1420, "width": 30898, "body_table_width": 30088}
    assert len(kit.slots) == 20 and kit.slots["과목"] == "1813016033" and kit.slots["총쪽수"] == "1813016051"
    assert set(kit.styles) == {"normal", "number", "choice1", "choice2", "choice3", "choice5", "box_guide", "box"}
    assert {k: v for k, v in kit.tailbox.items() if k != "note"} == {
        "vertRelTo": "PAPER", "horzRelTo": "PAPER", "horzOffset": 37136, "vertOffset": 85400,
        "width": 30888, "height": 8974, "outMargin": 284, "room": 980,  # room = 줄 아래끝 여유(렌더 실측, Task 15b)
        "match_text": "저작권"}
    assert kit.slots_removed == ["논술형_문항수", "논술형_만점"]
    assert kit.notice_box_height == 10668
    assert len(kit.slot_ids()) == 18
    assert kit.placeholders["요일"] == "요일" and kit.placeholders["머리_학기"] is None and len(kit.placeholders) == 20


def test_킷_버전은_README_이력_맨_위와_같다():
    import json
    import re

    version = json.loads((킷_디렉터리 / "kit.json").read_text(encoding="utf-8"))["version"]
    이력 = (킷_디렉터리 / "README.md").read_text(encoding="utf-8").split("## 개정 이력", 1)[1]
    assert version == re.search(r"^- (\d+\.\d+\.\d+) ", 이력, re.M).group(1)


def test_양식_sha가_kit과_같다(양식_hwpx):
    kit = load_kit(킷_디렉터리)
    assert sha256(양식_hwpx) == kit.form_sha256


def test_style_ids_양식(양식_hwpx):
    ids = style_ids(HwpxDocument.open(str(양식_hwpx)))
    assert ids["문항자동번호넣기"] == ("1", "24", "25")
    assert ids["박스안내용"] == ("7", "25", "8")


def test_verify_kit_양식(양식_hwpx):
    kit = load_kit(킷_디렉터리)
    assert verify_kit(kit, form_path=양식_hwpx) == []


# ---- 킷 스키마 2(범용화 R1) ------------------------------------------------------

def _킷_사본(tmp_path, *, habits=True):
    import shutil

    d = tmp_path / "킷"
    shutil.copytree(킷_디렉터리, d)
    if not habits:
        (d / "habits.json").unlink()
    return d


def test_습관값은_habits_json에서_읽고_출처를_남긴다():
    kit = load_kit(킷_디렉터리)
    assert kit.habits_source == "킷(habits.json)"
    assert (kit.question_gap, kit.question_gap_min, kit.gap_extra_max) == (1760, 880, None)
    assert (kit.letter_spacing_min, kit.letter_spacing_tail, kit.letter_spacing_safety) == (-17, 0.25, 1)
    assert kit.letter_spacing_role_min == {"발문": -17, "기타": -7}
    assert (kit.word_pull_min, kit.word_pull_gap) == (-4, 2.0)
    assert kit.code_font == "굴림체" and kit.box_min_height == 6336


def test_habits_json이_없으면_엔진_기본을_쓰고_출처에_적는다(tmp_path):
    import dataclasses

    기본 = load_kit(_킷_사본(tmp_path, habits=False))
    assert 기본.habits_source.startswith("엔진 기본 — ")
    # 엔진 기본값 = 첫 등록 학교 1학기 실측(이 누름틀 양식 킷의 습관값) — 출처 표시만 다르고 값은 같다
    assert dataclasses.replace(기본, root=킷_디렉터리, habits_source="") == dataclasses.replace(
        load_kit(킷_디렉터리), habits_source="")


def test_빠진_키와_모르는_키는_파일과_키를_적어_멈춘다(tmp_path):
    import json

    import pytest

    d = _킷_사본(tmp_path)
    k = json.loads((d / "kit.json").read_text(encoding="utf-8"))
    del k["code_font"]
    k["오타_키"] = 1
    (d / "kit.json").write_text(json.dumps(k, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=r"kit\.json.*빠진 키 \['code_font'\].*모르는 키 \['오타_키'\]"):
        load_kit(d)
    d2 = _킷_사본(tmp_path / "b")
    h = json.loads((d2 / "habits.json").read_text(encoding="utf-8"))
    del h["word_pull_gap"]
    (d2 / "habits.json").write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=r"habits\.json.*빠진 키 \['word_pull_gap'\]"):
        load_kit(d2)


def test_schema가_다르면_멈춘다(tmp_path):
    import json

    import pytest

    d = _킷_사본(tmp_path)
    k = json.loads((d / "kit.json").read_text(encoding="utf-8"))
    k["schema"] = 1
    (d / "kit.json").write_text(json.dumps(k, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="schema 1"):
        load_kit(d)


def test_양식에서_찾고_지우는_문구는_킷에_있다():  # 범용화 R2a — 코드에는 학교 문구가 없다
    import re

    kit = load_kit(킷_디렉터리)
    assert kit.admin["paragraph"] == 0 and kit.admin["notice_table_with"] == "인쇄된 문항지"
    assert kit.trim == {"rule": "first_page_break"} and kit.sample_region == "role_styles" and kit.leftover_prefix == "(원안지 마지막 장"
    assert len(kit.guidance_text) == 8 and len(kit.sample_text) == 5
    assert kit.forbidden_text == kit.guidance_text + kit.sample_text
    코드 = "".join(p.read_text(encoding="utf-8") for p in (Path(__file__).resolve().parents[1] / "exam_kit").glob("*.py"))
    코드 = re.sub(r"#.*|\"\"\"[\s\S]*?\"\"\"", "", 코드)  # 주석·docstring 밖에서만 본다
    for w in (*kit.forbidden_text, kit.admin["notice_table_with"], kit.tailbox["match_text"], kit.leftover_prefix,
              kit.boxes["보기"]["title"], kit.boxes["보기"]["title_match"], kit.teacher_cell["placeholder"]):
        assert repr(w) not in 코드 and f'"{w}"' not in 코드, w
