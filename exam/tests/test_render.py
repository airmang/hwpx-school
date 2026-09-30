from pathlib import Path

import pymupdf
import pytest

from _kits import kit_dir
from exam_kit.kit import load_kit
from exam_kit.prepare import prepare_document
from exam_kit.render import render, side_by_side

킷_디렉터리 = kit_dir()


@pytest.fixture
def 준비된_양식(양식_hwpx, tmp_path):
    kit = load_kit(킷_디렉터리)
    doc, _ = prepare_document(양식_hwpx, kit)
    p = tmp_path / "prepared.hwpx"
    doc.save_to_path(str(p))
    return p


def test_준비된_양식_렌더(준비된_양식, 오라클, tmp_path):
    r = render(준비된_양식, tmp_path / "r", oracle=오라클)
    assert r.page_count >= 1 and r.pdf.exists() and len(r.pages) == r.page_count and r.seconds < 120
    assert pymupdf.open(str(r.pdf)).page_count == r.page_count


def test_side_by_side(준비된_양식, 양식_hwpx, 오라클, tmp_path):
    a = render(양식_hwpx, tmp_path / "a", oracle=오라클)
    b = render(준비된_양식, tmp_path / "b", oracle=오라클)
    pngs = side_by_side(a.pdf, b.pdf, tmp_path / "sbs")
    assert len(pngs) == max(a.page_count, b.page_count)

    composite = pymupdf.Pixmap(str(pngs[0]))
    left = pymupdf.open(str(a.pdf))[0].get_pixmap(dpi=80)
    right = pymupdf.open(str(b.pdf))[0].get_pixmap(dpi=80)
    assert composite.width == left.width + right.width + 20
    assert composite.height == max(left.height, right.height)

    # 쪽 수가 달라도 모든 쪽이 같은 폭 — 없는 쪽은 빈 칸(예전엔 오른쪽 문서가 왼쪽 자리로 밀려왔다, Task 27 fix 1)
    assert all(pymupdf.Pixmap(str(p)).width == composite.width for p in pngs)


class _가짜_오라클:
    def __init__(self, 실패_횟수: int):
        self.남은_실패, self.호출 = 실패_횟수, 0

    def render_pdf(self, src: str, out: str):
        self.호출 += 1
        if self.남은_실패 > 0:
            self.남은_실패 -= 1
            return None
        doc = pymupdf.open()
        doc.new_page()
        doc.save(out)
        return out


def test_렌더_실패하면_한컴을_띄우고_한_번_재시도(tmp_path):
    import zipfile

    src = tmp_path / "x.hwpx"  # 꾸러미 검사(check_package)를 지나는 최소 hwpx
    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("Contents/header.xml", '<hh:head xmlns:hh="h"/>')
        z.writestr("Contents/section0.xml", '<hs:sec xmlns:hs="s"/>')
    띄움 = []
    o = _가짜_오라클(1)
    r = render(src, tmp_path / "r", oracle=o, launch=lambda: 띄움.append(1))
    assert r.page_count == 1 and o.호출 == 2 and 띄움 == [1]

    from exam_kit.render import RenderUnavailable
    o2 = _가짜_오라클(2)
    with pytest.raises(RenderUnavailable):
        render(src, tmp_path / "r2", oracle=o2, launch=lambda: None)
    assert o2.호출 == 2  # 재시도는 한 번뿐


def test_한컴_띄우기는_멈춘_호출에_막히지_않는다(monkeypatch):
    """System Events가 멈춰도(TimeoutExpired) wait 기한 안에 False로 끝난다 — 모든 호출에 timeout이 있다."""
    import subprocess

    from exam_kit import render as R

    호출 = []

    def 멈춤(args, **kw):
        호출.append(kw.get("timeout"))
        raise subprocess.TimeoutExpired(args, kw.get("timeout") or 0)

    monkeypatch.setattr(R.subprocess, "run", 멈춤)
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    assert R.launch_hancom(wait=0.05) is False
    assert 호출 and all(t is not None and t <= 10 for t in 호출)


def _색_pdf(path: Path, n: int, 색: tuple[float, float, float]) -> Path:
    """쪽마다 전면을 한 색으로 칠한 합성 PDF(A4 비율 200×300pt)."""
    doc = pymupdf.open()
    for _ in range(n):
        page = doc.new_page(width=200, height=300)
        page.draw_rect(page.rect, color=색, fill=색)
    doc.save(str(path))
    return path


