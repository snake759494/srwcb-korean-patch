#!/usr/bin/env python3
"""게이트: 레트일 스크립트에 **등록되지 않은 대사/블록 포인터 형식**이 없는가.

모든 재조준기와 게이트는 `analyze_sce_relocation.iter_pointer_sites` 의 하드코딩 목록으로
후보를 연다. 목록에 없는 형식은 '검사해서 통과' 가 아니라 **방문조차 안 된다**
(FREEZE_RULEBOOK R-OPSET). 제2차 8화 정지(제보 #1, v0.11.54)가 바로 이것이었다 —
작전목적 창을 여는 `E7 02 <s16>` 이 목록에 없어 번역으로 밀린 블록을 옛 변위로 가리켰다.

판정 (레트일 세 게임 시나리오 풀 앞 스크립트 전수):
  * 형식 = `<op> <s16>` (피연산자 +1) 또는 `<op> <sub> <s16>` (피연산자 +2)
  * 적중 = 목표가 풀 안이고 **바로 앞 바이트가 0xFF** (레코드·블록 시작 후보)
  * 기준선(무작위) 약 0.8%. 표본 MIN_SAMPLES 이상이고 적중률 THRESHOLD 이상인데 목록에
    없는 형식이 있으면 실패한다.
  * **그림자 제거**: `<x> B1 <s16>` 은 B1 앞 바이트를 옵코드로 잘못 읽은 것이라 +2 자리가
    B1 의 +1 피연산자와 같다. sub 가 +1 포인터 옵코드인 +2 형식은 버린다.

레트일만 읽는다(이미지 불필요). `--version` 은 build_all 호환용.
"""
from __future__ import annotations

import collections
import os
import struct
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "srwcb_paths.py")):
    _d = os.path.dirname(_d)
for _s in ("", "tools"):
    _p = os.path.join(_d, _s) if _s else _d
    if _p not in sys.path:
        sys.path.insert(0, _p)
import srwcb_paths as _P                    # noqa: E402
import analyze_sce_relocation as A          # noqa: E402

SCE = ("SECOND/2_SCE.BIN", "THIRD/3_SCE.BIN", "EX/E_SCE.BIN")
MIN_SAMPLES = 8
THRESHOLD = 0.20
#: 탐지기 건강 확인 — 이미 아는 형식이 이만큼은 걸려야 한다.
MUST_SEE = {("+1", 0xB1): 0.9, ("+2", (0xE7, 0x02)): 0.9, ("+2", (0xB9, 0x03)): 0.9}


def scan():
    agg = collections.Counter()
    hit = collections.Counter()
    for rel in SCE:
        buf = (_P.EXTRACTED / rel).read_bytes()
        for s in A.parse_scenarios(buf):
            lo, hi = s.pool_start, s.record_data_end
            for off in range(s.block_start, s.pool_start - 4):
                op = buf[off]
                t1 = off + 1 + struct.unpack_from("<h", buf, off + 1)[0]
                agg[("+1", op)] += 1
                if lo < t1 < hi and buf[t1 - 1] == 0xFF:
                    hit[("+1", op)] += 1
                sub = buf[off + 1]
                if sub in A.TEXT_POINTER_OPCODES:
                    continue                    # 그림자
                t2 = off + 2 + struct.unpack_from("<h", buf, off + 2)[0]
                agg[("+2", (op, sub))] += 1
                if lo < t2 < hi and buf[t2 - 1] == 0xFF:
                    hit[("+2", (op, sub))] += 1
    return agg, hit


def registered(key) -> bool:
    kind, form = key
    return (form in A.TEXT_POINTER_OPCODES if kind == "+1"
            else form in A.ARG_POINTER_FORMS or form in A.BLOCK_POINTER_FORMS)


def main() -> int:
    agg, hit = scan()
    bad = 0
    base = sum(hit.values()) / max(1, sum(agg.values()))
    for key, want in MUST_SEE.items():
        rate = hit[key] / agg[key] if agg[key] else 0
        if rate < want:
            print(f"  [실패] 탐지기 이상: {key} 적중률 {rate:.1%} < {want:.0%}")
            bad += 1
    flagged = []
    for key, n in agg.items():
        if n >= MIN_SAMPLES and hit[key] / n >= THRESHOLD and not registered(key):
            flagged.append((key, hit[key], n))
    for (kind, form), h, n in sorted(flagged, key=lambda x: -x[1] / x[2]):
        name = f"{form:02X}" if kind == "+1" else f"{form[0]:02X} {form[1]:02X}"
        print(f"  [실패] 미등록 포인터 형식 후보 {kind} {name}: {h}/{n} = {h / n:.1%} "
              f"(기준선 {base:.2%}) — 표본을 열어 보고 ARG/BLOCK_POINTER_FORMS 에 넣거나 제외 사유를 적어라")
        bad += 1
    print(f"  기준선 {base:.2%}, 형식 {len(agg)}종 검사, 미등록 고적중 {len(flagged)}종")
    if bad:
        print(f"FAIL 포인터 형식 {bad}건")
        return 1
    print("PASS 레트일에서 적중률이 높은 포인터 형식은 모두 등록돼 있다")
    return 0


if __name__ == "__main__":
    if "--version" in sys.argv:
        pass
    raise SystemExit(main())
