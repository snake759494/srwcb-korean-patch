#!/usr/bin/env python3
"""메타 게이트: **게이트가 과거의 그 결함을 정말 잡는가.**

이 프로젝트는 프리징을 스무 번 넘게 고쳤는데, v0.11.45 에서 예전에 고친 곳(EX 23화)이
다시 깨진 채 여덟 판이 나갔다. 게이트가 있었는데도 못 잡았다 — 그 게이트가 수정기와
같은 필터를 써서, 수정기가 건너뛴 자리는 게이트도 못 봤기 때문이다.

그래서 "게이트가 있다" 로는 부족하다. **그 게이트가 과거의 결함을 넣었을 때 실패하는지**
증명해야 한다. 이 스크립트는 완성된 배포본에 과거 결함을 **되심어** 게이트를 돌린다.

    정상 배포본  -> 위반 0건이어야 한다      (거짓 경보 없음)
    결함 주입본  -> 위반 1건 이상이어야 한다 (판별력 있음)

둘 중 하나라도 어긋나면 그 게이트는 믿을 수 없다.

    python audit/verify_gate_power.py --version v0.11.53
"""
from __future__ import annotations
import os, struct, sys
from pathlib import Path

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "srwcb_paths.py")):
    _d = os.path.dirname(_d)
for _s in ("", "tools", "image-build", "audit", "second-fixes"):
    _p = os.path.join(_d, _s) if _s else _d
    if _p not in sys.path:
        sys.path.insert(0, _p)
import srwcb_paths as _P                                    # noqa: E402
import assemble_image as AI                                 # noqa: E402
from analyze_sce_relocation import (parse_scenarios,        # noqa: E402
                                    iter_pointer_sites)
import verify_pool_event_refs as G_POOL                     # noqa: E402
import verify_sce_script as G_SCE                           # noqa: E402
import verify_page_bytes as G_PAGE                          # noqa: E402
import verify_ui_runs as G_UI                               # noqa: E402
import verify_bmess_tables as G_BM                          # noqa: E402
import verify_record_prefix as G_PFX                        # noqa: E402
import verify_objective_windows as G_OW                     # noqa: E402
import objective_windows as OW                              # noqa: E402

SCE = {"제2차": "SECOND/2_SCE.BIN", "제3차": "THIRD/3_SCE.BIN", "EX": "EX/E_SCE.BIN"}
WAR = {"제2차": "SECOND/SECOND.WAR", "제3차": "THIRD/THIRD.WAR",
       "EX": "EX/EX.WAR", "TR": "TR.WAR"}


# ---------------------------------------------------------------- 결함 주입기
def inject_stale_pool_ref(ko: bytes, jp: bytes, want: int = 3) -> tuple[bytes, int]:
    """이벤트 참조를 레트일 변위로 되돌린다 = v0.11.45~52 의 결함(#39·#28 회귀).

    번역으로 레코드가 밀렸는데 변위를 안 고치면 남의 레코드 한가운데를 가리킨다.
    """
    bj, bk = parse_scenarios(jp), parse_scenarios(ko)
    out = bytearray(ko)
    n = 0
    for sj, sk in zip(bj, bk):
        if len(sj.records) != len(sk.records):
            continue
        starts = {r.start for r in sj.records}
        for off, operand, _op in iter_pointer_sites(jp, sj.pool_start, sj.record_data_end):
            host = next((i for i, r in enumerate(sj.records) if r.start <= off < r.end), None)
            if host is None or operand >= sj.records[host].end:
                continue
            hj, hk = sj.records[host], sk.records[host]
            if hj.end - hj.start != hk.end - hk.start:
                continue
            disp = struct.unpack_from("<h", jp, operand)[0]
            if operand + disp not in starts:
                continue
            k_off = hk.start + (off - hj.start)
            k_operand = k_off + (operand - off)
            if out[k_off] != jp[off] or k_operand + 2 > len(out):
                continue
            if struct.unpack_from("<h", out, k_operand)[0] == disp:
                continue                      # 이미 같으면 결함이 안 된다
            struct.pack_into("<h", out, k_operand, disp)
            n += 1
            if n >= want:
                return bytes(out), n
    return bytes(out), n


