"""실한컴 렌더 — python-hwpx-automation[oracle]을 별도 런타임에서 부른다."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import uuid
from dataclasses import dataclass
from pathlib import Path

_후보 = "~/.claude/plugins/cache/hwpx/hwpx-plugin/*/.hwpx-mcp-runtime/envs/*/gen-*/bin/python"


@dataclass(frozen=True)
class RenderResult:
    """실한컴 렌더 결과 — 쪽수의 권위는 이 값뿐이다(M-6 `preview_stats()["pages_estimate"]`는
    근사값)."""

    pages: int
    pngs: tuple[Path, ...]
    pdf: Path


def _버전(경로: Path) -> tuple[tuple[int, str], ...]:
    """`.../hwpx-plugin/<버전>/...` 조각을 `(정수, 원본 문자열)` 쌍의 튜플로 판다.

    사전순 문자열 비교로는 `"2.10.0" < "2.2.0"`이 되어 틀린다 — 숫자로 비교해야 한다.
    조각이 숫자로 안 읽히면(프리릴리스 접미사 등, 예: `"0-beta"`) `int()`가 `ValueError`를
    던진다 — 0으로 치고 원본 조각 문자열을 보조 키로 붙여 그래도 결정적으로 정렬되게 한다.
    각 자리를 `(정수, 문자열)` 쌍으로 감싸는 이유: 조각 개수가 다른 버전끼리 비교할 때도
    (예: `"2.2"` vs `"2.2.0"`) 같은 자리에서 늘 정수-정수 또는 문자열-문자열만 맞붙는다 —
    평평한 튜플 끝에 문자열 하나만 덧붙이면 조각 개수가 다를 때 정수와 문자열이 같은
    자리에서 맞붙어 `TypeError`가 날 수 있다.
    """
    조각들 = 경로.parts
    버전_문자열 = 조각들[조각들.index("hwpx-plugin") + 1]
    쌍들 = []
    for 조각 in 버전_문자열.split("."):
        try:
            쌍들.append((int(조각), ""))
        except ValueError:
            쌍들.append((0, 조각))
    return tuple(쌍들)


def _pick(paths: list[Path]) -> Path:
    """오라클 런타임 후보 중 버전이 가장 높은 것 — `oracle_python()`의 glob 결과에서 쓴다."""
    return max(paths, key=_버전)


def oracle_python() -> Path:
    """python-hwpx-automation[oracle]이 설치된 인터프리터를 찾는다.

    ① 환경변수 `HWPX_ORACLE_PY`가 있으면 그 경로를 그대로 쓴다(없는 파일이면
    `FileNotFoundError`) — CI·다른 머신에서 플러그인 캐시 경로 없이도 오라클을 지정할 수
    있게 한다. ② 없으면 이 머신의 플러그인 캐시를 glob해 후보 중 버전이 가장 높은 것을
    고른다(`_pick`).
    """
    지정_경로 = os.environ.get("HWPX_ORACLE_PY")
    if 지정_경로:
        경로 = Path(지정_경로)
        if not 경로.exists():
            raise FileNotFoundError(f"HWPX_ORACLE_PY 가 가리키는 경로가 없다: {경로}")
        return 경로

    경로들 = list(Path("/").glob(_후보.replace("~", str(Path.home())).lstrip("/")))
    if not 경로들:
        raise FileNotFoundError(
            "실한컴 오라클 런타임을 찾지 못했다. hwpx 플러그인이 설치돼 있어야 한다: " + _후보
        )
    return _pick(경로들)


def _parse_result(stdout: str) -> RenderResult:
    """서브프로세스 stdout의 **마지막 줄**(JSON 한 줄)을 `RenderResult`로 바꾼다. 순수 함수 —
    한글 앱 없이 단위 테스트한다.

    앞에 다른 출력(폰트 로딩 메시지 등)이 섞여도 마지막 줄만 본다. 마지막 줄이 JSON이
    아니거나 stdout이 비어 있으면(렌더 스크립트가 계약을 어겼다는 뜻) `RuntimeError`.
    JSON은 맞지만 dict가 아니거나 `pages`/`pngs`/`pdf` 키가 없으면(형태는 맞는데 내용이
    틀린 경우) bare `KeyError`/`TypeError`를 새게 두지 않고 같은 계약으로 `RuntimeError`.
    `pngs` 개수가 `pages`와 다르면(렌더 스크립트 자체의 앞뒤가 안 맞는 결과) 마찬가지다.
    """
    줄들 = [줄 for 줄 in stdout.strip().splitlines() if 줄.strip()]
    if not 줄들:
        raise RuntimeError(f"실한컴 렌더 실패: stdout이 비어 있다: {stdout!r}")
    try:
        데이터 = json.loads(줄들[-1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"실한컴 렌더 실패: stdout 마지막 줄이 JSON이 아니다: {stdout!r}") from e
    try:
        결과 = RenderResult(
            pages=int(데이터["pages"]),
            pngs=tuple(Path(p) for p in 데이터["pngs"]),
            pdf=Path(데이터["pdf"]),
        )
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"실한컴 렌더 결과를 읽을 수 없다: {데이터!r}") from e
    if len(결과.pngs) != 결과.pages:
        raise RuntimeError(
            f"실한컴 렌더 결과를 읽을 수 없다: pngs 개수가 pages와 다르다: {데이터!r}"
        )
    return 결과


def render_hancom(hwpx: Path, out_png: Path, *, dpi: int = 110) -> RenderResult:
    """한글 앱으로 PDF를 뽑고 쪽마다 PNG로 저장한다. 1쪽 ≈ 6초, 직렬로만.

    PNG 이름은 쪽수와 무관하게 항상 `<out_png의 stem>-001.png`, `-002.png` …다(한 쪽짜리
    문서라도 분기 없이 같은 이름 규칙). 서브프로세스는 마지막 줄에 JSON 한 줄
    (`{"pages": N, "pngs": [...], "pdf": "..."}`)을 찍고, 이 함수가 그것을 `_parse_result`로
    읽는다. 서브프로세스가 실패하면(0이 아닌 종료 코드) stderr를 담아 `RuntimeError`.
    """
    hwpx, out_png = Path(hwpx).resolve(), Path(out_png).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pdf = out_png.with_suffix(".pdf")
    stem = str(out_png.with_suffix(""))

    코드 = textwrap.dedent(f"""
        import json, sys
        import pymupdf
        from hwpx_automation.office.rendering.oracle import MacHancomOracle
        oracle = MacHancomOracle()
        if not oracle.available():
            sys.exit("실한컴 오라클을 쓸 수 없다 — 한글 설치와 자동화(TCC) 권한을 확인한다")
        결과 = oracle.render_pdf({str(hwpx)!r}, {str(pdf)!r})
        if not 결과:
            sys.exit("렌더 실패")
        문서 = pymupdf.open(결과)
        pngs = []
        for i, 쪽 in enumerate(문서):
            이름 = {stem!r} + f"-{{i + 1:03d}}.png"
            쪽.get_pixmap(dpi={dpi}).save(이름)
            pngs.append(이름)
        print(json.dumps({{"pages": len(문서), "pngs": pngs, "pdf": {str(pdf)!r}}}))
    """)
    결과 = subprocess.run(
        [str(oracle_python()), "-c", 코드],
        capture_output=True, text=True, timeout=600,
    )
    if 결과.returncode != 0:
        raise RuntimeError(f"실한컴 렌더 실패: {결과.stderr}")
    return _parse_result(결과.stdout)


def _쪽_번호(p: Path) -> int:
    """`<접두>-1.png`·`<접두>-01.png` 같은 이름의 쪽 번호. `pdftoppm`은 쪽수에 따라 0-패딩
    폭이 다르다(1~9쪽은 폭 없음, 10쪽 이상은 폭 2 …) — 문자열이 아니라 정수로 비교해야
    쪽 순서가 폭과 무관하게 맞는다."""
    return int(p.stem.rsplit("-", 1)[1])


def _쪽_파일_정리(접두: Path) -> tuple[Path, ...]:
    """`pdftoppm`이 낸 쪽별 PNG(0-패딩 폭이 쪽수에 따라 다르다)를 쪽 번호 순으로
    `<접두>-001.png` … 로 통일해 돌려준다. 순수 함수 — `pdftoppm` 없이(가짜 파일로) 단위
    테스트한다. `_pdf_to_pngs`가 이 함수를 실제 렌더 뒤에 부른다."""
    원래들 = sorted(접두.parent.glob(접두.name + "-*.png"), key=_쪽_번호)
    결과 = []
    for i, p in enumerate(원래들, start=1):
        새 = 접두.parent / f"{접두.name}-{i:03d}.png"
        if p != 새:
            p.replace(새)
        결과.append(새)
    return tuple(결과)


def _잔존_쪽_PNG_지우기(접두: Path) -> None:
    """이전 실행이 같은 `out_png`(같은 `--out`을 되풀이해 쓰는 반복 실행 등)에 남긴
    `<접두>-<숫자>.png`만 지운다 — 그 밖의 파일(다른 이름의 잔존물)은 그대로 둔다. `pdftoppm`을
    부르기 **전**에 불러야 한다: 안 그러면 이전 실행이 이미 3자리로 정규화한 이름(`-001.png`)과
    이번 `pdftoppm`의 무패딩 출력(`-1.png`)이 같은 폴더에 공존해, `_쪽_파일_정리`가 쪽 번호를
    오해하고 파일을 잃거나(`FileNotFoundError`) 다른 실행의 내용을 뒤섞어 덮어쓴다."""
    for p in 접두.parent.glob(접두.name + "-*.png"):
        if re.fullmatch(re.escape(접두.name) + r"-\d+", p.stem):
            p.unlink()


def _pdf_to_pngs(pdf: Path, out_png: Path, dpi: int) -> tuple[Path, ...]:
    """pdftoppm(poppler)으로 쪽마다 `<stem>-001.png` … 을 만든다."""
    접두 = out_png.with_suffix("")
    _잔존_쪽_PNG_지우기(접두)
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(접두)], check=True, timeout=300)
    return _쪽_파일_정리(접두)


def render_libreoffice(docx: Path, out_png: Path, *, dpi: int = 110) -> RenderResult:
    """LibreOffice 헤드리스로 docx → pdf → 쪽별 PNG. 실한컴이 없는 머신·CI에서도 docx
    형태를 실물로 본다(간이 렌더 — 최종 판정은 사람이 실제 워드프로세서로 본다)."""
    docx, out_png = Path(docx).resolve(), Path(out_png).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as 임시:
        # 이 프로필 폴더가 없으면 이미 떠 있는(또는 동시에 도는) soffice 인스턴스의 사용자
        # 프로필 락에 걸려 변환이 조용히 멈출 수 있다 — 호출마다 고유한 프로필을 준다.
        프로필 = Path(임시) / "profile"
        r = subprocess.run(
            [
                "soffice", "--headless", f"-env:UserInstallation=file://{프로필}",
                "--convert-to", "pdf", "--outdir", 임시, str(docx),
            ],
            capture_output=True, text=True, timeout=300,
        )
        pdf임시 = Path(임시) / (docx.stem + ".pdf")
        if r.returncode != 0 or not pdf임시.exists():
            raise RuntimeError(f"LibreOffice 렌더 실패: {r.stderr.strip() or r.stdout.strip()}")
        pdf = out_png.with_suffix(".pdf")
        shutil.copy(pdf임시, pdf)
    pngs = _pdf_to_pngs(pdf, out_png, dpi)
    return RenderResult(pages=len(pngs), pngs=pngs, pdf=pdf)


def _gdocs_명령들(docx: Path, 원격_폴더: str, pdf: Path) -> list[list[str]]:
    """구글 문서 왕복이 쓰는 rclone 명령 세 개(올리기·받기·지우기). 순수 함수 —
    rclone·네트워크 없이 단위 테스트한다."""
    이름 = docx.stem
    return [
        ["rclone", "copyto", str(docx), f"{원격_폴더}/{이름}.docx", "--drive-import-formats", "docx"],
        ["rclone", "copyto", f"{원격_폴더}/{이름}.pdf", str(pdf), "--drive-export-formats", "pdf"],
        ["rclone", "purge", 원격_폴더],
    ]


def render_gdocs(docx: Path, out_png: Path, *, dpi: int = 110, 원격: str = "gdrive:_worksheet_render_tmp") -> RenderResult:
    """구글 문서로 변환해 PDF 로 받는다 — 사용자 드라이브의 전용 임시 폴더 하나만 쓰고, 끝나면
    (실패해도) 지운다."""
    docx, out_png = Path(docx).resolve(), Path(out_png).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pdf = out_png.with_suffix(".pdf")
    올리기, 받기, 지우기 = _gdocs_명령들(docx, f"{원격}/{uuid.uuid4().hex}", pdf)
    try:
        for 단계, 명령 in (("올리기", 올리기), ("받기", 받기)):
            r = subprocess.run(명령, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                raise RuntimeError(f"구글 문서 {단계} 실패: {r.stderr.strip()}")
    finally:
        subprocess.run(지우기, capture_output=True, text=True, timeout=120)
    pngs = _pdf_to_pngs(pdf, out_png, dpi)
    return RenderResult(pages=len(pngs), pngs=pngs, pdf=pdf)
