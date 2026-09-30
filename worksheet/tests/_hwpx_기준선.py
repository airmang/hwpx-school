"""hwpx 출력 비교용 정규화 — 같은 입력을 두 번 조판해도 도형·표의 임의 식별자(`id`·`instid`)만
다르다(실측). 그 두 속성 값을 지우고, XML 이 아닌 부품(그림 등)은 해시로 비교한다."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

_식별자 = re.compile(rb'\b(id|instid)="[^"]*"')


def 정규화(hwpx: Path) -> dict[str, str]:
    결과: dict[str, str] = {}
    with zipfile.ZipFile(hwpx) as z:
        for 이름 in sorted(z.namelist()):
            데이터 = z.read(이름)
            if 이름.endswith((".xml", ".hpf")):
                결과[이름] = _식별자.sub(rb'\1=""', 데이터).decode("utf-8")
            else:
                결과[이름] = "sha256:" + hashlib.sha256(데이터).hexdigest()
    return 결과
