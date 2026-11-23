"""Build the 720x480 MNU8 menu from the released MNU5 resource and Pillow artwork.

Run python3 scripts/build_gr3_roll_menu_art.py web/gr3/MENU-R5.M10 web/gr3/MENU-R8.M10.
The sibling JSON manifest records controller coordinates, patch IDs, and resource identity.
Use the same PingFang and Pillow versions as the R5 generator for matching text.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import pack, pack_into, unpack_from

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont

from build_gr3_menu_hub_art import EFFECTS, font_path, list_row, pingfang, sheet
from generate_m10v_icons import artwork, LEICA_CARD_INK, LEICA_CARD_PAPER, LEICA_CARD_RED
from pack_gr3_menu_hub import ENTRY_BYTES, MAX_PATCH_BYTES, hash_words


DONOR_SHA256 = "02948b58fbf744212c81e1bb5fe7dae1dab2991c0313836f29a02c245174fe63"
CANISTER_FIRST = 512
CANISTER_SIZE = (144, 197)
RECORD_COUNT = 578
HEADER_BYTES = 16 + RECORD_COUNT * ENTRY_BYTES
SIZE = (720, 480)
FRAME = (0, 0, *SIZE)
INK = "#efeee8"
VALUE = "#b6bcbe"
GOLD = "#efd17f"
BACKGROUND = "#171a1d"
SETUP_BACKGROUND = "#191a1f"
EDGE = "#343a3e"
EFFECT_ROWS = (86, 46)
DECK = {
    "about": (38, 169, 233, 380), "roll": (247, 151, 473, 397),
    "support": (487, 169, 682, 380), "previous": (8, 258, 38, 310),
}
BACK = (29, 13, 78, 62)
ELLIPSIS = (650, 13, 694, 62)
HERO = (35, 91, 237, 361)
CAPACITY = ((262, 130, 360, 174), (367, 130, 466, 174))
CAPACITY_LOCKED = (262, 130, 466, 176)
ASPECT = (481, 130, 686, 174)
FILMS = (
    (262, 226, 686, 269), (262, 277, 470, 320),
)
FILM_LOCKED = (262, 229, 686, 297)
FOOTER = {
    "primary": (601, 392, 686, 431), "close_paused": (541, 392, 595, 431),
    "close_active": (453, 392, 507, 431), "exit_active": (514, 392, 595, 431),
}
STOCKS = {
    33: ("CINESTILL", "800T", "TUNGSTEN", "#062333", "#f5f2dc", "#f54f61"),
    37: ("KODAK", "PORTRA", "400", "#e7cba9", "#42264d", "#a25472"),
    66: ("KODAK", "5207", "VISION3 250D", "#d5aa36", "#182b36", "#9e2b23"),
    65: ("RICOH", "GR II", "VIVID", "#3f6061", "#efeee8", "#a2c5bc"),
    0x10016: ("RICOH", "原厂负片", "NEGATIVE FILM", "#4e5660", "#eeeee9", "#f2f2e9"),
    0: ("M10V", "", "", "#374651", "#efeee8", "#bec9d0"),
}
RATIOS = ("3:2", "4:3", "6×7", "XPan")
LIVE_CHOICES = ("关闭", "快门前后", "仅快门后")
FRAMES = {
    "deck_unfocused": 384, "deck_roll_focused": 385, "display": 386,
    "setup_editable": 387, "setup_paused": 388, "setup_active": 389,
}


def closed_box(box):
    x, y, right, bottom = box
    return x, y, right - 1, bottom - 1


def size_of(box):
    return box[2] - box[0], box[3] - box[1]


def mix(a, b, fraction):
    return tuple(round(first + (second - first) * fraction) for first, second in zip(a, b))


def gradient(size, stops, axis="x"):
    width, height = size
    length = width if axis == "x" else height
    steps = [(at, ImageColor.getrgb(color)) for at, color in stops]
    strip = Image.new("RGB", (length, 1) if axis == "x" else (1, length))
    colors = []
    for i in range(length):
        pos = i / (length - 1)
        for (start, a), (end, b) in zip(steps, steps[1:]):
            if pos <= end:
                colors.append(mix(a, b, (pos - start) / (end - start)))
                break
    strip.putdata(colors)
    return strip.resize(size, Image.Resampling.NEAREST)


def glow(size, inner, outer, center=(0.47, 0.52)):
    width, height = 90, 60
    start, end = ImageColor.getrgb(inner), ImageColor.getrgb(outer)
    board = Image.new("RGB", (width, height))
    board.putdata([
        mix(start, end, min(1, (((x / width - center[0]) / .67) ** 2
                                + ((y / height - center[1]) / .60) ** 2) ** .55))
        for y in range(height) for x in range(width)
    ])
    return board.resize(size, Image.Resampling.BICUBIC)


def matte(image, art, box, radius):
    size = size_of(box)
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    image.paste(art, box[:2], mask)


def canister(identity, fonts):
    brand, model, subtitle, stock, ink, accent = identity
    tile = Image.new("RGBA", CANISTER_SIZE)
    rgb = ImageColor.getrgb(stock)
    shade = lambda factor: "#" + "".join(f"{round(value * factor):02x}" for value in rgb)
    highlight = "#" + "".join(f"{round(value + (255 - value) * .11):02x}" for value in rgb)
    shell = (1, 17, 143, 183)
    matte(tile, gradient(size_of(shell), ((0, shade(.42)), (.13, stock), (.38, highlight),
                                          (.72, stock), (1, shade(.45)))), shell, 15)
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle(closed_box(shell), radius=15, outline=shade(.78), width=1)
    draw.rounded_rectangle((14, 156, 129, 162), radius=2, fill=accent)
    metal = ((0, "#232429"), (.21, "#6b6b71"), (.42, "#9b9b9e"), (.77, "#48494f"), (1, "#191b1f"))
    for box in ((0, 5, 144, 24), (0, 177, 144, 194)):
        matte(tile, gradient(size_of(box), metal), box, 10)
        ImageDraw.Draw(tile).ellipse(closed_box(box), outline="#707177", width=1)
    draw = ImageDraw.Draw(tile)
    draw.ellipse((9, 7, 134, 16), fill="#55565b", outline="#8b8b8d")
    draw.text((14, 65), brand, fill=accent if brand == "CINESTILL" else ink,
              font=fonts["tube_brand"], anchor="lm")
    model_font = fonts["tube_large"] if len(model) <= 4 and model.isascii() else fonts["tube_small"]
    width = model_font.getlength(model)
    if width > 117:
        model_font = model_font.font_variant(size=int(model_font.size * 117 / width))
    draw.text((12, 104), model, fill=ink, font=model_font, anchor="lm")
    draw.text((14, 139), subtitle, fill=ink, font=fonts["tube_sub"], anchor="lm")
    return tile


def catalog_canisters():
    web = Path(__file__).resolve().parents[1] / "web/gr3"
    catalog = json.loads((web / "film-directory.json").read_text())
    icon_specs = {item["id"]: item for item in json.loads((web / "film-icons/catalog.json").read_text())}
    films = [film for group in catalog["groups"] for film in group["films"]]
    if len(films) != 64 or len({film["id"] for film in films}) != len(films):
        raise ValueError("MNU8 expects 64 distinct catalog films")
    for film in [*films, {"id": 0x10016, "name": "原厂负片"}, {"id": 0, "name": "LUT"}]:
        film_id, name = film["id"], film["name"]
        identity = STOCKS.get(film_id)
        if identity is None:
            identity = artwork(name, film_id, icon_specs[film_id])[:6]
            if 331 <= film_id <= 334:
                identity = ("LEICA", identity[1], "", LEICA_CARD_PAPER, LEICA_CARD_INK, LEICA_CARD_RED)
        yield film_id, name, identity


def pack_canister(tile, film_id):
    # Allocate indices 1–255 to RGB colors. Index zero leaves the background
    # visible and its reserved palette word identifies the corresponding film.
    opaque = tile.convert("RGB").quantize(colors=255, dither=Image.Dither.NONE)
    palette = opaque.getpalette()[:255*3]
    colors = bytearray(pack("<I", film_id))
    for i in range(0, len(palette), 3):
        colors.extend((*palette[i:i+3], 255))
    colors.extend(bytes(1024 - len(colors)))
    return colors + bytes(index + 1 if alpha else 0
                          for index, alpha in zip(opaque.tobytes(), tile.getchannel("A").tobytes()))


def draw_strip(image):
    draw = ImageDraw.Draw(image)
    draw.polygon([(266, 175), (560, 178), (560, 250), (541, 250), (522, 276), (266, 276)],
                 fill="#33231f")
    cells = gradient((74, 67), ((0, "#493027"), (.53, "#35251f"), (1, "#51372c")), axis="y")
    for x in (267, 343, 419, 495):
        cropped = cells.crop((0, 0, min(74, 560 - x), 67))
        image.paste(cropped, (x, 191))
        draw.rounded_rectangle((x, 191, min(x + 73, 559), 258), radius=2, outline="#674937")
    draw.polygon([(560, 250), (560, 276), (522, 276), (541, 250)], fill="#1b1c21")
    for y, end in ((182, 556), (267, 526)):
        for x in range(282, end, 18):
            draw.rectangle((x, y, x + 8, y + 5), fill="#1f2024")


def header(image, title, fonts, status=None, ellipsis=False):
    draw = ImageDraw.Draw(image)
    draw.line((35, 71, 685, 71), fill="#33363b")
    draw.line(((53, 34), (47, 40), (53, 46)), fill="#d3d6d0", width=3, joint="curve")
    draw.text((80, 37), title, fill=INK, font=fonts["title"], anchor="lm")
    if status:
        draw.text((684, 37), "• " + status, fill=GOLD, font=fonts["meta"], anchor="rm")
    if ellipsis:
        for x in (661, 669, 677):
            draw.ellipse((x - 1, 35, x + 1, 37), fill="#d3d6d0")


def roll_display(fonts, count=0, capacity=36):
    image = glow(SIZE, "#22242a", "#17181d")
    header(image, "胶卷模式", fonts, ellipsis=True)
    draw_strip(image)
    draw = ImageDraw.Draw(image)
    for x, digit in zip((321, 346), f"{count:02d}"):
        draw.text((x, 395), digit, fill=GOLD, font=fonts["tally"], anchor="mm")
    draw.text((365, 401), f"/ {capacity}", fill="#a9afb0", font=fonts["denom"], anchor="lm")
    return image


def chip(draw, box, label, fonts, selected=False, swatch=None, dropdown=False, disabled=False):
    left, top, right, bottom = box
    center = (top + bottom) // 2
    fill, outline, ink = "#27292f", "#44474e", INK
    if selected:
        fill, outline, ink = "#363026", "#a88c51", GOLD
    if disabled:
        fill, outline, ink = "#24262b", "#393c44", "#929691"
    draw.rounded_rectangle(closed_box(box), radius=6, fill=fill, outline=outline)
    if swatch:
        draw.rounded_rectangle((left + 10, center - 10, left + 17, center + 10),
                               radius=2, fill=swatch, outline="#b5b2ab")
    if swatch or dropdown:
        draw.text((left + (25 if swatch else 14), center), label, fill=ink, font=fonts["option"], anchor="lm")
    else:
        draw.text(((left + right) // 2, center), label, fill=ink, font=fonts["option"], anchor="mm")
    if dropdown:
        draw.line(((right - 19, center - 2), (right - 15, center + 2), (right - 11, center - 2)),
                  fill=GOLD, width=2, joint="curve")


def draw_lock(draw, x, y):
    draw.rounded_rectangle((x - 6, y - 2, x + 6, y + 8), radius=2, outline="#9c9f9e")
    draw.arc((x - 3, y - 8, x + 3, y + 2), 180, 360, fill="#9c9f9e")
    draw.line((x - 3, y - 3, x - 3, y), fill="#9c9f9e")
    draw.line((x + 3, y - 3, x + 3, y), fill="#9c9f9e")


def locked_field(draw, box, label, fonts):
    left, top, right, bottom = box
    y = (top + bottom) // 2
    draw.rounded_rectangle(closed_box(box), radius=6, fill="#22242a", outline="#393c44")
    draw.text((left + 13, y), label, fill=INK, font=fonts["option"], anchor="lm")
    draw_lock(draw, right - 22, y)


def primary_button(draw, label, fonts, disabled=False):
    if disabled:
        chip(draw, FOOTER["primary"], label, fonts, disabled=True)
    else:
        x0, y0, x1, y1 = FOOTER["primary"]
        draw.rounded_rectangle(closed_box(FOOTER["primary"]), radius=6, fill=GOLD)
        draw.text(((x0 + x1) // 2, (y0 + y1) // 2), label, fill="#211d17",
                  font=fonts["option"], anchor="mm")


def roll_setup(fonts, *, state="editable", negative=False, count=0, capacity=36,
               ratio=0, closed=False, unavailable=False):
    image = Image.new("RGB", SIZE, SETUP_BACKGROUND)
    statuses = {"editable": "已收卷" if closed else "未开卷", "paused": "已暂停", "active": "拍摄中"}
    header(image, "胶卷设置", fonts, status=statuses[state])
    matte(image, glow(size_of(HERO), "#29313a", "#202125", (.52, .51)), HERO, 9)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(closed_box(HERO), radius=9, outline="#424345")
    draw.line((44, 92, 228, 92), fill="#71644b")
    locked = state != "editable"
    draw.text((51, 118), "当前胶卷" if locked else "待开卷", fill=INK, font=fonts["meta"], anchor="lm")
    draw.text((128, 329), f"{count:02d}", fill=GOLD, font=fonts["small_tally"], anchor="rm")
    draw.text((139, 333), f"/ {capacity}", fill="#a9afb0", font=fonts["small_denom"], anchor="lm")
    for x, y, label in ((262, 111, "每卷张数"), (481, 111, "画幅"), (262, 207, "胶卷")):
        draw.text((x, y), label, fill="#b9bdbe", font=fonts["meta"], anchor="lm")
    if locked:
        locked_field(draw, CAPACITY_LOCKED, f"{capacity} 张", fonts)
        locked_field(draw, ASPECT, RATIOS[ratio], fonts)
        draw.rounded_rectangle(closed_box(FILM_LOCKED), radius=6, fill="#22242a", outline="#393c44")
        draw_lock(draw, 663, 258)
    else:
        for box, option in zip(CAPACITY, (24, 36)):
            chip(draw, box, f"{option} 张", fonts, selected=capacity == option)
        chip(draw, ASPECT, RATIOS[ratio], fonts, dropdown=True)
        chip(draw, FILMS[0], "", fonts, dropdown=True)
        chip(draw, FILMS[1], "原厂负片", fonts, selected=negative)
    draw.text((262, 320 if locked else 344), "本卷设置已锁定" if locked else "开卷后沿用这组设置",
              fill="#a7abac", font=fonts["summary"], anchor="lm")
    draw.line((35, 378, 685, 378), fill="#373a3e")
    if locked:
        draw.text((35, 412), "退出模式后仍可续拍这一卷。", fill="#a7abac",
                  font=fonts["summary"], anchor="lm")
        chip(draw, FOOTER["close_active" if state == "active" else "close_paused"], "收卷", fonts)
        if state == "active":
            chip(draw, FOOTER["exit_active"], "退出模式", fonts)
    actions = {"editable": "开始一卷", "paused": "继续拍摄", "active": "返回取景"}
    primary_button(draw, "未就绪" if unavailable else actions[state], fonts, disabled=unavailable)
    return image


def roll_deck(donor, fonts, focused, status="开卷与续卷"):
    image = glow(SIZE, "#27272d", "#16171c", (.49, .36))
    image.paste(donor_frame(donor, 0).crop((0, 0, 720, 72)), (0, 0))
    left = donor_frame(donor, 11).crop((124, 151, 350, 397))
    right = donor_frame(donor, 3).crop((370, 151, 596, 397))
    for art, slot in ((left, "about"), (right, "support")):
        box = DECK[slot]
        matte(image, art.resize(size_of(box), Image.Resampling.LANCZOS), box, 11)
    card = DECK["roll"]
    matte(image, gradient(size_of(card), ((0, "#3b3024" if focused else "#292831"),
                                         (.7, "#22232c"), (1, "#22232c")), "y"),
          card, 13)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(closed_box(card), radius=13, outline=GOLD if focused else EDGE)
    if focused:
        draw.arc((247, 151, 272, 176), 180, 270, GOLD, 2)
        draw.arc((447, 151, 472, 176), 270, 360, GOLD, 2)
        draw.line((259, 152, 460, 152), fill=GOLD, width=2)
    # A small graphic on the card uses the same cap and cylindrical lighting as the large display.
    emblem = Image.new("RGBA", (134, 132))
    tail = Image.new("RGBA", (62, 54), "#362120")
    tail_draw = ImageDraw.Draw(tail)
    for y in (2, 48):
        for x in range(2, 58, 11):
            tail_draw.rectangle((x, y, x + 7, y + 3), fill="#8f6a55")
    tail = tail.rotate(-12, expand=True, resample=Image.Resampling.BICUBIC)
    emblem.alpha_composite(tail, (60, 48))
    tube = Image.new("RGBA", (62, 106))
    matte(tube, gradient(tube.size, ((0, "#5e5139"), (.13, "#a78c52"), (.39, "#d5b475"),
                                    (.68, "#b69255"), (1, "#705e3c"))), (0, 0, *tube.size), 10)
    tube_draw = ImageDraw.Draw(tube)
    tube_draw.text((31, 54), "36", font=fonts["deck_count"], fill="#221c18", anchor="mm")
    for y in (2, 97):
        tube_draw.rounded_rectangle((0, y, 61, y + 6), radius=3, fill="#a09073")
    tube = tube.rotate(19, expand=True, resample=Image.Resampling.BICUBIC)
    emblem.alpha_composite(tube, (20, 0))
    image.paste(emblem, (293, 171), emblem)
    draw.line((261, 313, 460, 313), fill="#44434a")
    draw.text((261, 339), "胶卷模式", font=fonts["card"], fill=INK, anchor="lm")
    draw.text((261, 372), status, font=fonts["summary"], fill=GOLD if focused else VALUE, anchor="lm")
    draw.line(((446, 360), (451, 365), (446, 370)), fill=GOLD if focused else VALUE, width=2, joint="curve")
    draw.rounded_rectangle(closed_box(DECK["previous"]), radius=6, fill="#1d1f25")
    draw.line(((26, 279), (21, 284), (26, 289)), fill="#aeb1b3", width=2, joint="curve")
    draw.rounded_rectangle((342, 436, 348, 441), radius=3, fill="#62696b")
    draw.rounded_rectangle((366, 436, 384, 441), radius=3, fill="#e1e5e3")
    return image


def deck_focus_records(donor, fonts):
    base = roll_deck(donor, fonts, False)
    for first, slot in ((499, "about"), (503, "support")):
        card = DECK[slot]
        left, top, right, bottom = card
        variant = base.copy()
        ImageDraw.Draw(variant).rounded_rectangle(closed_box(card), radius=11, outline=GOLD, width=2)
        for index, bounds in enumerate((
                (left, top, right, top + 11), (left, bottom - 11, right, bottom),
                (left, top + 11, left + 2, bottom - 11),
                (right - 2, top + 11, right, bottom - 11))):
            yield patch(first + index, base, variant, bounds)


def effects(layout, fonts):
    rows = [row for row in EFFECTS if (row[0] != "撕纸效果" or layout & 1)
            and (row[0] != "滤镜快切" or layout & 2)]
    rows.insert(6 if layout & 1 else 5, ("Live 模式", ("联调中", *LIVE_CHOICES, "暂不可用"), 35))
    image = sheet("效果", fonts)
    draw = ImageDraw.Draw(image)
    start, height = EFFECT_ROWS
    for index, (label, values, _) in enumerate(rows):
        y = start + index * height
        draw.line((34, y + height - 1, 685, y + height - 1), fill=EDGE)
        draw.text((51, y + 23), label, fill=INK, font=fonts["effect_label"], anchor="lm")
        draw.text((644, y + 23), values[0], fill=VALUE, font=fonts["value"], anchor="rm")
        draw.line(((661, y + 17), (667, y + 23), (661, y + 29)), fill="#aab1b4", width=2, joint="curve")
    yield layout, FRAME, image

    for index, (_, values, field) in enumerate(rows):
        y = start + index * height
        for ordinal, value in enumerate(values[1:], 1):
            variant = image.copy()
            draw = ImageDraw.Draw(variant)
            draw.rectangle((390, y, 649, y + height - 2), fill=BACKGROUND)
            draw.text((644, y + 23), value, fill=VALUE, font=fonts["value"], anchor="rm")
            yield patch(64 + (layout - 4) * 48 + field + ordinal, image, variant, (390, y, 650, y + height - 1))


def patch(index, base, variant, allowed):
    box = ImageChops.difference(base.crop(allowed), variant.crop(allowed)).getbbox()
    if box is None:
        raise ValueError(f"No changed artwork at record {index}")
    x, y = allowed[:2]
    return index, (x + box[0], y + box[1], x + box[2], y + box[3]), variant


def donor_record(data, index):
    offset, checksum, x, y, width, height = unpack_from("<IIHHHH", data, 16 + ENTRY_BYTES * index)
    return (x, y, x + width, y + height), checksum, data[offset:offset + width * height * 4]


def donor_frame(data, index):
    box, _, pixels = donor_record(data, index)
    if box != FRAME:
        raise ValueError(f"Donor record {index} is not a frame")
    return Image.frombytes("RGBA", SIZE, pixels).convert("RGB")


def live_picker_records(donor, fonts):
    half = donor_frame(donor, 13)
    picker = sheet("Live 模式", fonts)
    draw = ImageDraw.Draw(picker)
    for index, label in enumerate(LIVE_CHOICES):
        list_row(draw, index, label, "", fonts, option=True)
    # The donor supplies the back button, first two radios, and footer.
    for index, box in enumerate(((83, 18, 300, 61), (50, 86, 220, 192),
                                 (50, 192, 220, 244), (650, 192, 670, 244),
                                 (34, 244, 686, 245)), 390):
        yield patch(index, half, picker, box)
    for index, choice in enumerate((1, 2, None), 395):
        status = picker.copy()
        if choice is not None:
            list_row(ImageDraw.Draw(status), choice, LIVE_CHOICES[choice], "使用中", fonts,
                     option=True)
        yield patch(index, half, status, (550, 86, 650, 244))


def roll_records(donor, fonts):
    deck = roll_deck(donor, fonts, True)
    display = roll_display(fonts)
    editable = roll_setup(fonts)
    paused = roll_setup(fonts, state="paused")
    frames = (
        roll_deck(donor, fonts, False), deck, display, editable, paused, roll_setup(fonts, state="active"),
    )
    for index, image in zip(FRAMES.values(), frames):
        yield index, FRAME, image
    for index, status in enumerate(("拍摄中", "已暂停"), 400):
        yield patch(index, deck, roll_deck(donor, fonts, True, status), (258, 360, 390, 386))
    for digit in range(1, 10):
        if digit <= 3:
            yield patch(401 + digit, display, roll_display(fonts, count=digit * 10), (308, 365, 334, 422))
        yield patch(404 + digit, display, roll_display(fonts, count=digit), (334, 365, 361, 422))
    yield patch(414, display, roll_display(fonts, capacity=24), (363, 382, 431, 424))
    for count in range(1, 37):
        yield patch(420 + count, paused, roll_setup(fonts, state="paused", count=count), (69, 308, 132, 350))
    edited_24, locked_24 = roll_setup(fonts, capacity=24), roll_setup(fonts, state="paused", capacity=24)
    yield patch(457, paused, locked_24, (137, 317, 189, 350))
    yield patch(458, editable, edited_24, (262, 130, 466, 174))
    yield patch(459, paused, locked_24, CAPACITY_LOCKED)
    for ratio in range(1, 4):
        yield patch(459 + ratio, editable, roll_setup(fonts, ratio=ratio), ASPECT)
        yield patch(462 + ratio, paused, roll_setup(fonts, state="paused", ratio=ratio), ASPECT)
    yield patch(478, editable, roll_setup(fonts, negative=True), FILMS[1])
    yield patch(479, editable, roll_setup(fonts, closed=True), (590, 18, 686, 59))
    yield patch(480, editable, roll_setup(fonts, unavailable=True), FOOTER["primary"])


def build(donor, fonts):
    if sha256(donor).hexdigest() != DONOR_SHA256:
        raise ValueError("Expected the released MNU5 MENU-R5.M10")
    records = {index: donor_record(donor, index) for index in range(384)}
    # Effects records move into a 46-pixel grid to fit Live alongside optional rows.
    for index in range(64, 256):
        records.pop(index)
    changed = {}
    changes = (rec for layout in range(4, 8) for rec in effects(layout, fonts))
    for group in (changes, roll_records(donor, fonts), deck_focus_records(donor, fonts),
                  live_picker_records(donor, fonts)):
        for index, box, image in group:
            if index in changed:
                raise ValueError(f"Duplicate menu asset record {index}")
            pixels = image.crop(box).convert("RGBA").tobytes()
            if box != FRAME and len(pixels) > MAX_PATCH_BYTES:
                raise ValueError(f"Record {index} exceeds the runtime scratch buffer: {box}")
            checksum = hash_words(pixels)
            records[index] = box, checksum, pixels
            changed[index] = {"xyxy": box, "bytes": len(pixels), "checksum": f"{checksum:08x}"}
    canisters = {}
    for index, (film_id, name, identity) in enumerate(catalog_canisters(), CANISTER_FIRST):
        box = (0, 0, *CANISTER_SIZE)
        pixels = pack_canister(canister(identity, fonts), film_id)
        checksum = hash_words(pixels)
        records[index] = box, checksum, pixels
        changed[index] = {"xyxy": box, "bytes": len(pixels), "checksum": f"{checksum:08x}"}
        canisters[film_id] = {"record": index, "name": name, "label": identity[:3]}
    directory = bytearray(RECORD_COUNT * ENTRY_BYTES)
    payload = bytearray()
    for index, (box, checksum, pixels) in sorted(records.items()):
        if not pixels:
            continue
        pack_into("<IIHHHH", directory, ENTRY_BYTES * index, HEADER_BYTES + len(payload),
                  checksum, *box[:2], *size_of(box))
        payload.extend(pixels)
    size = HEADER_BYTES + len(payload)
    if size >= 32 * 1024 * 1024:
        raise ValueError("Menu resource exceeds the runtime file size limit")
    resource = pack("<4sIII", b"MNU8", 8, RECORD_COUNT, size) + directory + payload
    manifest = {
        "format": "MNU8", "record_count": RECORD_COUNT, "bytes": size, "sha256": sha256(resource).hexdigest(),
        "donor_sha256": DONOR_SHA256, "frame_ids": FRAMES, "effect_row_y_and_height": EFFECT_ROWS,
        "hit_rects_xyxy": {
            "deck": DECK, "back": BACK, "ellipsis": ELLIPSIS, "capacity": CAPACITY,
            "aspect": ASPECT, "films": FILMS, "footer": FOOTER,
        },
        "canisters": canisters, "aspect_order": RATIOS,
        "live_picker": {"base": 13, "layout": [390, 391, 392, 393, 394],
                        "saved": [None, 395, 396], "unavailable": 397,
                        "overview_status_offsets": [36, 37, 38, 39]},
        "patches": {
            "deck_about_focused": [499, 502], "deck_support_focused": [503, 506],
            "deck_status": {"active": 400, "paused": 401}, "display_tens_1_to_3": [402, 404],
            "display_ones_1_to_9": [405, 413], "display_24": 414,
            "setup_counts_1_to_36": [421, 456], "setup_tally_24": 457, "setup_editable_24": 458,
            "setup_locked_24": 459, "setup_editable_aspects": [460, 462], "setup_locked_aspects": [463, 465],
            "setup_select_negative": 478, "setup_closed_status": 479, "setup_unavailable": 480,
        },
        "changed_records": changed,
    }
    return resource, manifest


def fonts_for(cjk_path, latin_path):
    fonts = pingfang(cjk_path)
    fonts.update({
        name: ImageFont.truetype(cjk_path, size, index=11)
        for name, size in (("meta", 16), ("option", 17), ("effect_label", 24), ("tube_small", 27))
    })
    fonts.update({
        name: ImageFont.truetype(latin_path, size, index=1)
        for name, size in (
            ("tally", 45), ("denom", 20), ("small_tally", 30), ("small_denom", 15),
            ("tube_brand", 13), ("tube_large", 44), ("tube_sub", 10), ("deck_count", 25),
        )
    })
    return fonts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("donor", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--font", type=Path, default=font_path())
    parser.add_argument("--latin-font", type=Path, default=Path("/System/Library/Fonts/Menlo.ttc"))
    args = parser.parse_args()
    resource, manifest = build(args.donor.read_bytes(), fonts_for(args.font, args.latin_font))
    args.output.write_bytes(resource)
    args.output.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
