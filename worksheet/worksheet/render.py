"""실한컴 렌더 — python-hwpx-automation의 공개 `render-pdf` 명령을 부른다."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

# python-hwpx-automation 8.0의 공개 렌더 진입점(`hwpx render-pdf`와 같은 명령, docs/render-pdf.md).
# 플러그인 캐시 안의 인터프리터 경로는 공개 표면이 아니다 — 찾아 쓰지 않는다.
_RENDER_MODULE = "hwpx_automation.office.rendering"
_UNAVAILABLE_EXIT = 3  # render-pdf: 닿는 한컴이 없음(HWPX_ORACLE_STRUCTURAL_ONLY 포함)
_TIMEOUT_GRACE = 60.0  # 초 — render-pdf가 자기 시간 예산을 넘긴 뒤 결과 줄을 쓰고 끝낼 여유


@dataclass(frozen=True)
class RenderResult:
    """실한컴 렌더 결과 — 쪽수의 권위는 이 값뿐이다(M-6 `preview_stats()["pages_estimate"]`는
    근사값)."""

    pages: int
    pngs: tuple[Path, ...]
    pdf: Path


class RenderError(RuntimeError):
    """render-pdf가 실패 결과(`{"ok": false, "error": <code>, ...}`)를 냈다. `code`는 그 오류 코드."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"실한컴 렌더 실패 [{code}]: {message}")
        self.code = code


class RenderUnavailable(RenderError):
    """닿는 한컴이 없다(`hancom-unavailable`, 종료 코드 3) — 한글 미설치·권한 없음·
    `HWPX_ORACLE_STRUCTURAL_ONLY`."""


def oracle_python() -> Path:
    """`render-pdf`를 돌릴 인터프리터.

    ① 환경변수 `HWPX_ORACLE_PY`가 있으면 그 인터프리터(없는 파일이면 `FileNotFoundError`) —
    이 프로젝트와 다른 별도 렌더 환경을 쓸 때. 그 환경에는
    `python-hwpx-automation[oracle]>=8.0`이 깔려 있어야 하고, 거기서도 같은 공개 모듈 진입점을
    부른다. ② 없으면 이 프로젝트의 인터프리터(`sys.executable`) — `[oracle]` extra가 이
    프로젝트의 의존성이다.
    """
    지정_경로 = os.environ.get("HWPX_ORACLE_PY")
    if 지정_경로:
        경로 = Path(지정_경로)
        if not 경로.exists():
            raise FileNotFoundError(f"HWPX_ORACLE_PY 가 가리키는 경로가 없다: {경로}")
        return 경로
    return Path(sys.executable)


def _render_command(
    python: Path, hwpx: Path, pdf: Path, png_prefix: Path, *, dpi: int, timeout: float
) -> list[str]:
    """공개 `render-pdf` 호출 한 줄. 순수 함수 — 한글 앱 없이 단위 테스트한다.

    `--backend auto`(기본값)는 Windows COM, 그다음 macOS 한글 순으로 처음 닿는 한컴을 쓴다.
    `--png PREFIX`는 `PREFIX-001.png`, `-002.png` …를 만든다.
    """
    return [
        str(python), "-m", _RENDER_MODULE, "render-pdf",
        str(hwpx), str(pdf),
        "--png", str(png_prefix),
        "--dpi", str(dpi),
        "--backend", "auto",
        "--timeout", f"{timeout:g}",
        "--json",
    ]


