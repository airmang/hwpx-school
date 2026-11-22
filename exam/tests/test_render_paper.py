"""렌더 PDF 용지 복원 — 한컴 없이 도는 시험(학교 킷 불필요)."""

import pymupdf


def test_줄여_저장한_PDF는_hwpx_용지로_되돌린다(tmp_path):
    """Windows 한컴이 B4 문서를 A4 PDF에 비율대로 맞춰 줄여 저장해도(11-22 실측) 쪽과 내용 자리가 hwpx 용지 좌표로 돌아온다."""
    import zipfile

    from exam_kit.render import hwpx_paper, restore_paper

    src = tmp_path / "x.hwpx"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("Contents/section0.xml",
                   '<hs:sec xmlns:hs="s" xmlns:hp="p"><hp:pagePr landscape="WIDELY" width="72852" height="103180"/></hs:sec>')
    paper = hwpx_paper(src)
    assert paper == (728.52, 1031.8)

    b4 = pymupdf.open()
    pg = b4.new_page(width=paper[0], height=paper[1])
    선 = pymupdf.Rect(35.43, 58.0, 693.09, 120.0)
    pg.draw_rect(선, color=(0, 0, 0), width=0.5)
    pg.insert_text((35.43, 300.0), "1.", fontsize=11)
    a4 = pymupdf.open()
    a4.new_page(width=595, height=841).show_pdf_page(pymupdf.Rect(0, 0, 595, 841), b4, 0)  # 비율 유지·가운데
    pdf = tmp_path / "a4.pdf"
    a4.save(str(pdf))

    assert restore_paper(pdf, paper) is True
    with pymupdf.open(str(pdf)) as d:
        p = d[0]
        assert abs(p.rect.width - 728.52) < 0.1 and abs(p.rect.height - 1031.8) < 0.1
        r = max((x["rect"] for x in p.get_drawings()), key=lambda r: r.width)
        assert all(abs(a - b) < 0.5 for a, b in zip(r, 선))
        글 = [s for b in p.get_text("dict")["blocks"] for ln in b.get("lines", []) for s in ln["spans"]]
        assert 글 and abs(글[0]["bbox"][0] - 35.43) < 0.5
    assert restore_paper(pdf, paper) is False  # 이미 용지 크기면 그대로


def test_용지를_못_읽으면_PDF를_건드리지_않는다(tmp_path):
    import zipfile

    from exam_kit.render import hwpx_paper

    src = tmp_path / "x.hwpx"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("Contents/section0.xml", '<hs:sec xmlns:hs="s"/>')
    assert hwpx_paper(src) is None
