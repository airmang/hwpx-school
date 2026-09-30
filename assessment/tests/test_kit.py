import json
import shutil

import pytest

from assessment.kit import load_kit, validate_font_map


def test_킷을_읽는다(킷_루트):
    k = load_kit(킷_루트)
    assert k.name == "standard"
    assert k.border_fill["underline"] == 7
    assert k.char_pr["answer_label"] == 12
    assert "answerLinePadUnit" not in k.furniture
    assert k.border_fill["none"] == 4 and k.furniture["widths"]["answerGap"] > 0
    assert k.char_pr["hint"] == 13
    assert k.skeleton.exists()
    assert k.para_pr["caption_left"] == 21  # 왼쪽 정렬 캡션 — 학번 줄과 같은 paraPr


def test_caption_left이_없으면_거부(킷_루트, tmp_path):
    def 고치기(d):
        del d["styles"]["paraPr"]["caption_left"]
    with pytest.raises(ValueError, match=r"필수 항목이 없다: .*styles\.paraPr\.caption_left"):
        load_kit(_변형(킷_루트, tmp_path, 고치기))


def _변형(킷_루트, tmp_path, 고치기):
    root = tmp_path / "킷"
    shutil.copytree(킷_루트, root)
    데이터 = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    고치기(데이터)
    (root / "kit.json").write_text(json.dumps(데이터, ensure_ascii=False), encoding="utf-8")
    return root


def test_필수_키가_빠지면_모아서_거부(킷_루트, tmp_path):
    def 고치기(d):
        del d["styles"]["charPr"]["hint"]
        del d["furniture"]["idLine"]
    with pytest.raises(ValueError, match=r"필수 항목이 없다: .*styles\.charPr\.hint.*furniture\.idLine"):
        load_kit(_변형(킷_루트, tmp_path, 고치기))


def test_스켈레톤에_없는_id_는_거부(킷_루트, tmp_path):
    def 고치기(d):
        d["styles"]["borderFill"]["box"] = 9999
    with pytest.raises(ValueError, match=r"borderFill\.box=9999 가 스켈레톤 header 에 없다"):
        load_kit(_변형(킷_루트, tmp_path, 고치기))


def test_모르는_최상위_키는_거부(킷_루트, tmp_path):
    with pytest.raises(ValueError, match=r"kit\.json 에 모르는 항목: 오타"):
        load_kit(_변형(킷_루트, tmp_path, lambda d: d.update({"오타": 1})))


# --- fontMap — 선택 최상위 키, 값은 문자열→문자열 사전이어야 한다 ------------------------


def test_fontMap이_있어도_허용한다(킷_루트, tmp_path):
    def 고치기(d):
        d["fontMap"] = {"가상장식체": "함초롬돋움"}
    k = load_kit(_변형(킷_루트, tmp_path, 고치기))
    assert k.name == "standard"


def test_fontMap이_dict가_아니면_거부(킷_루트, tmp_path):
    with pytest.raises(ValueError, match=r"fontMap 은.*꼴이어야 한다"):
        load_kit(_변형(킷_루트, tmp_path, lambda d: d.update({"fontMap": "문자열"})))


def test_fontMap_값이_문자열이_아니면_거부(킷_루트, tmp_path):
    def 고치기(d):
        d["fontMap"] = {"가상장식체": 1}
    with pytest.raises(ValueError, match=r"fontMap 은.*꼴이어야 한다"):
        load_kit(_변형(킷_루트, tmp_path, 고치기))


def test_fontMap_키가_문자열이_아니면_거부():
    with pytest.raises(ValueError, match=r"fontMap 은.*꼴이어야 한다"):
        validate_font_map({1: "함초롬돋움"})


def test_fontMap_값이_빈_문자열이면_거부():
    with pytest.raises(ValueError, match=r"fontMap 은.*꼴이어야 한다"):
        validate_font_map({"가상장식체": ""})


def test_답칸_틈이_칸_안_여백보다_좁으면_거부(킷_루트, tmp_path):
    """틈 칸이 안 여백(좌+우)보다 좁으면 한컴이 칸을 넓혀 표가 단 밖으로 삐져나간다(실렌더로 확인)."""
    def 고치기(d):
        d["furniture"]["widths"]["answerGap"] = d["furniture"]["cellInnerMargin"]
    with pytest.raises(ValueError, match=r"answerGap"):
        load_kit(_변형(킷_루트, tmp_path, 고치기))


@pytest.mark.parametrize("키", ["answerGap", "cellInnerMargin"])
def test_답칸_틈_값이_수가_아니면_한국어로_거부(킷_루트, tmp_path, 키):
    def 고치기(d):
        if 키 == "answerGap":
            d["furniture"]["widths"]["answerGap"] = "넓게"
        else:
            d["furniture"]["cellInnerMargin"] = "1020"
    with pytest.raises(ValueError, match=r"정수여야 한다"):
        load_kit(_변형(킷_루트, tmp_path, 고치기))
