# -*- coding: utf-8 -*-
"""작전목적 창 블록과 그것을 여는 `E7 02` 명령을 다룬다.

## 블록 구조 (2026-09-28, 제보 #1 제2차 8화 정지에서 역분석)

    04 00 | L 00 | 승리조건 … FF | [FF] | 패배조건 … FF | [FF]
    ^blk           ^blk+4                  ^blk+L+2

`E7 02 <s16 변위>` 핸들러(제2차 0x800C1700)가 이 블록을 읽는다.

* 블록 = 변위 자리 + 변위 (다른 대사 포인터와 같은 규칙)
* 문자열1 = blk + u16(blk+0)   (항상 4)
* 문자열2 = blk + u16(blk+2) + 2
  → **L 은 창폭이 아니라 '패배조건 시작 − 2 − blk' 다.**

변형 둘(레트일 실측), 규칙은 같다.

    A  … 승리 FF | FF | 패배 FF | FF      L = 승리 종단 위치         (대부분)
    B  … 승리 FF | 패배 FF                 L = 승리 종단 위치 − 1     (EX 일부)

두 문자열을 **스택의 128바이트 버퍼에 0xFF 까지 길이 검사 없이** 복사한다
(sp+16, 제2차에선 0x801FFE68). 그래서

* 블록이 밀렸는데 `E7 02` 변위가 옛 값이면 → 엉뚱한 u16 을 오프셋으로 읽어 시나리오
  밖(음악 데이터 등)을 문자열로 삼고, 첫 0xFF 까지 수 KB 를 복사해 메인 루프의 저장된
  ra 를 덮는다 → **장면이 끝나 메인 루프가 반환하는 순간** 쓰레기 주소로 뛰어 정지.
  (제2차 8화: 10,855바이트 복사, ra = 0x47003544)
* 블록은 제자리인데 L 이 옛 값이면 → 패배조건이 빈 칸이나 글자 중간부터 나온다.

## 블록을 어떻게 찾나

**모양으로 찾지 않는다.** `FF 04 00 ?? 00` 모양은 스크립트 속에서도 우연히 생기고
(EX sc1 `F1 FF 04 00 11 00 62 …`), 진짜 블록인데 앞 바이트가 FF 가 아닌 것도 있다
(EX sc1 +0x201D, 앞이 `08`). 그래서 블록 = **레트일 `E7 02` 가 실제로 겨누는 곳**
(레트일 세 게임 제2차 53 · 제3차 79 · EX 78 곳, 예외 없이 `04 00 L 00` 이고 L 규칙 일치)
∪ `E9 03 FE FF` 머리글 바로 뒤 블록. 배포본 위치 대응(레트일 목표 분류 실측):

    ① 레코드 시작     제2차 2 · 제3차 9 · EX 6   → 레코드 서수
    ② 머리글 바로 뒤  제2차 51 · 제3차 70 · EX 71 → 머리글 서수
    ③ 그 밖           EX 1 (sc1 +0x201D)          → 레코드 안 오프셋

②를 레코드 오프셋으로 풀면 안 된다 — 0xFF 피연산자 보정으로 레코드 **시작**이 달라진
시나리오(제2차 sc4, EX sc8·sc23)에서 엉뚱한 곳을 가리킨다.

이 파일은 수정기(image-build step_sce)와 게이트(audit/verify_objective_windows)가
같이 쓴다. 게이트는 수정기를 부르지 않고 레트일과 결과물을 대조한다.
"""
from __future__ import annotations

import struct

#: 제어 바이트 뒤에 붙는 인자 수 (second_translation_codec 과 같은 표)
_ARGS = {0xF6: 0, 0xF7: 0, 0xF8: 1, 0xF9: 0, 0xFA: 0, 0xFB: 2, 0xFC: 2, 0xFD: 2, 0xFE: 1}
#: L 바이트가 텍스트 토큰화에서 리드/제어 바이트로 읽히면 레코드 경계가 바뀐다.
L_MAX = 0xEA
#: 시나리오 앞머리 작전목적 머리글 앵커. `E9 03 FE FF` 바로 뒤가 블록이다.
ANCHOR = bytes((0xE9, 0x03, 0xFE, 0xFF, 0x04, 0x00))


