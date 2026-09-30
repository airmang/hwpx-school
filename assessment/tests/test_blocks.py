import struct
import zlib

import pytest

from assessment.blocks import InputError, plan_sheet
from assessment.kit import load_kit
from assessment.md import parse_sheet
from assessment.plan import CELL_ROLES, ColumnBreakPlan, ParaPlan, RunPlan, TablePlan, TitlePlan

머리 = "---\nkit: standard\ntitle: 인공지능 기초 수행평가(A)\nscore: 25점/기본점수 10점\ntotal: {total}\n---\n"


@pytest.fixture(scope="module")
def kit(킷_루트):
    return load_kit(킷_루트)


def _계획(kit, 본문, total=2, answers=False, base_dir=None):
    return plan_sheet(parse_sheet(머리.format(total=total) + 본문), kit, base_dir=base_dir or kit.root, answers=answers)


def test_cell_roles_키가_킷에_있다(kit):
    for 역할, (border, para, char, row) in CELL_ROLES.items():
        assert border in kit.border_fill, f"{역할}: borderFill 킷에 없다: {border}"
        assert para in kit.para_pr, f"{역할}: paraPr 킷에 없다: {para}"
        assert char in kit.char_pr, f"{역할}: charPr 킷에 없다: {char}"
        assert row in kit.furniture["rowHeight"], f"{역할}: rowHeight 킷에 없다: {row}"


def test_머리_제목과_점수(kit):
    p = _계획(kit, "## 가 {2점}\n:::정답\n답\n:::\n")
    assert p[0] == TitlePlan("인공지능 기초 수행평가", "(A)", "(25점/기본점수 10점)")


def test_문항_발문과_배점_run(kit):
    p = _계획(kit, "## 쓰시오 {총 2점}\n:::정답\n답\n:::\n")
    발문 = p[1]
    assert isinstance(발문, ParaPlan) and 발문.para == "body"
    assert [(r.text, r.char, r.memo) for r in 발문.runs] == [("1. 쓰시오 ", "body", None), ("[총 2점]", "body", None)]
    assert p[2] == ParaPlan((RunPlan("", "body"),), "body")  # 문항 뒤 빈 줄


def test_정답용이면_배점_run_에_메모(kit):
    발문 = _계획(kit, "## 쓰시오 {2점}\n:::정답\n(가) 노드\n(나) 간선\n:::\n", answers=True)[1]
    assert 발문.runs[1].memo == ("(가) 노드", "(나) 간선")


def test_답칸은_밑줄_균등(kit):
    표 = _계획(kit, "## 가 {2점}\n:::답칸 (가) | (나) | (다)\n:::정답\n답\n:::\n")[2]
    assert isinstance(표, TablePlan)
    # 밑줄은 칸 아래 테두리라 칸이 붙으면 한 줄로 이어진다 — 답칸 사이에 테두리 없는 틈 칸.
    assert [c.role for c in 표.rows[0]] == ["answer_line", "answer_gap"] * 2 + ["answer_line"]
    assert [c.lines for c in 표.rows[0] if c.role == "answer_line"] == [("(가)",), ("(나)",), ("(다)",)]
    w = kit.furniture["widths"]
    assert 표.width == w["answerLine"] == sum(표.col_widths)
    assert 표.col_widths[1] == 표.col_widths[3] == w["answerGap"]
    답폭 = 표.col_widths[0::2]
    assert max(답폭) - min(답폭) <= 1


def test_답칸_하나면_틈_칸이_없다(kit):
    표 = _계획(kit, "## 가 {2점}\n:::답칸 (예시)\n:::정답\n답\n:::\n")[2]
    assert [c.role for c in 표.rows[0]] == ["answer_line"]
    assert 표.col_widths == (kit.furniture["widths"]["answerLine"],)


def test_표답칸(kit):
    표 = _계획(kit, "## 가 {2점}\n:::표답칸\nBFS\nDFS\n:::\n:::정답\n답\n:::\n")[2]
    w = kit.furniture["widths"]
    assert 표.col_widths == (w["gridLabel"], w["box"] - w["gridLabel"])
    assert [[c.role for c in r] for r in 표.rows] == [["grid_label", "grid_blank"]] * 2


