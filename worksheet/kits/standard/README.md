# standard 킷 (배포용 — 중립 슬롯)

학교·교사·과목·학년이 **빈 슬롯**인 동작하는 킷이다. 어느 학교의 양식에서도 뽑지 않았다 —
`skeleton.hwpx`는 `scripts/씨앗_스켈레톤.py`가 python-hwpx 기본 템플릿에 킷 역할이 쓰는
글자·문단·테두리 모양만 더해 만든 합성 씨앗이다. 스타일과 용지 설정만 담고 있고, 그림·작성자
메타데이터는 들어 있지 않다. 스크립트는 더한 모양의 번호를 이 `kit.json`의 `styles`에 다시
쓰므로 스켈레톤과 킷이 늘 짝이다 — 씨앗 값을 바꿀 때는 스켈레톤을 손으로 고치지 않고
스크립트를 고쳐 다시 돌린다:

    uv run --python 3.13 python scripts/씨앗_스켈레톤.py

이 킷 자체가 다른 모든 킷의 **씨앗**이다(`worksheet.kit.seed_kit_path()`가 이 `kit.json`을
가리킨다) — `extract-kit`이 새 킷을 만들 때 이 파일을 복사해서 시작한다. 실제 학교 킷은
그 학교 자신의 양식 hwpx에서 `extract-kit`으로 뽑는다(아래).

## 표준 킷을 그대로 쓰는 절차

이 디렉터리는 배포 패키지 **안**에 있다 — 여기서 `kit.json`을 제자리에서 고치면 패키지를
업데이트할 때 그 수정이 덮여 사라진다. 그러므로:

① `kits/standard/`(이 디렉터리 전체, `kit.json` + `skeleton.hwpx`)를 자기 프로젝트로
   복사한다(예: `kits/우리학교/`).
② 복사본의 `kit.json`에서 `kit` 이름을 그 킷을 가리킬 이름으로 바꾼다 — 이 이름은 그 킷을
   쓰는 마크다운 회차의 front matter `kit:` 값과 반드시 같아야 한다(다르면 `compose()`가
   `킷 이름이 다르다`로 거부한다).
③ 복사본의 `kit.json`에서 `slots`(`school`·`teacher`·`subject`·`grade`)를 채운다.
④ `worksheet check`를 돌려 `빈 슬롯: …` 문제가 안 나오는지 확인한다.

## 다른 학교 양식으로 킷 만들기

표준 킷의 슬롯만 채워서는 값(치수·색·스타일 ID)이 다른 학교 양식에 안 맞는다 — 그 양식
hwpx로 킷을 하나 더 뽑는다:

    uv run python -m worksheet.cli extract-kit <양식.hwpx> kits/<이름> \
      --school "○○고등학교" --teacher "△△T" --subject 정보 --grade 2학년

`dest/kit.json`이 이미 있으면 `extract-kit`은 건드리지 않는다(저작물 — 손으로 맞춘 스타일
매핑을 지킨다). 다시 쓰려면 `--force`를 더한다. 그 다음 `kit.json`의 스타일 ID 매핑을 그
양식에 맞게 고치고 `verify_kit`이 빈 리스트를 내는지 확인한다.

## 글꼴 바꾸기

이 킷은 기본 템플릿의 함초롬돋움·함초롬바탕(한컴오피스 기본 포함 — Windows·Mac 공통)만
쓴다. 그래서 씨앗의 `fontMap`(`{"원래 글꼴": "바꿀 글꼴"}` 꼴의 선택 키)은 비어 있다 —
학교 양식이 일반 PC에 없는 장식 글꼴을 쓸 때 그 킷의 `fontMap`으로 스켈레톤을 뽑으면서
기본 글꼴로 옮긴다(근거는 [양식-해부](../../references/양식-해부.md)의 §2.1 fontface
문단). 글꼴을 바꾸려면 `kit.json`의 `fontMap`을 고치고 다음을 돌린다 — source와 dest가
같은 스켈레톤이어도 안전하다:

    uv run python -m worksheet.cli extract-kit kits/<이름>/skeleton.hwpx kits/<이름>
