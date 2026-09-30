# hwpx-school

학교에서 쓰는 한글(HWPX) 문서를 마크다운 한 장에서 만드는 도구입니다.
[python-hwpx](https://github.com/airmang/python-hwpx) 엔진 위에서 동작합니다.

| 폴더 | 문서 | 스킬 |
|---|---|---|
| `exam/` | 지필평가 원안지(학교 서식 그대로, 문항지·답 표시본) | `skills/exam` |
| `worksheet/` | 학습지(hwpx·docx) | `skills/worksheet` |
| `assessment/` | 수행평가 문제지(학생용·정답용) | `skills/assessment` |

학교마다 다른 양식은 각자 자기 PC에 만드는 **학교 킷**이 갖습니다. 이 저장소에는 학교 무관 엔진,
범용 스킬, 합성 씨앗 킷과 합성 테스트만 있습니다. 새 학교 원안지는 빈 서식 한 장으로 등록합니다 —
`skills/exam/references/학교-등록.md`.

각 폴더는 독립 [uv](https://docs.astral.sh/uv/) 프로젝트입니다. 실제 한글 렌더 검사는 한컴오피스가 설치된 Mac에서 돕니다.
