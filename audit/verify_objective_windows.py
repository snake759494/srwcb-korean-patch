#!/usr/bin/env python3
"""게이트: 작전목적 창 블록과 `E7 02` 변위가 맞물리는가.

블록 구조와 기전은 `tools/objective_windows.py` 머리말 참고. 요약:

    04 00 | L 00 | 승리조건 FF | FF | 패배조건 FF | FF      (E7 02 <변위> 가 겨눔)

`E7 02` 는 두 문자열을 **스택 128바이트 버퍼에 0xFF 까지 무검사 복사**한다. 그래서

1. 레트일이 블록 k 를 겨눈 `E7 02` 는 배포본에서도 **블록 k 의 시작**을 겨눠야 한다.
   어긋나면 쓰레기 u16 을 오프셋으로 읽어 시나리오 밖을 수 KB 복사하고 장면 끝에서
   메인 루프의 ra 가 깨져 정지한다(제보 #1, 제2차 8화, v0.11.54).
2. 모든 블록(E7 02 대상 ∪ `E9 03 FE FF` 머리글 블록)의 L 은 **패배조건 시작 − 2** 와
   같아야 한다(변형 A 는 승리 종단, 변형 B 는 승리 종단 − 1). 어긋나면 패배조건이 빈 칸이나
   글자 중간부터 나온다(v0.11.54 제2차 14곳 · EX 1곳).
3. 시나리오마다 머리글 블록 수가 레트일과 같아야 한다.

수정기(`objective_windows.fix`)를 부르지 않는다 — 레트일과 최종 이미지의 **모양**만
대조한다. 블록은 모양이 아니라 레트일 E7 02 의 목표로 정의한다(모양은 오탐이 난다).
"""
from __future__ import annotations

import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "srwcb_paths.py")):
    _d = os.path.dirname(_d)
for _s in ("", "tools", "image-build"):
    _p = os.path.join(_d, _s) if _s else _d
    if _p not in sys.path:
        sys.path.insert(0, _p)
import srwcb_paths as _P                     # noqa: E402
import assemble_image as AI                  # noqa: E402
import objective_windows as OW               # noqa: E402

SCE = {"제2차": "SECOND/2_SCE.BIN", "제3차": "THIRD/3_SCE.BIN", "EX": "EX/E_SCE.BIN"}
#: 레트일 실측 (E7 02 사이트 수, `E9 03 FE FF` 머리글 블록 수).
#: 탐지기가 상해 0건으로 조용히 통과하는 대신 소리 내어 실패하게 한다.
EXPECTED = {"제2차": (53, 51), "제3차": (79, 70), "EX": (78, 71)}


def check(ko: bytes, jp: bytes, label: str) -> int:
    rep = OW.audit(ko, jp)
    bad = 0
    want = EXPECTED.get(label)
    if want and (rep["retail_sites"], rep["anchored"]) != want:
        print(f"  [실패] {label}: 레트일 E7 02 {rep['retail_sites']}곳 · 머리글 블록 "
              f"{rep['anchored']}개 (기대 {want}) — 탐지기가 상했다")
        bad += 1
    for si, nj, nk in rep["anchor_mismatch"]:
        print(f"  [실패] {label} sc{si}: 머리글 블록 {nj}개 -> {nk}개")
        bad += 1
    for si, rel, prob in rep["problems"]:
        print(f"  [실패] {label} sc{si} +{rel:#x}: {prob}")
        bad += 1
    for si, rel, blk in rep["stale"]:
        print(f"  [실패] {label} sc{si} +{rel:#x}: E7 02 가 블록(+{blk:#x})을 못 겨눈다 "
              "(스테일 변위 — 장면 끝 정지)")
        bad += 1
    for si, off, have, need in rep["bad_len"]:
        print(f"  [실패] {label} sc{si} 블록 +{off:#x}: L {have:#x} ≠ 기대 {need:#x} "
              "(패배조건이 깨져 나온다)")
        bad += 1
    print(f"  {label:5} E7 02 {rep['retail_sites']}곳 · 머리글 {rep['anchored']}개 검사, 위반 {bad}건")
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
        print(f"FAIL 작전목적 창 {bad}건")
        return 1
    print("PASS 작전목적 창 블록·E7 02 변위·L 이 모두 맞물린다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
