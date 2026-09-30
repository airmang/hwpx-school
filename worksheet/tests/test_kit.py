import dataclasses
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from worksheet.kit import REQUIRED_KEYS, Kit, effective_slots, load_kit, seed_kit_path, verify_kit

from _helpers import _금칙장식체_심기


@pytest.fixture
def 임시킷(킷_루트, tmp_path):
    """`킷_루트`(kits/standard 복사 + 슬롯 채움)를 다시 복사한 쓰기용 사본 — 개별 테스트가
    kit.json을 자유롭게 망가뜨려도 다른 테스트에 안 번진다(`킷_루트`는 세션 스코프다)."""
    root = tmp_path / "테스트킷"
    shutil.copytree(킷_루트, root)
    데이터 = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    데이터["kit"] = "테스트킷"
    (root / "kit.json").write_text(
        json.dumps(데이터, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return root


def _데이터(root: Path) -> dict:
    return json.loads((root / "kit.json").read_text(encoding="utf-8"))


def _쓰기(root: Path, 데이터: dict) -> None:
    (root / "kit.json").write_text(json.dumps(데이터, ensure_ascii=False, indent=2), encoding="utf-8")


def test_킷을_읽는다(임시킷):
    kit = load_kit(임시킷)
    assert isinstance(kit, Kit)
    assert kit.name == "테스트킷"
    assert kit.slots["school"] == "시험고등학교"
    번호 = _데이터(임시킷)["styles"]
    assert kit.border_fill["shade"] == 번호["borderFill"]["shade"]
    assert kit.char_pr["headline"] == 번호["charPr"]["headline"]
    assert kit.para_pr["prompt"] == 번호["paraPr"]["prompt"]
    assert kit.body_width == 50460
    assert "비교표" in kit.blocks
    assert kit.skeleton_path == 임시킷 / "skeleton.hwpx"


def test_스타일_ID가_스켈레톤에_실재하면_문제없음(임시킷):
    assert verify_kit(load_kit(임시킷)) == []


def test_없는_스타일_ID는_잡아낸다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["styles"]["borderFill"]["shade"] = 99
    데이터["styles"]["charPr"]["headline"] = 777
    _쓰기(임시킷, 데이터)

    문제 = verify_kit(load_kit(임시킷))
    assert any("borderFill.shade=99" in m for m in 문제)
    assert any("charPr.headline=777" in m for m in 문제)


def test_엔진이_모르는_블록_이름을_잡는다(임시킷):
    kit = load_kit(임시킷)
    이상한_킷 = dataclasses.replace(kit, blocks=(*kit.blocks, "없는블록이름"))
    문제 = verify_kit(이상한_킷)
    assert any("엔진이 모르는 블록 이름: 없는블록이름" in m for m in 문제)


def test_스켈레톤이_없으면_거부한다(임시킷):
    (임시킷 / "skeleton.hwpx").unlink()
    with pytest.raises(FileNotFoundError):
        load_kit(임시킷)


# --- load_kit 이 킷 스키마를 검사한다 -----------------------------------------------------
# 스키마 규칙마다 테스트 1개. `임시킷`은 kits/standard(=킷_루트)의 완전한 사본이라,
# 각 테스트는 딱 하나의 값만 망가뜨려 그 검사 하나만 걸리게 한다.


def test_kit_json이_없으면_거부한다(임시킷):
    (임시킷 / "kit.json").unlink()
    with pytest.raises(ValueError, match="kit.json 을 읽을 수 없다"):
        load_kit(임시킷)


def test_kit_json이_JSON이_아니면_거부한다(임시킷):
    (임시킷 / "kit.json").write_text("이것은 JSON이 아니다", encoding="utf-8")
    with pytest.raises(ValueError, match="kit.json 을 읽을 수 없다"):
        load_kit(임시킷)


def test_필수_키가_없으면_전부_모아_점경로_정렬로_한번에_잡는다(임시킷):
    데이터 = _데이터(임시킷)
    del 데이터["furniture"]["band"]["nameLines"]
    del 데이터["furniture"]["labelWidth"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=r"kit\.json 에 필수 키가 없다: furniture\.band\.nameLines, furniture\.labelWidth",
    ):
        load_kit(임시킷)


def test_새_필수_키가_없으면_잡는다(임시킷):
    """셀 서식 넷·행 높이·출처 문구 여섯 자리 — 하나라도 빠지면 REQUIRED_KEYS가 잡는다."""
    데이터 = _데이터(임시킷)
    del 데이터["styles"]["charPr"]["heading_ref"]
    del 데이터["styles"]["paraPr"]["label"]
    del 데이터["furniture"]["rowHeight"]["cell"]
    del 데이터["furniture"]["heading"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=(
            r"kit\.json 에 필수 키가 없다: furniture\.heading\.textbookFormat, "
            r"furniture\.rowHeight\.cell, styles\.charPr\.heading_ref, styles\.paraPr\.label"
        ),
    ):
        load_kit(임시킷)


def test_charPr_prompt이_없으면_잡는다(임시킷):
    """kit.json에 값은 있지만 REQUIRED_KEYS 등록이 빠지면, 이 키가 없는 kit.json도
    load_kit()·verify_kit() 둘 다 조용히 통과하고, 발문을 실제로 그릴 때(_발문가
    kit.char_pr["prompt"]를 읽는 자리)에야 순수 KeyError로 터진다 — 스키마가 막으려던
    바로 그 실패 유형이 새 키 하나에서 다시 열리는 사례다."""
    데이터 = _데이터(임시킷)
    del 데이터["styles"]["charPr"]["prompt"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError, match=r"kit\.json 에 필수 키가 없다: styles\.charPr\.prompt",
    ):
        load_kit(임시킷)


# --- 정적 감사(부분적) — 소스에 리터럴로 박힌 킷 스타일 키가 REQUIRED_KEYS에 선언돼 있다 -----
# charPr.prompt처럼 "kit.json에 값은 넣었지만 REQUIRED_KEYS 등록을 빠뜨리는" 실패를 잡는다.
# worksheet/*.py 소스에서 `kit.char_pr["x"]`/`kit.para_pr["x"]`/`kit.border_fill["x"]` 꼴로
# **문자열 리터럴**로 읽는 자리만 정규식으로 긁어 REQUIRED_KEYS와 대조한다.
#
# 이 감사가 구조적으로 못 보는 것 — 실측으로 확인했다(정규식을 실제로 돌려 봄): ① 대괄호
# 안이 리터럴이 아니라 변수인 동적 호출. `blocks.py`의 `_셀_역할` 표가 이 경로다(예:
# `kit.border_fill[보더_키]`) — 그 결과 `styles.borderFill.answer`·`styles.charPr.cell`·
# `styles.charPr.label`·`styles.paraPr.label` 네 키는 이 정규식으로 **하나도** 못 찾는다
# (다른 리터럴 호출로도 안 읽혀서 대신 잡아 줄 자리가 없다 — `.shade`·`.plain`·`.grid`처럼
# `add_band`나 강조박스의 리터럴 호출이 또 있는 키들과는 다르다). ② `kit.furniture[...]`
# 읽기 — 애초에 char_pr/para_pr/border_fill만 본다. ③ 지역 별칭을 거친 접근(`설정 =
# kit.furniture["band"]` 다음 `설정["cols"]`) — furniture를 본다 해도 별칭까지는 못 좇는다.
# 이 세 사각을 실제로 메우는 건 `tests/test_kit_swap.py`의
# `test_런타임_기록으로_REQUIRED_KEYS_커버리지를_양방향으로_본다`다 — 실제로 조판을 돌려
# `Kit`의 값 딕셔너리를 읽힌 키를 기록하는 dict로 감싸는 방식이라, 정적 스캔이 못 보는
# 동적 호출·별칭·furniture까지 전부 잡고, 선언만 되고 한 번도 안 읽히는 죽은 키도 본다
# (이 테스트는 그 반대쪽, "읽은 키가 선언 안에 있는가"만 본다).
#
# ④ 계획 데이터로 넘어가는 역할·스타일 키(예: `border="grid"`, `ParagraphPlan(para="prompt",
# char="prompt")`) — 계획자는 키 이름만 적고 백엔드가 `kit.border_fill[plan.border]`처럼
# 변수로 읽으므로 이 정규식에 안 걸린다. 이것도 위 런타임 기록 테스트(tests/test_kit_swap.py)가
# 지킨다. 그리기 코드가 `worksheet/backends/` 아래에 있으므로 하위 폴더까지 훑는다.
_킷_스타일_그룹 = {"char_pr": "charPr", "para_pr": "paraPr", "border_fill": "borderFill"}


def test_엔진이_읽는_킷_스타일_키는_모두_REQUIRED_KEYS에_선언돼_있다():
    """소스의 리터럴 키만 보는 부분적 감사다 — 위 주석의 사각(동적 호출·furniture·별칭)은
    tests/test_kit_swap.py의 런타임 기록 테스트가 메운다."""
    루트 = Path(__file__).resolve().parents[1] / "worksheet"
    패턴 = re.compile(r'kit\.(char_pr|para_pr|border_fill)\["(\w+)"\]')
    읽는_키: set[tuple[str, str]] = set()
    for 파일 in 루트.rglob("*.py"):
        for 그룹, 키 in 패턴.findall(파일.read_text(encoding="utf-8")):
            읽는_키.add((_킷_스타일_그룹[그룹], 키))

    assert 읽는_키, "정규식이 소스에서 하나도 못 찾았다 — 패턴이 코드와 어긋났을 수 있다"

    선언됨 = set(REQUIRED_KEYS)
    빠짐 = sorted(
        f"styles.{그룹}.{키}" for 그룹, 키 in 읽는_키 if f"styles.{그룹}.{키}" not in 선언됨
    )
    assert 빠짐 == [], f"엔진이 읽지만 REQUIRED_KEYS에 선언되지 않은 스타일 키: {빠짐}"


def test_band_cols가_4칸이_아니면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["band"]["cols"] = [5929, 7390, 17295, 5685, 5685]
    _쓰기(임시킷, 데이터)

    with pytest.raises(ValueError, match=r"furniture\.band\.cols 는 4칸이어야 한다: 5칸"):
        load_kit(임시킷)


def test_band_cols_합이_width와_다르면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["band"]["cols"] = [1, 2, 3, 4]  # 길이는 4, 합은 width(41984)와 다르다
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError, match=r"furniture\.band\.cols 합\(10\)이 width\(41984\)와 다르다"
    ):
        load_kit(임시킷)


def test_nameLines가_모르는_슬롯을_쓰면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["band"]["nameLines"] = ["{homeroom}"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError, match=r"furniture\.band\.nameLines 가 모르는 슬롯을 쓴다: homeroom"
    ):
        load_kit(임시킷)


def test_자리표시자_문법_오류를_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["band"]["teacherLines"] = ["{ }"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=r"furniture\.band\.teacherLines 자리표시자를 읽을 수 없다: '\{ \}'",
    ):
        load_kit(임시킷)


def test_짝_없는_중괄호도_자리표시자_오류로_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["band"]["teacherLines"] = ["{school"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=r"furniture\.band\.teacherLines 자리표시자를 읽을 수 없다: '\{school'",
    ):
        load_kit(임시킷)


def test_curSz가_정수_2개가_아니면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["circle"]["curSz"] = [1713]
    _쓰기(임시킷, 데이터)

    with pytest.raises(ValueError, match=r"furniture\.circle\.curSz 는 \[가로, 세로\] 여야 한다"):
        load_kit(임시킷)


def test_labelWidth가_bodyWidth_이상이면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["labelWidth"] = 데이터["bodyWidth"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=r"furniture\.labelWidth\(50460\)가 bodyWidth\(50460\)보다 작아야 한다",
    ):
        load_kit(임시킷)


# --- kit.json 값의 형태 오류는 순수 TypeError로 샐 수 있다 -----------------------------------
# band.cols를 정수 하나로, labelWidth/bodyWidth를 문자열로 적으면 len()·비교 연산이 바로
# TypeError를 던진다 — CLI의 (ValueError, OSError) 포획망 밖이라 트레이스백이 그대로 샌다.


def test_band_cols가_리스트가_아니면_정수_4개_목록_문구로_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["band"]["cols"] = 41984  # len()이 TypeError로 죽는 자리
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError, match=r"furniture\.band\.cols 는 정수 4개의 목록이어야 한다"
    ):
        load_kit(임시킷)


