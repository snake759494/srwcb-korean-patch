# -*- coding: utf-8 -*-
"""제2차 스크립트 인터프리터의 **제어 흐름 추적 빌드**를 만든다 (진단 전용).

전투 후 정지의 직접 원인은 IP 스크립트 포인터(`gp+0x288`)가 유효 범위를 벗어나
옵코드 0 만 읽으며 매 프레임 양보만 반복하는 것이다. 그런데 **어디서 튀는지**는
정적으로 안 잡힌다. 그래서 인터프리터가 크게 점프할 때마다 (출발지 → 목적지)를
링버퍼에 남기고, 멈춘 뒤 세이브스테이트에서 읽는다.

## 심는 것

* 디스패처 루프 머리 `0x800693AC`(`lw $v0,0x28c($gp)`)를 `j TRAMP` 로 바꾼다.
  바로 뒤 `0x800693B0` 은 원래 `nop` 이라 지연슬롯으로 그대로 둔다.
* 트램폴린·링버퍼는 **PS-EXE 본문을 옛 모듈 끝 너머로 늘려** 그 뒤에 둔다
  (t_size · 모듈끝 워드 · 힙 베이스를 새 끝으로, BSS 클리어 끝은 옛 끝 그대로).
  파일이 커지므로 이미지에서는 `assemble()` 로 SECOND.WAR 만 뒤로 재배치한다.
  (1차 시도의 in-file 패딩 0x801229F0 은 초기화 때 0 으로 지워져 실패했다.)

## 로그 형식 (LOG = 옛 모듈 끝)

    LOG+0x00  u32  기록 횟수(증가만)
    LOG+0x04  u32  마지막으로 기록한 포인터
    LOG+0x08  u32  래치 (0 이 아니면 더 기록하지 않음)
    LOG+0x10  엔트리 128개 × 16바이트, 링
                +0 출발 포인터  +4 목적 포인터  +8 서브콜 깊이  +12 옵코드 인덱스

**512바이트**를 넘게 움직였을 때만 기록한다. 탈선 뒤의 기어가기는 매번 정확히
0x41(65)바이트씩 움직이는 것이 1차 시도에서 확인됐다 — 64바이트 문턱으로는 그게 전부
기록돼 링(128칸)을 덮어써 정작 필요한 직전 이력이 밀려났다.

추가로 **래치**를 둔다: 목적지가 `[0x80010000, 0x801F0000)` 밖으로 나가면 그 뒤로는
아예 기록하지 않는다(LOG+8). 한 번 튀고 나면 이력이 보존된다.
"""
import argparse
import os
import struct
import sys
from pathlib import Path

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "srwcb_paths.py")):
    _d = os.path.dirname(_d)
for _s in ("", "image-build", "audit"):
    _p = os.path.join(_d, _s) if _s else _d
    if _p not in sys.path:
        sys.path.insert(0, _p)

import srwcb_paths as _P                        # noqa: E402
import assemble_image as AI                     # noqa: E402

BASE, FOFF = 0x80010000, 0x800
# 1차 시도(0x801229F0 패딩)는 실패했다: 그 자리는 게임 초기화가 0 으로 지우는 데이터라
# 트램폴린이 사라져 훅이 0(nop) 을 타고 내려가 BIOS 로 빠졌다(#1 세이브 3장으로 확인).
# 코드 영역에 진짜 패딩이 없으므로 **PS-EXE 본문을 옛 모듈 끝 너머까지 늘려** 그 뒤에
# 트램폴린과 링버퍼를 둔다. BSS 클리어 [0x8013A370,0x8015BE70) 는 그대로 두어 우리
# 코드가 지워지지 않게 하고, 힙 베이스·모듈끝 워드·t_size 만 새 끝으로 민다.
# 모듈 끝은 레트일 0x8015BE70 이지만 한글판은 전투 스크래치 확장으로 이미 밀려 있다
# (v0.11.55: 0x8015C670). 그래서 word@0x800 에서 **읽어서** 잡는다. 아래는 자리표시.
OLD_END = 0x8015C670        # 모듈 끝 (word@0x800, BSS 클리어 끝, 힙 베이스) — patch() 가 갱신
TRAMP = OLD_END             # 새로 늘린 본문의 머리
LOG   = OLD_END + 0x400
NEW_END = 0x8015D800        # 새 본문 끝 (섹터 배수) — patch() 가 갱신
BSS_SITE  = 0x80053B54      # lui v1,0x8016 / addiu v1,-16784  (건드리지 않음, 확인만)
HEAP_SITE = 0x80053B9C      # lui a0,0x8016 / addiu a0,-16784  -> NEW_END
HOOK = 0x800693AC           # 디스패처 루프 머리 (lw v0,0x28c(gp))
HOOK_RET = 0x800693B4       # 원래 명령 + 지연슬롯 다음
RESERVE = 0x1000
RING = 128                  # 엔트리 개수 (2의 거듭제곱)

GP, AT, V0, T0, T1, T2, T3, T4, T5, T6, T7 = 28, 1, 2, 8, 9, 10, 11, 12, 13, 14, 15


