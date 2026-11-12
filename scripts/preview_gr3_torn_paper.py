"""Render the textured torn-paper concept on a desktop, outside camera firmware."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy.ndimage import binary_fill_holes, distance_transform_edt, label, shift

from scripts.build_gr3_torn_overlay import MASK_HEIGHT, MASK_SHAPES, MASK_WIDTH


def ragged_path(polygon, size, rng):
    """Displace each authored edge along its normal at three spatial scales."""
    scale = np.array([size[0] / MASK_WIDTH, size[1] / MASK_HEIGHT])
    vertices = np.asarray(polygon, dtype=float) * scale
    result = []
    for start, end in zip(vertices, np.roll(vertices, -1, axis=0)):
        tangent = end - start
        length = float(np.linalg.norm(tangent))
        normal = np.array([-tangent[1], tangent[0]]) / length
        t = np.linspace(0, 1, max(3, int(length / 1.1)), endpoint=False)
        displacement = np.zeros_like(t)
        for spacing, amplitude in ((24, 4.5), (8, 2.5), (2.7, 1.1)):
            knots = np.linspace(0, 1, max(3, round(length / spacing) + 1))
            noise = rng.normal(0, amplitude, len(knots)).clip(-2 * amplitude, 2 * amplitude)
            noise[[0, -1]] = 0
            displacement += np.interp(t, knots, noise)
        points = start + t[:, None] * tangent + displacement[:, None] * normal
        result.extend(map(tuple, points))
    return result


def texture(size, rng, scale):
    width, height = size
    noise = rng.integers(0, 256, (max(2, height // scale), max(2, width // scale)), dtype=np.uint8)
    return np.asarray(Image.fromarray(noise).resize(size, Image.Resampling.BICUBIC), dtype=float) / 255 - .5


def blend(base, color, alpha):
    return np.clip(base * (1 - alpha[..., None]) + color * alpha[..., None], 0, 255)


def render(photo, variant):
    rng = np.random.default_rng(490 + variant)
    size = photo.size
    width, height = size
    mask = Image.new("L", size)
    fibers = Image.new("L", size)
    draw, threads = ImageDraw.Draw(mask), ImageDraw.Draw(fibers)
    for polygon in MASK_SHAPES[variant]:
        path = ragged_path(polygon, size, rng)
        draw.polygon(path, fill=255)
        center = np.mean(path, axis=0)
        for index in rng.choice(len(path), len(path) // 3, replace=False):
            point = np.array(path[index])
            vector = point - center
            vector /= np.linalg.norm(vector)
            tangent = np.array([-vector[1], vector[0]])
            tip = point + vector * rng.uniform(1, 6) + tangent * rng.uniform(-3, 3)
            threads.line([tuple(point - 2 * vector), tuple(tip)],
                         fill=int(rng.integers(60, 205)), width=1)

    solid = np.asarray(mask) > 127
    distance = distance_transform_edt(solid) - distance_transform_edt(~solid)
    fine = texture(size, rng, 1)
    pulp = texture(size, rng, 5)
    clouds = texture(size, rng, 40)
    y, x = np.ogrid[:height, :width]
    light = np.sqrt(((x - .39 * width) / width)**2 + ((y - .34 * height) / height)**2)
    background = np.array([249., 247., 242.]) + (fine*2 + pulp*2 + clouds*1.8 - light*2.5)[..., None]
    shadow = Image.new("L", size)
    shadow.paste(mask, (2, 5))
    contact = np.asarray(shadow.filter(ImageFilter.GaussianBlur(2.2)), dtype=float) / 255
    cast = np.asarray(shadow.filter(ImageFilter.GaussianBlur(10)), dtype=float) / 255
    background = blend(background, np.array([68., 56., 43.]), .21*contact + .10*cast)

    fiber_alpha = np.asarray(fibers.filter(ImageFilter.GaussianBlur(.35)), dtype=float) / 255
    background = blend(background, np.array([253., 250., 242.]), fiber_alpha)
    paper = np.array([247., 242., 230.]) + (fine*22 + pulp*12 + clouds*7)[..., None]
    paper_coverage = np.asarray(mask.filter(ImageFilter.GaussianBlur(.65)), dtype=float) / 255
    result = blend(background, paper, paper_coverage)
    rim_width = 3.8 + pulp*5 + clouds*4 + fine*1.5
    printed = np.clip((distance - rim_width + .7) / 1.7, 0, 1)
    result = blend(result, np.asarray(photo, dtype=float), printed)
    return Image.fromarray(np.round(result).astype(np.uint8))


def render_cutout(photo):
    """Simulate physical paper on an existing white-backed R8 JPEG."""
    rng = np.random.default_rng(1540)
    width, height = size = photo.size
    pixels = np.asarray(photo)
    # R8 leaves a white gap between every fragment. Keep the four major
    # components and fill internal highlights so they stay part of the print.
    labels, _ = label(pixels.min(axis=2) < 238)
    counts = np.bincount(labels.ravel())
    counts[0] = 0
    pieces = [binary_fill_holes(labels == n) for n in np.argsort(counts)[-4:]]
    if any(piece.sum() < width * height * .025 for piece in pieces):
        raise ValueError("expected four separated photo fragments on white")
    solid = np.logical_or.reduce(pieces)
    inside = distance_transform_edt(solid)
    distance = inside - distance_transform_edt(~solid)
    coarse = texture(size, rng, 43)
    pulp = texture(size, rng, 9)
    fine = texture(size, rng, 3)
    grain = texture(size, rng, 1)
    # A rough physical edge may extend beyond the original cutout. Only
    # exposed paper does so; printed pixels always come from inside R8.
    tear = distance + 9 * coarse + 8 * pulp + 3.5 * fine + grain
    paper = np.clip((tear + 2.8) / 1.6, 0, 1)
    print_inset = 4.7 + 5.5 * pulp + 3.5 * coarse + 1.2 * fine
    printed = np.clip((tear - print_inset) / 1.35, 0, 1) * np.clip((inside - 2) / 1.5, 0, 1)

    y, x = np.ogrid[:height, :width]
    light = ((x - width * .34) / width)**2 + ((y - height * .28) / height)**2
    backing = np.array([247., 245., 239.]) + (
        5 * coarse + 3 * pulp + 3.5 * grain - 7 * light
    )[..., None]
    # Keep one direction of light, but vary the lift of the individual pieces.
    shadow = np.zeros_like(tear)
    for index, piece in enumerate(pieces):
        piece_alpha = paper * (distance_transform_edt(~piece) < 10)
        offset = (4 + 1.8 * index, 2 + index)
        shifted = shift(piece_alpha, offset, order=1, prefilter=False)
        shadow_image = Image.fromarray(np.uint8(np.clip(shifted * 255, 0, 255)))
        contact = np.asarray(shadow_image.filter(ImageFilter.GaussianBlur(2.4)), dtype=float) / 255
        cast = np.asarray(shadow_image.filter(ImageFilter.GaussianBlur(11)), dtype=float) / 255
        np.maximum(shadow, .20 * contact + .13 * cast, out=shadow)
    backing = blend(backing, np.array([78., 66., 53.]), shadow)

    # Individual light pulp fibers, biased along the local edge normal.
    threads = Image.new("L", size)
    draw = ImageDraw.Draw(threads)
    gy, gx = np.gradient(distance)
    edge_y, edge_x = np.where((tear > -3.5) & (tear < -1.5))
    for index in rng.choice(len(edge_x), min(len(edge_x), 3600), replace=False):
        py, px = edge_y[index], edge_x[index]
        normal = np.array([gx[py, px], gy[py, px]])
        length = np.linalg.norm(normal)
        if length < .1:
            continue
        normal /= length
        tangent = np.array([-normal[1], normal[0]])
        base = np.array([px, py], dtype=float)
        tip = base - rng.uniform(1.8, 6.0) * normal + rng.uniform(-2.2, 2.2) * tangent
        draw.line([tuple(base + normal * 2), tuple(tip)], fill=int(rng.integers(55, 185)))
    fiber = np.asarray(threads.filter(ImageFilter.GaussianBlur(.35)), dtype=float) / 255
    backing = blend(backing, np.array([255., 253., 245.]), fiber)
    core = np.array([252., 249., 239.]) + (8 * coarse + 14 * pulp + 16 * grain)[..., None]
    result = blend(backing, core, paper)
    result = blend(result, pixels, printed)
    return Image.fromarray(np.round(result).astype(np.uint8))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--variant", type=int, choices=range(1, len(MASK_SHAPES)+1), default=1)
    parser.add_argument("--from-cutout", action="store_true", help="use an existing R8 JPEG")
    args = parser.parse_args()
    with Image.open(args.photo) as image:
        source = ImageOps.exif_transpose(image).convert("RGB")
        if args.from_cutout:
            source.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            photo = source
        else:
            photo = ImageOps.fit(source, (1800, 1200))
    result = render_cutout(photo) if args.from_cutout else render(photo, args.variant-1)
    result.save(args.output, quality=96, subsampling=0)


if __name__ == "__main__":
    main()