def test_서술칸_여러줄과_한줄과_라벨(kit):
    p = _계획(kit, "## 가 {2점}\n:::서술칸 6줄\n:::서술칸 1줄\n:::서술칸\n최단 경로\n노드 순서\n:::\n:::정답\n답\n:::\n")
    여러, 한, 라벨 = p[2], p[3], p[4]
    assert [r[0].role for r in 여러.rows] == ["rule"] * 6
    assert [r[0].role for r in 한.rows] == ["single"]
    assert [r[0].lines for r in 라벨.rows] == [("최단 경로 : ",), ("노드 순서 : ",)]


def test_제시문_조건_자료표(kit):
    p = _계획(kit, "## 가 {2점}\n:::제시문\n줄1\n줄2\n:::\n:::조건\n조건 : 하나\n:::\n| 노드 | 거리 |\n|---|---|\n| S | 16 |\n:::정답\n답\n:::\n")
    제시, 조건, 자료 = p[2], p[3], p[4]
    assert 제시.rows[0][0].role == "passage" and 제시.rows[0][0].lines == ("줄1", "줄2")
    assert 제시.width == kit.furniture["widths"]["passage"]
    assert 조건.rows[0][0].role == "condition"
    assert [[c.role for c in r] for r in 자료.rows] == [["data_head", "data_head"], ["data", "data"]]
    assert 자료.col_widths[0] == kit.furniture["widths"]["dataLabel"]


