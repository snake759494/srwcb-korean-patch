# -*- coding: utf-8 -*-
"""C_SMAP 의 EX 오프닝·제3차 엔딩/예고편 글판을 한글로 다시 그린다.

이 파일의 대상은 모두 ``C_SMAP.BIN`` 안의 TIM 픽셀 블록이다. TIM 헤더와 CLUT,
그리고 각 블록의 폭·높이는 건드리지 않는다. 특히 EX 인용문은 한 글자씩 늘어나는
스트립이므로, 한국어 문장을 가장 긴 원본 폭에 그린 뒤 각 단계의 원래 폭으로
잘라서 타자기 애니메이션의 구조를 보존한다.
"""
from __future__ import annotations

import struct
from collections import Counter
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import title_menu_strips as TM


FONT = "C:/Windows/Fonts/HANDotum.ttf"
FONT_FALLBACK = "C:/Windows/Fonts/malgun.ttf"
QUOTE_BDF = Path(__file__).resolve().parents[2] / "font" / "Galmuri14.bdf"
QUOTE_INK_WIDTH = 9
QUOTE_ADVANCE = 10
QUOTE_BASELINE = 14
SS = 4


def _palette(data: bytes | bytearray, tim: tuple) -> list[tuple[int, int, int]]:
    """TIM 의 CLUT 를 8비트 RGB 로 읽는다."""
    flags = struct.unpack_from("<I", data, tim[0] + 4)[0]
    if not flags & 8:
        return []
    q = tim[0] + 8
    _size, _x, _y, width, _height = struct.unpack_from("<IHHHH", data, q)
    out = []
    for i in range(width):
        v = struct.unpack_from("<H", data, q + 12 + 2 * i)[0]
        out.append(((v & 31) * 8, ((v >> 5) & 31) * 8, ((v >> 10) & 31) * 8))
    return out


