"""페이지 가구의 계획 — 머리띠·섹션 제목·키워드면. 그리기는 worksheet.backends.* 가 한다."""

from __future__ import annotations

from worksheet.kit import Kit
from worksheet.plan import BandPlan, HeadingPlan, KeywordPagePlan


def plan_band(kit: Kit, *, title: str, slots: dict[str, str] | None = None, stamp: bool = False) -> BandPlan:
    """회차 머리띠. 이것이 곧 회차 경계다.

    `slots`는 키워드 전용이고 기본은 `None` → 이때는 `kit.slots`를 그대로 쓴다. `compose()`는
    `worksheet.kit.effective_slots(kit, grade=sheet.grade)`로 회차별 학년을 덮은 값을
    넘긴다 — 킷은 "학교-과목" 단위라 학년이 고정돼 있지 않다.
    """
    슬롯 = slots if slots is not None else kit.slots
    설정 = kit.furniture["band"]
    return BandPlan(
        title=title,
        teacher_lines=tuple(줄.format(**슬롯) for 줄 in 설정["teacherLines"]),
        name_lines=tuple(줄.format(**슬롯) for 줄 in 설정["nameLines"]),
        stamp=stamp,
    )


def plan_heading(kit: Kit, *, number: int, text: str, textbook: str | None = None, with_stamp: bool = False) -> HeadingPlan:
    """섹션 제목: 원문자 번호 + 제목 텍스트 (+ 출처 문구, + 회차 첫 제목이면 확인도장).

    출처 문구는 킷(furniture.heading.textbookFormat)에서 온다."""
    참조 = kit.furniture["heading"]["textbookFormat"].format(textbook=textbook) if textbook else None
    return HeadingPlan(number=number, text=text, textbook_ref=참조, stamp=with_stamp)


def plan_keyword_page(kit: Kit) -> KeywordPagePlan:
    """'오늘의 키워드' 줄 노트면 — 한 쪽을 통째로 차지한다."""
    설정 = kit.furniture["keywordPage"]
    return KeywordPagePlan(head=설정["head"], rows=int(설정["rows"]))
