---
name: worksheet
description: 학교 양식 그대로의 학습지(hwpx·docx)를 마크다운 한 장에서 조판한다. '학습지 만들어줘', 차시 학습지·활동지·빈칸 학습지 hwpx·docx 제작, 학습지 양식 조판 요청이면 이 스킬을 쓴다. 학교·교사마다 다른 양식은 사용자 로컬 학교 킷이 갖는다. 내용(활동의 연쇄·누출 규율)은 내용 스킬이 정하고, 이 스킬은 형태(머리띠·확인도장·원문자 제목·블록 10종 — 나란히·칸 안 그림 포함)만 맡는다.
---

# worksheet — 학습지 hwpx·docx 조판 (학교 무관)

엔진과 문법의 정본은 hwpx-school `worksheet/`다. **작업 전에 그 안의 `SKILL.md`와 `references/블록-문법.md`를 읽는다.**

## 킷 — 학교 킷은 저장소 밖

- 학교·교사마다 다른 것(머리띠 슬롯의 학교·교사·과목, 스켈레톤, 글꼴)은 **학교 킷**이 갖는다. 학교 킷은 제품 저장소에 없다 — 각 사용자가 자기 PC에 만든다(폴더 하나 = 킷 하나, 그 안의 `SKILL.md`가 그 킷의 경로·주의를 적는다).
- 사용자가 학습지를 요청하면 먼저 그 사용자의 학습지 학교 킷 폴더의 `SKILL.md`를 찾아 읽는다. 없으면 킷부터 만든다.
- 저장소의 `worksheet/kits/standard`는 **씨앗 킷**이다 — 슬롯이 비어 머리띠가 공백으로 나온다. 새 학교 킷은 이것을 자기 킷 폴더로 복사해 슬롯(`slots`)을 채우고, 자기 양식이 다르면 `worksheet/SKILL.md`의 절차대로 그 양식에서 스켈레톤을 다시 뽑아 스타일 ID를 맞춘다.
- md 의 front matter `kit:` 은 그 킷 이름.
- 산출물과 md 는 그 차시의 수업 자료 폴더에 둔다(엔진 폴더·저장소 안에 두지 않는다).

## 형식 고르기 — hwpx 냐 docx 냐

사용자가 docx 를 요청하면(예: "워드로도", "구글 문서로 열 것") `-o <이름>.docx`, 아무 말이
없으면 `-o <이름>.hwpx`, 둘 다 요청하면 같은 md 를 두 번(확장자만 바꿔서) 조판해 둘 다
낸다. 마크다운·킷은 형식과 무관하게 그대로다 — `-o` 의 확장자만 바뀐다.

## 명령 (엔진 폴더 `worksheet/`에서)

    uv run --python 3.13 python -m worksheet.cli compose <md 절대경로> --kit <학교 킷 폴더> -o <hwpx 또는 docx 절대경로>
    uv run --python 3.13 python -m worksheet.cli check   <md 절대경로> --kit <학교 킷 폴더> --out <hwpx 또는 docx 절대경로>

- 종료코드 `0` 통과 · `1` 검사 문제(JSON 의 `"문제"` 를 읽고 md 를 고친다) · `2` 입력 오류(`오류: …` 한 줄 — md 나 kit.json 을 고친다).
- `check` 의 `pages_estimate` 는 hwpx 만의 근사값이다(docx 는 처음부터 `None`). 쪽수·쪽
  나눔·도형 위치·그린 모양은 형식마다 다른 실물 렌더로 확인한다:
  - **hwpx** — 실한컴 렌더(한글 앱이 뜬다 — 직렬로만, 공용 한컴은 다른 세션과 나눠 쓴다):
    `uv run --python 3.13 python -c "from pathlib import Path; from worksheet.render import render_hancom; print(render_hancom(Path('<hwpx>'), Path('<png>')))"`
  - **docx** — LibreOffice 헤드리스(`soffice`·`pdftoppm`(poppler) 필요):
    `uv run --python 3.13 python -c "from pathlib import Path; from worksheet.render import render_libreoffice; print(render_libreoffice(Path('<docx>'), Path('<png>')))"`
  렌더 PNG 를 눈으로 본 뒤에 사용자에게 건넨다.
- docx 를 구글 문서에서도 열 계획이면 킷의 `docx.font`가 구글 문서에도 있는 글꼴인지 먼저 확인한다 — 맑은 고딕은 구글 문서가 굴림으로 대체해 확인도장 문구가 두 줄로 꺾일 수 있다. 글꼴 값을 바꾸는 것은 사용자의 판단이다.
- pytest: `-m`을 주지 않는다(addopts가 한컴·LibreOffice·구글 문서 테스트를 뺀다 — `-m`을 주면 그 기본이 덮여 공용 한컴이 돈다).

## 이 스킬이 하지 않는 것

- 학습지 **내용** 판정(학습지=개념, 활동의 연쇄, 시험 골격 누출) — 내용 스킬 소관.
- 원본 교과서 스캔 그림 재사용 — 그림은 새로 그려 PNG 로 넣는다.
- 학교 킷·학교 이름을 저장소나 공개물에 넣는 것. 공개 배포 전 위생 검사는 `worksheet/scripts/export_public.py <dest> --forbidden <로컬 금칙어 파일>`.
