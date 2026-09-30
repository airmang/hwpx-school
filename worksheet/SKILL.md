---
name: worksheet
description: "학교 양식 그대로의 학습지(hwpx·docx)를 마크다운 한 장에서 만드는 스킬. '학습지 만들어줘', 차시 학습지·수업 활동지·빈칸 학습지 제작, 기존 hwpx 학습지 양식 템플릿화, 학교 양식으로 조판 요청이면 이 스킬을 쓴다. 머리띠·확인도장·원문자 섹션 제목·비교표·답칸·데이터표 같은 양식 고유 블록을 킷으로 기술하고, 마크다운+한글 펜스로 내용을 써서 hwpx 또는 docx로 조판한다(출력 경로의 확장자로 고른다). v0.1은 표준 양식 + 슬롯 채우기를 지원하고, 다른 학교 양식은 킷을 새로 뽑은 뒤 스타일 ID를 손으로 맞춰 대응한다."
---

# worksheet (학습지 hwpx 조판)

학습지 한 회차 = 마크다운 한 장. 형태는 **킷**이, 내용은 **마크다운**이 갖는다.

## 3층

1. **킷** — 학교 양식을 데이터로 기술(`kits/<이름>/kit.json` + `skeleton.hwpx`)
2. **엔진** — `worksheet.compose`가 마크다운을 킷 위에 앉힌다
3. **스킬** — 이 문서

## 쓰는 법

    uv run python -m worksheet.cli compose 차시15.md --kit kits/standard -o 차시15.hwpx
    uv run python -m worksheet.cli check   차시15.md --kit kits/standard --out 차시15.hwpx

`-o`/`--out`(`check`는 `--hwpx`도 같은 뜻으로 받는다)의 **확장자**로 출력 형식을 고른다 —
`.hwpx` 또는 `.docx`. md·킷은 그대로 두고 `-o 차시15.docx`로만 바꾸면 같은 회차를 docx로
조판한다. 그 밖의 확장자는 md·킷을 읽기도 전에
`출력 형식을 알 수 없다: <확장자> — .hwpx 또는 .docx`로 거부된다.

## docx 출력

`.docx`로 조판하면 같은 계획(머리띠·제목·블록)을 Word·구글 문서 둘 다에서 여는 docx로
그린다 — hwpx와 달리 **떠 있는 도형을 쓰지 않는다.** 그 대가로 두 자리가 hwpx와 다르게
보인다: 확인도장은 머리띠 표의 마지막 칸(테두리 없는 간격 칸 다음)이고, 섹션 제목의
원문자 번호는 도형이 아니라 글자다(❶❷…⓴, 스물한 번째부터는 `(21)`). 글꼴은 킷마다
하나(`kit.json`의 선택 키 `docx.font`, 생략하면 맑은 고딕)이고, 표 안 모든 글자가 이
글꼴을 쓴다.

구글 문서에는 맑은 고딕이 없어 굴림으로 대체되고, 확인도장 문구가 두 줄로 꺾일 수 있다
— 구글 문서에서도 한 줄로 보이게 하려면 그 킷의 `docx.font`를 구글 문서에 있는 글꼴
(나눔고딕·Noto Sans KR 등)로 바꾼다. 다만 그 글꼴이 배포 대상 PC(특히 Windows)에도
설치돼 있는지는 별도로 확인해야 한다 — 엔진은 글꼴 설치 여부를 검사하지 않는다.

docx 실물을 한글 앱 없이 빠르게 보려면 LibreOffice 헤드리스 렌더(`soffice`와 poppler의
`pdftoppm`이 있어야 한다):

    uv run python -c "from pathlib import Path; from worksheet.render import render_libreoffice; print(render_libreoffice(Path('차시15.docx'), Path('차시15.png')))"

hwpx의 실한컴 렌더(M-7)와 같은 자리다 — 간이 렌더이므로 최종 판정은 사람이 실제
워드프로세서(Word·구글 문서)로 열어 본다.

새 학교 양식은 킷부터 뽑는다:

    uv run python -m worksheet.cli extract-kit <양식.hwpx> kits/<이름> \
      --school "○○고등학교" --teacher "△△T" --subject 정보 --grade 2학년

슬롯 인자를 안 주면(또는 `kit.json`이 이미 있으면 그대로) 중립 킷이 된다 — `kit.json`이
이미 있으면 `extract-kit`은 그것을 건드리지 않는다(저작물). `extract-kit`이 새로 쓰는
`kit.json`은 표준 킷의 스타일 ID를 그대로 씨앗 삼은 것이지, 그 양식을 실측해 자동으로
맞춘 값이 아니다 — 다른 학교 양식이면 거의 항상 값이 틀리므로, `header.xml`을 직접 보고
`kit.json`의 스타일 ID·치수를 그 양식에 맞게 손으로 고친 뒤 `worksheet check`로 확인한다.
킷 규격과 씨앗 값의 근거는 [양식-해부](references/양식-해부.md)를 본다.

**종료코드**: `0` 통과 · `1` `check`가 [기계] 검사 문제를 냄(md/킷 자체는 읽었다) · `2`
입력(md·kit.json)을 읽을 수 없음 — `오류: <메시지>`를 stderr에 한 줄로 낸다. 그 밖의
예외는 버그이므로 잡지 않고 트레이스백을 그대로 낸다. 문구는
[블록-문법](references/블록-문법.md)의 "오류 문형 한눈에"에 정리돼 있다.

## 문법

블록 10종과 속성은 [블록-문법](references/블록-문법.md). 양식 구조와 스타일 매핑의 근거는
[양식-해부](references/양식-해부.md).

## 검사

[기계]/[의미]를 나눈다. 스크립트가 낼 수 있는 판정은 [검사-레지스트리](references/검사-레지스트리.md)의
M-1~M-7뿐이고, **내용 품질과 "원본과 같은 학습지로 보이는가"라는 총평은 사람이 판정한다**.
`check`가 통과해도 "기계 잔존 0"까지만 보고한다. M-2(패키지)·M-3(슬롯 잔존)·M-6(미리보기)은
hwpx·docx 둘 다 돈다 — M-6은 docx에서 근사 쪽수 없이 "실물 렌더로 본다"는 안내만 낸다.

렌더는 두 층이다. 빠른 층은 `render_layout_preview`(쪽수·용지·표 수, hwpx 전용)이고, 실물
층은 형식마다 다르다: hwpx는 `worksheet.render.render_hancom`이 한글 앱을 몰아 뽑는 실한컴
PDF, docx는 `worksheet.render.render_libreoffice`가 LibreOffice 헤드리스로 뽑는 간이
PDF다(M-7). **도형(원문자 타원·확인도장)의 외형과 위치는 실물 층에서만 보인다** — hwpx의
빠른 층은 도형을 `[도형]` 자리표시자로 그리고, docx는 애초에 도형을 쓰지 않으므로(위
"docx 출력") 조판된 글자·표 자체가 곧 실물이다. 실한컴 렌더는 GUI를 띄우므로 직렬로만
돌리고(1쪽 ≈ 6초), pytest에서는 `-m hancom`으로 분리한다(docx의 LibreOffice·구글 문서
렌더는 각각 `-m libreoffice`·`-m gdocs`).

## 하지 않는 것

- 학습지 내용 품질·전이 누출 판정 — 수업 준비 스킬 소관이다.
- 원본 교과서 스캔 재사용 — 그림은 새로 생성해서 넣는다.
- 실한컴 렌더의 병렬 실행 — 단일 GUI 세션이라 직렬만 안전하다.