def test_band_cols_원소가_정수가_아니면_정수_4개_목록_문구로_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["band"]["cols"] = [5929, 7390, 17295, "11370"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError, match=r"furniture\.band\.cols 는 정수 4개의 목록이어야 한다"
    ):
        load_kit(임시킷)


@pytest.mark.parametrize("바꿀_키", ["labelWidth", "bodyWidth"])
def test_labelWidth나_bodyWidth가_문자열이면_거부한다(임시킷, 바꿀_키):
    데이터 = _데이터(임시킷)
    if 바꿀_키 == "labelWidth":
        데이터["furniture"]["labelWidth"] = "4041"  # 숫자처럼 보이는 문자열
    else:
        데이터["bodyWidth"] = "50460"
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError, match=r"furniture\.labelWidth 와 bodyWidth 는 정수여야 한다"
    ):
        load_kit(임시킷)


@pytest.mark.parametrize(
    "부모, 키",
    [
        ("band", "width"),
        ("band", "height"),
        ("keywordPage", "rows"),
        ("keywordPage", "width"),
        ("keywordPage", "height"),
        ("rowHeight", "label"),
        ("rowHeight", "cell"),
        ("rowHeight", "answer"),
    ],
)
def test_furniture_숫자_자리에_문자열을_넣으면_거부한다(임시킷, 부모, 키):
    데이터 = _데이터(임시킷)
    데이터["furniture"][부모][키] = "50460"  # 숫자처럼 보여도 문자열이면 거부해야 한다
    _쓰기(임시킷, 데이터)

    점경로 = f"furniture.{부모}.{키}"
    with pytest.raises(
        ValueError, match=rf"{re.escape(점경로)} 는 정수여야 한다: '50460'"
    ):
        load_kit(임시킷)


