#!/usr/bin/env python3
"""게이트: 작전목적 헤더 `04 00 <창폭> 00` 이 레트일과 바이트까지 같은가.

작전목적(승리/패배조건) 레코드는 텍스트 앞에 **이진 제어 프리픽스**를 갖는다. 그 안의
`04 00 <창폭> 00` 이 재인코딩에서 찌그러지면(`04 XX` 로 뭉개지는 등) 목표가 바뀌는
순간 게임이 멈춘다 — EX 마사키 9·11·27화, 류네 45·49화, 슈우 58화(제보 #10·#11·#24).

**이 부류를 보는 게이트가 지금까지 하나도 없었다.** `verify_image.check_objective_block`
은 같은 레코드 집합을 보지만 재는 것이 **줄 수**뿐이고, 게다가 `_is_dialogue` 텍스트다움
필터를 먼저 걸어 이진 레코드를 통째로 건너뛴다. `verify_sce_script` 는 풀 **앞** 구간만
본다 — 작전목적 레코드는 풀 **안**이라 범위 밖이다. 레코드 길이는 보존되므로 재배치·
포인터 계열 게이트에도 안 걸린다. 실제로 v0.11.53 에서 EX 헤더 6곳을 뭉개고 기존 게이트를
전부 돌렸더니 "깨진 레코드 0" 으로 통과했다.

불변식:
    레코드 시작부터 `04 00 <창폭> 00` 끝까지의 바이트는 레트일과 완전히 같다.

생성기(ex_gap_apply._obj_hdr, build_second_expanded_patch 의 prefix 계산)를 import 하지
않는다 — 레트일과 최종 이미지를 직접 대조한다.
"""
from __future__ import annotations
import os, struct, sys
from pathlib import Path

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "srwcb_paths.py")):
    _d = os.path.dirname(_d)
for _s in ("", "tools", "image-build"):
    _p = os.path.join(_d, _s) if _s else _d
    if _p not in sys.path:
        sys.path.insert(0, _p)
import srwcb_paths as _P                                        # noqa: E402
import assemble_image as AI                                     # noqa: E402
from analyze_sce_relocation import (parse_scenarios,            # noqa: E402
                                    objective_block_records)

SCE = {"제2차": "SECOND/2_SCE.BIN", "제3차": "THIRD/3_SCE.BIN", "EX": "EX/E_SCE.BIN"}
#: 작전목적 머리글 앵커. `E9 03 FE FF` 뒤에 `04 00 <창폭> 00` 이 온다.
ANCHOR = bytes((0xE9, 0x03, 0xFE, 0xFF, 0x04, 0x00))
#: 레트일 실측 개수. 탐지기가 상하면 조용히 0건 통과하는 대신 소리 내어 실패한다.
EXPECTED = {"제2차": 51, "제3차": 70, "EX": 71}


def headers(buf: bytes) -> list[tuple[int, int, int]]:
    """(시나리오 번호, 레코드 순번, 창폭) — 나온 순서 그대로.

    헤더는 레코드 선두가 아니다. 제2차·제3차는 앞에 VM 스크립트가 붙어
    프리픽스 **끝**에 온다. 그 프리픽스에는 재배치로 값이 바뀌는 B3/B4 변위가
    섞여 있으므로 프리픽스 전체를 대조하면 안 된다 — 앵커만 본다.
    """
    out = []
    for si, scn in enumerate(parse_scenarios(buf)):
        for ri, rec in enumerate(scn.records):
            p = rec.start
            while True:
                p = buf.find(ANCHOR, p, rec.end)
                if p < 0:
                    break
                if p + 8 <= rec.end and buf[p + 7] == 0x00:
                    out.append((si, ri, buf[p + 6]))
                p += 1
    return out


def check(ko: bytes, jp: bytes, label: str) -> int:
    hj, hk = headers(jp), headers(ko)
    bad = 0
    want = EXPECTED.get(label)
    if want is not None and len(hj) != want:
        print(f"  [실패] {label}: 레트일 머리글 {len(hj)}개 (기대 {want}) — 탐지기가 상했다")
        bad += 1
    if len(hj) != len(hk):
        print(f"  [실패] {label}: 머리글 {len(hj)}개 -> {len(hk)}개 "
              f"({len(hj) - len(hk)}개가 사라졌다 = 머리글이 찌그러졌다)")
        bad += 1
        gone = [x for x in hj if x not in set(hk)][:6]
        for si, ri, w in gone:
            print(f"          없어진 것: sc{si} rec{ri} 창폭 {w}")
    else:
        for x, y in zip(hj, hk):
            if x != y:
                print(f"  [실패] {label}: sc{x[0]} rec{x[1]} 창폭 {x[2]} -> "
                      f"sc{y[0]} rec{y[1]} 창폭 {y[2]}")
                bad += 1
    print(f"  {label:5} 작전목적 머리글 {len(hj)}개 검사, 위반 {bad}건")
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
    for label, rel in SCE.items():
        if rel not in by:
            print(f"  [실패] 이미지에 {rel} 없음")
            bad += 1
            continue
        bad += check(AI.read_file(img, by[rel].lba, by[rel].size),
                     (_P.EXTRACTED / rel).read_bytes(), label)
    if bad:
        print(f"FAIL 작전목적 헤더 {bad}건")
        return 1
    print("PASS 작전목적 헤더가 레트일과 바이트까지 같다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