def _png(w, h):
    def c(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + c(b"IDAT", zlib.compress(raw)) + c(b"IEND", b"")


def test_그림_박스와_캡션_기본폭은_칸_안쪽(kit, tmp_path):
    (tmp_path / "a.png").write_bytes(_png(200, 100))
    표 = _계획(kit, "## 가 {2점}\n![캡1\\n캡2](a.png)\n:::정답\n답\n:::\n", base_dir=tmp_path)[2]
    칸 = 표.rows[0][0]
    안쪽 = kit.furniture["widths"]["box"] - kit.furniture["cellInnerMargin"]
    assert 칸.role == "figure" and 칸.lines == ("캡1", "캡2")
    assert 칸.picture.width == 안쪽 and 칸.picture.height == 안쪽 // 2
    assert 칸.caption_para is None


def test_그림_캡션_왼쪽이면_caption_para가_caption_left(kit, tmp_path):
    """caption=left 면 칸의 캡션 문단 모양이 킷 키 'caption_left' 다(문단 모양 자체는 백엔드가 킷에서 찾는다)."""
    (tmp_path / "a.png").write_bytes(_png(200, 100))
    표 = _계획(kit, "## 가 {2점}\n![캡](a.png){caption=left}\n:::정답\n답\n:::\n", base_dir=tmp_path)[2]
    칸 = 표.rows[0][0]
    assert 칸.caption_para == "caption_left"


def test_그림이_칸보다_넓으면_거부(kit, tmp_path):
    """Minor-5: 이건 check_sheet 가 못 잡는 입력 오류라 InputError(ValueError 의 하위)로 낸다 — cli 가 종료코드 2로 다룬다."""
    (tmp_path / "a.png").write_bytes(_png(10, 10))
    with pytest.raises(InputError, match="그림 폭이 칸 안쪽보다 넓다"):
        _계획(kit, "## 가 {2점}\n![](a.png){width=20cm}\n:::정답\n답\n:::\n", base_dir=tmp_path)


def test_묶음_머리와_단나눔(kit):
    p = _계획(kit, "::::묶음 1-1 공통 발문\n## 가 {2점}\n:::정답\n답\n:::\n::::\n:::단나눔\n## 나 {0점}\n:::정답\n답\n:::\n")
    assert p[1].runs[0].text == "[1-1] 공통 발문"
    assert any(isinstance(x, ColumnBreakPlan) for x in p)


def test_꼬리_문항수와_득점표(kit):
    p = _계획(kit, "## 가 {2점}\n:::정답\n답\n:::\n")
    글들 = [x.runs[0].text for x in p if isinstance(x, ParaPlan)]
    assert "*총 1문제 모두 오류 없이 풀었는지*" in 글들
    득점 = p[-1]
    assert 득점.col_widths == tuple(kit.furniture["widths"]["score"])
    assert 득점.merges == ((0, 0, 0, 1), (1, 0, 1, 1), (2, 1, 2, 2))
    assert 득점.rows[1][0].lines == ("   /2",) and 득점.rows[1][2].lines == ("   /25",)


def test_병합_머리_자료표_계획(kit):
    본문 = (
        "## 가 {2점}\n"
        "| 답칸 1-① | 예측 | < |\n| ^ | 예측 양성 | 예측 음성 |\n|---|---|---|\n"
        "| 실제 양성 |  |  |\n| 실제 음성 |  |  |\n"
        ":::정답\n답\n:::\n"
    )
    자료 = _계획(kit, 본문)[2]
    assert isinstance(자료, TablePlan)
    assert [[c.role for c in r] for r in 자료.rows] == [["data_head"] * 3] * 2 + [["data"] * 3] * 2
    assert 자료.rows[1][1].lines == ("예측 양성",)
    assert 자료.merges == ((0, 0, 1, 0), (0, 1, 0, 2))
    w = kit.furniture["widths"]
    assert 자료.col_widths[0] == w["dataLabel"] and sum(자료.col_widths) == w["box"]


# --- 나란히 그림·문항 밖 블록 --------------------------------------------------
def test_나란히_한_행_N칸_균등_기본폭은_칸_안쪽(kit, tmp_path):
    for n in "abc":
        (tmp_path / f"{n}.png").write_bytes(_png(200, 100))
    w, 여백 = kit.furniture["widths"]["box"], kit.furniture["cellInnerMargin"]
    for 줄들 in (("a", "b"), ("a", "b", "c")):
        그림들 = "".join(f"![캡{x}](" + x + ".png)\n" for x in 줄들)
        표 = _계획(kit, f"## 가 {{2점}}\n:::나란히\n{그림들}:::\n:::정답\n답\n:::\n", base_dir=tmp_path)[2]
        n = len(줄들)
        assert isinstance(표, TablePlan) and len(표.rows) == 1 and len(표.rows[0]) == n
        assert 표.width == w and max(표.col_widths) - min(표.col_widths) <= 1
        for 칸, 폭, x in zip(표.rows[0], 표.col_widths, 줄들):
            assert 칸.role == "figure" and 칸.lines == (f"캡{x}",)
            assert 칸.picture.width == 폭 - 여백 and 칸.picture.height == (폭 - 여백) // 2


def test_나란히_width_와_caption_left(kit, tmp_path):
    for n in "ab":
        (tmp_path / f"{n}.png").write_bytes(_png(100, 100))
    표 = _계획(kit, "## 가 {2점}\n:::나란히\n![캡](a.png){width=3cm caption=left}\n![](b.png)\n:::\n:::정답\n답\n:::\n", base_dir=tmp_path)[2]
    왼, 오 = 표.rows[0]
    assert 왼.picture.width == round(30 * 7200 / 25.4) and 왼.caption_para == "caption_left"
    assert 오.caption_para is None


def test_나란히_그림이_칸_안쪽보다_넓으면_거부(kit, tmp_path):
    for n in "ab":
        (tmp_path / f"{n}.png").write_bytes(_png(10, 10))
    with pytest.raises(InputError, match="그림 폭이 칸 안쪽보다 넓다: b.png"):
        _계획(kit, "## 가 {2점}\n:::나란히\n![](a.png)\n![](b.png){width=8cm}\n:::\n:::정답\n답\n:::\n", base_dir=tmp_path)


def test_안내는_조건_상자와_같다(kit):
    p = _계획(kit, "## 가 {2점}\n:::안내\n알림\n:::\n:::조건\n조건\n:::\n:::정답\n답\n:::\n")
    안내, 조건 = p[2], p[3]
    assert 안내.col_widths == 조건.col_widths == (kit.furniture["widths"]["box"],)
    assert 안내.rows[0][0].role == 조건.rows[0][0].role == "condition"


def test_문항_밖_블록은_그_자리에_블록과_빈_줄(kit):
    p = _계획(kit, ":::안내\n알림\n:::\n## 가 {2점}\n:::정답\n답\n:::\n")
    assert isinstance(p[1], TablePlan) and p[1].rows[0][0].lines == ("알림",)
    assert p[2] == ParaPlan((RunPlan("", "body"),), "body")
    assert p[3].runs[0].text == "1. 가 "
