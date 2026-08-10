#!/usr/bin/env python3
"""Experimental half-width Hangul renderer support.

The retail renderer treats every glyph index at or above ``0x101`` as a
stateful 16-pixel glyph.  The Korean font occupies that range, so Hangul
alternates between one and two 8-pixel cursor units.  This module defines the
experimental layout rule and installs a tiny MIPS classifier which keeps
retail Japanese/structural glyphs wide while drawing only Hangul through the
8-pixel path.

The helper lives in four glyph cells from the already guarded font-donor
tail.  Those cells must be excluded from every donor allocator before
``patch_runtime_renderer`` is called.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass


GLYPH_BYTES = 32
HANGUL_INK_WIDTH = 7

HANGUL_BASE_START = 0x101
HANGUL_BASE_END = 0xA2E

# The original font cells at these indices are retained for the UI VM.  Their
# displaced Hangul syllables are allocated in the dynamic tail instead.
STRUCTURAL_GLYPH_INDICES = frozenset({0x3FF, 0x6FF, 0x700})

# The stable v0.11.19 build assigns symbols at 0xA2F..0xA36 and relocated or
# supplemental Hangul at 0xA37..0xA3D.  Keep the former wide and the latter
# half-width.  The build verifier checks that the dynamic map still obeys this
# contract.
HANGUL_EXTRA_START = 0xA37
HANGUL_EXTRA_END = 0xA3D

# Four cells (128 bytes) are sufficient for the classifier.  0xA68 is also
# the first cell of SECOND/SLPS's guarded static donor tail, making the
# reservation explicit and easy to audit in every executable.
RUNTIME_CODE_GLYPH_START = 0xA68
RUNTIME_CODE_GLYPH_COUNT = 4
RUNTIME_CODE_GLYPH_INDICES = frozenset(
    range(RUNTIME_CODE_GLYPH_START, RUNTIME_CODE_GLYPH_START + RUNTIME_CODE_GLYPH_COUNT)
)
RUNTIME_CODE_BYTES = RUNTIME_CODE_GLYPH_COUNT * GLYPH_BYTES


def is_hangul_character(char: str) -> bool:
    """Return whether *char* is a modern/precomposed Hangul code point."""

    if len(char) != 1:
        return False
    cp = ord(char)
    return (
        0xAC00 <= cp <= 0xD7A3
        or 0x1100 <= cp <= 0x11FF
        or 0x3130 <= cp <= 0x318F
        or 0xA960 <= cp <= 0xA97F
        or 0xD7B0 <= cp <= 0xD7FF
    )


def is_halfwidth_hangul_glyph(index: int) -> bool:
    """Return whether the patched runtime draws *index* through its 8px path."""

    if HANGUL_BASE_START <= index <= HANGUL_BASE_END:
        return index not in STRUCTURAL_GLYPH_INDICES
    return HANGUL_EXTRA_START <= index <= HANGUL_EXTRA_END


def retail_glyph_advance(index: int, phase: int) -> tuple[int, int]:
    """Retail mixed-width cursor rule, used for Japanese layout targets."""

    if index < HANGUL_BASE_START:
        return 1, phase
    return 1 + phase, phase ^ 1


def patched_glyph_advance(index: int, phase: int) -> tuple[int, int]:
    """Experimental cursor rule used by rebuilt Korean records."""

    if index < HANGUL_BASE_START or is_halfwidth_hangul_glyph(index):
        return 1, phase
    return 1 + phase, phase ^ 1


def validate_dynamic_hangul_mapping(mapping: dict[str, int]) -> None:
    """Fail if a Hangul extra falls outside the runtime's half-width range."""

    bad = sorted(
        (char, index)
        for char, index in mapping.items()
        if is_hangul_character(char) and not is_halfwidth_hangul_glyph(index)
    )
    if bad:
        sample = ", ".join(f"{char}=0x{index:X}" for char, index in bad[:8])
        raise ValueError(f"Hangul glyphs outside half-width classifier: {sample}")


# Retail classifier in the shared low-level renderer:
#   slti v0,a0,0x101; bnez v0,+2; li t0,1; li t0,2
RETAIL_CLASSIFIER = bytes.fromhex(
    "01 01 82 28 02 00 40 14 01 00 08 24 02 00 08 24"
)


_ZERO = 0
_V0 = 2
_A0 = 4
_T0 = 8
_RA = 31


class _MipsBuilder:
    """Minimal assembler for the branch-only classifier below."""

    def __init__(self, address: int):
        self.address = address
        self.words: list[int | tuple[str, str, int, int]] = []
        self.labels: dict[str, int] = {}

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate MIPS label {name}")
        self.labels[name] = len(self.words)

    def word(self, value: int) -> None:
        self.words.append(value & 0xFFFFFFFF)

    def i(self, opcode: int, rs: int, rt: int, immediate: int) -> None:
        self.word((opcode << 26) | (rs << 21) | (rt << 16) | (immediate & 0xFFFF))

    def branch(self, opcode: int, rs: int, rt: int, label: str) -> None:
        self.words.append(("branch", label, (opcode << 26) | (rs << 21) | (rt << 16), 0))

    def jump(self, label: str) -> None:
        self.words.append(("jump", label, 0x08000000, 0))

    def build(self) -> bytes:
        output: list[int] = []
        for index, item in enumerate(self.words):
            if isinstance(item, int):
                output.append(item)
                continue
            kind, label, base, _ = item
            if label not in self.labels:
                raise ValueError(f"undefined MIPS label {label}")
            target_index = self.labels[label]
            if kind == "branch":
                delta = target_index - (index + 1)
                if not -0x8000 <= delta <= 0x7FFF:
                    raise ValueError("MIPS branch target is out of range")
                output.append(base | (delta & 0xFFFF))
            else:
                target = self.address + target_index * 4
                output.append(base | ((target >> 2) & 0x03FFFFFF))
        return b"".join(struct.pack("<I", word) for word in output)


