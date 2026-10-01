# exam — 원안지 조판 엔진 (exam_kit, 학교 무관)

지필평가 원안지 hwpx를 마크다운 원고 한 장에서 조판한다. 학교 원안지 서식 파일 그대로 위에 문항지·답 표시본 두 판을 내고, 실한컴 렌더로 배치를 굳히고, [기계] 검사 보고서를 쓴다.

**학교 킷은 이 저장소에 없다.** 학교마다 다른 것(kit.json·rules.json·habits.json·결정표·학교 스킬 문서)은 각 사용자가 자기 학교를 등록해 자기 PC에 만든다 — `skills/exam/references/학교-등록.md`. 엔진은 `--kit <킷 폴더>`로 어디에 있는 킷이든 읽는다.

- 쓰는 법·절대 규칙·검수: 스킬 `skills/exam/SKILL.md` · 새 학교 등록: `skills/exam/references/학교-등록.md`

## 실행

엔진 폴더에서 `uv run`을 접두어로 쓴다(Python 3.13, 의존성은 `uv.lock`).

    cd exam
    uv run python -m exam_kit.onboard scan <서식.hwpx> [--out 해부.md]   # 새 학교 ① 해부 · draft --name … --out kits/… = 킷 초안
    uv run python -m exam_kit.lint <원고.md> --kit <학교 킷 폴더>      # 규칙 검사(엔진 + 그 학교 rules.json) — 끝 코드 1 = 오류 있음
    uv run python -W ignore -m exam_kit.build <원고.md> --kit <학교 킷 폴더> --form <서식.hwpx> --out <미추적 폴더> \
        [--draft] [--lint-warn] [--gap distribute|fixed] [--pack balanced|greedy] [--compare <제출본.hwpx>] [--stage "<문구>"]
    uv run python -W ignore -m exam_kit.fit <엔진 문항지.hwpx> <기준본.hwpx> --kit <학교 킷 폴더>   # 줄 대조(실한컴 2회)
    uv run python -m exam_kit.reverse <제출본.hwpx> --kit <학교 킷 폴더> --out <미추적 폴더>/원고.md  # 역변환
    uv run python -m exam_kit.convert <지필 원고.md> --out <미추적 폴더>/원고.md [--figures <인쇄 규격 그림 폴더>] --front 과목코드=… 출제교사=…  # 원고 변환 + 불변 검사

`build` 끝 코드: 0 기계 잔존 0 · 1 규칙 오류로 조판 안 함 · 2 기계 잔존 있음. 산출물과 원고는 저장소 밖(git 미추적 폴더)에만 둔다.

## 파일 구조

```
exam_kit/
  frontmatter.py   원고 머리 → FrontMatter(슬롯 값의 원천, `__`/`_` = 미확정)
  scan.py          원고 본문 → 검사용 IR(문항·세트·블록·답지·지시), 귀속 불가 줄은 오류
  lint.py          학교 연수자료 규칙의 [기계] 검사(E·W 코드)
  kit.py           kit.json 로드·양식 sha 확인
  prepare.py       양식 hwpx를 조판 직전 상태로(안내물만 걷기, 꼬리 박스 고정, 조판 뒤 세척·검사)
  slots.py         누름틀 20개·출제교사 셀 채움
  compose.py       조판: 샘플 구역 → 문항(자동번호·답지 배치형·〈보기〉/자료 견본 복제·격자표·그림·코드·답항표), 형광펜
  render.py        실한컴 렌더(직렬) → pdf·쪽 png — 넣기 전 zip 검사(check_package)
  geometry.py      렌더 PDF 기하(글리프 bbox): 문항 머리 자리·단 끝·분할·꼬리 박스·묶음 높이
  fit.py           자간 맞춤·낱말 끌어올림(한컴 줄 캐시로 잰다), 줄 대조 CLI
  layout.py        렌더 루프 settle: 접힌 답지 → 자간 → 균형 배치 → 분할 → 맨 위 간격 → 꼬리 → 간격 나눔 → 총쪽수
  verify.py        조판본 [기계] 검사(M6~M11), 정답 추출
  build.py         파이프라인 CLI와 보고서
  gate.py          엔진 회귀 게이트: 기준·새 산출물 비교(paraPr는 내용으로, 문단 id·그림 instid는 정규화)
  reverse.py       제출본 hwpx → 원고 md(원본 재현용)
  convert.py       지필 원고(문제지·정답키 형식) → 원고 md + 문항 내용 불변 검사
  _png.py          합성 PNG(세척·픽스처)
kits/synthetic/     합성 서식(synthetic_form.hwpx) + 합성 킷 — 학교 무관, 테스트·예시용
tools/              make_synthetic_form.py — 합성 서식 생성기(python-hwpx 6.6.0)
(학교 킷)          저장소 밖 사용자 로컬 — 폴더 하나 = 학교 하나: kit.json·rules.json·habits.json·README·결정표·SKILL.md
tests/             pytest — 픽스처는 합성 문항만(fixtures/*.md, 그림.png)
```

