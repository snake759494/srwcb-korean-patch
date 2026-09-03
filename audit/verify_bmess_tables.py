#!/usr/bin/env python3
"""게이트: 실행파일에 복제된 BMESS 목차표가 배포본 아카이브의 실제 표와 같은가.

전투 대사 아카이브(BMESS2/3/4)는 머리에 **블록 오프셋 표**를 갖고, 그 표의 **사본이
실행파일 안에도 박혀 있다**. 번역으로 아카이브를 재패킹하면 블록 위치가 바뀌는데,
실행파일 안 사본이 레트일 그대로면 전투 대사를 **블록 한가운데부터** 읽어 전투가
그 자리에서 멈춘다(트레이닝 모드에서 실측, v0.11.37 에서 아홉 사본을 모두 갱신).

네 실행파일은 저마다 세 게임의 표를 **모두** 품는다. 자기 게임 것만 갱신하면 나머지는
죽은 사본이지만, 언제 선택될지 모르므로 스테일을 하나도 남기지 않는다.

불변식:
    레트일 실행파일이 어떤 BMESS 표 사본을 갖고 있었다면, 배포본 실행파일의 같은
    자리에는 **배포본 아카이브의 표**가 있어야 하고, 레트일 표는 어디에도 남아
    있지 않아야 한다.

수정기(image-build/build_image.py:step_bmess_tables)와 코드도 전제도 공유하지 않는다 —
레트일 원본과 배포 이미지를 직접 대조한다.
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
import srwcb_paths as _P                                  # noqa: E402
import assemble_image as AI                               # noqa: E402

ARCHIVES = ("BMESS2.BIN", "BMESS3.BIN", "BMESS4.BIN")
EXES = ("SECOND/SECOND.WAR", "THIRD/THIRD.WAR", "EX/EX.WAR", "TR.WAR", "SLPS_020.70")


def header_table(buf: bytes) -> bytes:
    """아카이브 머리의 블록 오프셋 표 — 첫 워드가 표의 끝이다."""
    if len(buf) < 4:
        return b""
    n = struct.unpack_from("<I", buf, 0)[0]
    return buf[:n] if 4 <= n <= len(buf) else b""


def audit(shipped: dict[str, bytes], retail: dict[str, bytes]) -> list[str]:
    bad: list[str] = []
    checked = 0
    for arc in ARCHIVES:
        if arc not in shipped or arc not in retail:
            continue
        old = header_table(retail[arc])
        new = header_table(shipped[arc])
        if not old or not new:
            bad.append(f"{arc}: 목차표를 못 읽었다")
            continue
        for exe in EXES:
            if exe not in shipped or exe not in retail:
                continue
            had = retail[exe].count(old)
            if not had:
                continue                       # 이 실행파일엔 이 표 사본이 없다
            checked += 1
            stale = shipped[exe].count(old) if old != new else 0
            fresh = shipped[exe].count(new)
            if stale:
                bad.append(f"{exe}: {arc} 레트일 표가 {stale}곳 남아 있다 (스테일 사본)")
            if fresh < had:
                bad.append(f"{exe}: {arc} 배포본 표가 {fresh}곳뿐 (레트일은 {had}곳)")
    if not checked:
        bad.append("검사 대상이 하나도 없다 — 표를 못 찾았거나 대상 목록이 낡았다")
    print(f"  실행파일 x 아카이브 사본 {checked}건 검사, 위반 {len(bad)}건")
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
    shipped, retail = {}, {}
    for rel in (*ARCHIVES, *EXES):
        if rel in by:
            shipped[rel] = AI.read_file(img, by[rel].lba, by[rel].size)
        p = _P.EXTRACTED / rel
        if p.exists():
            retail[rel] = p.read_bytes()
    bad = audit(shipped, retail)
    for m_ in bad[:20]:
        print("  [실패] " + m_)
    if bad:
        print(f"FAIL BMESS 목차표 사본 {len(bad)}건")
        return 1
    print("PASS 실행파일에 박힌 BMESS 목차표가 모두 배포본 아카이브와 같다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
