#!/usr/bin/env python3
"""게이트: 풀 안 이벤트 스크립트의 레코드 참조가 배포본에서도 같은 레코드를 가리키는가.

**재조준기(second-fixes/fix_sce_event_refs.py)와 독립적으로** 판정한다. 재조준기가
어떤 자리를 '포인터가 아니다'라고 걸러 내면 그 자리는 스테일로 남는데, 재조준기의
자체 점검은 같은 필터를 쓰므로 함께 눈이 먼다. v0.11.45~v0.11.52 의 제2차 sc4
rec0+0x85 이 정확히 그랬고(피연산자의 낮은 바이트가 레코드 종단자 0xFF 와 겹치는
자리), 제2차 초반 이벤트가 남의 레코드 한가운데로 뛰어 정지했다(#39).

불변식:
    레트일에서 **레코드 시작을 겨누던** 대사 포인터는, 배포본에서도
    **어떤 레코드의 시작**에 착지해야 한다.

서수(몇 번째 레코드인가)로 판정하지 않는다. 변위가 0xFF 를 품으면 레코드 훑기가
레트일과 다른 데서 끊겨 서수가 밀리기 때문이다(제2차 sc4). 반면 **실패 양상은 늘
같다** — 참조가 레코드 시작이 아닌 곳에 착지해 스크립트가 남의 레코드 한가운데로
뛴다. 그 하나만 본다.
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


def _operand_mask(jp: bytes, scn, start: int, end: int) -> set[int]:
    """[start, end) 안에서 대사 포인터의 2바이트 피연산자가 차지하는 자리."""
    mask: set[int] = set()
    for off, operand, _op in iter_pointer_sites(jp, start, end):
        for k in (operand, operand + 1):
            if start <= k < end:
                mask.add(k)
    return mask


def _prefix_matches(jp: bytes, j_start: int, ko: bytes, k_start: int,
                    rel: int, scn, host: int) -> bool:
    """레코드 시작부터 참조 자리까지가 같은가 — 피연산자 자리는 빼고 본다."""
    if j_start + rel > len(jp) or k_start + rel > len(ko):
        return False
    mask = _operand_mask(jp, scn, j_start, j_start + rel)
    for i in range(rel):
        if j_start + i in mask:
            continue
        if jp[j_start + i] != ko[k_start + i]:
            return False
    return True


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
        ko_starts = {r.start for r in sk.records}
        for off, operand, _op in iter_pointer_sites(jp, sj.pool_start, sj.record_data_end):
            host = next((i for i, r in enumerate(sj.records) if r.start <= off < r.end), None)
            if host is None or operand >= sj.records[host].end:
                continue
            # host 레코드 **길이**로 거르면, 변위가 0xFF 를 품어 레코드 훑기가
            # 다른 데서 끊긴 자리(제2차 sc4)를 검사에서 통째로 빼 버린다. 그건
            # 정확히 이 게이트가 잡아야 할 자리다. 길이 대신 **레코드 시작부터
            # 참조 자리까지의 바이트가 같은지**로 판정한다. 이벤트 스크립트 본문은
            # 재번역되지 않으므로, 앞부분이 같으면 상대 오프셋 매핑이 성립한다
            # (달라질 수 있는 것은 다른 참조의 2바이트 피연산자뿐이다).
            hj, hk = sj.records[host], sk.records[host]
            rel = off - hj.start
            if hk.start + rel + 3 > len(ko):
                continue
            if not _prefix_matches(jp, hj.start, ko, hk.start, rel, sj, host):
                continue
            disp = struct.unpack_from("<h", jp, operand)[0]
            ordinal = starts.get(operand + disp)
            if ordinal is None:
                continue                       # 레코드 시작을 안 겨누면 이벤트 참조가 아니다
            seen += 1
            k_off = hk.start + rel
            k_operand = k_off + (operand - off)
            if k_operand + 2 > len(ko):
                print(f"  [실패] {label} sc{si} rec{host}+0x{rel:X}: 피연산자가 파일 밖")
                bad += 1
                continue
            if ko[k_off] != jp[off]:
                continue                       # 옵코드가 다르면 대응하는 자리가 아니다
            k_disp = struct.unpack_from("<h", ko, k_operand)[0]
            k_tgt = k_operand + k_disp
            # 판정 기준은 **착지 지점**이다. 서수 대응은 레코드 분할이 흔들리면
            # (변위가 0xFF 를 품으면 레코드 훑기가 다른 데서 끊긴다) 못 믿는다.
            # 반면 실패 양상은 늘 같다 — 참조가 **레코드 시작이 아닌 곳**에 착지해
            # 스크립트가 남의 레코드 한가운데로 뛴다. 그것만 본다.
            if k_tgt not in ko_starts:
                near = max((x for x in ko_starts if x <= k_tgt), default=None)
                off_in = f", 레코드 시작 0x{near:X} 에서 +{k_tgt - near}" if near else ""
                print(f"  [실패] {label} sc{si} rec{host}+0x{rel:X}: "
                      f"0x{k_tgt:X} 는 레코드 시작이 아니다{off_in}")
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
    print("PASS 모든 풀 이벤트 참조가 레코드 시작에 착지한다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
