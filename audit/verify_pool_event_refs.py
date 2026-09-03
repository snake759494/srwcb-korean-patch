#!/usr/bin/env python3
"""게이트: 풀 안 이벤트 스크립트의 레코드 참조가 배포본에서도 같은 레코드를 가리키는가.

**재조준기(second-fixes/fix_sce_event_refs.py)와 독립적으로** 판정한다. 재조준기가
어떤 자리를 '포인터가 아니다'라고 걸러 내면 그 자리는 스테일로 남는데, 재조준기의
자체 점검은 같은 필터를 쓰므로 함께 눈이 먼다. v0.11.45~v0.11.52 의 제2차 sc4
rec0+0x85 이 정확히 그랬고(피연산자의 낮은 바이트가 레코드 종단자 0xFF 와 겹치는
자리), 제2차 초반 이벤트가 남의 레코드 한가운데로 뛰어 정지했다(#39).

불변식:
    레트일에서 **레코드 시작을 겨누는** 대사 포인터는, 배포본에서도
    **같은 서수의 레코드 시작**을 겨눠야 한다.
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
import srwcb_paths as _P                                       # noqa: E402
import assemble_image as AI                                    # noqa: E402
from analyze_sce_relocation import parse_scenarios, iter_pointer_sites  # noqa: E402

FILES = {"제2차": "SECOND/2_SCE.BIN", "제3차": "THIRD/3_SCE.BIN", "EX": "EX/E_SCE.BIN"}


def check(ko: bytes, jp: bytes, label: str) -> int:
    bj, bk = parse_scenarios(jp), parse_scenarios(ko)
    if len(bj) != len(bk):
        print(f"  [실패] {label}: 시나리오 수 {len(bj)} != {len(bk)}")
        return 1
    bad = seen = 0
    for si, (sj, sk) in enumerate(zip(bj, bk)):
        if len(sj.records) != len(sk.records):
            print(f"  [실패] {label} sc{si}: 레코드 수 {len(sj.records)} != {len(sk.records)}")
            bad += 1
            continue
        starts = {r.start: i for i, r in enumerate(sj.records)}
        for off, operand, _op in iter_pointer_sites(jp, sj.pool_start, sj.record_data_end):
            host = next((i for i, r in enumerate(sj.records) if r.start <= off < r.end), None)
            if host is None or operand >= sj.records[host].end:
                continue
            # 이벤트 스크립트 레코드는 재번역되지 않으므로 길이가 그대로다. 길이가
            # 달라진 레코드는 텍스트라 host 상대 오프셋이 대응하지 않는다 — 건너뛴다.
            hj, hk = sj.records[host], sk.records[host]
            if hj.end - hj.start != hk.end - hk.start:
                continue
            disp = struct.unpack_from("<h", jp, operand)[0]
            ordinal = starts.get(operand + disp)
            if ordinal is None:
                continue                       # 레코드 시작을 안 겨누면 이벤트 참조가 아니다
            seen += 1
            rel = off - sj.records[host].start
            k_off = sk.records[host].start + rel
            k_operand = k_off + (operand - off)
            if k_operand + 2 > len(ko):
                print(f"  [실패] {label} sc{si} rec{host}+0x{rel:X}: 피연산자가 파일 밖")
                bad += 1
                continue
            if ko[k_off] != jp[off]:
                continue                       # 옵코드가 다르면 대응하는 자리가 아니다
            k_disp = struct.unpack_from("<h", ko, k_operand)[0]
            want = sk.records[ordinal].start
            if k_operand + k_disp != want:
                print(f"  [실패] {label} sc{si} rec{host}+0x{rel:X}: "
                      f"0x{k_operand + k_disp:X} 를 겨눔, 서수 {ordinal} 은 0x{want:X}")
                bad += 1
    print(f"  {label:5} 레코드 참조 {seen}건 검사, 스테일 {bad}건")
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
    for label, rel in FILES.items():
        if rel not in by:
            print(f"  [실패] 이미지에 {rel} 없음")
            bad += 1
            continue
        ko = AI.read_file(img, by[rel].lba, by[rel].size)
        jp = (_P.EXTRACTED / rel).read_bytes()
        bad += check(ko, jp, label)
    if bad:
        print(f"FAIL 풀 이벤트 참조 스테일 {bad}건")
        return 1
    print("PASS 모든 풀 이벤트 참조가 같은 서수의 레코드를 겨눈다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
