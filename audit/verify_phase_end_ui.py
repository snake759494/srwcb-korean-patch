# -*- coding: utf-8 -*-
"""최종 컴플리트 박스의 제2차 페이즈 종료 UI 제어폭을 검증한다.

제2차 UI master entry 20은 동적으로 남은 유닛 수를 그린다. 한국어 문구가
일본어보다 짧아진 만큼 그 숫자 앞의 커서 이동을 `FC 10`에서 `FC 0B`로
줄여야 한다. 중간 `font_extracted` 파일만 검사하면 최종 이미지 조립기가
낡은 v0.8.7 이미지에서 다시 읽는 회귀를 놓칠 수 있으므로, 반드시
`build/final/SECOND_SECOND.WAR`를 직접 검사한다.
"""
from __future__ import annotations

import os as _os
import struct
import sys
from pathlib import Path

_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, "srwcb_paths.py")):
    _d = _os.path.dirname(_d)
if _d not in sys.path:
    sys.path.insert(0, _d)
sys.path.insert(0, str(Path(_d) / "tools"))

import srwcb_paths as _P  # noqa: E402
from patch_second_exe_ui import parse_second_ui_vm_record  # noqa: E402


SECOND = _P.FINAL / "SECOND_SECOND.WAR"
POINTER_FIELD = 0x24374
OLD_CONTROL = bytes.fromhex("FC 10 FC F8 82")
NEW_CONTROL = bytes.fromhex("FC 0B FC F8 82")


def main() -> int:
    if not SECOND.exists():
        raise SystemExit(f"[없음] 최종 제2차 실행파일: {SECOND}")
    data = SECOND.read_bytes()
    if POINTER_FIELD + 4 > len(data):
        raise SystemExit("제2차 페이즈 UI 포인터 필드가 파일 밖이다")
    target = POINTER_FIELD + struct.unpack_from("<i", data, POINTER_FIELD)[0]
    end, _tokens = parse_second_ui_vm_record(data, target)
    record = data[target:end]
    new_count = record.count(NEW_CONTROL)
    old_count = record.count(OLD_CONTROL)
    if new_count != 1 or old_count != 0:
        raise SystemExit(
            "제2차 페이즈 종료 UI 제어폭 검증 실패: "
            f"target={target:#x}, FC0B={new_count}, FC10={old_count}"
        )
    print(
        "제2차 페이즈 종료 UI 검증 통과: "
        f"entry20 target={target:#x}, FC 0B 1건, FC 10 0건"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
