"""Pack the approved GR III RGB frames and tight, lossless status patches."""
import argparse
import json
from pathlib import Path
from struct import pack

from PIL import Image, ImageChops

RECORD_COUNT = 384
ENTRY_BYTES = 16
HEADER_BYTES = 16 + RECORD_COUNT * ENTRY_BYTES
MAX_PATCH_BYTES = 48 * 1024


def base_id(record):
    if record < 13:
        return record
    if record < 64:
        return (record - 16) // 11
    if record < 256:
        return 4 + (record - 64) // 48
    return 8 + (record - 256) // 64


def hash_words(data):
    value = 2166136261
    for red, green, blue, alpha in zip(data[0::4], data[1::4], data[2::4], data[3::4]):
        pixel = red | green << 8 | blue << 16 | alpha << 24
        value = ((value ^ pixel) * 16777619) & 0xffffffff
    return value


def value_box(index, layout):
    if index < 256:
        field = ((index - 64) % 48) // 8
        row = [0, 1, 2, 3, 4, 6][field]
        if row == 6 and not layout & 1:
            row -= 1
    else:
        field = (index - 256) % 64
        row = 0 if field < 8 else 1 if field < 16 else 2 if field < 24 else 5 if field < 49 else 4
        if row > 1 and layout == 8:
            row -= 1
    y = 86 + row * 53
    return 390, y, 674, y + 53


def build(source, output):
    catalog = {}
    directory = bytearray(RECORD_COUNT * ENTRY_BYTES)
    payload = bytearray()
    frames = {}
    for index in range(13):
        frames[index] = Image.open(source / f"{index}.png").convert("RGB")
    for file in sorted(source.glob("*.png"), key=lambda p: int(p.stem)):
        index = int(file.stem)
        if not 0 <= index < RECORD_COUNT:
            raise ValueError("Menu record outside directory")
        image = Image.open(file).convert("RGB")
        if image.size != (720, 480):
            raise ValueError(f"Wrong frame size: {file}")
        if index < 13:
            box = (0, 0, 720, 480)
        elif index < 64:
            # Chrome may dither recomposited blurred card shadows. Take
            # the counter strip from the variant and preserve all base art.
            box = (260, 360, 370, 386)
        else:
            background = frames[base_id(index)]
            x0, y0, x1, y1 = value_box(index, base_id(index))
            cut = (x0, y0, x1, y1)
            box = ImageChops.difference(background.crop(cut), image.crop(cut)).getbbox()
            if box is None:
                raise ValueError(f"Missing changed value at record {index}")
            box = (x0+box[0], y0+box[1], x0+box[2], y0+box[3])
        raw = image.crop(box).convert("RGBA").tobytes()
        x, y, right, bottom = box
        if index >= 13 and len(raw) > MAX_PATCH_BYTES:
            raise ValueError(f"Status patch touched unrelated pixels: {index} {box}")
        offset = HEADER_BYTES + len(payload)
        checksum = hash_words(raw)
        directory[index*ENTRY_BYTES:(index+1)*ENTRY_BYTES] = pack(
            "<IIHHHH", offset, checksum, x, y, right-x, bottom-y)
        payload += raw
        catalog[index] = dict(base=base_id(index), rect=box, checksum=f"{checksum:08x}")
    output.write_bytes(pack("<4sIII", b"MNU4", 4, RECORD_COUNT, HEADER_BYTES + len(payload)) +
                       directory + payload)
    output.with_suffix(".json").write_text(json.dumps(catalog, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.output)