def _text_end(buf: bytes, p: int, lim: int) -> int | None:
    """글리프 단위로 훑어 종단 FF 위치를 돌려준다.

    2바이트 글리프(리드 0xEB~0xF5)의 둘째 바이트가 0xFF 여도 종단이 아니다.
    """
    while p < lim:
        x = buf[p]
        if x == 0xFF:
            return p
        if x < 0xEB:
            p += 1
        elif x < 0xF6:
            p += 2
        else:
            p += 1 + _ARGS.get(x, 0)
    return None


def is_block(buf: bytes, blk: int) -> bool:
    return (0 < blk and blk + 6 < len(buf) and buf[blk] == 0x04 and buf[blk + 1] == 0x00
            and buf[blk + 3] == 0x00)


def expected_len(buf: bytes, blk: int) -> int | None:
    """블록의 올바른 L (= 패배조건 시작 − 2 − blk). 모양이 안 맞으면 None."""
    if not is_block(buf, blk):
        return None
    e1 = _text_end(buf, blk + 4, len(buf))
    if e1 is None or e1 + 1 >= len(buf):
        return None
    s2 = e1 + 2 if buf[e1 + 1] == 0xFF else e1 + 1
    return s2 - 2 - blk


def anchored_blocks(buf: bytes, lo: int, hi: int) -> list[int]:
    """[lo, hi) 안에서 `E9 03 FE FF` 머리글 바로 뒤 블록 시작들."""
    out = []
    p = lo
    while True:
        p = buf.find(ANCHOR, p, hi)
        if p < 0:
            return out
        if p + 8 <= hi and buf[p + 7] == 0x00:
            out.append(p + 4)
        p += 1


def e7_sites(buf: bytes, scn) -> list[tuple[int, int, int]]:
    """풀 앞 스크립트의 `E7 02 <s16>` 사이트 (옵코드, 피연산자, 목표).

    `F0 00 <변위>` 의 변위 자리에서 시작하는 것은 명령이 아니므로 건너뛴다
    (iter_pointer_sites 와 같은 규칙).
    """
    lo, hi = scn.block_start, scn.pool_start
    f0 = bytearray(hi - lo)
    p = lo
    while p < hi - 3:
        if buf[p] == 0xF0 and buf[p + 1] == 0x00:
            f0[p + 2 - lo] = f0[p + 3 - lo] = 1
            p += 4
        else:
            p += 1
    out = []
    for off in range(lo, hi - 3):
        if f0[off - lo]:
            continue
        if buf[off] == 0xE7 and buf[off + 1] == 0x02:
            o = off + 2
            out.append((off, o, o + struct.unpack_from("<h", buf, o)[0]))
    return out


def _host(scn, pos):
    for i, r in enumerate(scn.records):
        if r.start <= pos < r.end:
            return i
    return None


def _pairs(ko: bytes, jp: bytes):
    """시나리오마다 (레트일, 배포본, [(레트일 사이트, 배포본 사이트 옵코드 위치, 배포본 피연산자,
    배포본 블록 위치 | None, 문제)])"""
    from analyze_sce_relocation import parse_scenarios
    sj, sk = parse_scenarios(jp), parse_scenarios(ko)
    for a, b in zip(sj, sk):
        rows = []
        same_pre = (a.pool_start - a.block_start) == (b.pool_start - b.block_start)
        same_rec = len(a.records) == len(b.records)
        starts_j = {r.start: i for i, r in enumerate(a.records)}
        anch_j = {blk: i for i, blk in enumerate(anchored_blocks(jp, a.pool_start, a.record_data_end))}
        anch_k = anchored_blocks(ko, b.pool_start, b.record_data_end)
        for off, opnd, tgt in e7_sites(jp, a):
            rel = off - a.block_start
            prob = None
            off_k = b.block_start + rel
            opnd_k = off_k + (opnd - off)
            blk_k = None
            if not same_pre:
                prob = "풀 앞 스크립트 길이가 다르다"
            elif ko[off_k] != 0xE7 or ko[off_k + 1] != 0x02:
                prob = "배포본 같은 자리에 E7 02 가 없다"
            elif expected_len(jp, tgt) != struct.unpack_from("<H", jp, tgt + 2)[0]:
                prob = "레트일 블록이 규칙과 다르다(모델이 틀렸다)"
            elif not same_rec:
                prob = "레코드 수가 다르다"
            elif tgt in starts_j:
                # ① 레코드 시작 → 레코드 서수 (레코드 분할은 레트일과 같다)
                blk_k = b.records[starts_j[tgt]].start
            elif tgt in anch_j:
                # ② `E9 03 FE FF` 머리글 뒤 → 머리글 서수. 레코드 시작이 패딩 보정으로
                #    달라진 시나리오(제2차 sc4, EX sc8·sc23)에서도 흔들리지 않는다.
                i = anch_j[tgt]
                blk_k = anch_k[i] if len(anch_k) == len(anch_j) else None
                if blk_k is None:
                    prob = "머리글 블록 수가 레트일과 다르다"
            else:
                # ③ 그 밖(EX sc1 +0x201D, 앞이 스크립트) → 레코드 안 오프셋
                h = _host(a, tgt)
                if h is None:
                    prob = "레트일 블록이 레코드 밖이다"
                else:
                    blk_k = b.records[h].start + (tgt - a.records[h].start)
            if blk_k is not None and not is_block(ko, blk_k):
                prob = f"배포본 대응 자리(+{blk_k - b.block_start:#x})가 블록이 아니다"
                blk_k = None
            rows.append((rel, off_k, opnd_k, blk_k, prob))
        yield a, b, rows


