#!/usr/bin/env python3
"""게이트: EX·트레이닝 '어느 장부터?' 장 선택 줄의 이름 칸이 레트일과 같은 폭인가.

장 선택 줄은 `[장 이름] EE FF [레벨]` 두 칸이다. `EE FF`(0x3FF) 는 전각 스페이서라 폭이
`1 + phase` 이고, 이름 칸의 폭·끝 phase 가 레트일과 다르면 레벨 칸 시작이 어긋난다
(srwcb-ui-column-spacer). 레트일:

    マサキの章  폭 5, 끝 phase 1      リュ-ネの章  폭 6, 끝 phase 1      シュウの章  폭 5, 끝 phase 1

v0.11.45 에서 EX 의 `슈우편 ␣` 을 `슈우편` 으로 줄였다(폭 4). 레벨 앞 공백도 함께 지워
레벨 칸이 다른 줄보다 2 만큼 왼쪽에서 시작했고, 칸 구분선이 `레|벨` 사이에 걸렸다
(제보 #4, v0.11.54). 트레이닝 모드(TR.WAR)는 바뀌지 않아 정상이었다.

불변식 (UI 표 94~97 의 스페이서 줄마다, 레트일 같은 줄과 비교):
  1. 스페이서(칸 구분자)가 있다.
  2. 첫 칸(이름)의 폭과 끝 phase 가 같다.
  3. 둘째 칸 첫 '보이는' 글자의 절대 위치가 같다(원문은 모든 줄이 8).
     ISS 질문 창에 가려 잘린 부분 줄(94·95·97 의 뒷줄)도 같은 규칙이다.

생성기(inject_ex_ui)를 import 하지 않는다 — 최종 이미지의 실행파일을 직접 읽는다.
"""
from __future__ import annotations

import os
import struct
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "srwcb_paths.py")):
    _d = os.path.dirname(_d)
for _s in ("", "tools", "image-build"):
    _p = os.path.join(_d, _s) if _s else _d
    if _p not in sys.path:
        sys.path.insert(0, _p)
import srwcb_paths as _P                                          # noqa: E402
import assemble_image as AI                                       # noqa: E402
from patch_second_exe_ui import parse_second_ui_vm_record         # noqa: E402
from second_translation_codec import glyph_advance                # noqa: E402

#: (이미지 경로, UI 표 머리, 항목 수) — ex-ui/inject_ex_ui.py · tr-ui/inject_tr_ui.py 와 같은 값
TARGETS = {"EX": ("EX/EX.WAR", 0x188C4, 107), "트레이닝": ("TR.WAR", 0x188BC, 107)}
SPACER = 0x3FF
#: 장 선택 화면 레코드 (UI 표 항목 94~97: 2장 / 2장+ISS / 3장 / 3장+ISS). EX·TR 공통.
CHAPTER_RECORDS = range(94, 98)
#: 레트일에서 스페이서로 칸이 나뉜 줄 수(제목 줄 제외): 2 + 2 + 3 + 3
EXPECTED_LINES = 10


def _glyph_index(raw: bytes) -> int:
    return raw[0] if len(raw) == 1 else ((raw[0] - 0xEB) << 8) | raw[1]


#: 폭 0 으로 보이는 빈 글리프: 0x00(반각 빈칸)과 전각 빈칸. 첫 '보이는 글자' 위치를 잴 때 건너뛴다.
BLANKS = {0x00}


def lines(buf: bytes, start: int):
    """레코드를 F6 로 나눈 줄마다 스페이서 칸 정보.

    반환: [(이름 칸 폭, 이름 칸 끝 phase, 둘째 칸 첫 보이는 글자의 절대 위치 | None)]
    스페이서가 없는 줄은 None 으로 둔다.
    """
    _end, toks = parse_second_ui_vm_record(buf, start)
    out = []
    adv = phase = 0
    col1 = None
    first2 = None
    seen_sp = False

    def flush():
        out.append((col1[0], col1[1], first2) if seen_sp else None)

    for t in toks:
        if t.kind not in ("glyph", "compact_data"):
            if t.raw[:1] == bytes((0xF6,)):
                flush()
                adv = phase = 0
                col1 = None
                first2 = None
                seen_sp = False
            continue
        g = _glyph_index(t.raw)
        if g == SPACER and not seen_sp:
            col1 = (adv, phase)
            seen_sp = True
        elif seen_sp and first2 is None and g not in BLANKS and g != SPACER and g not in blank_glyphs:
            first2 = adv
        step, phase = glyph_advance(g, phase)
        adv += step
    return out


