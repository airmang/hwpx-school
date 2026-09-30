# worksheet — 학습지 hwpx·docx 조판 스킬

학교 양식 그대로의 학습지(.hwpx·.docx)를 마크다운 한 장에서 만드는 엔진 + 에이전트 스킬.
**쓰는 법은 [SKILL.md](SKILL.md)를 본다** — 이 문서는 저장소 구조와 개발 환경만 담는다.

## 구조

```
worksheet/          조판 엔진 — skeleton·kit·style·md·furniture·blocks·backends(hwpx·docx)·
                     compose·checks·render·cli
kits/
  standard/          배포용 중립 킷 — 학교·교사·과목·학년 슬롯이 비어 있다. 스켈레톤은
                     `scripts/씨앗_스켈레톤.py`가 python-hwpx 기본 템플릿에서 합성한다
  <로컬 실 양식 킷>/    로컬 전용(배포 금지) — 실 슬롯값 + 원본 스켈레톤. `kits/`를 직접 본다
tests/               pytest 스위트. 한글 앱·LibreOffice·구글 문서를 실제로 부르는 실물 렌더
                     테스트만 각각 `-m hancom`·`-m libreoffice`·`-m gdocs`로 분리
SKILL.md             스킬 문서 — 언제·어떻게 쓰는가, 3층 구조, 검사 개요
references/          SKILL.md가 가리키는 상세 참고 자료 3종 (배포 대상)
```

`worksheet/`는 킷을 바꿔 넣으면 그 킷의 값으로 조판하는 패키지다 — 단, 킷이 바꿀 수 있는 건
**값**(치수·색·스타일 ID·문구, docx는 `docx.font` 하나가 더 있다)뿐이다. **구조**(블록마다
표를 어떻게 구성하는가, 머리띠 4칸의 역할 순서, 섹션 제목 = 원문자 번호 + 글 + 확인도장,
도장을 앉히는 방식)는 엔진 코드에 있고 킷으로 바꿀 수 없다 — hwpx·docx 둘 다 같은 계획
(`worksheet/plan.py`)에서 그리므로 구조 자체는 형식과 무관하게 하나다. 형식별 그리기는
`worksheet/backends/`에 갈려 있다: hwpx는 도형(원문자 타원·확인도장)을 쓰고, docx는 Word·
구글 문서 둘 다에서 열리도록 떠 있는 도형 대신 표 칸과 글자로 그린다(자세한 차이는
[SKILL.md](SKILL.md)의 "docx 출력"과 [양식-해부](references/양식-해부.md)의 "docx 출력"
절을 본다). v0.1이 실제로 지원하는 범위는 "표준 양식 + 슬롯 채우기"다 — 다른 학교 양식으로
킷을 새로 만들려면 `extract-kit`으로 스켈레톤을 뽑은 뒤, 그 양식의 `header.xml`에서 스타일
ID를 직접 찾아 `kit.json`의 매핑을 손으로 고쳐야 한다(스타일 ID를 자동으로 찾아 주는 도구는
아직 없다).

## 개발 환경

`python-hwpx[preview]>=6.4,<7` · `python-docx>=1.2,<2` · Python 3.13 · uv로 프로젝트를
격리한다(시스템 python에는 이 둘이 없다). 하드 고정(`==6.4.0`) 대신 범위 고정이다 —
재현성은 커밋된 `uv.lock`이 맡고, 버전을 올릴 때의 회귀 검사는 로컬 전용 재현 테스트
(`tests_local`)와 실물 렌더가 맡는다.

    uv sync
    uv run pytest -q

조판 자체는 `uv sync`만으로 되지만, **결과물을 한글 앱에서 원본과 같은 모양으로 보려면
킷의 `fonts` 목록에 있는 글꼴이 그 기기에 설치돼 있어야 한다.** 표준 킷은 기본 템플릿의
어디서나 있는 글꼴(함초롬돋움·함초롬바탕 — 한컴오피스 기본 포함, Windows·Mac 공통)만
쓴다. 학교 양식을 새로 킷화했는데 그 원본이 일반 PC에 없는 글꼴을 쓴다면 그 킷의
`fontMap`으로 스켈레톤을 뽑을 때 기본 글꼴로 옮길 수 있다(자세한 내용은
[양식-해부](references/양식-해부.md)의 §2.1 fontface 문단을 본다) — 안 쓰면 그 글꼴이 없는 기기에서 한글 앱이 폭이 더 넓은 대체 글꼴로 다시 줄을
맞추면서 좁은 칸(예: 머리띠의 학교명 칸)에서 글자가 줄바꿈될 수 있다.

