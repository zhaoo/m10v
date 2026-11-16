"""Render the GR III MNU5 menu from the released MNU4 artwork using Pillow.

Extract the donor with git show 47a3fb6:web/gr3/MENU.M10 > /tmp/R4.M10.
Run python3 scripts/build_gr3_menu_hub_art.py /tmp/R4.M10 web/gr3/MENU-R5.M10.
The checked-in MNU5 artwork was rendered with Pillow 11.3.0 / FreeType 2.13.3 and
macOS PingFang.ttc (SHA-256 6bccdb1a967b2ae7e856927eb559591b2ce05656b0d4ad2764b9c9429f12c0b7).
Override the font file location with --font.
"""
import argparse
from hashlib import sha256
from pathlib import Path
from struct import iter_unpack, pack, pack_into

from PIL import Image, ImageChops, ImageDraw, ImageFont

from pack_gr3_menu_hub import ENTRY_BYTES, HEADER_BYTES, MAX_PATCH_BYTES, RECORD_COUNT, hash_words


DONOR_SHA256 = "8b666e2ddfb276078ed09bf486591f3ca10ad91b67ea74c35f289266f63e0be0"
SIZE = (720, 480)
FRAME = (0, 0, *SIZE)
COUNTER = (260, 360, 370, 386)
BACKGROUND = "#171a1d"
INK = "#efeee8"
VALUE = "#b6bcbe"
LINE = "#343a3e"
ARROW = "#aab1b4"
RADIO = "#717a7d"
ACCENT = "#eac47a"
ROW_Y = 86
ROW_HEIGHT = 53

EFFECTS = (
    ("HDF", ("关闭", "弱", "中", "强", "—"), 0),
    ("边框", ("关闭", "拍立得", "胶卷", "—"), 8),
    ("胶卷印花", ("关", "小猫吃鱼", "樱花纷飞", "绚烂彩虹", "深海水母",
              "小猫爪爪", "呆头大鹅", "宝可梦"), 16),
    ("暗角", ("关", "弱", "中", "强", "—"), 24),
    ("撕纸效果", ("关", "开", "—"), 32),
    ("半格", ("关", "开"), 34),
    ("滤镜快切", ("未启用", "已启用", "—"), 40),
)
SETTINGS = (
    ("水印", ("关闭", "仅日期", "日期和时间", "胶卷名称", "—"), 0),
    ("关键画面", ("原厂画面", "图片 1", "图片 2", "图片 3", "—"), 8),
    ("画幅", ("3:2", "4:3", "16:9", "1:1", "XPan", "6x7", "Half", "—"), 16),
    ("ADJ", ("6–9",), None),
    ("构图线", ("沿用原厂", "黄金分割", "黄金螺旋（左上）", "黄金螺旋（右上）",
             "黄金螺旋（左下）", "黄金螺旋（右下）", "—"), 49),
    ("裁切焦距", ("关闭", *(f"{n} mm" for n in range(28, 51)), "—"), 24),
)
HOME_CARDS = (
    ("设置", "照片与机身", "#d0bff3", 53, 335, 357, 27),
    ("胶卷库", "已选", "#eed078", 262, 347, 373, 31),
    ("效果", "全局与逐卷", "#efad98", 502, 335, 357, 27),
)
MORE_CARDS = (
    ("说明", "官网与使用指南", "#9fd4cc", 139, 349, 373, 27),
    ("打赏", "支持 m10v", "#eed078", 385, 349, 373, 27),
)


def font_path():
    system_fonts = Path("/System/Library")
    assets = system_fonts.glob("AssetsV2/com_apple_MobileAsset_Font7/*/AssetData/PingFang.ttc")
    return next(iter(sorted(assets)), system_fonts / "Fonts/PingFang.ttc")


def pingfang(font):
    # TTC indices for Simplified Chinese regular, medium, and semibold.
    return {
        name: ImageFont.truetype(font, size, index=index)
        for name, size, index in (
            ("summary", 15, 7), ("button", 23, 7), ("value", 24, 3),
            ("label", 27, 7), ("card", 27, 11), ("hero", 31, 11), ("title", 31, 7),
        )
    }


