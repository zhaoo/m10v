"""Render the textured torn-paper concept on a desktop, outside camera firmware."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy.ndimage import distance_transform_edt

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--variant", type=int, choices=range(1, len(MASK_SHAPES)+1), default=1)
    args = parser.parse_args()
    with Image.open(args.photo) as image:
        photo = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGB"), (1800, 1200))
    render(photo, args.variant-1).save(args.output, quality=96, subsampling=0)


if __name__ == "__main__":
    main()
