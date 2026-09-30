"""docx 실물 렌더 — LibreOffice(와 요청하면 구글 문서) 렌더를 뽑아 PNG 경로를 찍는다(비공개).

    uv run --python 3.13 python scripts/docx_실물_렌더.py <md> --kit <킷_루트> --out <출력_폴더> [--gdocs]

기본은 LibreOffice 렌더만 돈다. `--gdocs`를 **명시해야** 구글 문서 왕복이 더해진다 — owner 구글
드라이브의 전용 임시 폴더(`gdrive:_worksheet_render_tmp/<uuid>`)를 오가고 끝나면(실패해도)
지우므로, 드라이브를 건드리는 쪽을 기본값으로 두지 않는다. md·킷은 공개 `worksheet.compose.compose`로
그대로 조판하므로, 이 스크립트 자체는 렌더 두 개를 잇는 배선일 뿐이다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from worksheet.compose import compose
from worksheet.render import render_gdocs, render_libreoffice


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docx_실물_렌더")
    parser.add_argument("md", help="조판할 마크다운")
    parser.add_argument("--kit", required=True, help="킷 루트")
    parser.add_argument("--out", required=True, help="출력 폴더(없으면 새로 만든다)")
    # LibreOffice 는 늘 돈다 — 이 플래그는 예전 호출과의 호환으로만 받는다.
    parser.add_argument("--libreoffice", action="store_true", help="(기본값) LibreOffice 렌더")
    parser.add_argument("--gdocs", action="store_true", help="구글 문서 왕복 렌더를 더한다(드라이브를 오간다)")
    args = parser.parse_args(argv)

    출력_폴더 = Path(args.out)
    출력_폴더.mkdir(parents=True, exist_ok=True)
    docx = 출력_폴더 / (Path(args.md).stem + ".docx")
    compose(Path(args.md), Path(args.kit), docx)
    print(f"조판 완료: {docx}")

    결과 = render_libreoffice(docx, 출력_폴더 / "libreoffice" / (docx.stem + ".png"))
    for png in 결과.pngs:
        print(f"LibreOffice: {png}")

    if args.gdocs:
        결과 = render_gdocs(docx, 출력_폴더 / "gdocs" / (docx.stem + ".png"))
        for png in 결과.pngs:
            print(f"구글 문서: {png}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