def test_중립킷_슬롯은_비어있고_스타일은_살아있다():
    standard = Path(__file__).resolve().parents[1] / "kits" / "standard"
    kit = load_kit(standard)
    assert kit.name == "standard"
    assert kit.slots == {"school": "", "teacher": "", "subject": "", "grade": ""}
    assert verify_kit(kit) == []
    assert len(kit.blocks) == 10


# --- 블록 셀 서식·행 높이·제목 출처 run: 새 킷 키의 스키마 검사 ------------------------------


def test_표준_킷의_rowHeight와_출처_문구가_씨앗값이다():
    """값은 코드가 아니라 여기(kits/standard/kit.json)에서만 정해진다. 스타일 번호는 씨앗
    스크립트가 다시 쓰므로 수 대신 역할끼리의 관계(같은 모양을 나눠 쓰는지)를 본다."""
    standard = Path(__file__).resolve().parents[1] / "kits" / "standard"
    kit = load_kit(standard)
    assert kit.furniture["rowHeight"] == {"label": 2048, "cell": 2131, "answer": 2614}
    assert kit.furniture["heading"]["textbookFormat"] == ": 교과서 {textbook}"
    assert kit.char_pr["cell"] == kit.char_pr["label"]  # 셀·라벨은 같은 글자 모양
    assert kit.char_pr["keyword_head"] == kit.char_pr["band_title"]
    assert kit.char_pr["prompt"] != kit.char_pr["body"]
    assert kit.char_pr["heading_ref"] not in (kit.char_pr["headline"], kit.char_pr["body"])
    assert kit.para_pr["cell"] != kit.para_pr["label"]  # 셀은 왼쪽, 라벨은 가운데
    assert verify_kit(kit) == []