def lui(rt, i): return 0x3C000000 | (rt << 16) | (i & 0xFFFF)
def ori(rt, rs, i): return 0x34000000 | (rs << 21) | (rt << 16) | (i & 0xFFFF)
def lw(rt, off, rs): return 0x8C000000 | (rs << 21) | (rt << 16) | (off & 0xFFFF)
def sw(rt, off, rs): return 0xAC000000 | (rs << 21) | (rt << 16) | (off & 0xFFFF)
def subu(rd, rs, rt): return (rs << 21) | (rt << 16) | (rd << 11) | 0x23
def addu(rd, rs, rt): return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def addiu(rt, rs, i): return 0x24000000 | (rs << 21) | (rt << 16) | (i & 0xFFFF)
def andi(rt, rs, i): return 0x30000000 | (rs << 21) | (rt << 16) | (i & 0xFFFF)
def sll(rd, rt, sa): return (rt << 16) | (rd << 11) | ((sa & 0x1F) << 6)
def slti(rt, rs, i): return 0x28000000 | (rs << 21) | (rt << 16) | (i & 0xFFFF)
def beqz(rs, off): return 0x10000000 | (rs << 21) | (off & 0xFFFF)
def bnez(rs, off): return 0x14000000 | (rs << 21) | (off & 0xFFFF)
def j(t): return 0x08000000 | ((t >> 2) & 0x03FFFFFF)
NOP = 0


def trampoline(log_base):
    hi = (log_base >> 16) & 0xFFFF
    lo = log_base & 0xFFFF
    code = []

    def emit(*ws):
        code.extend(ws)

    T8, T9 = 24, 25
    #  t0 = LOG
    emit(lui(T0, hi), ori(T0, T0, lo))
    #  래치가 서 있으면 아무것도 안 한다
    emit(lw(T9, 8, T0), NOP)
    idx_latch = len(code)
    emit(bnez(T9, 0), NOP)                       # -> SKIP
    #  t2 = 현재 스크립트 포인터, t3 = 마지막 기록값
    emit(lw(T2, 0x288, GP), lw(T3, 4, T0), NOP)
    emit(subu(T4, T2, T3))
    #  -512 < delta < 513 이면 기록하지 않는다
    emit(slti(T5, T4, 0x201))
    idx_b1 = len(code)
    emit(beqz(T5, 0), NOP)                       # -> DOLOG
    emit(slti(T5, T4, -0x200))
    idx_b2 = len(code)
    emit(bnez(T5, 0), NOP)                       # -> DOLOG
    idx_j = len(code)
    emit(j(0), NOP)                              # -> SKIP
    # DOLOG:
    do_log = len(code)
    emit(sw(T2, 4, T0))
    emit(lw(T1, 0, T0), NOP)
    emit(andi(T5, T1, RING - 1))
    emit(sll(T6, T5, 4))
    emit(addiu(T7, T0, 0x10))
    emit(addu(T6, T6, T7))
    emit(sw(T3, 0, T6))                          # 출발
    emit(sw(T2, 4, T6))                          # 목적
    emit(lw(T4, 0x2A8, GP), NOP)
    emit(sw(T4, 8, T6))                          # 서브콜 깊이
    emit(lw(T4, 0x28C, GP), NOP)
    emit(sw(T4, 12, T6))                         # 옵코드 인덱스
    emit(addiu(T1, T1, 1))
    emit(sw(T1, 0, T0))
    #  목적지가 RAM 유효 범위 밖이면 래치를 세운다
    emit(lui(T9, 0x8001))
    emit(0x00000000 | (T2 << 21) | (T9 << 16) | (T8 << 11) | 0x2B)      # sltu t8,t2,t9
    idx_lo = len(code)
    emit(bnez(T8, 0), NOP)                       # -> SETLATCH
    emit(lui(T9, 0x801F))
    emit(0x00000000 | (T2 << 21) | (T9 << 16) | (T8 << 11) | 0x2B)      # sltu t8,t2,t9
    idx_hi = len(code)
    emit(bnez(T8, 0), NOP)                       # 범위 안 -> SKIP
    # SETLATCH:
    set_latch = len(code)
    emit(addiu(T9, 0, 1))
    emit(sw(T9, 8, T0))
    # SKIP:
    skip = len(code)
    emit(lw(V0, 0x28C, GP))                      # 훅으로 지운 원래 명령
    emit(j(HOOK_RET), NOP)

    code[idx_latch] = bnez(T9, skip - (idx_latch + 1))
    code[idx_b1] = beqz(T5, do_log - (idx_b1 + 1))
    code[idx_b2] = bnez(T5, do_log - (idx_b2 + 1))
    code[idx_j] = j(TRAMP + skip * 4)
    code[idx_lo] = bnez(T8, set_latch - (idx_lo + 1))
    code[idx_hi] = bnez(T8, skip - (idx_hi + 1))
    return code


def sites(buf):
    import expand_battle_scratch as BS
    return BS.sites(buf)


