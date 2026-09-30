import ast
from pathlib import Path

import pytest

루트 = Path(__file__).resolve().parents[1] / "worksheet"


@pytest.mark.parametrize("이름", ["md.py", "plan.py", "blocks.py", "furniture.py", "style.py"])
def test_형식_무관_층은_문서_라이브러리를_import_하지_않는다(이름):
    트리 = ast.parse((루트 / 이름).read_text(encoding="utf-8"))
    모듈들 = {
        (n.module or "").split(".")[0] for n in ast.walk(트리) if isinstance(n, ast.ImportFrom)
    } | {a.name.split(".")[0] for n in ast.walk(트리) if isinstance(n, ast.Import) for a in n.names}
    assert not ({"hwpx", "docx"} & 모듈들), f"{이름} 이 {모듈들 & {'hwpx', 'docx'}} 를 import 한다"


def test_가구_계획은_킷의_슬롯과_문구를_채운_값을_담는다(킷_루트):
    from worksheet.furniture import plan_band, plan_heading, plan_keyword_page
    from worksheet.kit import load_kit
    from worksheet.plan import BandPlan, HeadingPlan, KeywordPagePlan

    kit = load_kit(킷_루트)
    띠 = plan_band(kit, title="제목", slots={**kit.slots, "grade": "3학년"}, stamp=True)
    assert isinstance(띠, BandPlan) and 띠.title == "제목" and 띠.stamp
    설정 = kit.furniture["band"]
    assert 띠.teacher_lines == tuple(줄.format(**{**kit.slots, "grade": "3학년"}) for 줄 in 설정["teacherLines"])
    assert 띠.name_lines == tuple(줄.format(**{**kit.slots, "grade": "3학년"}) for 줄 in 설정["nameLines"])

    제목 = plan_heading(kit, number=2, text="탐색", textbook="40P", with_stamp=False)
    assert 제목 == HeadingPlan(
        number=2, text="탐색",
        textbook_ref=kit.furniture["heading"]["textbookFormat"].format(textbook="40P"), stamp=False,
    )
    assert plan_heading(kit, number=1, text="탐색").textbook_ref is None

    면 = plan_keyword_page(kit)
    assert 면 == KeywordPagePlan(
        head=kit.furniture["keywordPage"]["head"], rows=int(kit.furniture["keywordPage"]["rows"])
    )


def test_열_폭은_본문_폭을_앞_열_반올림_마지막_열_나머지로_나눈다(킷_루트):
    from worksheet.kit import load_kit
    from worksheet.plan import CellPlan, TablePlan, column_widths

    kit = load_kit(킷_루트)
    assert kit.body_width == 50460

    def 표(n):
        return TablePlan("비교표", (tuple(CellPlan("cell") for _ in range(n)),), None, equal_columns=True)

    기대 = {
        2: [25230, 25230],
        3: [16820, 16820, 16820],
        4: [12615] * 4,
        5: [10092] * 5,
        7: [7209] * 6 + [7206],  # 50460/7 = 7208.57… → 앞 열 7209, 마지막 열이 나머지
    }
    for n, 폭들 in 기대.items():
        assert column_widths(표(n), kit) == 폭들
        assert sum(폭들) == kit.body_width
    # 블록 계획자의 그림 크기는 근사 열 폭 bodyWidth // n 으로 잡는다 — 마지막 열만 그보다 좁을 수 있다
    assert column_widths(표(7), kit)[-1] < kit.body_width // 7 < column_widths(표(7), kit)[0]

    # 중첩표는 담는 칸의 안쪽 폭을 폭= 으로 받는다
    assert column_widths(TablePlan("강조박스", ((CellPlan("cell"),),), None), kit, 폭=49440) == [49440]
    assert column_widths(표(2), kit, 폭=10001) == [5000, 5001]
