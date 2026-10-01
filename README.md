# hwpx-school

학교 문서를 마크다운 원고 한 장에서 한글(HWPX)로 만듭니다. 학교 서식 파일 그대로 위에 조판하고, 실제 한글로 렌더해
배치를 확인합니다. [python-hwpx](https://github.com/airmang/python-hwpx) 위에서 동작합니다.

| 문서 | 폴더 | 할 수 있는 것 |
|---|---|---|
| 지필평가 원안지 | `exam/` | 학교 서식 그대로 문항지·답 표시본(정답 형광펜) 두 판. 〈보기〉·〈조건〉·자료 박스, 표, 그림, 코드, 인라인 수식(`$LaTeX$`), 세트 문항, 짝짓기 답항표. 렌더로 단·쪽 배치를 굳히고 [기계] 검사 보고서를 씁니다 |
| 학습지 | `worksheet/` | hwpx·docx. 머리띠·확인도장·블록 10종 |
| 수행평가 문제지 | `assessment/` | 학생용·정답용(정답은 메모) 두 파일 |

## 시작하기

Python 3.13과 [uv](https://docs.astral.sh/uv/)가 필요합니다. 배치 확인(렌더)에는 한컴오피스 한글(Windows 또는 macOS)이 필요합니다.

    git clone https://github.com/airmang/hwpx-school
    cd hwpx-school/exam
    uv run pytest -q -m "not render"     # 한글 없이 — 합성 서식·합성 킷으로 엔진 확인
    uv run python -W ignore -m exam_kit.build tests/fixtures/합성서식_6문항.md \
        --kit kits/synthetic --form kits/synthetic/synthetic_form.hwpx --out ~/hwpx-school-예시   # 한글 렌더까지

한/글에서 이미 만든 원안지(`.hwp`·`.hwpx`)는 원고로 되돌릴 수 있습니다 — `uv run python -m exam_kit.reverse <원안지> --kit <학교 킷> --out <폴더>/원고.md`. 서술형·논술형은 원본 모양 그대로 보존 블록으로 옮겨 심습니다.

학습지·수행평가는 `worksheet/`·`assessment/`에서 `uv run --python 3.13 pytest -q`로 시작합니다. 폴더마다 독립 프로젝트입니다.

## 학교 양식

학교마다 다른 양식은 각자 자기 PC에 만드는 **학교 킷**이 갖습니다. 이 저장소에는 학교 무관 엔진, 범용 스킬, 합성
씨앗 킷과 합성 테스트만 있습니다. 새 학교 원안지는 빈 서식 한 장으로 등록합니다 —
[학교 등록](skills/exam/references/학교-등록.md).

## AI 에이전트와 쓰기

`skills/`의 `SKILL.md`(exam·worksheet·assessment)를 Claude 같은 에이전트에 주면, 에이전트가 원고를 쓰고 조판·검사를
돌립니다. 원고 문법은 [문법](skills/exam/references/문법.md)에 있습니다.

검사 결과는 "기계 잔존 N"일 뿐입니다. 시험지로 내기 전에 교사가 직접 확인합니다.

## 아직 안 되는 것

- 서술형·논술형 블록을 원고에서 조판하기(지금은 원본 그대로 옮겨 심는다)
- 가정통신문·공문(기안) 등 다른 학교 문서

## 라이선스

Apache-2.0 — [LICENSE](LICENSE), [NOTICE](NOTICE)