def _blank_glyphs() -> set[int]:
    """반각·전각 빈칸 글리프 인덱스(레트일 폰트 + 한글 폰트)."""
    import json
    out = set()
    doc = json.loads(_P.FONT_MAPPING.read_text(encoding="utf-8"))
    out |= {int(r["glyph_index"]) for r in doc["rows"] if r.get("character") in ("　", " ")}
    from second_translation_codec import load_safe_glyph_map
    gm = load_safe_glyph_map()
    out |= {gm[c] for c in (" ", "　") if c in gm}
    return out


blank_glyphs: set[int] = _blank_glyphs()


def chapter_records(buf: bytes, head: int, count: int, want: range):
    out = {}
    for k in want:
        f = head + 4 + 4 * k
        out[k] = f + struct.unpack_from("<i", buf, f)[0]
    return out


def check(ko: bytes, jp: bytes, label: str, head: int, count: int) -> int:
    bad = 0
    n = 0
    rj = chapter_records(jp, head, count, CHAPTER_RECORDS)
    rk = chapter_records(ko, head, count, CHAPTER_RECORDS)
    for k in CHAPTER_RECORDS:
        lj, lk = lines(jp, rj[k]), lines(ko, rk[k])
        if len(lj) != len(lk):
            print(f"  [실패] {label} ui[{k}]: 줄 수 {len(lj)} -> {len(lk)}")
            bad += 1
            continue
        for li, (a, b) in enumerate(zip(lj, lk)):
            if a is None:
                continue
            n += 1
            if b is None:
                print(f"  [실패] {label} ui[{k}] 줄{li}: 스페이서(칸 구분자)가 사라졌다")
                bad += 1
                continue
            if (a[0], a[1]) != (b[0], b[1]):
                print(f"  [실패] {label} ui[{k}] 줄{li}: 이름 칸 폭/끝 phase {b[0]}/{b[1]} ≠ 레트일 {a[0]}/{a[1]}")
                bad += 1
            if a[2] is not None and b[2] is not None and a[2] != b[2]:
                print(f"  [실패] {label} ui[{k}] 줄{li}: 둘째 칸 첫 글자 위치 {b[2]} ≠ 레트일 {a[2]} "
                      "(칸 구분선이 글자에 걸린다)")
                bad += 1
    if n < EXPECTED_LINES:
        print(f"  [실패] {label}: 스페이서 줄을 {n}개만 찾았다 (기대 {EXPECTED_LINES}) — 탐지기가 상했다")
        bad += 1
    print(f"  {label:5} 장 선택 레코드 {len(CHAPTER_RECORDS)}개 · 칸 나눈 줄 {n}개 검사, 위반 {bad}건")
    return bad


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    a = ap.parse_args()
    img = _P.OUT / f"Super Robot Taisen Complete Box Korean {a.version} (Track 1).bin"
    with AI.RawMode2Image(img) as m:
        _, entries = AI.read_tree(m)
    by = {e.path.strip("/"): e for e in entries}
    bad = 0
    for label, (rel, head, count) in TARGETS.items():
        ko = AI.read_file(img, by[rel].lba, by[rel].size)
        jp = (_P.EXTRACTED / rel).read_bytes()
        bad += check(ko, jp, label, head, count)
    if bad:
        print(f"FAIL 장 선택 줄 {bad}건")
        return 1
    print("PASS 장 선택 줄의 이름 칸 폭·phase 와 레벨 칸 시작이 레트일과 맞는다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