def patch(war: bytes, log=print):
    """본문을 OLD_END 까지 0 으로 늘리고 그 뒤 [OLD_END, NEW_END) 에 코드·로그를 둔다."""
    b = bytearray(war)
    if b[:8] != b"PS-X EXE":
        raise SystemExit("PS-X EXE 헤더가 아니다")
    t_addr, t_size = struct.unpack_from("<II", b, 0x18)
    if t_addr != BASE or FOFF + t_size != len(b):
        raise SystemExit(f"헤더/길이 불일치 t_addr={t_addr:08X} t_size={t_size:X} len={len(b):X}")
    global OLD_END, TRAMP, LOG, NEW_END
    OLD_END = struct.unpack_from("<I", b, 0x800)[0]
    if not 0x80130000 < OLD_END < 0x80170000:
        raise SystemExit(f"모듈끝 워드가 이상하다: {OLD_END:08X}")
    TRAMP, LOG = OLD_END, OLD_END + 0x400
    NEW_END = (OLD_END + RESERVE + 0x7FF) & ~0x7FF
    def site(a, reg):
        o = FOFF + (a - BASE)
        hi, lo = struct.unpack_from("<II", b, o)
        exp_hi = 0x3C000000 | (reg << 16) | ((OLD_END + 0x8000) >> 16)
        exp_lo = 0x24000000 | (reg << 21) | (reg << 16) | (OLD_END & 0xFFFF)
        if (hi, lo) != (exp_hi, exp_lo):
            raise SystemExit(f"{a:08X} 명령이 예상과 다르다: {hi:08X} {lo:08X}")
        return o
    site(BSS_SITE, 3)                       # 그대로 둔다 — 우리 코드가 지워지면 안 된다
    heap_off = site(HEAP_SITE, 4)
    # 본문 확장
    b.extend(bytes(FOFF + (NEW_END - BASE) - len(b)))
    struct.pack_into("<I", b, 0x1C, NEW_END - BASE)          # t_size
    struct.pack_into("<I", b, 0x800, NEW_END)                # 모듈 끝
    struct.pack_into("<I", b, heap_off + 4, 0x24840000 | (NEW_END & 0xFFFF))  # addiu a0
    assert ((NEW_END + 0x8000) >> 16) == ((OLD_END + 0x8000) >> 16)
    log(f"  본문 {t_size:X} -> {NEW_END-BASE:X}, 힙 베이스/모듈끝 -> 0x{NEW_END:08X} (BSS 클리어 끝 0x{OLD_END:08X} 유지)")
    need = 0x10 + RING * 16
    code = trampoline(LOG)
    if TRAMP + len(code) * 4 > LOG or LOG + need > NEW_END:
        raise SystemExit("배치가 넘친다")
    off = FOFF + (TRAMP - BASE)
    for i, w in enumerate(code):
        struct.pack_into("<I", b, off + i * 4, w)
    log(f"  트램폴린 {len(code)}명령 @0x{TRAMP:08X}")
    log(f"  링버퍼 {need}B @0x{LOG:08X}")
    hoff = FOFF + (HOOK - BASE)
    orig = struct.unpack_from("<I", b, hoff)[0]
    if orig != lw(V0, 0x28C, GP):
        raise SystemExit(f"훅 자리 명령이 예상과 다르다: {orig:08X}")
    struct.pack_into("<I", b, hoff, j(TRAMP))
    log(f"  디스패처 0x{HOOK:08X} -> j 0x{TRAMP:08X}")
    return bytes(b), LOG


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v0.11.55")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    src = _P.OUT / f"Super Robot Taisen Complete Box Korean {a.version} (Track 1).bin"
    if not src.exists():
        raise SystemExit(f"[없음] {src}")
    out = a.out or (_P.OUT / f"Super Robot Taisen Complete Box Korean {a.version}-trace3 (Track 1).bin")
    import shutil
    with AI.RawMode2Image(src) as m:
        _, entries = AI.read_tree(m)
    e = {x.path.strip("/"): x for x in entries}["SECOND/SECOND.WAR"]
    war = AI.read_file(src, e.lba, e.size)
    new, log_base = patch(war)
    # 커진 파일은 제자리에 못 넣는다 — 한글판 이미지를 기준으로 SECOND.WAR 만 재배치.
    AI.assemble(src, out, {"SECOND/SECOND.WAR": new})
    cue = out.with_suffix(".cue")
    # 레트일 컴플리트 박스는 **2트랙**이다(트랙 2 = CD-DA). 트랙 2 를 빠뜨리면
    # CD-DA 를 읽는 장면에서 정식 빌드와 다르게 동작한다 — 진단 빌드가 원판과
    # 다르게 굴면 진단이 무의미하므로 정식 릴리스와 같은 cue 를 쓴다.
    src_cue = src.with_suffix(".cue")
    if src_cue.exists():
        cue.write_bytes(src_cue.read_bytes().replace(src.name.encode(),
                                                     out.name.encode()))
    else:
        raise SystemExit(f"[없음] 원본 cue: {src_cue}")
    print(f"\nOUT {out}")
    print(f"    로그 버퍼 RAM 0x{log_base:08X}")


if __name__ == "__main__":
    main()
