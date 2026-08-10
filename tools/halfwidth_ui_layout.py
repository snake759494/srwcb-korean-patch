#!/usr/bin/env python3
"""Layout helpers for the isolated half-width Hangul experiment.

Dialogue deliberately benefits from the compact 8-pixel Hangul cursor.  UI
resources are different: many of them draw a pointer-selected value and then
position the next field relative to the cursor left by that value.  Merely
patching the static UI script therefore pulls every later column to the left.

This module keeps the visible Hangul compact while restoring the *field
extent* of pointer-backed menu/status strings.  Missing cells are represented
by the renderer's ordinary invisible low glyph immediately before F6/FF.  A
source record with an explicit leading blank prefix is treated as right
aligned, so the compensating blanks are put before the Korean text instead.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from halfwidth_hangul import patched_glyph_advance, retail_glyph_advance


LOW_BLANK = b"\x00"
HIGH_BLANK_INDEX = 0x3FF
INVISIBLE_GLYPH_INDICES = frozenset({0x000, HIGH_BLANK_INDEX})
CONTROL_ARGUMENT_BYTES = {
    0xF6: 0,
    0xF7: 0,
    0xF8: 1,
    0xF9: 1,
    0xFA: 0,
    0xFB: 2,
    0xFC: 2,
    0xFD: 2,
    0xFE: 1,
}


# The common SECOND overlay does not contain a few short labels that occur
# only in THIRD/EX/TR.  These aliases are semantic, deterministic, and small
# enough for the original one- or few-cell fields.
CROSS_GAME_FIXED_ALIASES: dict[str, dict[str, str]] = {
    "terrain_names": {
        "谷": "골",
        "柱": "기",
        "池": "못",
    },
    "spirit_commands": {
        "指定したユニットのエネルギ-,残弾を最大まで補給します。ただし,補給されたパイロットの気力は-10されます。": "지정 유닛의 EN·탄약 보급[F6]보급 시 기력 -10",
        "1タ-ンの間,攻撃の命中率が100%になります。ただし,相手が「ひらめき」を使っていた場合,「ひらめき」が優先されます。": "1턴간 명중률 100%[F6]번뜩임 우선",
        "敵ユニットを倒さずに,HPを10だけ残します。ただし,相手より技量が上回っていなければ無効になります。": "적 HP를 10만 남김[F6]기량 낮으면 무효",
        "1タ-ンの間,敵から攻撃されなくなります。また,反撃も受けません。": "1턴간 적 공격 무효[F6]반격도 없음",
        "自爆し,隣接したユニット(味方含む)にHP分の防御無視ダメ-ジを与えます。": "자폭하여 인접 유닛에[F6]HP만큼 방어무시 피해",
        "一回だけ指定した味方ユニットの代わりに,マップ兵器以外の敵の攻撃を受けます。": "1회 지정 아군 대신[F6]공격을 받음",
        "1タ-ンの間,敵の命中率が半分になります。ただし「必中」は優先されます。": "1턴간 적 명중률 절반[F6]필중 우선",
        "1回だけ相手に与えるダメ-ジが3倍になります。「熱血」との併用はできません。": "1회 피해 3배[F6]열혈과 병용 불가",
        "マップ上にいる好きな味方キャラクタ-の精神コマンドを,通常の倍の精神ポイント消費で使えます。": "아군 정신기를[F6]SP 2배로 사용",
        # EX carries nine retail text variants with one damaged/missing source
        # glyph.  They are the same spirit descriptions and share the reviewed
        # two-line Korean layout above.
        "指定したユニットのエネルギ-,残弾を最大まで補給します。だし,補給されたパイロットの気力は-10されます。": "지정 유닛의 EN·탄약 보급[F6]보급 시 기력 -10",
        "1タ-ンの間,攻撃の命中率が100%になります。ただし,相手がひらめき」を使っていた場合,「ひらめき」が優先されます。": "1턴간 명중률 100%[F6]번뜩임 우선",
        "敵ユニットを倒さずに,HPを10だけ残します。ただし,相手よりレ量が上回っていなければ無効になります。": "적 HP를 10만 남김[F6]기량 낮으면 무효",
        "1タ-ンの間,敵から攻撃されなくなります。た,反撃も受けません。": "1턴간 적 공격 무효[F6]반격도 없음",
        "自爆し,隣接したユニット(味方含む)にHP分のぼ御無視ダメ-ジを与えます。": "자폭하여 인접 유닛에[F6]HP만큼 방어무시 피해",
        "一回だけ指定した味方ユニットの代わりに,ップ兵器以外の敵の攻撃を受けます。": "1회 지정 아군 대신[F6]공격을 받음",
        "1タ-ンの間,敵の命中率が半分になります。だし「必中」は優先されます。": "1턴간 적 명중률 절반[F6]필중 우선",
        "1回だけ相手に与えるダメ-ジが3倍になります。熱血」との併用はできません。": "1회 피해 3배[F6]열혈과 병용 불가",
        "マップ上にいる好きな味方キャラクタ-の精神コマンドを,D常の倍の精神ポイント消費で使えます。": "아군 정신기를[F6]SP 2배로 사용",
    },
    "scenario_titles": {
        "妹よ!": "누이!",
        "宇宙の渦": "우주와류",
        "陰謀の影": "음모그림자",
        "父と子": "부자",
    },
    "pilot_short_names": {
        "大作": "다이",
        "洸": "빛",
        "麗": "령",
        "猿丸": "사루",
    },
    "pilot_full_names": {
        "兜甲児": "코우지",
        "弓さやか": "사야카",
        "剣鉄也": "테츠야",
        "車弁慶": "벤케이",
        "葵豹馬": "효마",
        "西川大作": "다이사쿠",
        "北小介": "코스케",
        "巴武蔵": "무사시",
        "ひびき洸": "아키라",
    },
    "unit_names": {
        "ザクⅢ改": "자3개",
        "キュベレイmkⅡ": "큐베레Mk2",
    },
}


def glyph_index(raw: bytes) -> int:
    if len(raw) == 1 and raw[0] < 0xEB:
        return raw[0]
    if len(raw) == 2 and 0xEB <= raw[0] <= 0xF5:
        return ((raw[0] - 0xEB) << 8) | raw[1]
    raise ValueError(f"not a renderer glyph: {raw.hex(' ').upper()}")


def split_simple_renderer_record(raw: bytes) -> list[tuple[list[bytes], bytes]]:
    """Split a glyph/F6/FF record into lines while retaining delimiters.

    Fixed pointer tables use only glyph tokens, F6 line breaks and a final FF.
    Rejecting every other control makes this helper fail closed if it is ever
    accidentally used for a stateful UI-VM record.
    """

    lines: list[tuple[list[bytes], bytes]] = []
    glyphs: list[bytes] = []
    cursor = 0
    while cursor < len(raw):
        value = raw[cursor]
        if value in {0xF6, 0xFF}:
            lines.append((glyphs, bytes([value])))
            glyphs = []
            cursor += 1
            if value == 0xFF:
                if cursor != len(raw):
                    raise ValueError("bytes follow simple renderer terminator")
                return lines
            continue
        if value < 0xEB:
            glyphs.append(bytes([value]))
            cursor += 1
            continue
        if value <= 0xF5 and cursor + 1 < len(raw):
            glyphs.append(raw[cursor:cursor + 2])
            cursor += 2
            continue
        raise ValueError(
            f"unsupported simple renderer byte 0x{value:02X} at {cursor}"
        )
    raise ValueError("unterminated simple renderer record")


def glyph_run_signature(
    glyphs: Iterable[bytes],
    *,
    retail: bool,
) -> tuple[int, int]:
    stepper = retail_glyph_advance if retail else patched_glyph_advance
    advance = 0
    phase = 0
    for raw in glyphs:
        step, phase = stepper(glyph_index(raw), phase)
        advance += step
    return advance, phase


def simple_renderer_line_advances(raw: bytes, *, retail: bool) -> tuple[int, ...]:
    return tuple(
        glyph_run_signature(glyphs, retail=retail)[0]
        for glyphs, _delimiter in split_simple_renderer_record(raw)
    )


def split_controlled_renderer_record(
    raw: bytes,
) -> list[tuple[list[bytes], bytes]]:
    """Split a UI record into glyph runs followed by guarded controls.

    System-message pools use the same renderer as the simple pointer tables,
    but may place colour/coordinate controls between text fields.  Control
    arguments are opaque and must never be mistaken for glyph bytes.
    """

    segments: list[tuple[list[bytes], bytes]] = []
    glyphs: list[bytes] = []
    cursor = 0
    while cursor < len(raw):
        value = raw[cursor]
        if value < 0xEB:
            glyphs.append(bytes([value]))
            cursor += 1
            continue
        if value <= 0xF5:
            if cursor + 1 >= len(raw):
                raise ValueError("truncated two-byte renderer glyph")
            glyphs.append(raw[cursor:cursor + 2])
            cursor += 2
            continue
        if value == 0xFF:
            segments.append((glyphs, b"\xFF"))
            cursor += 1
            if cursor != len(raw):
                raise ValueError("bytes follow controlled renderer terminator")
            return segments
        if value not in CONTROL_ARGUMENT_BYTES:
            raise ValueError(
                f"unsupported controlled renderer byte 0x{value:02X} at {cursor}"
            )
        length = 1 + CONTROL_ARGUMENT_BYTES[value]
        if cursor + length > len(raw):
            raise ValueError(f"truncated renderer control 0x{value:02X}")
        segments.append((glyphs, raw[cursor:cursor + length]))
        glyphs = []
        cursor += length
    raise ValueError("unterminated controlled renderer record")


def _pad_renderer_glyph_run(
    source: list[bytes],
    output: list[bytes],
    *,
    floor: int | None = None,
) -> bytes:
    source_advance, _source_phase = glyph_run_signature(source, retail=True)
    output_advance, _output_phase = glyph_run_signature(output, retail=False)
    target = max(source_advance, floor or source_advance, output_advance)

    source_prefix: list[bytes] = []
    for token in source:
        if glyph_index(token) not in INVISIBLE_GLYPH_INDICES:
            break
        source_prefix.append(token)

    if source_prefix:
        core = list(output)
        while core and glyph_index(core[0]) in INVISIBLE_GLYPH_INDICES:
            core.pop(0)
        while core and glyph_index(core[-1]) in INVISIBLE_GLYPH_INDICES:
            core.pop()
        base = [*source_prefix, *core]
        base_advance, _ = glyph_run_signature(base, retail=False)
        if base_advance > target:
            raise ValueError(
                f"right-aligned output advances {base_advance}, target {target}"
            )
        return (
            b"".join(source_prefix)
            + LOW_BLANK * (target - base_advance)
            + b"".join(core)
        )

    if output_advance > target:
        raise ValueError(f"output advances {output_advance}, target {target}")
    return b"".join(output) + LOW_BLANK * (target - output_advance)


def pad_simple_renderer_record(
    source_raw: bytes,
    output_raw: bytes,
    *,
    target_floor: Iterable[int] | None = None,
) -> bytes:
    """Restore retail line extents without widening visible Hangul.

    ``target_floor`` is used only by name lists whose renderer owns a shared
    fixed column.  A translated name may legitimately be wider than its own
    Japanese spelling; in that case its current width becomes the floor and
    no text is shortened.
    """

    source_lines = split_simple_renderer_record(source_raw)
    output_lines = split_simple_renderer_record(output_raw)
    if len(source_lines) != len(output_lines):
        raise ValueError("simple renderer line count changed")
    floors = tuple(target_floor or ())
    if floors and len(floors) != len(source_lines):
        raise ValueError("simple renderer target-floor line count changed")

    rebuilt = bytearray()
    for line_index, ((source, source_delim), (output, output_delim)) in enumerate(
        zip(source_lines, output_lines)
    ):
        if source_delim != output_delim:
            raise ValueError("simple renderer delimiters changed")
        try:
            rebuilt.extend(
                _pad_renderer_glyph_run(
                    source,
                    output,
                    floor=floors[line_index] if floors else None,
                )
            )
        except ValueError as exc:
            raise ValueError(f"line {line_index}: {exc}") from exc
        rebuilt.extend(output_delim)
    return bytes(rebuilt)


def pad_controlled_renderer_record(source_raw: bytes, output_raw: bytes) -> bytes:
    """Restore every text-field extent while preserving UI control tokens.

    The source and output must have the same control opcode sequence.  Output
    arguments are retained because a reviewed translation may deliberately
    adjust a coordinate; only the glyph run immediately before each control
    is padded to the corresponding retail extent.
    """

    source_segments = split_controlled_renderer_record(source_raw)
    output_segments = split_controlled_renderer_record(output_raw)
    if len(source_segments) != len(output_segments):
        raise ValueError("controlled renderer segment count changed")

    rebuilt = bytearray()
    for segment_index, ((source, source_control), (output, output_control)) in enumerate(
        zip(source_segments, output_segments)
    ):
        if source_control[0] != output_control[0]:
            raise ValueError(
                f"controlled renderer opcode changed at segment {segment_index}: "
                f"0x{source_control[0]:02X} -> 0x{output_control[0]:02X}"
            )
        try:
            rebuilt.extend(_pad_renderer_glyph_run(source, output))
        except ValueError as exc:
            raise ValueError(f"segment {segment_index}: {exc}") from exc
        rebuilt.extend(output_control)
    return bytes(rebuilt)


def choose_fixed_text(
    *,
    asset_id: str,
    source_text: str,
    default_text: str,
    source_raw: bytes,
    encode: Callable[[str], bytes],
    reviewed_width_aliases: dict[str, dict[str, str]] | None = None,
    phase_aliases: dict[str, dict[str, str]] | None = None,
    extra_candidates: Iterable[str | None] = (),
) -> str:
    """Choose the first full-quality candidate that fits every retail line."""

    candidates: list[str] = []

    def add(value: str | None) -> None:
        if isinstance(value, str) and value not in candidates:
            candidates.append(value)

    add(default_text)
    if reviewed_width_aliases:
        add(reviewed_width_aliases.get(asset_id, {}).get(source_text))
    if phase_aliases:
        add(phase_aliases.get(asset_id, {}).get(source_text))
    add(CROSS_GAME_FIXED_ALIASES.get(asset_id, {}).get(source_text))
    for candidate in extra_candidates:
        add(candidate)
    add(default_text.replace(" ", "").replace("\u3000", ""))

    source_advances = simple_renderer_line_advances(source_raw, retail=True)
    last: tuple[int, ...] | None = None
    for candidate in candidates:
        encoded = encode(candidate) + b"\xFF"
        try:
            output_advances = simple_renderer_line_advances(encoded, retail=False)
            # This also accounts for a guarded leading high-blank prefix used
            # by right-aligned terrain/type fields.  A candidate that fits the
            # total line may still be too wide once that prefix is restored.
            pad_simple_renderer_record(source_raw, encoded)
        except ValueError:
            continue
        last = output_advances
        if len(output_advances) == len(source_advances) and all(
            output <= source
            for source, output in zip(source_advances, output_advances)
        ):
            return candidate
    raise ValueError(
        f"no half-width UI alias for {asset_id} {source_text!r} -> "
        f"{default_text!r}; source={source_advances}, output={last}"
    )


__all__ = [
    "CROSS_GAME_FIXED_ALIASES",
    "choose_fixed_text",
    "glyph_index",
    "glyph_run_signature",
    "pad_controlled_renderer_record",
    "pad_simple_renderer_record",
    "simple_renderer_line_advances",
    "split_controlled_renderer_record",
    "split_simple_renderer_record",
]
