# -*- coding: utf-8 -*-
"""제3차·EX 단독판 `Z_SMAP.BIN` 의 타이틀 메뉴(スタート/ロード/コンティニュー)를 한글로.

단독판 3종의 `Z_SMAP.BIN` 은 CB `C_SMAP.BIN` 과 **같은 멤버 번호**에 같은 타이틀 그림을
갖는다 — 멤버 29 = 제3차, 멤버 33 = EX (파일 오프셋 0x10FEDF / 0x135007). 단독판 멤버는
CB 것과 TIM 두 장이 더 있지만 메뉴 9장은 VRAM 좌표가 같아 CB 의 `redraw_menu` 가 그대로
먹는다. 재압축 여유는 788B / 873B (실측).

제2차 단독판(`build_zsmap_ko.py`)이 멤버 25 + 프롤로그를 처리하는 것과 짝을 이룬다.
여기서는 **타이틀 메뉴만** 손댄다(이슈 #3). 두 멤버를 모두 고쳐 어느 쪽 화면이 뜨든 한글이다.

    python standalone/build_zsmap_title_ko.py srw3
    python standalone/build_zsmap_title_ko.py srwex
"""
import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "srwcb_paths.py")):
    _d = os.path.dirname(_d)
if _d not in sys.path:
    sys.path.insert(0, _d)
import srwcb_paths as _P  # noqa: E402

sys.path.insert(0, os.path.join(_d, "tools", "graphics"))
sys.path.insert(0, os.path.join(_d, "image-build"))
import smap_ko as SM  # noqa: E402
import assemble_image as AI  # noqa: E402

DISCS = {
    "srw3": ("SRWCB_SRW3_BIN", "Dai 3 Ji Super Robot Taisen.bin"),
    "srwex": ("SRWCB_SRWEX_IMG", "Super Robot Taisen EX (J).img"),
}
TITLE_MEMBERS = (29, 33)          # 제3차, EX — 둘 다 고친다
NAME = "Z_SMAP.BIN"


def retail_zsmap(key):
    cached = _P.WORK / key / "extracted" / NAME
    if cached.exists():
        return cached.read_bytes()
    env, default = DISCS[key]
    img = _P.WORK / key / default
    img = __import__("pathlib").Path(os.environ.get(env, str(img)))
    with AI.RawMode2Image(img) as m:
        _, entries = AI.read_tree(m)
    for e in entries:
        if e.path.strip("/") == NAME:
            data = AI.read_file(img, e.lba, e.size)
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
            return data
    raise SystemExit(f"[없음] {key} 디스크에 {NAME} 이 없습니다")


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    if key not in DISCS:
        raise SystemExit("사용법: build_zsmap_title_ko.py srw3|srwex")
    src = retail_zsmap(key)
    ms = SM.members(src)
    out = bytearray(src)
    for idx in TITLE_MEMBERS:
        s, e = ms[idx]
        new, used = SM._patch_stream(src, s, e, SM.redraw_menu, f"{key} 타이틀 멤버{idx}", print)
        out[s:s + len(new)] = new          # 남는 꼬리는 원본 바이트 유지
    assert len(out) == len(src), "크기 변동 — 제자리 교체가 안 된다"
    dst = _P.BUILD / "gfx" / f"Z_SMAP_{key}_ko.BIN"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(bytes(out))
    print(f"WROTE {dst} ({len(out):,}B, 원본과 같은 크기)")


if __name__ == "__main__":
    main()
