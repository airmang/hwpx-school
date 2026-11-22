"""실한컴 렌더(직렬) → pdf · 쪽 png · 쪽수. 렌더 없이는 쪽 배치를 알 수 없다."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .kit import sha256


class RenderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderResult:
    pdf: Path
    pages: list[Path]
    page_count: int
    seconds: float
    hwpx_sha256: str


class HancomBusy(RenderUnavailable):
    """다른 프로세스가 한컴 데스크톱 잠금을 기한 넘게 쥐고 있다."""


# 한컴 데스크톱 공용 잠금(Task 33) — 한컴은 한 데스크톱에 하나라 두 렌더가 같은 메뉴·저장 창을 동시에 몰면 서로 깨진다.
# 잠금 파일은 upstream(hwpx_automation.office.rendering.mac_session)의 것을 그대로 쓴다 — 같은 파일에 flock을 걸어야
# 렌더 워커·다른 세션·hwpx-school과 서로 기다린다. upstream에 공개 잠금 함수는 없어(cli._shared_desktop은 CLI 오류를
# 내는 내부 함수) 경로 함수만 가져오고, flock 대기는 cli._shared_desktop과 같은 방식(비차단 시도 + 짧은 간격 재시도 + 기한)이다.
HANCOM_LOCK_WAIT = 1800.0  # 초 — 다른 세션의 긴 조판(렌더 여러 번)을 기다릴 만큼, 영원히는 아니게
_LOCK_POLL = 0.25
_held = threading.local()  # 이 프로세스(스레드)가 이미 쥐었으면 다시 잡지 않는다 — 같은 파일의 두 번째 잠금은 스스로를 막는다
# Windows에는 upstream 데스크톱 잠금이 없다 — COM은 렌더마다 한컴을 따로 띄우므로 upstream CLI는 잠그지 않는다. 엔진 렌더끼리
# 한 번에 하나씩 돌도록 사용자 임시 폴더의 이 파일에 잠금을 건다(계약은 macOS와 같다: 기한을 넘으면 HancomBusy, 같은 스레드는 중첩).
_WINDOWS_LOCK_NAME = "hwpx-school-hancom.lock"


def _lock_path() -> Path:
    if sys.platform == "win32":
        return Path(tempfile.gettempdir()) / _WINDOWS_LOCK_NAME
    from hwpx_automation.office.rendering.mac_session import _gui_lock_path

    return _gui_lock_path()


def _try_lock(handle) -> bool:
    """잠금을 한 번 시도한다(기다리지 않는다). 잡으면 True — macOS·Linux는 flock, Windows는 첫 바이트 msvcrt 잠금."""
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock(handle) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def hancom_lock(wait: float | None = None):
    """한컴을 여는·저장하는·렌더하는 동안 공용 잠금을 쥔다. 다른 쪽이 쥐고 있으면 wait초(기본 HANCOM_LOCK_WAIT)까지
    기다리고, 넘으면 HancomBusy. 이미 이 스레드가 쥐고 있으면 그대로 지나간다(중첩)."""
    if getattr(_held, "depth", 0):
        _held.depth += 1
        try:
            yield
        finally:
            _held.depth -= 1
        return
    wait = HANCOM_LOCK_WAIT if wait is None else wait
    path = _lock_path()
    deadline = time.monotonic() + wait
    with open(path, "a") as handle:
        while not _try_lock(handle):
            if time.monotonic() >= deadline:
                raise HancomBusy(f"다른 작업이 한컴 데스크톱 잠금을 {wait:g}초 넘게 쥐고 있다 — 기다렸다 다시 한다: {path}")
            time.sleep(_LOCK_POLL)
        _held.depth = 1
        try:
            yield
        finally:
            _held.depth = 0
            _unlock(handle)


def _oracle(oracle=None):
    """렌더 오라클 — 넘겨받은 것, 아니면 이 PC의 실한컴(Windows COM, 그다음 macOS 한글 앱)."""
    if oracle is not None:
        return oracle
    from hwpx_automation.office.rendering.oracle import MacHancomOracle, WindowsComOracle

    for backend in (WindowsComOracle, MacHancomOracle):
        o = backend(timeout=300.0)
        if o.available():
            return o
    raise RenderUnavailable("실한컴 오라클을 쓸 수 없다(Windows: 한글 COM 등록 · macOS: Hancom Office HWP.app과 자동화 권한 확인)")


_앱 = "Hancom Office HWP"
_창_수 = f'tell application "System Events" to count windows of process "{_앱}"'


def launch_hancom(*, wait: float = 40.0) -> bool:
    """macOS: 한컴을 띄우고 창이 뜰 때까지(최대 wait초) 기다린다 — 앱이 안 떠 있으면 render_pdf가 -1700으로 None을 낸다(09-23 실측).
    Windows: COM이 렌더마다 한컴을 띄우므로 할 일이 없다."""
    if sys.platform != "darwin":
        return True
    deadline = time.time() + wait

    def 실행(args: list[str]):
        """호출마다 timeout — 멈춘 System Events 호출이 wait 기한을 넘겨 붙잡지 못하게."""
        try:
            return subprocess.run(args, capture_output=True, text=True, check=False,
                                  timeout=max(0.1, min(10.0, deadline - time.time())))
        except subprocess.TimeoutExpired:
            return None

    실행(["open", "-a", _앱])
    while time.time() < deadline:
        r = 실행(["osascript", "-e", _창_수])
        if r is not None and r.returncode == 0 and r.stdout.strip().isdigit() and int(r.stdout.strip()) > 0:
            return True
        time.sleep(1.0)
    return False


def check_package(hwpx: Path) -> None:
    """한컴에 넘기기 전 hwpx 꾸러미 검사 — 반쯤 쓴 사본을 한컴이 열면 '파일이 손상되었습니다' 모달이 떠 모든 세션의
    렌더를 막는다(Task 29 사고). zip 무결성(testzip), 첫 항목 mimetype·무압축, section0·header XML 파싱."""
    import zipfile

    import lxml.etree as ET

    try:
        with zipfile.ZipFile(hwpx) as z:
            bad = z.testzip()
            if bad is not None:
                raise ValueError(f"손상된 zip 항목 {bad}")
            first = z.infolist()[0]
            if first.filename != "mimetype" or first.compress_type != zipfile.ZIP_STORED:
                raise ValueError("첫 항목이 무압축 mimetype이 아니다")
            for name in ("Contents/section0.xml", "Contents/header.xml"):
                ET.fromstring(z.read(name))
    except (zipfile.BadZipFile, KeyError, IndexError, ET.XMLSyntaxError, ValueError) as e:
        raise ValueError(f"한컴에 넘길 수 없는 hwpx: {hwpx} — {e}") from e


_쪽_크기_허용 = 1.0  # pt — PDF 쪽이 hwpx 용지와 이만큼 넘게 다르면 맞춰 줄여 인쇄된 것으로 본다


def hwpx_paper(hwpx: Path) -> tuple[float, float] | None:
    """hwpx 첫 구역의 용지 (폭, 높이) pt — section0.xml 첫 pagePr(HWPUNIT ÷ 100). 없으면 None."""
    import re
    import zipfile

    try:
        with zipfile.ZipFile(hwpx) as z:
            xml = z.read("Contents/section0.xml").decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile, OSError):
        return None
    m = re.search(r"<(?:\w+:)?pagePr\b[^>]*>", xml)
    if not m:
        return None
    w = re.search(r'\swidth="(\d+)"', m.group(0))
    h = re.search(r'\sheight="(\d+)"', m.group(0))
    if not (w and h):
        return None
    return int(w.group(1)) / 100.0, int(h.group(1)) / 100.0


def restore_paper(pdf: Path, paper: tuple[float, float]) -> bool:
    """한컴이 문서를 다른 용지에 맞춰 줄여(예: B4 문서를 A4 PDF로) 저장한 PDF를 hwpx 용지 크기로 되돌린다(그 자리에서).

    Windows 한컴의 PDF 저장은 인쇄 설정에 따라 문서를 다른 용지에 비율을 지켜 가운데 맞춰 넣는다(축소율 = 두 변 비 중 작은
    것 — 11-22 Windows 실측: 728.5×1031.8pt 문서가 595×841pt PDF로, 축소 0.8151·좌우 여백 0.59pt). 엔진의 자리 판정(단 왼끝·
    문항 머리·꼬리 박스)은 모두 킷의 용지 좌표라, 그 역변환(cm)을 쪽 내용 앞에 붙이고 쪽 상자를 용지 크기로 바꾼다.
    모든 쪽이 이미 용지 크기면 손대지 않고 False. PDF 쪽과 가로·세로 방향이 다르면 용지의 두 변을 바꿔 맞춘다.
    """
    W, H = paper
    pdf = Path(pdf)
    tmp = pdf.with_name(pdf.stem + ".용지복원.pdf")
    changed = False
    with pymupdf.open(str(pdf)) as doc:
        for page in doc:
            r = page.mediabox
            pw, ph = r.width, r.height
            w, h = (W, H) if (pw >= ph) == (W >= H) else (H, W)
            if abs(pw - w) <= _쪽_크기_허용 and abs(ph - h) <= _쪽_크기_허용:
                continue
            s = min(pw / w, ph / h)
            ox, oy = (pw - w * s) / 2, (ph - h * s) / 2
            page.clean_contents()
            xrefs = page.get_contents()
            body = b"\n".join(doc.xref_stream(x) for x in xrefs)
            pre = f"q {1 / s:.6f} 0 0 {1 / s:.6f} {-(r.x0 + ox) / s:.4f} {-(r.y0 + oy) / s:.4f} cm\n".encode()
            doc.update_stream(xrefs[0], pre + body + b"\nQ\n")
            for x in xrefs[1:]:
                doc.update_stream(x, b"")
            page.set_mediabox(pymupdf.Rect(0, 0, w, h))
            changed = True
        if changed:
            doc.save(str(tmp), garbage=1, deflate=True)
    if changed:
        tmp.replace(pdf)
    return changed


def render(hwpx: Path, out_dir: Path, *, oracle=None, dpi: int = 110, launch=launch_hancom) -> RenderResult:
    hwpx, out_dir = Path(hwpx), Path(out_dir)
    check_package(hwpx)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / (hwpx.stem + ".pdf")
    t0 = time.time()
    o = _oracle(oracle)
    with hancom_lock():  # 한컴을 띄우고 렌더하는 동안만 — 쪽 PNG는 잠금 밖에서
        got = o.render_pdf(str(hwpx.resolve()), str(pdf.resolve()))
        if not got or not pdf.exists():
            launch()  # 한 번만: 한컴을 띄우고 다시 시도
            got = o.render_pdf(str(hwpx.resolve()), str(pdf.resolve()))
    if not got or not pdf.exists():
        raise RenderUnavailable(f"렌더 실패: {hwpx}")
    paper = hwpx_paper(hwpx)
    if paper is not None:
        restore_paper(pdf, paper)  # Windows 한컴이 다른 용지(A4)에 맞춰 줄여 저장했으면 hwpx 용지로 되돌린다
    pages: list[Path] = []
    with pymupdf.open(str(pdf)) as doc:
        page_count = doc.page_count
        for i, page in enumerate(doc, 1):
            png = out_dir / f"{hwpx.stem}-{i}.png"
            page.get_pixmap(dpi=dpi).save(str(png))
            pages.append(png)
    return RenderResult(pdf=pdf, pages=pages, page_count=page_count, seconds=time.time() - t0,
                        hwpx_sha256=sha256(hwpx))


def side_by_side(left_pdf: Path, right_pdf: Path, out_dir: Path, *, dpi: int = 80, stem: str = "대조") -> list[Path]:
    """쪽별 좌우 PNG(왼쪽 = left_pdf, 오른쪽 = right_pdf). 쪽 수가 다르면 긴 쪽 기준 — 없는 쪽은 그 문서 첫 쪽 폭만큼
    빈 칸으로 비워 두어, 오른쪽 문서가 왼쪽 자리로 밀려오지 않는다(오른쪽 x 자리는 모든 쪽에서 같다)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with pymupdf.open(str(left_pdf)) as a, pymupdf.open(str(right_pdf)) as b:
        wa = a[0].get_pixmap(dpi=dpi).width if len(a) else 0
        wb = b[0].get_pixmap(dpi=dpi).width if len(b) else 0
        x_right = wa + 20
        for i in range(max(len(a), len(b))):
            pa = a[i].get_pixmap(dpi=dpi) if i < len(a) else None
            pb = b[i].get_pixmap(dpi=dpi) if i < len(b) else None
            w = x_right + max(wb, pb.width if pb else 0)
            h = max(pa.height if pa else 0, pb.height if pb else 0)
            canvas = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
            canvas.clear_with(255)
            if pa:
                pa.set_origin(0, 0)
                canvas.copy(pa, pa.irect)
            if pb:
                pb.set_origin(x_right, 0)
                canvas.copy(pb, pb.irect)
            png = out_dir / f"{stem}_p{i + 1}.png"
            canvas.save(str(png))
            out.append(png)
    return out