def _parse_result(stdout: str) -> RenderResult:
    """`render-pdf --json` stdout의 **마지막 줄**(JSON 한 줄)을 `RenderResult`로 바꾼다. 순수
    함수 — 한글 앱 없이 단위 테스트한다.

    앞에 다른 출력이 섞여도 마지막 줄만 본다. 마지막 줄이 JSON이 아니거나 stdout이 비어
    있으면(명령이 계약을 어겼다는 뜻) `RuntimeError`. `"ok": false`면 그 오류 코드를 담은
    `RenderError`(닿는 한컴이 없으면 `RenderUnavailable`). JSON은 맞지만 dict가 아니거나
    `pages`/`pngs`/`pdf` 키가 없으면(형태는 맞는데 내용이 틀린 경우) bare `KeyError`/
    `TypeError`를 새게 두지 않고 같은 계약으로 `RuntimeError`. `pngs` 개수가 `pages`와 다르면
    마찬가지다.
    """
    줄들 = [줄 for 줄 in stdout.strip().splitlines() if 줄.strip()]
    if not 줄들:
        raise RuntimeError(f"실한컴 렌더 실패: stdout이 비어 있다: {stdout!r}")
    try:
        데이터 = json.loads(줄들[-1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"실한컴 렌더 실패: stdout 마지막 줄이 JSON이 아니다: {stdout!r}") from e
    if isinstance(데이터, dict) and 데이터.get("ok") is False:
        코드 = str(데이터.get("error") or "unknown")
        메시지 = str(데이터.get("message") or "")
        if 코드 == "hancom-unavailable":
            raise RenderUnavailable(코드, 메시지)
        raise RenderError(코드, 메시지)
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


def _read_completed(returncode: int, stdout: str, stderr: str) -> RenderResult:
    """끝난 `render-pdf`의 종료 코드·stdout·stderr를 `RenderResult`로 읽는다. 순수 함수.

    결과 줄이 있으면 그 판정(`RenderError`/`RenderUnavailable`)이 우선이다. 결과 줄이 없이 0이
    아닌 코드로 끝났으면(모듈이 없는 인터프리터 등) stderr를 담아 — 종료 코드 3이면
    `RenderUnavailable`, 그 밖은 `RuntimeError`. 0이 아닌 코드인데 성공 줄이면 믿지 않는다.
    """
    try:
        결과 = _parse_result(stdout)
    except RenderError:
        raise
    except RuntimeError as e:
        if returncode == 0:
            raise
        사유 = stderr.strip() or stdout.strip()
        if returncode == _UNAVAILABLE_EXIT:
            raise RenderUnavailable("hancom-unavailable", 사유) from e
        raise RuntimeError(f"실한컴 렌더 실패(종료 코드 {returncode}): {사유}") from e
    if returncode != 0:
        raise RuntimeError(f"실한컴 렌더 실패(종료 코드 {returncode}): 성공 결과 줄과 어긋난다: {stdout!r}")
    return 결과


def render_hancom(hwpx: Path, out_png: Path, *, dpi: int = 110, timeout: float = 600.0) -> RenderResult:
    """한글 앱으로 PDF를 뽑고 쪽마다 PNG로 저장한다. 1쪽 ≈ 6초, 직렬로만.

    python-hwpx-automation의 공개 `render-pdf`(`python -m hwpx_automation.office.rendering
    render-pdf ... --json`)를 `oracle_python()` 인터프리터로 부른다. PDF는 `<out_png>.pdf`,
    PNG 이름은 쪽수와 무관하게 항상 `<out_png의 stem>-001.png`, `-002.png` …다. `timeout`초는
    render-pdf의 한컴 시간 예산이고, 프로세스가 그보다 한참 넘게 안 끝나면 `RuntimeError`.
    한컴이 없으면 `RenderUnavailable`, 렌더가 실패하면 `RenderError`(둘 다 `RuntimeError`).
    """
    hwpx, out_png = Path(hwpx).resolve(), Path(out_png).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pdf = out_png.with_suffix(".pdf")
    명령 = _render_command(oracle_python(), hwpx, pdf, out_png.with_suffix(""), dpi=dpi, timeout=timeout)
    try:
        결과 = subprocess.run(
            명령, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout + _TIMEOUT_GRACE, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"실한컴 렌더 시간 초과({timeout + _TIMEOUT_GRACE:g}초): {hwpx}") from e
    return _read_completed(결과.returncode, 결과.stdout or "", 결과.stderr or "")


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