def card_matte(image, boxes):
    # Interpolate the small text strips from the clean pixels at either side.
    # Keep original card outlines, artwork, arrows and footer rules.
    pixels = image.load()
    for left, top, right, bottom in boxes:
        for y in range(top, bottom):
            start, end = pixels[left - 1, y], pixels[right, y]
            for x in range(left, right):
                fraction = (x - left + 1) / (right - left + 1)
                pixels[x, y] = tuple(round(a + (b - a) * fraction)
                                     for a, b in zip(start, end))


def draw_deck(image, fonts, more):
    cards = MORE_CARDS if more else HOME_CARDS
    footers = ((133, 328, 280, 383), (381, 328, 512, 383)) if more else (
        (47, 320, 145, 367), (258, 328, 365, 383), (496, 320, 596, 367),
    )
    card_matte(image, ((85, 25, 163, 58), *footers))
    draw = ImageDraw.Draw(image)
    draw.text((86, 40), "m10v", font=fonts["card"], fill="#f5f2eb", anchor="lm")
    for name, summary, color, x, title_y, summary_y, size in cards:
        draw.text((x, title_y), name, font=fonts["hero" if size == 31 else "card"],
                  fill="#f5f2eb", anchor="lm")
        if name != "胶卷库":
            draw.text((x, summary_y), summary, font=fonts["summary"], fill=color, anchor="lm")
    for page, center in enumerate((345, 375)):
        current = page == int(more)
        half_width = 9 if current else 3
        draw.rounded_rectangle((center - half_width, 436, center + half_width, 441),
                               radius=3, fill="#e1e5e3" if current else "#62696b")


def deck_count(image, font, count):
    variant = image.copy()
    ImageDraw.Draw(variant).text((262, 373), f"已选 {count}/10", font=font,
                                fill="#eed078", anchor="lm")
    return variant


