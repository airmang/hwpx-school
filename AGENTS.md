# hwpx-school — Agent Guide

## 제품 정의

학교에서 다루는 문서를 한글(HWPX)로 만든다 — 시험지(원안지)·학습지·수행평가 문제지, 이어서
가정통신문·학교 공문(기안)·평가계획 등. `python-hwpx` 엔진 위에 짓는 **별도 제품**이다.

## 헌법

1. **공개 API만 쓴다 — 복사하지 않고 의존한다.** 허용 범위는 `python-hwpx` 공개 API와
   `python-hwpx-automation`의 `public-modules.json` 등재 모듈. 내부(사설 헬퍼, 미등재 모듈)를
   만지고 싶어지면 그것은 상류 이슈다 — 상류에 올리고 우회 구현하지 않는다.
2. **두뇌는 스킬, 파이썬은 손.** 장르·학교 판단(문체·배치·위계·지울 것)은 스킬 문서와 킷(데이터)에
   둔다. 학교나 장르를 하나 더할 때 파이썬 코드가 늘어나면 설계 실패 신호다.
3. **근거는 실문서.** 기본값은 실제 문서 실측에서 유도하고 근거를 기록한다.
4. **점수 ≠ 제출 가능.** 기계 검사 결과는 "기계 잔존 N"으로만 쓴다. 최종 권위는 실제 한컴 렌더와
   교사(사용자) 검수다.
5. **성공 지표 = 실제 업무 문서를 이걸로 냈는가.** 기능 개수가 아니다.

## 이 저장소는 특정 학교용이 아니다

- 학교 킷·학교 스킬·서식 원본·실제 문항·학생 정보는 저장소에 넣지 않는다 — 각 사용자 로컬.
- 저장소에는 학교 무관 엔진·범용 스킬·합성 씨앗 킷·합성 테스트만 둔다. 씨앗 스켈레톤·합성 서식은
  python-hwpx 기본 템플릿에서 생성기로 만든다(`exam/tools/make_synthetic_form.py`,
  `worksheet/scripts/씨앗_스켈레톤.py`, `assessment/scripts/씨앗_스켈레톤.py`).
- `exam/tests/test_no_school_names.py`는 로컬 킷 이름(`EXAM_KITS_DIR`)과 로컬 금칙어 파일
  (`HWPX_FORBIDDEN_FILE`)의 이름이 저장소에 들어오면 실패한다. 커밋 전에 돌린다.

## 구조

| 폴더 | 내용 | 스킬 |
|---|---|---|
| `exam/` | 원안지 조판 엔진 `exam_kit` — 학교 서식 파일 그대로 위에 조판, 새 학교 등록(`onboard`) | `skills/exam` |
| `worksheet/` | 학습지 조판(hwpx·docx) — 씨앗 킷 `kits/standard` | `skills/worksheet` |
| `assessment/` | 수행평가 문제지 조판 — 씨앗 킷 `kits/standard` | `skills/assessment` |

각 폴더는 독립 uv 프로젝트다(자기 `pyproject.toml`·`uv.lock`). 엔진 폴더에서 `uv run`으로 돌린다.

## 테스트와 한컴

- `exam`: `uv run pytest -q -m "not render"`(한컴 없이). 학교 킷이 필요한 테스트는 환경변수가 없으면 skip — `exam/README.md`.
- `worksheet`·`assessment`: `uv run --python 3.13 pytest -q`. **`-m`을 주지 않는다** — addopts가 한컴·외부 렌더 테스트를 빼는데 `-m`이 그 기본을 덮는다.
- 실제 한컴 렌더는 공용 자원이다: 한 번에 하나, 넣기 전 zip 검사, 다른 세션의 창·대화상자는 건드리지 않는다.
