"""정답 메모 — python-hwpx 의 `doc.notes.add_memo` 로 단다.

python-hwpx 7.0 은 메모를 한/글 2024 가 저장하는 꼴(MEMO 누름틀 안 글, 매개변수 일곱)로 쓴다.
메모 문단의 모양·스타일은 킷의 메모 역할로 주고, 정답 한 줄을 메모 문단 하나로 둔다."""

from __future__ import annotations

from typing import Any

from assessment.kit import Kit


def add_answer_memo(doc: Any, paragraph: Any, anchor: str, lines: tuple[str, ...], *, kit: Kit) -> Any:
    """paragraph 안 글 anchor(한 run 안에 있어야 한다)에 정답 메모를 단다 — 줄마다 메모 문단 하나.

    메모 문단은 킷의 메모 문단 모양(`para_pr["memo"]`)·메모 스타일(`memo_style`)·본문 글자 모양
    (`char_pr["body"]`)이다. 돌려주는 값은 python-hwpx 메모 객체다."""
    memo = doc.notes.add_memo(lines[0] if lines else "", paragraph=paragraph, match=anchor or None,
                              author="assessment", char_pr_id_ref=str(kit.char_pr["body"]))
    first = memo.paragraphs[0]
    first.para_pr_id_ref = kit.para_pr["memo"]
    first.style_id_ref = kit.memo_style
    last = first
    for line in lines[1:]:
        last = last.insert_after(line)  # 문단 모양·스타일·첫 run 글자 모양을 잇는다
    return memo