def test_textbookFormat이_textbook_말고_다른_자리표시자를_쓰면_거부한다(임시킷):
    """{textbook} 이 아예 없는지부터 먼저 보므로, 이 테스트는 {textbook} 은 있고 그 말고
    다른 자리표시자가 하나 더 있는 값으로 "다른 자리표시자" 검사 하나만 걸리게 한다."""
    데이터 = _데이터(임시킷)
    데이터["furniture"]["heading"]["textbookFormat"] = "{textbook} {other} 쪽"
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=r"furniture\.heading\.textbookFormat 은 \{textbook\} 만 쓸 수 있다: other",
    ):
        load_kit(임시킷)


def test_textbookFormat_자리표시자_문법_오류를_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["heading"]["textbookFormat"] = "{textbook"
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=r"furniture\.heading\.textbookFormat 자리표시자를 읽을 수 없다: '\{textbook'",
    ):
        load_kit(임시킷)


def test_textbookFormat이_textbook만_쓰면_통과한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["furniture"]["heading"]["textbookFormat"] = "(교재 {textbook})"
    _쓰기(임시킷, 데이터)

    assert load_kit(임시킷).furniture["heading"]["textbookFormat"] == "(교재 {textbook})"


def test_textbookFormat에_textbook이_아예_없으면_거부한다(임시킷):
    """자리표시자가 하나도 없는 문구(예: '교과서 참고')를 그냥 두면, 교사가 md에 적은
    `교과서: 36P`가 모든 학습지에서 조용히 사라진다(값이 끼워질 자리 자체가 없다) —
    교사가 적은 내용이 조용히 증발하는 실패 유형이라 별도로 막는다."""
    데이터 = _데이터(임시킷)
    데이터["furniture"]["heading"]["textbookFormat"] = "교과서 참고"
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=r"furniture\.heading\.textbookFormat 에 \{textbook\} 이 없다: '교과서 참고'",
    ):
        load_kit(임시킷)