def test_side_by_side_쪽_수가_다르면_없는_쪽은_빈_칸(tmp_path):
    """왼쪽 2쪽 · 오른쪽 4쪽: p3·p4도 폭이 같고, 오른쪽 문서는 오른쪽 자리에 · 왼쪽 자리는 흰 칸."""
    a = _색_pdf(tmp_path / "a.pdf", 2, (1, 0, 0))
    b = _색_pdf(tmp_path / "b.pdf", 4, (0, 0, 1))
    pngs = side_by_side(a, b, tmp_path / "sbs")
    assert len(pngs) == 4
    ims = [pymupdf.Pixmap(str(p)) for p in pngs]
    w = ims[0].width
    assert all(im.width == w for im in ims)
    half = pymupdf.open(str(a))[0].get_pixmap(dpi=80).width
    left, right = (half // 2, 50), (half + 20 + half // 2, 50)
    assert ims[0].pixel(*left) == (255, 0, 0) and ims[0].pixel(*right) == (0, 0, 255)
    assert ims[3].pixel(*left) == (255, 255, 255) and ims[3].pixel(*right) == (0, 0, 255)
    rev = [pymupdf.Pixmap(str(p)) for p in side_by_side(b, a, tmp_path / "rev")]  # 반대: 오른쪽이 짧다
    assert rev[3].width == rev[0].width and rev[3].pixel(*right) == (255, 255, 255)


# ---- 한컴 공용 잠금(Task 33) ------------------------------------------------------


def _쥐기(path, hold: float, ready):
    import fcntl
    import time

    with open(path, "a") as h:
        fcntl.flock(h, fcntl.LOCK_EX)
        ready.set()
        time.sleep(hold)
        fcntl.flock(h, fcntl.LOCK_UN)


@pytest.mark.real_lock
def test_잠금_경로는_upstream_공용_잠금():
    """경로는 hwpx_automation 렌더 워커와 같은 파일(mac_session._gui_lock_path) — 스스로 만들지 않는다."""
    from hwpx_automation.office.rendering.mac_session import _gui_lock_path

    import exam_kit.render as r

    assert r._lock_path() == _gui_lock_path()


def _합성_hwpx(tmp_path: Path) -> Path:
    import zipfile

    src = tmp_path / "x.hwpx"  # 꾸러미 검사(check_package)를 지나는 최소 hwpx
    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("Contents/header.xml", '<hh:head xmlns:hh="h"/>')
        z.writestr("Contents/section0.xml", '<hs:sec xmlns:hs="s"/>')
    return src


def test_다른_쪽이_쥐면_기다렸다_들어간다(tmp_path, monkeypatch):
    import threading
    import time

    import exam_kit.render as r

    lock = tmp_path / "hancom.lock"
    monkeypatch.setattr(r, "_lock_path", lambda: lock)
    ready = threading.Event()
    t = threading.Thread(target=_쥐기, args=(lock, 0.6, ready))
    t.start()
    ready.wait(5)
    t0 = time.monotonic()
    with r.hancom_lock(wait=10):
        waited = time.monotonic() - t0
    t.join()
    assert waited >= 0.4  # 앞 사람이 놓을 때까지 기다렸다


def test_기한을_넘기면_HancomBusy(tmp_path, monkeypatch):
    import threading

    import exam_kit.render as r

    lock = tmp_path / "hancom.lock"
    monkeypatch.setattr(r, "_lock_path", lambda: lock)
    ready = threading.Event()
    t = threading.Thread(target=_쥐기, args=(lock, 1.5, ready))
    t.start()
    ready.wait(5)
    with pytest.raises(r.HancomBusy, match="0.3초 넘게"):
        with r.hancom_lock(wait=0.3):
            pass
    t.join()


def test_렌더와_줄_캐시_저장은_잠금_안에서(tmp_path, monkeypatch):
    """render()의 render_pdf, fit.hancom_lines의 refresh_document는 잠금을 쥔 채로 부른다 — 부르는 동안 다른 쪽은 못 잡는다.
    중첩(이미 쥔 스레드가 다시)은 스스로를 막지 않는다."""
    import fcntl

    import exam_kit.render as r
    from exam_kit.fit import hancom_lines

    lock = tmp_path / "hancom.lock"
    monkeypatch.setattr(r, "_lock_path", lambda: lock)

    def 잠겼나() -> bool:
        with open(lock, "a") as h:
            try:
                fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(h, fcntl.LOCK_UN)
            return False

    seen = []
    src = _합성_hwpx(tmp_path)

    class 가짜:
        def render_pdf(self, s, out):
            seen.append(("렌더", 잠겼나()))
            import pymupdf

            d = pymupdf.open()
            d.new_page()
            d.save(out)
            return out

        def refresh_document(self, path):
            seen.append(("저장", 잠겼나()))
            return True

    r.render(src, tmp_path / "out", oracle=가짜())
    hancom_lines(src, tmp_path / "줄", oracle=가짜())
    assert seen == [("렌더", True), ("저장", True)]
    assert not 잠겼나()  # 끝나면 놓는다
    with r.hancom_lock(wait=1):
        with r.hancom_lock(wait=0.1):  # 중첩은 바로 들어간다
            pass