## 테스트

    uv run pytest -q                    # 전부(실한컴 렌더 17개 포함 — 한컴이 한 번에 하나씩 돈다)
    uv run pytest -q -m "not render"    # 한컴 없이

- 실한컴 오라클 픽스처(`오라클`)를 쓰는 테스트에는 conftest가 `render` 표지를 붙인다(17개). 오라클이 없으면 skip.
- **합성 킷 `kits/synthetic`**(학교 무관 합성 서식 + 킷, `tools/make_synthetic_form.py`로 생성)으로 도는 `tests/test_synthetic.py`는 환경변수 없이 누구 PC에서든 돈다 — 서식 준비·머리 값·두 판 조판·기계 검사(한컴 없이), 전체 조판 1건(실한컴).
- 학교 킷·서식은 저장소 밖이라 **환경변수로만** 받는다. 없으면 그 테스트(모듈)는 skip:
  - `EXAM_KIT_PATH`·`EXAM_FORM_PATH`: 누름틀 양식 킷 폴더와 그 서식 hwpx(엔진 회귀의 첫 기준)
  - `EXAM_KIT_B_PATH`·`EXAM_FORM_B_PATH`: 글자 자리 양식 킷 폴더와 그 서식 hwpx
  - `EXAM_KITS_DIR`: 로컬 학교 킷 폴더(저장소에 학교 이름이 없는지 검사 — `test_no_school_names.py`)
- 1학기 제출본이 필요한 테스트(`제출본_hwpx` — `test_build`·`test_reverse`의 대조)는 없으면 skip — `EXAM_SUBMITTED_PATH`.
- 실문항 글을 테스트·픽스처에 넣지 않는다. 합성 문항은 실제 시험 문항과 주제·수치가 겹치지 않게 만든다.

## 버전 올리기

`python-hwpx-automation`은 범위 지정(`>=7.2,<8`)이고 재현성은 `uv.lock`이 진다. `==` 고정은 쓰지 않는다.

1. `uv lock --upgrade-package python-hwpx-automation` → `uv sync`
2. `uv run pytest -q -m "not render"` 전부 통과 + 렌더 테스트 2~3개(한 번에 하나)
3. 등록된 학교 킷이 있으면 기준 산출물을 다시 뽑아 `uv run python -m exam_kit.gate <기준 폴더> <새 폴더>`로 견주고, 기준 제출본 재현의 (쪽, 단) 대조와 `exam_kit.fit` 줄 대조가 전과 같은지 본다. 다르면 사용자 검수에 올린다.
4. `uv.lock`만 pathspec으로 커밋하고 보고서에 버전을 적는다.

렌더 런타임(플러그인의 oracle 환경)은 프로젝트 환경과 따로 움직인다 — 렌더 문제를 보고할 때 두 버전을 함께 적는다.