def inject_clobbered_opcode(ko: bytes, jp: bytes, want: int = 2) -> tuple[bytes, int]:
    """`F0 00 <변위>` 뒤 명령을 덮어쓴다 = v0.11.39 의 결함(전투 후 정지).

    재조준기가 F0 의 변위 바이트를 옵코드로 오인해 다음 명령을 변위로 덮었다.
    """
    out = bytearray(ko)
    n = 0
    for sj in parse_scenarios(jp):
        p = sj.block_start
        end = min(sj.pool_start, len(jp) - 4)
        while p < end and n < want:
            if jp[p] == 0xF0 and jp[p + 1] == 0x00:
                if p + 5 < len(out) and out[p + 4:p + 6] == jp[p + 4:p + 6]:
                    out[p + 4] = (out[p + 4] + 1) & 0xFF      # 다음 명령 훼손
                    n += 1
                p += 4
            else:
                p += 1
        if n >= want:
            break
    return bytes(out), n


def inject_long_page(ko: bytes) -> tuple[bytes, int]:
    """대사 한 페이지를 128바이트 넘게 만든다 = v0.11.40 의 결함(스택 버퍼 넘침).

    가장 긴 페이지의 레코드에서 종단자 앞 글리프를 늘리는 대신, 페이지 경계
    (3번째 F6/F7/FF) 하나를 평범한 글리프로 바꿔 두 페이지를 하나로 합친다.
    """
    out = bytearray(ko)
    for start, end in G_PAGE.dialogue_records(ko):
        lens = G_PAGE.page_lengths(ko, start, end)
        if len(lens) < 2:
            continue
        if lens[0] + lens[1] <= G_PAGE.LIMIT:
            continue
        p, seen = start, 0
        while p < end:
            b = out[p]
            if b in (0xF6, 0xF7):
                seen += 1
                if seen == 3:
                    out[p] = 0x41                 # 페이지 경계를 평범한 글리프로
                    return bytes(out), 1
                p += 1
            elif b < 0xEB:
                p += 1
            elif b <= 0xF5:
                p += 2
            else:
                break
    return bytes(out), 0


def inject_midglyph_string_ref(ko: bytes, jp: bytes, want: int = 1) -> tuple[bytes, int]:
    """UI 문자열표 포인터를 글리프 한가운데로 민다 = v0.11.34 의 결함(유닛 개조 정지).

    착지 바이트가 VM 옵코드(>= 0xF6)면 렌더러가 그것을 명령으로 오독해 멈춘다.
    """
    span = G_UI.string_table(ko)
    if span is None:
        return ko, 0
    lo, hi = span
    out = bytearray(ko)
    n = 0
    for f in range(lo, hi + 1, 4):
        t = f + struct.unpack_from("<i", ko, f)[0]
        if not (0x800 <= t + 1 < len(ko)):
            continue
        if ko[t + 1] < 0xF6:
            continue                       # 착지 바이트가 옵코드여야 치명이 된다
        struct.pack_into("<i", out, f, (t + 1) - f)
        n += 1
        if n >= want:
            break
    return bytes(out), n


