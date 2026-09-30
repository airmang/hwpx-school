"""블록 이름 집합 — blocks.py와 kit.py가 함께 읽는다.

kit.py가 blocks.py를 직접 import하면 순환(blocks.py는 이미 kit.py를 import한다)이므로,
이름 집합만 담은 이 작은 모듈을 양쪽이 각각 읽는다. `worksheet/blocks.py`의 `PLANNERS`·
`STRUCTURAL`이 실제 선언표고, 여기 두 집합은 그 키 집합과 반드시 같아야 한다 —
`tests/test_blocks.py`가 그 일치를 지킨다.
"""

from __future__ import annotations

FENCE_BLOCKS: frozenset[str] = frozenset({
    "라벨설명", "용어카드", "비교표", "데이터표", "답칸", "강조박스", "나란히",
})
STRUCTURAL_BLOCKS: frozenset[str] = frozenset({"정의빈칸", "발문", "그림칸"})
