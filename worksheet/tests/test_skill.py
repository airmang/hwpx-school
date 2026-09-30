from pathlib import Path

import pytest

루트 = Path(__file__).resolve().parents[1]


def test_SKILL_frontmatter가_규격을_지킨다():
    본문 = (루트 / "SKILL.md").read_text(encoding="utf-8")
    줄 = 본문.splitlines()
    assert 줄[0] == "---"
    닫힘 = 줄.index("---", 1)
    머리 = "\n".join(줄[1:닫힘])
    assert "name: worksheet" in 머리
    assert "description:" in 머리
    assert len(머리) < 1500


@pytest.mark.parametrize(
    "이름", ["references/양식-해부.md", "references/블록-문법.md", "references/검사-레지스트리.md"]
)
def test_references가_있고_SKILL이_가리킨다(이름):
    assert (루트 / 이름).exists()
    assert 이름.split("/")[-1] in (루트 / "SKILL.md").read_text(encoding="utf-8")


# 금칙어 검사(진짜 금칙어가 필요하다)는 로컬 전용 스위트의 공개위생 테스트로 흡수된다 —
# 그쪽은 SKILL.md·references/ 뿐 아니라 공개될 트리 전체를 본다.