# ---------------------------------------------------------------- 표본 정의
def fixtures():
    """(id, 규칙, 설명, 대상, 주입기, 게이트) — 게이트는 (ko, jp, label) -> 위반수."""
    return [
        ("F-pool-ref", "R-포인터-서수보존",
         "이벤트 참조를 레트일 변위로 되돌림 (v0.11.45~52, #39·#28 회귀)",
         SCE, inject_stale_pool_ref,
         lambda ko, jp, lb: G_POOL.check(ko, jp, lb)),
        ("F-f0-clobber", "R-스크립트-바이트보존",
         "F0 00 변위 뒤 명령 훼손 (v0.11.39, 전투 후 정지)",
         SCE, inject_clobbered_opcode,
         lambda ko, jp, lb: G_SCE.check_file(ko, jp, lb)),
        ("F-page-128", "R-페이지-128바이트",
         "대사 페이지를 128바이트 초과로 (v0.11.40, s0/s1 훼손 후 BIOS 정지)",
         SCE, lambda ko, jp, want=1: inject_long_page(ko),
         lambda ko, jp, lb: len(G_PAGE.check(ko, lb)[1])),
        ("F-midglyph", "R-문자열표-글리프경계",
         "UI 문자열표 포인터를 글리프 한가운데로 (v0.11.34, 유닛 개조 정지)",
         WAR, inject_midglyph_string_ref,
         lambda ko, jp, lb: len(G_UI.check_string_table(ko, lb)[0])),
        ("F-objhdr", "R-작전목적-머리글",
         "작전목적 머리글 04 00 <창폭> 00 을 뭉갬 (v0.11.33, EX 목표 변경 시 정지)",
         SCE, inject_mangled_objective_header,
         lambda ko, jp, lb: G_PFX.check(ko, jp, lb)),
        ("F-objwin-disp", "R-작전목적-창-변위",
         "E7 02 변위를 이웃 블록으로 어긋냄 (v0.11.54, 제2차 8화 장면 끝 정지 #1)",
         SCE, inject_stale_e7_disp,
         lambda ko, jp, lb: G_OW.check(ko, jp, lb)),
        ("F-objwin-len", "R-작전목적-창-길이",
         "작전목적 블록 L 을 승리조건 종단과 다르게 (v0.11.54, 패배조건 깨짐)",
         SCE, inject_stale_block_len,
         lambda ko, jp, lb: G_OW.check(ko, jp, lb)),
        ("F-objhdr-len", "R-작전목적-머리글",
         "머리글 L 을 승리조건 종단과 다르게 — 옛 게이트는 레트일 값에 묶여 못 잡았다",
         SCE, inject_stale_block_len,
         lambda ko, jp, lb: G_PFX.check(ko, jp, lb)),
    ]


def inject_stale_e7_disp(ko: bytes, jp: bytes, want: int = 2) -> tuple[bytes, int]:
    """블록을 겨누는 E7 02 의 변위를 2바이트 앞으로 = 블록이 밀렸는데 변위가 옛 값인 상태.

    v0.11.54 제2차 8화: 앞 블록의 승리조건이 2바이트 늘어 뒤 블록이 밀렸는데 E7 02 는
    옛 변위 그대로였다 → 쓰레기 오프셋 → 10,855바이트 스택 복사 → 장면 끝 정지.
    """
    out = bytearray(ko)
    n = 0
    for b in parse_scenarios(ko):
        for off, opnd, tgt in OW.e7_sites(ko, b):
            if OW.is_block(ko, tgt):
                struct.pack_into("<h", out, opnd, struct.unpack_from("<h", out, opnd)[0] - 2)
                n += 1
                if n >= want:
                    return bytes(out), n
    return bytes(out), n


def inject_stale_block_len(ko: bytes, jp: bytes, want: int = 3) -> tuple[bytes, int]:
    """작전목적 블록의 L 을 2 줄인다 = 승리조건을 늘리고 L 은 옛 값으로 둔 상태."""
    out = bytearray(ko)
    n = 0
    for b in parse_scenarios(ko):
        blks = {t for _, _, t in OW.e7_sites(ko, b) if OW.is_block(ko, t)}
        blks |= set(OW.anchored_blocks(ko, b.pool_start, b.record_data_end))
        for blk in sorted(blks):
            L = struct.unpack_from("<H", out, blk + 2)[0]
            if L > 6:
                struct.pack_into("<H", out, blk + 2, L - 2)
                n += 1
                if n >= want:
                    return bytes(out), n
    return bytes(out), n


def inject_mangled_objective_header(ko: bytes, jp: bytes, want: int = 3) -> tuple[bytes, int]:
    """작전목적 머리글 `E9 03 FE FF 04 00 <창폭> 00` 을 뭉갠다 = v0.11.33 의 결함.

    목표가 바뀌는 순간 게임이 멈춘다(EX 마사키 9·11·27화, 류네 45·49화, 슈우 58화 —
    제보 #10·#11·#24). 레코드 길이는 그대로 두므로 재배치·포인터 게이트에는 안 걸린다.
    """
    out = bytearray(ko)
    n = 0
    p = 0
    while n < want:
        p = out.find(G_PFX.ANCHOR, p)
        if p < 0:
            break
        if p + 8 <= len(out) and out[p + 7] == 0x00:
            out[p + 5] = 0x01          # `04 00` 의 00 을 뭉갠다 -> 앵커가 사라진다
            n += 1
        p += 1
    return bytes(out), n


