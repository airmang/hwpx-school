"""원본 양식 → <킷 폴더>/skeleton.hwpx. 양식이 바뀌었거나 새 양식으로 킷을 만들 때 돌린다.

    uv run --python 3.13 python scripts/뽑기_스켈레톤.py <원본 양식.hwpx> <킷 폴더>

킷 폴더는 보통 저장소 밖(사용자 로컬 학교 킷)이다 — 씨앗은 kits/standard를 복사해 시작한다.
"""
import json
import sys
from pathlib import Path

from assessment.kit import validate_font_map
from assessment.skeleton import extract_skeleton

if len(sys.argv) != 3:
    raise SystemExit(__doc__)
원본, 킷_루트 = Path(sys.argv[1]), Path(sys.argv[2])
대상 = 킷_루트 / "skeleton.hwpx"

# fontMap(원본 글꼴 → 배포 환경 글꼴)은 kit.json 이 다스린다 — CLI 인자로는 안
# 받는다. 검사 없이 그대로 extract_skeleton 에 넘기면, 값이 문자열이 아닌 항목이
# header.xml 에 hh:font 를 지으려 할 때 라이브러리의 원문 오류가 그대로 샌다.
킷_데이터 = json.loads((킷_루트 / "kit.json").read_text(encoding="utf-8"))
font_map = 킷_데이터.get("fontMap") or {}
validate_font_map(font_map)

print(extract_skeleton(원본, 대상, font_map=font_map))