def test_textbookFormat이_문자열이_아니면_거부한다(임시킷):
    """parse_slot_fields 는 str 이 아니면 bare TypeError 를 던진다 — textbookFormat 처럼
    문자열이어야 하는 자리에 정수 같은 다른 타입이 들어오면 str 검사가 먼저 걸러야 한다."""
    데이터 = _데이터(임시킷)
    데이터["furniture"]["heading"]["textbookFormat"] = 36
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError, match=r"furniture\.heading\.textbookFormat 는 문자열이어야 한다: 36",
    ):
        load_kit(임시킷)


@pytest.mark.parametrize("키", ["teacherLines", "nameLines"])
def test_band_자리표시자_줄이_문자열이_아니면_거부한다(임시킷, 키):
    """_band_자리표시자_검사 도 자리표시자를 읽기 전에 str 인지부터 확인해야 한다 —
    아니면 bare TypeError 가 샌다."""
    데이터 = _데이터(임시킷)
    데이터["furniture"]["band"][키] = [123]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError, match=rf"furniture\.band\.{키} 는 문자열이어야 한다: 123",
    ):
        load_kit(임시킷)


# --- effective_slots — grade 는 회차별 입력, 킷 슬롯을 덮는다 -------------------------------


def test_effective_slots는_grade가_없으면_킷_슬롯_그대로다(임시킷):
    kit = load_kit(임시킷)
    assert effective_slots(kit) == kit.slots
    assert effective_slots(kit, grade=None) == kit.slots