def build_runtime_classifier(address: int) -> bytes:
    """Build the MIPS helper returning ``t0=1`` for Hangul, else retail width."""

    b = _MipsBuilder(address)
    # Existing low glyphs remain low.
    b.i(0x0B, _A0, _V0, HANGUL_BASE_START)       # sltiu v0,a0,0x101
    b.branch(0x05, _V0, _ZERO, "low")            # bnez v0,low
    b.word(0)                                      # delay slot

    # Base Hangul is contiguous through 0xA2E, apart from the three retained
    # structural cells.
    b.i(0x0B, _A0, _V0, HANGUL_BASE_END + 1)      # sltiu v0,a0,0xA2F
    b.branch(0x04, _V0, _ZERO, "extra")           # beqz v0,extra
    b.word(0)
    for structural in sorted(STRUCTURAL_GLYPH_INDICES):
        b.i(0x0D, _ZERO, _V0, structural)          # ori v0,zero,index
        b.branch(0x04, _A0, _V0, "high")          # beq a0,v0,high
        b.word(0)
    b.jump("low")
    b.word(0)

    # Dynamic symbols stay wide.  Relocated/supplemental Hangul is a guarded
    # contiguous range immediately after them.
    b.label("extra")
    b.i(0x0B, _A0, _V0, HANGUL_EXTRA_START)
    b.branch(0x05, _V0, _ZERO, "high")            # below A37 => symbol
    b.word(0)
    b.i(0x0B, _A0, _V0, HANGUL_EXTRA_END + 1)
    b.branch(0x05, _V0, _ZERO, "low")             # A37..A3D => Hangul
    b.word(0)

    b.label("high")
    b.i(0x09, _ZERO, _T0, 2)                      # addiu t0,zero,2
    b.word((_RA << 21) | 0x08)                    # jr ra
    b.word(0)

    b.label("low")
    b.i(0x09, _ZERO, _T0, 1)                      # addiu t0,zero,1
    b.word((_RA << 21) | 0x08)
    b.word(0)

    raw = b.build()
    if len(raw) > RUNTIME_CODE_BYTES:
        raise AssertionError(
            f"half-width classifier is {len(raw)}B, reserved {RUNTIME_CODE_BYTES}B"
        )
    return raw + bytes(RUNTIME_CODE_BYTES - len(raw))


def _jal(address: int) -> bytes:
    return struct.pack("<I", 0x0C000000 | ((address >> 2) & 0x03FFFFFF))


@dataclass(frozen=True)
class RuntimePatchReport:
    executable: str
    classifier_offset: int
    classifier_address: int
    helper_offset: int
    helper_address: int
    helper_size: int
    helper_sha256: str


def patch_runtime_renderer(
    executable: bytes | bytearray,
    *,
    executable_name: str,
    font_offset: int,
) -> tuple[bytes, RuntimePatchReport]:
    """Install the half-width classifier in one translated WAR executable."""

    data = bytearray(executable)
    if data[:8] != b"PS-X EXE":
        raise ValueError(f"{executable_name}: not a PS-X EXE")
    hits: list[int] = []
    start = 0
    while True:
        found = data.find(RETAIL_CLASSIFIER, start)
        if found < 0:
            break
        hits.append(found)
        start = found + 1
    if len(hits) != 1:
        raise ValueError(
            f"{executable_name}: expected one retail renderer classifier, found {len(hits)}"
        )
    classifier_offset = hits[0]
    load_address = struct.unpack_from("<I", data, 0x18)[0]
    helper_offset = font_offset + RUNTIME_CODE_GLYPH_START * GLYPH_BYTES
    helper_address = load_address + helper_offset - 0x800
    classifier_address = load_address + classifier_offset - 0x800
    if helper_offset + RUNTIME_CODE_BYTES > len(data):
        raise ValueError(f"{executable_name}: helper reservation is outside executable")
    if (classifier_address >> 28) != (helper_address >> 28):
        raise ValueError(f"{executable_name}: helper is outside JAL region")

    helper = build_runtime_classifier(helper_address)
    data[helper_offset:helper_offset + len(helper)] = helper
    # Return address is classifier+8.  The remaining two old instructions are
    # NOPs, then execution resumes at the original post-classification code.
    data[classifier_offset:classifier_offset + len(RETAIL_CLASSIFIER)] = (
        _jal(helper_address) + bytes(12)
    )
    return bytes(data), RuntimePatchReport(
        executable=executable_name,
        classifier_offset=classifier_offset,
        classifier_address=classifier_address,
        helper_offset=helper_offset,
        helper_address=helper_address,
        helper_size=len(helper),
        helper_sha256=hashlib.sha256(helper).hexdigest(),
    )


__all__ = [
    "HANGUL_INK_WIDTH",
    "HANGUL_BASE_START",
    "HANGUL_BASE_END",
    "HANGUL_EXTRA_START",
    "HANGUL_EXTRA_END",
    "STRUCTURAL_GLYPH_INDICES",
    "RUNTIME_CODE_GLYPH_INDICES",
    "RUNTIME_CODE_GLYPH_START",
    "RUNTIME_CODE_GLYPH_COUNT",
    "is_hangul_character",
    "is_halfwidth_hangul_glyph",
    "retail_glyph_advance",
    "patched_glyph_advance",
    "validate_dynamic_hangul_mapping",
    "build_runtime_classifier",
    "patch_runtime_renderer",
    "RuntimePatchReport",
]
