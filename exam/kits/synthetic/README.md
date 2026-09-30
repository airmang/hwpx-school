# synthetic — 합성 서식·합성 킷 (학교 무관)

학교 킷이 없는 PC에서도 시험지 엔진 테스트가 돌도록 만든 **합성** 서식과 킷이다. 실제 학교의 서식을 가공하지 않았다 — python-hwpx 기본 템플릿에서 `tools/make_synthetic_form.py`로 새로 만들었다. 실제 학교는 이 킷을 쓰지 않는다(학교 등록: `skills/exam/references/학교-등록.md`).

- `synthetic_form.hwpx` — B4 세로 2단(단 사이 실선). 관리박스(결재 표·유의 상자, 함초롬돋움), 샘플 문항 구역(글자 번호 문항·5/2/3/1행 답항·〈보기〉 2×1·자료 1×1·세트 표지), `【논술형` 샘플, 꼬리 박스 `※ 확인 사항`, 꼬리말 `과목명 1학년 (1쪽 중 N쪽)`. 본문 함초롬바탕 11pt.
- `kit.json` — 글자 자리 슬롯 양식(누름틀 없음), 글자 번호, 발문 둘째 줄 공백 한 칸 내어쓰기, 텍스트 층 렌더 판정. 교사 습관은 엔진 기본, 학교 규칙은 없음(엔진 규칙만).
- 다시 만들기: `uv run --no-project --with "python-hwpx==6.6.0" --with lxml python tools/make_synthetic_form.py kits/synthetic/synthetic_form.hwpx` → `kit.json`의 `form.sha256` 갱신(문단 id가 매번 달라 sha가 바뀐다).
- 글자 폭(`metrics`)은 이 서식의 실한컴 렌더에서 잰 값이다(샘플 답지에 대소문자·숫자 줄을 둔 까닭).

## 개정 이력
- 0.1.0 (2026-09-30): 초판.