def _read4(data: bytes | bytearray, tim: tuple) -> list[list[int]]:
    w, h, p0, p1 = tim[2], tim[3], tim[6], tim[7]
    stride = (p1 - p0) // h
    return [
        [
            (data[p0 + y * stride + x // 2] & 0x0F)
            if x % 2 == 0
            else (data[p0 + y * stride + x // 2] >> 4)
            for x in range(w)
        ]
        for y in range(h)
    ]


def _write4(data: bytearray, tim: tuple, px: list[list[int]]) -> None:
    p0, p1, h = tim[6], tim[7], tim[3]
    stride = (p1 - p0) // h
    for y, row in enumerate(px):
        for x in range(0, len(row), 2):
            data[p0 + y * stride + x // 2] = (row[x] & 0x0F) | ((row[x + 1] & 0x0F) << 4)


def _read8(data: bytes | bytearray, tim: tuple) -> list[list[int]]:
    w, h, p0, p1 = tim[2], tim[3], tim[6], tim[7]
    stride = (p1 - p0) // h
    return [[data[p0 + y * stride + x] for x in range(w)] for y in range(h)]


def _write8(data: bytearray, tim: tuple, px: list[list[int]]) -> None:
    p0, p1, h = tim[6], tim[7], tim[3]
    stride = (p1 - p0) // h
    for y, row in enumerate(px):
        for x, value in enumerate(row):
            data[p0 + y * stride + x] = value & 0xFF


def _font_for(lines: list[str], max_w: int, line_h: int, margin: int) -> ImageFont.FreeTypeFont:
    """모든 줄이 같은 크기로 들어가는 가장 큰 글꼴을 고른다."""
    avail_w = max(1, max_w - margin * 2)
    avail_h = max(3, line_h - 2)
    for path in (FONT, FONT_FALLBACK):
        for size in range(max(7, line_h + 6), 5, -1):
            try:
                font = ImageFont.truetype(path, size * SS)
            except Exception:
                break
            probe = Image.new("L", (max_w * SS + 32, line_h * SS + 32), 0)
            draw = ImageDraw.Draw(probe)
            ok = True
            for line in lines:
                if not line:
                    continue
                box = draw.textbbox((0, 0), line, font=font)
                if box[2] - box[0] > avail_w * SS or box[3] - box[1] > avail_h * SS:
                    ok = False
                    break
            if ok:
                return font
    raise SystemExit(f"한글 글판 글꼴 크기를 정하지 못했습니다: 폭={max_w}, 줄={line_h}")


def _mask(lines: list[str], w: int, h: int, margin: int = 4) -> list[list[int]]:
    """줄 배열을 고해상도에서 그린 뒤 0..255 알파 마스크로 줄인다."""
    if not lines:
        return [[0] * w for _ in range(h)]
    slot_h = max(1, h // len(lines))
    font = _font_for(lines, w, slot_h, margin)
    canvas = Image.new("L", (w * SS, h * SS), 0)
    draw = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        if not line:
            continue
        box = draw.textbbox((0, 0), line, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        y0 = (i * h // len(lines)) * SS
        y1 = ((i + 1) * h // len(lines)) * SS
        x = margin * SS - box[0]
        y = y0 + max(0, (y1 - y0 - th) // 2) - box[1]
        draw.text((x, y), line, font=font, fill=255)
    small = canvas.resize((w, h), Image.Resampling.LANCZOS)
    return [[small.getpixel((x, y)) for x in range(w)] for y in range(h)]


def _luminance(rgb: tuple[int, int, int]) -> float:
    return rgb[0] * 0.299 + rgb[1] * 0.587 + rgb[2] * 0.114


@lru_cache(maxsize=1)
def _quote_glyphs() -> dict[int, tuple[int, int, int, int, tuple[int, ...], int]]:
    """인용문에 쓰는 Galmuri14 BDF 글리프를 읽는다."""
    if not QUOTE_BDF.is_file():
        raise SystemExit(f"인용문 비트맵 글꼴이 없습니다: {QUOTE_BDF}")
    lines = QUOTE_BDF.read_text(encoding="utf-8").splitlines()
    glyphs: dict[int, tuple[int, int, int, int, tuple[int, ...], int]] = {}
    pos = 0
    while pos < len(lines):
        if not lines[pos].startswith("STARTCHAR "):
            pos += 1
            continue
        pos += 1
        encoding = None
        bbx = None
        bitmap: list[int] = []
        while pos < len(lines) and lines[pos] != "ENDCHAR":
            line = lines[pos]
            if line.startswith("ENCODING "):
                encoding = int(line.split()[1])
            elif line.startswith("BBX "):
                _, w, h, xoff, yoff = line.split()
                bbx = (int(w), int(h), int(xoff), int(yoff))
            elif line == "BITMAP":
                pos += 1
                while pos < len(lines) and lines[pos] != "ENDCHAR":
                    bitmap.append(int(lines[pos], 16))
                    pos += 1
                break
            pos += 1
        if encoding is not None and encoding >= 0 and bbx is not None:
            w, h, xoff, yoff = bbx
            if len(bitmap) == h:
                glyphs[encoding] = (w, h, xoff, yoff, tuple(bitmap), ((w + 7) // 8) * 8)
        pos += 1
    return glyphs


def _quote_cell(char: str, ink_width: int, baseline: int) -> list[list[bool]]:
    """Galmuri14 글리프 하나를 16x16 1bpp 셀로 복원한다."""
    glyph = _quote_glyphs().get(ord(char))
    if glyph is None:
        raise SystemExit(f"인용문 글꼴에 글리프가 없습니다: U+{ord(char):04X}")
    width, height, _xoff, yoff, bitmap, bitmap_bits = glyph
    cell = [[False] * 16 for _ in range(16)]
    top = baseline - (yoff + height - 1)
    for source_y, row_bits in enumerate(bitmap):
        for source_x in range(width):
            if not row_bits & (1 << (bitmap_bits - 1 - source_x)):
                continue
            if width <= ink_width:
                scaled_x = source_x + (ink_width - width) // 2
            else:
                scaled_x = (source_x * ink_width) // width
            x = 1 + scaled_x
            y = top + source_y
            if 0 <= x < 16 and 0 <= y < 16:
                cell[y][x] = True
    return cell


def _quote_layout(char: str) -> tuple[int, int | None]:
    """문자별 표시 폭과 픽셀 잉크 폭을 정한다."""
    if char == " ":
        return 5, None
    if char in ".,":
        return 3, 1
    if char == "-":
        return 5, 5
    glyph = _quote_glyphs().get(ord(char))
    if glyph is None:
        raise SystemExit(f"인용문 글꼴에 글리프가 없습니다: U+{ord(char):04X}")
    if ord(char) < 0x80:
        ink = min(7, max(4, glyph[0] - 1))
        return ink + 1, ink
    return QUOTE_ADVANCE, QUOTE_INK_WIDTH


def _quote_mask(text: str, width: int, height: int, band: tuple[int, int]) -> list[list[bool]]:
    """게임 본문과 같은 픽셀 글꼴로 읽히는 인용문 마스크를 만든다."""
    top, bottom = band
    baseline = QUOTE_BASELINE + int(round(((top + bottom) - 15) / 2))
    mask = [[False] * width for _ in range(height)]
    x = 0
    for char in text:
        advance, ink_width = _quote_layout(char)
        if x + advance > width:
            raise SystemExit(f"인용문이 프레임 폭을 넘습니다: '{text}' ({x + advance}>{width})")
        if ink_width is not None:
            cell = _quote_cell(char, ink_width, baseline)
            for y in range(min(height, 16)):
                for xx in range(min(16, width - x)):
                    if cell[y][xx]:
                        mask[y][x + xx] = True
        x += advance
    return mask


def _quote_band(source: list[list[int]], pal: list[tuple[int, int, int]], bg: int) -> tuple[int, int]:
    """장식 테두리를 제외한 원본의 밝은 글자 영역을 찾는다."""
    core = TM.body_index(source, bg, pal)
    ys = [y for y, row in enumerate(source) if core in row]
    return (min(ys), max(ys)) if ys else TM.text_band(source, bg)


def _indexed_block(data: bytes | bytearray, tim: tuple, lines: list[str], margin: int) -> list[list[int]]:
    """4bpp 글판을 CLUT 의 본체·윤곽·배경 3단계로 다시 그린다.

    원본 내레이션 글판도 대부분 이 세 단계만 사용한다. 모든 안티앨리어싱
    단계까지 양자화하면 한글 획마다 고유한 바이트가 늘어 제자리 재압축 여유를
    소진하므로, 게임의 기존 윤곽 방식과 같은 3색으로 제한한다.
    """
    source = _read4(data, tim)
    pal = _palette(data, tim)
    if len(pal) < 16:
        raise SystemExit(f"4bpp 글판 CLUT 가 16색이 아닙니다: {len(pal)}")
    bg = TM.background(source)
    mask = _mask(lines, tim[2], tim[3], margin)
    lum = [_luminance(c) for c in pal]
    foreground = max((lum[i] for i in range(16) if i != bg), default=255.0)
    edge_candidates = [i for i in range(16) if i != bg and lum[i] > lum[bg]]
    edge = min(edge_candidates, key=lambda i: lum[i]) if edge_candidates else bg
    out = [[bg] * tim[2] for _ in range(tim[3])]
    for y in range(tim[3]):
        for x in range(tim[2]):
            if mask[y][x] > 110:
                out[y][x] = min(range(16), key=lambda i: abs(lum[i] - foreground))
    for y in range(tim[3]):
        for x in range(tim[2]):
            if out[y][x] != bg:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < tim[3] and 0 <= xx < tim[2] and out[yy][xx] != bg:
                        out[y][x] = edge
                        break
                if out[y][x] != bg:
                    break
    return out


def _prefix_frame(
    source: list[list[int]],
    mask: list[list[bool]],
    pal: list[tuple[int, int, int]],
    bg: int,
    solid: bool = False,
) -> list[list[int]]:
    """원본 스트립의 밝기/윤곽 규칙을 유지한 한 프레임을 만든다."""
    h, w = len(source), len(source[0])
    depth = TM._depth_map(mask, h, w)
    rule = TM.learn(source, bg)
    core = TM.body_index(source, bg, pal)
    edge = rule.get(1, core)
    if edge == core:
        inner = [d for d in rule if d > 0]
        if inner:
            edge = rule[max(inner)]
    out = [[bg] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            d = depth[y][x]
            if d is None:
                continue
            if d > 0:
                out[y][x] = core if solid else (edge if d == 1 else core)
            else:
                out[y][x] = rule.get(d, bg)
    return out


def _left_align(mask: list[list[bool]]) -> list[list[bool]]:
    """TM 렌더러가 가운데 둔 글자를 스트립처럼 왼쪽으로 옮긴다."""
    h, w = len(mask), len(mask[0])
    xs = [x for row in mask for x, value in enumerate(row) if value]
    if not xs:
        return mask
    shift = min(xs)
    return [
        [mask[y][x + shift] if x + shift < w else False for x in range(w)]
        for y in range(h)
    ]


def _prefixes(
    body: bytearray,
    tl: list[tuple],
    groups: list[tuple[list[int], str]],
) -> list[tuple[int, int]]:
    touched: list[tuple[int, int]] = []
    for indices, text in groups:
        last = tl[indices[-1]]
        assert last[1] == 4 and last[3] == 16, f"인용 스트립 규격 오류: {indices[-1]}"
        max_w = last[2]
        final_source = _read4(body, last)
        final_bg = TM.background(final_source)
        band = _quote_band(final_source, _palette(body, last), final_bg)
        full = _left_align(_quote_mask(text, max_w, 16, band))
        for idx in indices:
            tim = tl[idx]
            assert tim[1] == 4 and tim[3] == 16, f"인용 TIM 규격 오류: {idx}"
            source = _read4(body, tim)
            bg = TM.background(source)
            pal = _palette(body, tim)
            clipped = [[full[y][x] for x in range(tim[2])] for y in range(16)]
            _write4(body, tim, _prefix_frame(source, clipped, pal, bg, solid=True))
            touched.append((tim[6], tim[7]))
    return touched


def _rgb_image(data: bytes | bytearray, tim: tuple) -> tuple[Image.Image, list[tuple[int, int, int]]]:
    pal = _palette(data, tim)
    px = _read8(data, tim)
    img = Image.new("RGB", (tim[2], tim[3]))
    out = img.load()
    for y, row in enumerate(px):
        for x, value in enumerate(row):
            out[x, y] = pal[value]
    return img, pal


def _title_mask(text: str, w: int, h: int) -> Image.Image:
    """예고편 타이틀을 기존 320x128 글판의 중앙에 맞춰 그린다."""
    box_w, box_h = 230, 68
    for path in (FONT, FONT_FALLBACK):
        for size in range(64, 18, -1):
            try:
                font = ImageFont.truetype(path, size)
            except Exception:
                break
            probe = Image.new("L", (w * 2, h * 2), 0)
            bb = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
            if bb[2] - bb[0] <= box_w and bb[3] - bb[1] <= box_h:
                mask = Image.new("L", (w, h), 0)
                draw = ImageDraw.Draw(mask)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                x = (w - tw) // 2 - bb[0]
                y = 34 + (box_h - th) // 2 - bb[1]
                draw.text((x, y), text, font=font, fill=255)
                return mask
    raise SystemExit("예고편 타이틀 글꼴 크기를 정하지 못했습니다")


def _title(data: bytearray, tim: tuple, text: str) -> None:
    """8bpp 녹색 글로우 타이틀에서 일본어 글자 영역만 지우고 한글을 얹는다."""
    img, pal = _rgb_image(data, tim)
    # 원본의 흰 글자를 포함한 중앙 영역을 흐린 글로우로 되돌린다. 주변의
    # 글로우는 유지되고, 이후 한글 마스크가 같은 CLUT 로 다시 양자화된다.
    blurred = img.filter(ImageFilter.GaussianBlur(7))
    base = img.copy()
    bp, srcp = base.load(), blurred.load()
    for y in range(28, min(100, tim[3])):
        for x in range(40, min(tim[2] - 40, 280)):
            bp[x, y] = srcp[x, y]
    mask = _title_mask(text, tim[2], tim[3])
    mp, bp = mask.load(), base.load()
    nearest = []
    for color in pal:
        nearest.append(color)
    out = [[0] * tim[2] for _ in range(tim[3])]
    for y in range(tim[3]):
        for x in range(tim[2]):
            alpha = mp[x, y]
            br, bg, bb = bp[x, y]
            if alpha:
                a = alpha / 255.0
                color = (int(br * (1 - a) + 255 * a), int(bg * (1 - a) + 255 * a),
                         int(bb * (1 - a) + 255 * a))
            else:
                color = (br, bg, bb)
            out[y][x] = min(range(len(nearest)), key=lambda i: sum((nearest[i][k] - color[k]) ** 2 for k in range(3)))
    _write8(data, tim, out)


def redraw(body: bytearray, tl: list[tuple], spec: dict) -> list[tuple[int, int]]:
    """한 멤버에 지정된 인용문·글판·타이틀을 적용한다."""
    touched: list[tuple[int, int]] = []
    for indices, text in spec.get("prefixes", []):
        touched.extend(_prefixes(body, tl, [(list(indices), text)]))
    for idx, lines in spec.get("blocks", {}).items():
        tim = tl[idx]
        assert tim[1] == 4, f"글판은 4bpp 여야 합니다: TIM {idx}"
        _write4(body, tim, _indexed_block(body, tim, lines, spec.get("margin", 4)))
        touched.append((tim[6], tim[7]))
    for idx, text in spec.get("titles", {}).items():
        tim = tl[idx]
        assert tim[1] == 8, f"타이틀은 8bpp 여야 합니다: TIM {idx}"
        _title(body, tim, text)
        touched.append((tim[6], tim[7]))
    return touched


EX_PATCHES = {
    40: {
        "margin": 4,
        "prefixes": [
            (list(range(11, 25)), "고도로 발달한"),
            (list(range(25, 37)), "과학기술은"),
            (list(range(37, 47)), "마술과"),
            (list(range(47, 61)), "구분할 수 없다."),
            (list(range(61, 69)), "아서 C. 클라크"),
        ],
        "blocks": {
            69: ["이성인과의 싸움도 끝나고, 제2의 고향인", "지저세계 라 기아스로 돌아온 마사키."],
            70: ["반년 전 왕도를 덮친 대규모 테러로,", "란그란 왕국은 중앙 정부의 기능을 잃고", "사실상 무너졌다."],
            71: ["같은 시기에 슈테드니아스 연합이 침공해,", "란그란은 혼란의 소용돌이에 휘말렸다."],
            72: ["테러 계획을 조종한 것으로 의심받던 슈를", "쫓아 지상으로 나온 마사키였지만, 슈의 죽음으로", "다시 란그란으로 돌아왔다."],
            73: ["현재 란그란은 슈테드니아스군, 구 란그란군,", "새 정권을 빼앗은 카크스군이", "세 세력으로 맞서고 있다."],
        },
    },
    45: {
        "margin": 4,
        "prefixes": [
            (list(range(2, 16)), "자유롭다는 것은,"),
            (list(range(16, 31)), "자유롭도록"),
            (list(range(31, 42)), "저주받은...."),
            (list(range(42, 55)), "존재하는 것이다"),
            (list(range(55, 63)), "J-P. 사르트르"),
        ],
        "blocks": {
            63: ["그의 의식은 어둠의 일부가 되어 있었다."],
            64: ["그는 자신의 의지를 위해", "소중한 시간까지도 아낌없이 바쳤다."],
            65: ["그의 의식은 한순간에 모든 것을 붙잡았다.", "그 일부가 어둠 속에 녹아들었다."],
            66: ["그리고…… 그는 돌아왔다."],
        },
    },
}


THIRD_PATCHES = {
    250: {
        "margin": 3,
        "blocks": {
            0: ["슈퍼로봇대전", "컴플리트 박스", "", "스태프", "", "프로듀서", "테라다 타카노부", "모리즈미 소이치로", "", "각본", "사카타 마사히코", "", "연출", "토쿠무라 요시노리"],
            1: ["메인 프로그래머", "쇼 신야                 쿠사노 카즈야", "", "서브 프로그래머", "타나베 유우지", "", "전투 애니메이션 데이터", "이와사키 타카요시", "", "사운드 어시스턴트"],
            2: ["사운드 어시스턴트", "사무카와 마사미       후지와라 타츠야", "이나다 요시히로", "", "2D 그래픽 감독", "마츠모토 켄이치로     호소즈 후미에", "미야시타 카요코", "", "2D 그래픽", "우치다 요시노리       칸베 타카코", "쿠로사와 코지         시모야마 타케시", "토다 아츠키           후지사와 케이코"],
            3: ["그래픽 어시스턴트", "이와사키 마사미       도이타 쇼코", "", "무비 감독", "카마타 타카시", "", "무비", "나카다 요시야스       나카무라 마코토", "요시다 와타루         나카무라 나오키", "나카데 히데지로       키쿠치 코지", "", "오리지널 메카 디자인"],
        },
    },
    251: {
        "margin": 3,
        "blocks": {
            0: ["오리지널 메카 디자인", "하시모토 토모유키        오다베 이사오", "이시이 히데아키          하마가미 타케시", "야시마 유미", "", "성우 출연", "아오노 타케시           아키모토 요스케", "아다치 시노부           이이즈카 쇼조", "이케다 슈이치           이시다 아키라", "이노우에 키쿠코         우에다 유지", "오오타 아키라           오오타키 신야", "오오츠카 아키오         오오바야시 류조"],
            1: ["성우 출연진", "제2차·제3차·EX 출연 성우", "", "주요 배역", "마사키 안도", "류네 조레브", "슈우 시라카와", "", "조연 및 게스트 배역", "각 배역 담당 성우"],
            2: ["성우 출연진", "지구 연방과 DC의 인물들", "", "주요 배역", "카미유 비단", "아무로 레이", "쥬도 아시타", "하만 칸", "", "각 배역 담당 성우"],
            3: ["성우 출연진", "론도 벨과 각 세력의 파일럿", "", "주요 배역", "코우 우라키", "시로코", "카츠 코바야시", "라라아 슨", "", "각 배역 담당 성우"],
        },
    },
    258: {
        "margin": 5,
        "titles": {3: "예고편"},
        "blocks": {6: ["제1화 「암운」", "론도 벨 부대, 출격!"]},
    },
    259: {
        "margin": 6,
        "blocks": {
            0: ["전 세계를 혼란에 빠뜨린", "‘DC 전쟁’으로부터 반년, 지구에", "새로운 위기가 다가오고 있었다.", "", "DC의 부활, 정체불명의 적의 습격.", "마침내 우주에서 온 침략자가", "그 모습을 드러낸다.", "", "다시 일어선 영웅들은", "평화를 되찾을 수 있을까?"],
            1: ["지구를 지킬 슈퍼로봇들이", "집결하기 시작했다.", "", "콤바트라V, 라이딘, 다이탄3……", "새로운 동료들과 함께", "뜨거운 전투가 시작된다.", "", "다음 이야기", "‘제3차 슈퍼로봇대전’"],
        },
    },
    261: {
        "margin": 5,
        "blocks": {
            3: ["‘제3차 슈퍼로봇대전’이", "끝난 지 한 달……,", "", "사람들은 아직도 평화라는 이름의", "달콤한 열매를 맛보지 못했다.", "", "DC의 부활과 이성인의 습격이라는,", "두 가지 큰 존망의 위기가 있었지만,", "연방 정부의 지구 우선주의가", "우주 이민자들의 반발을 샀고,", "그 결과 곳곳에서 소규모 충돌과 테러,", "게릴라 활동이 벌어지기 시작했다."],
            5: ["그렇게 세워진 특수부대", "‘티탄즈’는 그들을 진압하며", "공적을 쌓고 있었다.", "", "징조는 어느 날 갑자기 나타났다.", "", "어느 날부터 각지에서 인간과 병기가", "섬광에 휩싸여 흔적도 없이 사라지는", "괴현상이 잇따르기 시작했다.", "", "론도 벨을 비롯한 연방군과", "구 DC 대원들은", "사건의 진상을 쫓기 시작했다."],
        },
    },
    262: {
        "margin": 6,
        "titles": {4: "예고편"},
        "blocks": {
            0: ["티탄즈의 대원들과", "행방불명된 사람들은", "제3차 대전을 헤쳐 온", "우수한 파일럿이 대부분이었다.", "", "민간인 학생들까지 포함된", "수수께끼의 실종 사건.", "새로운 사건의 전조를", "사람들은 두려워했다.", "", "그때 신기한 로봇이 나타났다……"],
            2: ["그들은 어디로 사라진 것일까?", "", "그리고 대체 무엇이", "시작되려는 것일까?", "", "‘슈퍼로봇대전 EX’ 뒤에", "‘라 기아스 사건’이라 불릴", "또 하나의 이야기가 시작된다."],
        },
    },
    264: {
        "margin": 6,
        "blocks": {
            0: ["……이상이 20년 만에 공개된", "이성인 전쟁, 이른바", "제3차 슈퍼로봇대전의 진실이다.", "", "이 중대한 정보를 20년 동안", "숨겨 온 연방의 처사에는", "실망하지 않을 수 없다.", "", "그러나 진실을 밝힌 지금,", "같은 실수를 되풀이하지 않을", "길이 열렸다고 믿는다."],
            2: ["이성인은 과연 무엇인가?", "그들은 인류가 지금까지의", "이기적인 사고를 버리고", "우주를 적으로 보지 않기를 바란다.", "", "이 지구를 구해 준", "론도 벨에 감사하며,", "인류의 미래를 함께 생각해야 한다.", "", "이 보고서를 읽는 여러분,", "그리고 앞으로 읽게 될 여러분에게", "묻고 싶다."],
            4: ["우리 인류는 어디로 가려는가?", "무엇을 해야 하는가?", "", "그 답은 여러분 한 사람 한 사람의", "마음속에 있다.", "그것이 인류의 앞날을", "열어 갈 길이다."],
        },
    },
    265: {
        "margin": 6,
        "blocks": {
            0: ["이 싸움은 훗날", "제3차 슈퍼로봇대전이라 불리게 되었다.", "", "이 전쟁이 우리에게 남긴 교훈은", "무엇이었을까?", "", "오늘도 세계 곳곳에서 전쟁이 벌어진다.", "그 모습을 볼 때마다", "나는 인간이 아직 오만함을 버리지", "못했음을 느낀다.", "", "하지만 절망할 필요는 없다."],
            2: ["말할 수 있기 때문이다.", "인류가 지금과 같은", "독선적인 생각을 버리지 않는 한,", "우주를 적으로 삼게 될 것이다.", "", "작은 한 걸음이라도", "멈추지 말고 나아가야 한다.", "", "우리 앞에는 빛나는 세계가 있다."],
        },
    },
    266: {
        "margin": 6,
        "blocks": {
            0: ["슈우 시라카와…… 그의 목적이 무엇이었는지,", "그것을 아는 유일한 남자 마사키 안도는,", "이 싸움이 끝난 뒤 자취를 감췄다.", "", "이제 와서는 그것을 알 방법이 없지만,", "슈우의 행동은 우리에게 무엇을 전하려 했을까?", "", "힘만을 추구하는 자는 언젠가", "힘에 의해 멸망한다.", "오늘의 우리는 이 말을 풀 열쇠를", "찾지 못한 미숙한 자일 뿐이다.", "", "하지만 언젠가는,"],
            2: ["이 세계가 힘만으로가 아니라,", "사람들의 화합으로 만들어지는 날이 온다.", "", "……아니, 오는 것이 아니다.", "우리가 그날을 향해 걸어가야 한다."],
        },
    },
    272: {
        "margin": 3,
        "blocks": {
            0: ["오리지널 메카 디자인"],
            1: ["오리지널 메카 디자인", "카토키 하지메          후쿠치 히토시", "모리 준이치            후지이 다이스케", "", "게스트 메카 디자인 (레이 업)", "후지이 타이사쿠         테라시마 신야", "미야 토요시            야마다 타카시", "", "오리지널 캐릭터 디자인", "코우노 사치코", "", "SD 캐릭터 원화 (레이 업)", "카게야마 이치코         사쿠라이 코지"],
            2: ["합체 제작", "미야 토요시             테라시마 신야", "", "음악 제작", "하마다 아야 (아트프로)", "테오 케이코 (아트프로)", "", "녹음 스튜디오", "타바타 스튜디오", "", "영업 스태프", "나가타 하치로          와타나베 유타카", "야마자키 아츠시        나고야 히데토시"],
            3: ["홍보 스태프", "이시카와 케이          마츠다 요시후미", "스즈키 미카            키무라 치에", "코바야시 마도카        마스다 준지", "치바 토모히로", "", "지원 스태프", "카도하라 유타          이케다 히로시", "모리테 야스오          미야케 미츠나리", "", "협력"],
            4: ["주식회사 프로덕션", "주식회사 선라이즈", "주식회사 창조 에이전시", "다이내믹 기획 주식회사", "동영 주식회사", "주식회사 토호신사", "", "주식회사 아트프로", "스튜디오 스태프", "주식회사 레이 업", "", "스페셜 땡스", "아베 마코토             이토 렌", "이노우에 시게키        오자와 토모미"],
        },
    },
}


PATCHES = [(40, EX_PATCHES[40], "EX 오프닝 인용문·프롤로그"),
           (45, EX_PATCHES[45], "EX 오프닝 보조 인용문"),
           *[(i, THIRD_PATCHES[i], f"제3차 엔딩·예고편 멤버 {i}") for i in THIRD_PATCHES]]