def audit(ko: bytes, jp: bytes) -> dict:
    """레트일 대비 결과물의 작전목적 창 상태. 고치지 않는다."""
    rep = {"retail_sites": 0, "anchored": 0, "problems": [], "stale": [], "bad_len": [],
           "anchor_mismatch": []}
    for a, b, rows in _pairs(ko, jp):
        aj = anchored_blocks(jp, a.pool_start, a.record_data_end)
        ak = anchored_blocks(ko, b.pool_start, b.record_data_end)
        rep["anchored"] += len(aj)
        if len(aj) != len(ak):
            rep["anchor_mismatch"].append((a.index, len(aj), len(ak)))
        blocks = set(ak)
        for rel, off_k, opnd_k, blk_k, prob in rows:
            rep["retail_sites"] += 1
            if prob:
                rep["problems"].append((a.index, rel, prob))
                continue
            if opnd_k + struct.unpack_from("<h", ko, opnd_k)[0] != blk_k:
                rep["stale"].append((a.index, rel, blk_k - b.block_start))
            blocks.add(blk_k)
        for blk in sorted(blocks):
            need = expected_len(ko, blk)
            have = struct.unpack_from("<H", ko, blk + 2)[0]
            if need is None or have != need:
                rep["bad_len"].append((b.index, blk - b.block_start, have,
                                       -1 if need is None else need))
    return rep


def fix(ko: bytes, jp: bytes) -> tuple[bytes, int, int, list[str]]:
    """`E7 02` 변위를 레코드 대응 위치로 다시 겨누고, 블록 L 을 실제 길이로 쓴다.

    반환: (결과, 고친 변위 수, 고친 L 수, 문제 목록)
    """
    out = bytearray(ko)
    n_disp = n_len = 0
    problems: list[str] = []
    for a, b, rows in _pairs(ko, jp):
        blocks = set(anchored_blocks(ko, b.pool_start, b.record_data_end))
        for rel, off_k, opnd_k, blk_k, prob in rows:
            if prob:
                problems.append(f"sc{a.index} +{rel:#x}: {prob}")
                continue
            want = blk_k - opnd_k
            if not -0x8000 <= want <= 0x7FFF:
                problems.append(f"sc{a.index} +{rel:#x}: 변위 범위 초과")
                continue
            if struct.unpack_from("<h", out, opnd_k)[0] != want:
                struct.pack_into("<h", out, opnd_k, want)
                n_disp += 1
            blocks.add(blk_k)
        for blk in sorted(blocks):
            L = expected_len(out, blk)
            if L is None:
                problems.append(f"sc{b.index} +{blk - b.block_start:#x}: 작전목적 블록 모양이 깨졌다")
                continue
            if L > L_MAX:
                problems.append(f"sc{b.index} +{blk - b.block_start:#x}: 승리조건이 너무 길다 (L={L:#x})")
                continue
            if struct.unpack_from("<H", out, blk + 2)[0] != L:
                struct.pack_into("<H", out, blk + 2, L)
                n_len += 1
    return bytes(out), n_disp, n_len, problems