def sheet(title, fonts):
    image = Image.new("RGB", SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.line(((57, 33), (51, 39), (57, 45)), fill=INK, width=2, joint="curve")
    draw.text((90, 40), title, font=fonts["title"], fill=INK, anchor="lm")
    draw.line((33, 71, 686, 71), fill=LINE)
    return image


def list_row(draw, index, label, value, fonts, option=False):
    top = ROW_Y + index * ROW_HEIGHT
    center = top + 26
    draw.line((34, top + ROW_HEIGHT - 1, 685, top + ROW_HEIGHT - 1), fill=LINE)
    draw.text((51, center), label, font=fonts["label"], fill=INK, anchor="lm")
    draw.text((633 if option else 644, center), value, font=fonts["value"],
              fill=VALUE, anchor="rm")
    if option:
        draw.ellipse((650, center - 10, 669, center + 9), outline=RADIO, width=2)
    else:
        draw.line(((661, center - 6), (667, center), (661, center + 6)),
                  fill=ARROW, width=2, joint="curve")


def half_detail(saved, fonts):
    image = sheet("半格", fonts)
    draw = ImageDraw.Draw(image)
    for index, label in enumerate(("关", "开")):
        list_row(draw, index, label, "使用中" if index == saved else "", fonts, option=True)
    draw.rounded_rectangle((578, 419, 685, 463), radius=6, fill=ACCENT)
    draw.text((514, 441), "取消", font=fonts["button"], fill=VALUE, anchor="mm")
    draw.text((632, 441), "保存", font=fonts["button"], fill=BACKGROUND, anchor="mm")
    return image


def overview(layout, fonts):
    effect = layout < 8
    title = "效果" if effect else "设置"
    hidden = set()
    if effect and not layout & 1:
        hidden.add("撕纸效果")
    if effect and not layout & 2:
        hidden.add("滤镜快切")
    if layout == 8:
        hidden.add("关键画面")
    rows = [row for row in (EFFECTS if effect else SETTINGS) if row[0] not in hidden]
    image = sheet(title, fonts)
    draw = ImageDraw.Draw(image)
    for index, (label, values, _) in enumerate(rows):
        list_row(draw, index, label, values[0], fonts)
    yield layout, FRAME, image

    offset = 64 + (layout - 4) * 48 if effect else 256 + (layout - 8) * 64
    for index, (_, values, start) in enumerate(rows):
        y = ROW_Y + index * ROW_HEIGHT
        cut = (390, y, 650, y + ROW_HEIGHT - 1)
        for ordinal, value in enumerate(values[1:], 1):
            variant = image.copy()
            draw = ImageDraw.Draw(variant)
            draw.rectangle((cut[0], cut[1], cut[2] - 1, cut[3] - 1), fill=BACKGROUND)
            draw.text((644, y + 26), value, font=fonts["value"], fill=VALUE, anchor="rm")
            box = ImageChops.difference(image, variant).getbbox()
            if box is None or not (
                cut[0] <= box[0] < box[2] <= cut[2] and cut[1] <= box[1] < box[3] <= cut[3]
            ):
                raise ValueError(f"Unexpected status rectangle for record {offset + start + ordinal}")
            yield offset + start + ordinal, box, variant


def donor_frames(raw):
    if sha256(raw).hexdigest() != DONOR_SHA256:
        raise ValueError("Expected the released MNU4 MENU.M10 from commit 47a3fb6")
    records = list(iter_unpack("<IIHHHH", raw[16:HEADER_BYTES]))
    for index in (0, 1, 2, 3, 10, 11, 12):
        offset, _, x, y, width, height = records[index]
        if (x, y, width, height) != FRAME:
            raise ValueError(f"Invalid MNU4 frame {index}")
        yield index, raw[offset:offset + width * height * 4]


def render_records(donor, fonts):
    for index, raw in donor_frames(donor):
        original = Image.frombytes("RGBA", SIZE, raw)
        if index in (10, 12):
            yield index, FRAME, original
            continue
        original = original.convert("RGB")
        draw_deck(original, fonts, more=index in (3, 11))
        if index in (3, 11):
            yield index, FRAME, original
            continue
        yield index, FRAME, deck_count(original, fonts["summary"], 10)
        for count in range(10):
            yield 16 + index * 11 + count, COUNTER, deck_count(original, fonts["summary"], count)
    for layout in range(4, 10):
        yield from overview(layout, fonts)
    for saved in (0, 1):
        yield 13 + saved, FRAME, half_detail(saved, fonts)


def pack_records(records, reference):
    encoded = {}
    for index, box, image in records:
        if index in encoded:
            raise ValueError(f"Duplicate menu record {index}")
        raw = image.crop(box).convert("RGBA").tobytes()
        if index >= 15 and len(raw) > MAX_PATCH_BYTES:
            raise ValueError(f"Patch {index} exceeds the runtime scratch buffer")
        encoded[index] = box, raw
        if reference:
            image.save(reference / f"{index}.png")
    directory = bytearray(RECORD_COUNT * ENTRY_BYTES)
    payload = bytearray()
    for index, ((x, y, right, bottom), raw) in sorted(encoded.items()):
        pack_into("<IIHHHH", directory, index * ENTRY_BYTES, HEADER_BYTES + len(payload),
                  hash_words(raw), x, y, right - x, bottom - y)
        payload.extend(raw)
    size = HEADER_BYTES + len(payload)
    if size >= 32 * 1024 * 1024:
        raise ValueError("Menu resource exceeds the runtime file size limit")
    return pack("<4sIII", b"MNU5", 5, RECORD_COUNT, size) + directory + payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("donor", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--font", type=Path, default=font_path())
    parser.add_argument("--reference", type=Path, help="write reference frame and variant PNGs")
    args = parser.parse_args()
    if args.reference:
        args.reference.mkdir(parents=True, exist_ok=True)
    records = render_records(args.donor.read_bytes(), pingfang(args.font))
    args.output.write_bytes(pack_records(records, args.reference))


if __name__ == "__main__":
    main()
