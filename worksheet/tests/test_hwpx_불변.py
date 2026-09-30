"""hwpx 출력이 바뀌지 않았는가 — 조판 계층을 나누는 리팩터의 안전망.

기준선은 리팩터 **전** 코드로 한 번만 쓴다: `env 'WORKSHEET_기준선_갱신=1' uv run --python 3.13 pytest -q tests/test_hwpx_불변.py`(한글 변수 이름이라 zsh에서는 `env`로 넘긴다).
갱신 모드는 기준선을 쓰고 일부러 실패한다 — 조용히 통과하는 갱신이 없게."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from _helpers import _png
from _hwpx_기준선 import 정규화
from worksheet.compose import compose

기준선 = Path(__file__).parent / "기준선" / "전체블록.json"

_전체_블록 = """---
kit: 시험킷
title: 기준선 회차
grade: 2학년
keywordPage: true
---

## 첫 제목
교과서: 33-35P

> 발문 한 줄이다.

■ 정의: 빈칸이 [[8]] 들어간 줄

![](본문.png){width=5cm}

:::라벨설명 labelWidth=3cm
[1] 라벨 하나
: 설명 하나
[2] 라벨 둘
: ![](칸.png)
:::

:::용어카드 cols="가|나|다"
설명 가
![](칸.png){width=2cm}
설명 다
:::

## 둘째 제목

:::비교표 cols="왼쪽|오른쪽" rows="첫째|둘째"
값1|![](칸.png)
값3|값4
:::

:::데이터표 head="단계|값" rows=3
1|가
2|나
:::

:::답칸 label="답 쓰는 곳" lines=2
:::

:::강조박스 title="규칙"
한 줄
두 줄
:::

:::나란히 cols="예제 1|예제 2"
![](칸.png){width=4cm}|![](칸.png){width=4cm}
DFS 순서 :|DFS 순서 :
:::
"""


def _조판(폴더: Path, 킷_루트: Path) -> Path:
    (폴더 / "본문.png").write_bytes(_png(400, 200))
    (폴더 / "칸.png").write_bytes(_png(300, 120))
    md = 폴더 / "기준선.md"
    md.write_text(_전체_블록, encoding="utf-8")
    out = 폴더 / "기준선.hwpx"
    compose(md, 킷_루트, out)
    return out


def test_같은_입력을_두_번_조판하면_정규화_결과가_같다(tmp_path, 킷_루트):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert 정규화(_조판(tmp_path / "a", 킷_루트)) == 정규화(_조판(tmp_path / "b", 킷_루트))


def test_hwpx_출력이_기준선과_같다(tmp_path, 킷_루트):
    실제 = 정규화(_조판(tmp_path, 킷_루트))
    if os.environ.get("WORKSHEET_기준선_갱신") == "1":
        기준선.parent.mkdir(parents=True, exist_ok=True)
        기준선.write_text(json.dumps(실제, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        pytest.fail("기준선을 새로 썼다 — 커밋하고 갱신 모드 없이 다시 돌린다")
    기대 = json.loads(기준선.read_text(encoding="utf-8"))
    assert sorted(실제) == sorted(기대)
    for 부품 in 기대:
        assert 실제[부품] == 기대[부품], f"hwpx 부품이 바뀌었다: {부품}"