def test_effective_slots는_grade를_주면_킷의_grade_슬롯을_덮는다(임시킷):
    kit = load_kit(임시킷)  # 킷_루트 기준이라 slots["grade"] == "2학년"
    덮은것 = effective_slots(kit, grade="3학년")
    assert 덮은것["grade"] == "3학년"
    assert {k: v for k, v in 덮은것.items() if k != "grade"} == {
        k: v for k, v in kit.slots.items() if k != "grade"
    }


# --- extract-kit — CLI와 얽힌 동작 --------------------------------------------------------

from worksheet.cli import main as cli_main  # noqa: E402


def test_extract_kit_은_새_dest에_씨앗으로_kit_json을_쓴다(원본_hwpx, tmp_path):
    """kit.json 이 없는 새 dest — 씨앗을 복사해 kit=디렉터리 이름, slots=인자값으로 채운다."""
    out = tmp_path / "새킷"
    코드 = cli_main(["extract-kit", str(원본_hwpx), str(out), "--school", "시험고등학교"])
    assert 코드 == 0

    씨앗 = json.loads(seed_kit_path().read_text(encoding="utf-8"))
    쓰인 = json.loads((out / "kit.json").read_text(encoding="utf-8"))

    assert 쓰인["kit"] == out.name
    assert 쓰인["slots"]["school"] == "시험고등학교"

    def 나머지(d: dict) -> dict:
        return {k: v for k, v in d.items() if k not in ("kit", "slots")}

    assert 나머지(쓰인) == 나머지(씨앗)


def test_extract_kit_은_있는_kit_json을_지킨다(원본_hwpx, tmp_path, capsys):
    """kit.json 이 이미 있으면 건드리지 않는다 — 저작물(손으로 맞춘 스타일 매핑)이라서다.

    슬롯 인자를 더해 다시 부르면(--force 없이) 거부된다 — CLI가 이 예외를 삼켜 종료코드
    2 + stderr 로 바꾸므로, 여기서도 그 계약으로 확인한다(`pytest.raises(ValueError)`로
    직접 잡지 않는다 — main()을 거치면 예외가 밖으로 새지 않기 때문이다).
    """
    out = tmp_path / "기존킷"
    코드 = cli_main(["extract-kit", str(원본_hwpx), str(out)])
    assert 코드 == 0
    이전_바이트 = (out / "kit.json").read_bytes()

    코드 = cli_main(["extract-kit", str(원본_hwpx), str(out)])
    assert 코드 == 0
    assert (out / "kit.json").read_bytes() == 이전_바이트

    코드 = cli_main(["extract-kit", str(원본_hwpx), str(out), "--school", "시험고등학교"])
    assert 코드 == 2
    assert "오류: kit.json 이 이미 있다" in capsys.readouterr().err
    assert (out / "kit.json").read_bytes() == 이전_바이트  # 거부됐으니 그대로다


def test_extract_kit_은_force면_있는_kit_json도_다시_쓴다(원본_hwpx, tmp_path):
    out = tmp_path / "강제킷"
    cli_main(["extract-kit", str(원본_hwpx), str(out)])

    코드 = cli_main([
        "extract-kit", str(원본_hwpx), str(out), "--school", "시험고등학교", "--force",
    ])
    assert 코드 == 0
    kit = json.loads((out / "kit.json").read_text(encoding="utf-8"))
    assert kit["slots"]["school"] == "시험고등학교"


# --- extract-kit — dest/kit.json의 fontMap을 쓴다(있으면 그 값, CLI 인자는 안 더한다) -------


