# report — 보고서·계획서

한/글로 저장한 **견본**(글 자리에 `{{자리표시}}`를 적은 문서)의 서식 그대로 보고서·계획서를 만든다.
장 제목 띠, 제목표, □·ㅇ·-·※ 위계의 색·글꼴·들여쓰기는 견본이 갖고, 엔진은 그 문단·표를 복제해
글만 바꾼다. 조립은 python-hwpx-automation `office.authoring.design`이 한다.

    uv run python -m report_kit roles kits/standard
    uv run python -m report_kit make kits/standard/예시_계획.json --kit kits/standard -o /tmp/예시.hwpx

- `kits/standard` — 합성 씨앗 킷. `견본.hwpx`는 `scripts/씨앗_견본.py`가 python-hwpx 기본 템플릿에서
  만든다. 다시 만든 뒤 `uv run python -m report_kit register kits/standard/견본.hwpx kits/standard`.
- 학교·교육청 견본은 사용자 로컬 킷 폴더에 둔다. 절차는 `skills/report/SKILL.md`.
- 테스트: `uv run pytest -q` (한컴 렌더는 `-m hancom`).
