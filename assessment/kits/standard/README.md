# standard 킷 — 수행평가 문제지 씨앗 킷

학교 이름·교사 이름이 없는 **씨앗 킷**이다. 스켈레톤(`skeleton.hwpx`)은 `scripts/씨앗_스켈레톤.py`가
python-hwpx 기본 템플릿에서 새로 짓는 **빈** 뼈대다 — 어느 학교·교사의 양식에서 뽑은 것이 아니고,
글·그림 없이 스타일·용지·단 설정만 있다. 다시 지으려면(킷 역할의 모양을 바꿨을 때):

    uv run --python 3.13 python scripts/씨앗_스켈레톤.py

스크립트가 `skeleton.hwpx`를 다시 쓰고, 더한 모양의 번호를 이 폴더 `kit.json`의 `styles`에 다시 적는다.

실제로 쓸 킷은 자기 양식에서 만든다. 이 폴더를 자기 PC의 킷 폴더로 복사하고, 자기 양식 원본에서
스켈레톤을 뽑은 뒤 값(스타일 ID·폭·높이)을 그 양식에 맞춘다. 학교 킷은 이 저장소에 넣지 않는다(각 사용자 로컬).

    uv run --python 3.13 python scripts/뽑기_스켈레톤.py <원본 양식.hwpx> <킷 폴더>

킷 폴더의 `kit.json`(fontMap 포함)을 읽어 그 폴더에 `skeleton.hwpx`를 쓴다. 원본은 첫 문단에 용지
설정(secPr), 세 번째 문단에 1단 → 2단 전환(colCount=2)이 있어야 한다 — 머리(제목·학번 줄)는 1단,
본문은 2단이다.

## 값의 근거

- `borderFill.*`: 테두리와 채우기 스타일 ID
- `paraPr.*`: 문단 스타일 ID
- `charPr.*`: 문자 스타일 ID
- `furniture.widths`: 열/칸 폭(HWPUNIT 단위, 1 mm = 7200/25.4 ≈ 283.46 HWPUNIT)
- `furniture.rowHeight`: 행 높이(HWPUNIT 단위)

씨앗 스켈레톤의 모양(모두 함초롬돋움, 굵게 없음):

| 역할 | 값 |
|---|---|
| charPr | title 30pt · title_suffix 29pt · score 12pt · note 15pt · body 11pt · answer_label 10pt · hint 9pt · blank = 템플릿 charPr 0 |
| paraPr | title·center 가운데 160% · id_line·footer_gap·caption_left 왼쪽 160% · body·memo 양쪽 160% · passage 양쪽 150% · score_value 가운데 100% |
| borderFill | box 검정 · none 테두리 없음 · shade 검정 + 채움 `#DEE7F1` · rule `#808080` (모두 SOLID 0.12 mm) |
| memoStyle | 17 = 템플릿의 "메모" 스타일 |
| 용지 | A4, 여백 좌우 2835 · 위아래 1417 · 머리말/꼬리말 2835, 2단 간격 1134 |

- `borderFill.underline`: 밑줄 답칸. 아래 테두리만 SOLID 0.12 mm 검정 — 양식 header 에 이런 borderFill 이 없으면 `extract_skeleton` 이 결정적으로 더한다(기존 최대 id + 1). 밑줄 길이 = 칸 폭이라 글꼴과 무관하다.
- `borderFill.none`: 테두리 없음. 밑줄 답칸 사이 틈 칸에 쓴다.
- `furniture.widths.answerGap` = 1417(= 5 mm): 한 줄에 답칸이 여럿일 때(`(가) | (나) | (다)`) 칸 사이 틈 칸 폭. 밑줄이 칸 아래 테두리라 칸이 붙으면 한 줄로 이어져 보이기 때문에 끊는다. 답칸 폭 = (answerLine − 틈×(n−1)) / n. 빈 틈 칸이 안 여백(`cellInnerMargin` 1020 = 좌 510 + 우 510)보다 좁으면 한컴이 칸을 넓혀 표가 단 밖으로 삐져나가므로(850 으로 실렌더해 확인) `load_kit` 이 answerGap > cellInnerMargin 을 요구한다.
- `charPr.answer_label`: 밑줄 답칸의 라벨 `(가)`. 글자 밑줄이 없는 10pt 글자 — 밑줄은 칸 테두리가 그린다.
- `furniture.tableOutMargin`: 표 바깥 여백(HWPUNIT, 사방 같은 값). python-hwpx 는 표 바깥 여백을 0 으로 만들어 표 둘레 간격이 좁아지므로 킷 값으로 채운다.
- `furniture.widths.gridLabel` = 10600: 표답칸 왼쪽 라벨 칸 폭. 함초롬돋움 11pt 로 `DFS(깊이우선탐색)` 같은 긴 라벨을 재면 약 9210 HWPUNIT — 칸 안 여백(`cellInnerMargin` 1020)을 더한 최소 폭은 약 10230 이라, 여유를 두고 10600 으로 두어 한 줄에 들어가게 한다. 이보다 좁으면 라벨이 2줄로 꺾인다.
- `furniture.widths.score` = [3600, 9014, 12614]: 득점표 세 열. 첫째 값(`학생 확인` 라벨 칸)은 함초롬돋움 12pt 로 `학생`·`확인` 각각을 재면 2328 HWPUNIT — 칸 안 여백을 더한 최소 폭은 약 3348 이라, 여유를 두고 3600 으로 두어 `학생`/`확인` 2줄로 꺾이게 한다(더 좁으면 한 글자씩 세로로 꺾인다). `득점` 머리·`/15` 값은 첫째+둘째 열을 병합해 쓰고(합 12614), `변환점수` 머리·`/25` 값은 셋째 열(12614)만 쓴다. 서명 칸은 둘째+셋째 열을 병합해 쓴다.

## 글꼴 옮기기(fontMap)

양식 본문 글꼴이 배포 환경에 없으면 그대로 두면 다른 글꼴로 자동 치환되며 지면이 흐트러진다.
`kit.json` 최상위의 `fontMap`(`{"원래 글꼴": "바꿀 글꼴"}` 꼴)이 그런 글꼴을 배포 환경에 있는
글꼴(예: 함초롬돋움 — 어디서나 같은 모양으로 조판된다)로 옮긴다. 스켈레톤을 뽑을 때
`scripts/뽑기_스켈레톤.py`가 이 값을 읽어 `extract_skeleton(..., font_map=...)`에 그대로 넘긴다.
씨앗 킷은 기본 템플릿 글꼴만 쓰므로 `fontMap`이 비어 있다.