def test_extract_kit_은_지키는_kit_json의_fontMap을_쓴다(킷_루트, tmp_path, capsys):
    """dest/kit.json 이 이미 있으면(보존) `extract_skeleton`에 그 fontMap 을 넘긴다 — 씨앗의
    fontMap 이 아니라. kit.json 이 이미 있는 경로라 슬롯 인자는 안 준다(주면 거부된다)."""
    dirty = tmp_path / "dirty.hwpx"
    _금칙장식체_심기(킷_루트 / "skeleton.hwpx", dirty)

    out = tmp_path / "폰트킷"
    out.mkdir()
    킷_데이터 = json.loads(seed_kit_path().read_text(encoding="utf-8"))
    킷_데이터["kit"] = out.name
    킷_데이터["fontMap"] = {"금칙장식체": "함초롬돋움"}
    (out / "kit.json").write_text(
        json.dumps(킷_데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    코드 = cli_main(["extract-kit", str(dirty), str(out)])
    assert 코드 == 0

    보고 = json.loads(capsys.readouterr().out)
    assert 보고["kit_json"] == "kept"
    assert 보고["fonts_remapped"] > 0

    header = zipfile.ZipFile(out / "skeleton.hwpx").read("Contents/header.xml").decode()
    assert "금칙장식체" not in header


def test_extract_kit_자기_자신을_원본으로_써도_fontMap이_멱등이다(킷_루트, tmp_path):
    """공개 사용자는 원본 hwpx가 없고 스켈레톤만 있다 — 글꼴을 바꾸려면 자기 킷의 fontMap을
    고치고 `extract-kit <자기 킷>/skeleton.hwpx <자기 킷>`을 돌린다(source == dest). 이
    경로가 안전해야 하고, 같은 fontMap으로 두 번 돌리면(두 번째는 더는 원래 글꼴이 없으므로)
    바이트가 같아야 한다."""
    kit_root = tmp_path / "자기킷"
    kit_root.mkdir()
    _금칙장식체_심기(킷_루트 / "skeleton.hwpx", kit_root / "skeleton.hwpx")
    킷_데이터 = json.loads(seed_kit_path().read_text(encoding="utf-8"))
    킷_데이터["kit"] = kit_root.name
    킷_데이터["fontMap"] = {"금칙장식체": "함초롬돋움"}
    (kit_root / "kit.json").write_text(
        json.dumps(킷_데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    자기_경로 = str(kit_root / "skeleton.hwpx")
    코드1 = cli_main(["extract-kit", 자기_경로, str(kit_root)])
    assert 코드1 == 0
    한_번_돌린_뒤 = (kit_root / "skeleton.hwpx").read_bytes()
    # 1회차가 실제로 일을 했다는 증거 없이는 2회차와 바이트가 같다는 단언이 공허하다.
    assert "금칙장식체" not in zipfile.ZipFile(kit_root / "skeleton.hwpx").read(
        "Contents/header.xml"
    ).decode()

    코드2 = cli_main(["extract-kit", 자기_경로, str(kit_root)])
    assert 코드2 == 0
    assert (kit_root / "skeleton.hwpx").read_bytes() == 한_번_돌린_뒤


def test_extract_kit_은_지키는_kit_json의_잘못된_fontMap을_한_줄_오류로_거부한다(
    킷_루트, tmp_path, capsys,
):
    """dest/kit.json 이 이미 있고 그 fontMap 값이 문자열이 아니면(예: 정수), `check`·
    `compose`처럼 트레이스백이 아니라 `오류: …` 한 줄 + 종료코드 2로 거부해야 한다 —
    kit.json 은 교사가 손으로 고치는 파일이다. 이 시점엔 아직 skeleton.hwpx가 없어서
    `load_kit()`은 못 쓴다(`FileNotFoundError`로 엉뚱하게 실패한다) — 스키마 검사만
    따로 부른다.

    원본이 `금칙장식체`를 실제로 갖고 있어야 한다 — 없으면 언어별 루프가 "그 목록에
    없으면 건너뛴다"로 먼저 빠져나가 대상 글꼴(123)까지 도달하지 않으므로, 버그가 있어도
    이 테스트가 공허하게 통과한다."""
    dirty = tmp_path / "dirty.hwpx"
    _금칙장식체_심기(킷_루트 / "skeleton.hwpx", dirty)

    out = tmp_path / "망가진킷"
    out.mkdir()
    킷_데이터 = json.loads(seed_kit_path().read_text(encoding="utf-8"))
    킷_데이터["kit"] = out.name
    킷_데이터["fontMap"] = {"금칙장식체": 123}
    (out / "kit.json").write_text(
        json.dumps(킷_데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    코드 = cli_main(["extract-kit", str(dirty), str(out)])
    assert 코드 == 2

    stderr = capsys.readouterr().err
    assert stderr.startswith("오류: kit.json 의 fontMap"), stderr
    assert "Traceback" not in stderr
    assert not (out / "skeleton.hwpx").exists()


# --- Kit.residue_markers ------------------------------------------------------------


def test_킷의_기본_흔적_마커는_네_문자다(임시킷):
    from worksheet.kit import DEFAULT_RESIDUE_MARKERS

    kit = load_kit(임시킷)
    assert kit.residue_markers == ("《", "》", "TODO", "TBD") == DEFAULT_RESIDUE_MARKERS


def test_킷json의_residueMarkers를_읽는다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["residueMarkers"] = ["FIXME", "XXX"]
    _쓰기(임시킷, 데이터)

    kit = load_kit(임시킷)
    assert kit.residue_markers == ("FIXME", "XXX")


# --- Kit.font_map — 선택 키, kit.json의 fontMap을 옮긴다 ------------------------------


def test_킷의_기본_fontMap은_빈_dict다(임시킷):
    데이터 = _데이터(임시킷)
    데이터.pop("fontMap", None)
    _쓰기(임시킷, 데이터)

    kit = load_kit(임시킷)
    assert kit.font_map == {}


def test_킷json의_fontMap을_읽는다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["fontMap"] = {"금칙장식체": "함초롬돋움"}
    _쓰기(임시킷, 데이터)

    kit = load_kit(임시킷)
    assert kit.font_map == {"금칙장식체": "함초롬돋움"}


def test_fontMap이_dict가_아니면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["fontMap"] = ["금칙장식체", "함초롬돋움"]
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=re.escape('kit.json 의 fontMap 은 {"원래 글꼴": "바꿀 글꼴"} 꼴이어야 한다'),
    ):
        load_kit(임시킷)


def test_fontMap_값이_문자열이_아니면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["fontMap"] = {"금칙장식체": 123}
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=re.escape('kit.json 의 fontMap 은 {"원래 글꼴": "바꿀 글꼴"} 꼴이어야 한다'),
    ):
        load_kit(임시킷)


def test_fontMap_값이_빈_문자열이면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["fontMap"] = {"금칙장식체": ""}
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=re.escape('kit.json 의 fontMap 은 {"원래 글꼴": "바꿀 글꼴"} 꼴이어야 한다'),
    ):
        load_kit(임시킷)


def test_fontMap에서_원래와_바뀐_글꼴이_같으면_거부한다(임시킷):
    데이터 = _데이터(임시킷)
    데이터["fontMap"] = {"함초롬돋움": "함초롬돋움"}
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=re.escape("kit.json 의 fontMap 에서 원래 글꼴과 바꿀 글꼴이 같다: '함초롬돋움'"),
    ):
        load_kit(임시킷)


def test_fontMap_항목이_연쇄하면_거부한다(임시킷):
    """{"A":"B","B":"C"}는 한 단계 매핑이 아니라 순차 적용되면서 A가 결국 C를 가리키게
    되는 연쇄다 — 사후조건의 핵심 단언(단일 조회)과 어긋나므로 스키마에서 미리 막는다."""
    데이터 = _데이터(임시킷)
    데이터["fontMap"] = {"A": "B", "B": "C"}
    _쓰기(임시킷, 데이터)

    with pytest.raises(
        ValueError,
        match=re.escape(
            "kit.json 의 fontMap 항목이 연쇄한다: 'A' → 'B' → 'C' — 한 단계로만 적는다"
        ),
    ):
        load_kit(임시킷)