# ------------------------------------------------- 파일집합 단위 표본(다중 파일)
def inject_stale_bmess_table(shipped: dict, retail: dict) -> tuple[dict, int]:
    """실행파일 안 BMESS 목차표 사본을 레트일 표로 되돌린다 = v0.11.37 이전의 결함.

    표가 스테일이면 전투 대사를 블록 한가운데부터 읽어 전투가 멈춘다.
    """
    out = dict(shipped)
    n = 0
    for arc in G_BM.ARCHIVES:
        if arc not in shipped or arc not in retail:
            continue
        old = G_BM.header_table(retail[arc])
        new = G_BM.header_table(shipped[arc])
        if not old or not new or old == new:
            continue
        for exe in G_BM.EXES:
            if exe not in out:
                continue
            at = out[exe].find(new)
            if at < 0:
                continue
            b = bytearray(out[exe])
            b[at:at + len(old)] = old
            out[exe] = bytes(b)
            n += 1
            if n >= 2:
                return out, n
    return out, n


def set_fixtures():
    """(id, 설명, 주입기, 게이트) — 게이트는 (shipped, retail) -> 위반 목록."""
    return [
        ("F-bmess-tbl",
         "실행파일 안 BMESS 목차표를 레트일 표로 되돌림 (v0.11.37 이전, 전투 정지)",
         inject_stale_bmess_table,
         lambda sh, rt: G_BM.audit(sh, rt)),
    ]


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
    for fid, rule, desc, targets, inject, gate in fixtures():
        clean_total = dirty_total = injected_total = 0
        for label, rel in targets.items():
            if rel not in by:
                continue
            ko = AI.read_file(img, by[rel].lba, by[rel].size)
            jp = (_P.EXTRACTED / rel).read_bytes()
            clean_total += _quiet(gate, ko, jp, label)
            dirty, n = inject(ko, jp)
            injected_total += n
            if n:
                dirty_total += _quiet(gate, dirty, jp, label)
        ok_clean = clean_total == 0
        ok_dirty = injected_total > 0 and dirty_total > 0
        mark = "OK " if (ok_clean and ok_dirty) else "실패"
        print(f"  [{mark}] {fid:14} 정상 {clean_total:3} · 주입 {injected_total:2}곳 -> 위반 {dirty_total:3}   {desc}")
        if not ok_clean:
            print(f"          ! 정상 배포본에서 위반 {clean_total}건 — 거짓 경보")
            bad += 1
        if not ok_dirty:
            print("          ! 결함을 심었는데 게이트가 못 잡는다 — 판별력 없음"
                  if injected_total else "          ! 결함을 심지 못했다 — 표본이 낡았다")
            bad += 1
    # ---- 파일집합 단위 표본 ----
    shipped, retail = {}, {}
    for rel in (*G_BM.ARCHIVES, *G_BM.EXES):
        if rel in by:
            shipped[rel] = AI.read_file(img, by[rel].lba, by[rel].size)
        p = _P.EXTRACTED / rel
        if p.exists():
            retail[rel] = p.read_bytes()
    for fid, desc, inject, gate in set_fixtures():
        clean = len(_quiet2(gate, shipped, retail))
        dirty_files, n = inject(shipped, retail)
        dirty = len(_quiet2(gate, dirty_files, retail)) if n else 0
        ok = clean == 0 and n > 0 and dirty > 0
        print(f"  [{'OK ' if ok else '실패'}] {fid:14} 정상 {clean:3} · 주입 {n:2}곳 -> 위반 {dirty:3}   {desc}")
        if not ok:
            print("          ! 정상에서 거짓 경보" if clean else
                  ("          ! 결함을 심었는데 못 잡는다" if n else "          ! 결함을 심지 못했다"))
            bad += 1

    if bad:
        print(f"FAIL 게이트 판별력 문제 {bad}건")
        return 1
    print("PASS 모든 게이트가 자기 과거 결함을 되심었을 때 실패한다")
    return 0


def _quiet2(gate, a, b):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return gate(a, b)


def _quiet(gate, ko, jp, label):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return gate(ko, jp, label)


if __name__ == "__main__":
    raise SystemExit(main())
