# -*- coding: utf-8 -*-
"""컴플리트 박스 제2차·제3차·EX 타이틀 메뉴 그래픽 검증.

C_SMAP.BIN 안의 세 타이틀 화면은 서로 다른 압축 멤버지만, 메뉴 9장(TIM)의
VRAM 좌표와 한글 렌더링 규칙은 같다. 각 멤버를 레트일에서 다시 생성한 기대값과
비교해 한 화면만 빠지는 회귀를 잡는다.
"""
import os
import sys
from pathlib import Path

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "srwcb_paths.py")):
    _d = os.path.dirname(_d)
for _s in ("", "tools/graphics"):
    _p = os.path.join(_d, *_s.split("/")) if _s else _d
    if _p not in sys.path:
        sys.path.insert(0, _p)

import srwcb_paths as _P             # noqa: E402
import smap_ko as SM                 # noqa: E402
from srw_lz_fast import decompress   # noqa: E402


TARGETS = (
    (25, "제2차"),
    (29, "제3차"),
    (33, "EX"),
)


def raw_member(data: bytes, target: int) -> tuple[int, int, bytes]:
    start, end = SM.members(data)[target]
    raw, used = decompress(data[start:end], 0)
    # 제자리 재압축 멤버는 종료 마커 뒤에 원본 꼬리를 보존할 수 있다.
    if used > end - start:
        raise SystemExit(f"C_SMAP 멤버 {target}: 압축 소비 길이 불일치")
    return start, end, raw


def main() -> None:
    retail_path = _P.EXTRACTED / "C_SMAP.BIN"
    korean_path = _P.BUILD / "gfx" / "C_SMAP_ko.BIN"
    if not retail_path.exists() or not korean_path.exists():
        raise SystemExit("C_SMAP 원본/한글판이 없습니다 — 그래픽 빌드를 먼저 실행하세요.")

    retail = retail_path.read_bytes()
    korean = korean_path.read_bytes()
    if len(retail) != len(korean):
        raise SystemExit("C_SMAP 파일 크기가 달라졌습니다")

    bad = 0
    for target, name in TARGETS:
        rs, re, rraw = raw_member(retail, target)
        ks, ke, kraw = raw_member(korean, target)
        if (rs, re) != (ks, ke):
            print(f"  [실패] {name}: 멤버 위치가 레트일과 다름")
            bad += 1
            continue
        expected = bytearray(rraw)
        touched = SM.redraw_menu(expected, SM.tims(rraw))
        if len(touched) != len(SM.MENU_BY_VRAM):
            print(f"  [실패] {name}: 메뉴 TIM {len(touched)}/9")
            bad += 1
            continue
        if SM.tims(kraw) != SM.tims(rraw):
            print(f"  [실패] {name}: TIM 목록이 레트일과 다름")
            bad += 1
            continue
        if kraw != bytes(expected):
            changed = sum(a != b for a, b in zip(rraw, kraw))
            print(f"  [실패] {name}: 한글 메뉴 기대값과 불일치 (변경 {changed}B)")
            bad += 1
            continue
        print(f"  {name}: 메뉴 9장·TIM 구조·렌더링 기대값 일치")

    if bad:
        raise SystemExit(f"타이틀 메뉴 검증 실패 {bad}건")
    print("타이틀 메뉴 검증 통과: 제2차·제3차·EX 모두 한글")


if __name__ == "__main__":
    main()