`@pytest.mark.hancom`이 붙은 테스트는 한글 앱 GUI를 실제로 몰아 렌더한다(1쪽 ≈ 6초) —
`pyproject.toml`의 `addopts`(`-m 'not hancom and not libreoffice and not gdocs'`)로 기본
실행에서 제외된다. 따로 돌리려면:

    uv run pytest -m hancom

이 테스트는 `python-hwpx-automation[oracle]`이 설치된 별도 런타임과 한글 앱의 macOS
자동화(TCC) 권한을 요구한다 — 자세한 내용은 `worksheet/render.py`와
[검사-레지스트리](references/검사-레지스트리.md)의 M-7을 본다.

docx는 같은 자리를 두 마커로 나눠 본다. `@pytest.mark.libreoffice`는 LibreOffice
헤드리스로 docx→PDF→PNG를 뽑는다(`soffice`와, PDF를 쪽별 PNG로 자르는 poppler의 `pdftoppm`이
있어야 한다) — GUI가 없어 hancom
렌더보다 빠르고, 실한컴이 없는 머신·CI에서도 docx 형태를 실물로 본다. `@pytest.mark.gdocs`는
구글 드라이브의 전용 임시 폴더 하나로 docx를 올렸다 PDF로 받아 오고(성공·실패와 무관하게
끝나면 그 폴더를 지운다) 구글 문서가 실제로 여는 모습(글꼴 대체 등)을 본다 — `rclone`과 그
드라이브 접근 설정, 그리고 `pdftoppm`이 있어야 한다. 기본 실행에서 둘 다 빠진다:

    uv run pytest -m libreoffice
    uv run pytest -m gdocs

## 새 학교 양식으로 킷 만들기

    uv run python -m worksheet.cli extract-kit <원본 학습지.hwpx> kits/<새 이름> \
      --school "○○고등학교" --teacher "△△T" --subject 정보 --grade 2학년

`dest/skeleton.hwpx`는 매번 새로 뽑는다(생성물). `dest/kit.json`은 **없을 때만** 씨앗
(`kits/standard/kit.json`)을 복사해 슬롯 인자로 채운다 — 이미 있으면 손으로 맞춘 스타일
매핑이 재추출 한 번에 사라지지 않도록 건드리지 않는다(저작물). 슬롯 인자 없이 그대로
실행하면(또는 이미 있는 `kit.json`을 지키면) 중립 킷이 된다. `kit.json`이 이미 있는데 슬롯
인자를 주면(예: `--school`) `--force` 없이는 `오류: kit.json 이 이미 있다`로 거부된다 —
손으로 고친 매핑을 슬롯 인자가 조용히 덮어쓰는 사고를 막는다. 이미 있는 `kit.json`도 씨앗+
인자로 다시 쓰려면 `--force`를 더한다. 원본 hwpx를 안전하게 중립화하지 못하면(섹션이
둘 이상, 첫 문단의 컨트롤 안에 내용이 있음, 세척 뒤 사후조건 실패 등) `오류: 스켈레톤을
안전하게 만들지 못했다: …`로 거부하고 아무 파일도 쓰지 않는다. 문법·속성·검사의 자세한
내용은 [SKILL.md](SKILL.md)와 `references/`를, 킷 뽑기 절차(스켈레톤 미리보기 세척 포함)는
[양식-해부](references/양식-해부.md)의 "킷 뽑기"를 본다.

## 배포 위생

저장소 전체가 공개다. 학교 킷·로컬 전용 테스트(`재현/`·`tests_local/`)는 저장소 밖에 두고, 추적하는
파일 어디에도 학교·교사 실명이 없어야 한다. `worksheet.checks.check_hygiene(경로, 금칙어_목록)`로
파일 하나 또는 디렉터리를 검사한다. 엔진만 따로 묶어 내보낼 때는
`scripts/export_public.py <dest> --forbidden <금칙어 파일>`이 실행에 필요한 경로(`SKILL.md`·
`README.md`·`pyproject.toml`·`uv.lock`·`references/`·`worksheet/`·`kits/standard/`·`tests/`)만
복사하고 **내보낸 트리 전체**를 검사한다. 금칙어 목록 자신은 저장소에 두지 않는다 — 각자 로컬에 갖는다.
