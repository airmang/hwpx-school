"""보고서·계획서 킷 — 자리표시를 적은 한/글 견본으로 문서를 만든다.

서식은 견본이 정한다. 이 패키지는 python-hwpx-automation 공개 API
(`office.authoring.design`)를 부르는 손일 뿐, 색·글꼴·위계를 알지 못한다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hwpx.document import HwpxDocument
from hwpx_automation.office.authoring.design import Profile, compose
from hwpx_automation.office.authoring.design.marked import harvest_marked_profile


def register(template: str | Path, kit_dir: str | Path) -> dict[str, Any]:
    """견본을 수확해 *kit_dir* 에 킷(profile.json·template.hwpx·fragments.hwpx)을 쓴다."""

    kit_dir = Path(kit_dir)
    manifest = harvest_marked_profile(template, kit_dir.name, kit_dir.parent)
    return {
        "kit": str(kit_dir),
        "roles": manifest["slots"],
        "ignoredStaticParagraphs": manifest["ignored_static_paragraphs"],
        "skeletonOpenSafe": manifest["skeleton_open_safe"],
    }


def roles(kit_dir: str | Path) -> dict[str, list[str]]:
    """킷이 아는 역할과 각 역할의 칸 이름 (`""` = 이름 없는 칸)."""

    manifest = json.loads((Path(kit_dir) / "profile.json").read_text(encoding="utf-8"))
    return manifest["slots"]


def make(plan: dict[str, Any], kit_dir: str | Path, output: str | Path) -> dict[str, Any]:
    """계획(블록 목록)을 킷 위에 조립해 *output* 에 저장하고 결과를 돌려준다.

    블록 = ``{"role": "1단계", "text": "추진 근거"}`` 또는
    ``{"role": "띠", "values": {"번호": "Ⅰ", "제목": "추진 배경"}}``.
    """

    profile = Profile.load(kit_dir)
    blocks = [{"type": "paragraph", **block} for block in plan["blocks"]]
    result = compose({"profile": profile.id, "blocks": blocks}, profile=profile, output_path=output)
    if result.ok:
        _stamp(Path(output))
    return result.to_dict() | {"visualComplete": None}


def _stamp(path: Path) -> None:
    """만든 날짜 = 고친 날짜 = 자유 꼴 날짜(date) = 지금(`SOURCE_DATE_EPOCH`가 있으면 그 시각), 사람 이름은 비운다.
    automation 저장은 만든·고친 날짜만 찍는다 — date가 비면 한/글이 재저장 시각으로 채워 만든 날짜와 어긋난다."""
    값 = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    때 = datetime.fromtimestamp(int(값), timezone.utc) if 값.isdigit() else datetime.now(timezone.utc)
    t = 때.strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = HwpxDocument.open(str(path))
    doc.parts.clear_document_authors()
    doc.parts.set_document_metadata(created_date=t, modified_date=t, date=때)
    doc.save(str(path))


__all__ = ["register", "roles", "make"]
