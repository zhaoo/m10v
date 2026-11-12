"""Render the textured torn-paper concept on a desktop, outside camera firmware."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy.ndimage import binary_fill_holes, distance_transform_edt, gaussian_filter, label, shift

R8_MASK_WIDTH,R8_MASK_HEIGHT=64,80
# Jagged paper fragments in normalized frame coordinates. Gaps are painted
# white by the blend; the polygons preserve the underlying scene.
R8_MASK_SHAPES=(
 (((7,23),(11,18),(24,15),(33,12),(41,13),(40,21),(43,26),(36,30),(33,35),
   (24,34),(19,38),(14,34),(10,32)),
  ((45,13),(50,15),(56,20),(58,28),(55,35),(51,38),(44,36),(38,35),(40,32),
   (47,27),(43,21)),
  ((9,36),(14,38),(18,43),(25,40),(32,40),(36,47),(35,53),(29,55),(29,64),
   (25,68),(18,64),(14,64),(12,57),(9,54),(10,47),(7,44)),
  ((35,39),(43,39),(49,42),(57,38),(58,46),(54,52),(55,58),(48,63),(44,68),
   (36,69),(29,67),(33,61),(33,57),(39,54),(40,47))),
 (((9,19),(16,15),(23,16),(30,13),(37,17),(34,22),(38,27),(32,32),(24,30),
   (20,34),(13,31),(11,25)),
  ((41,17),(51,17),(56,22),(54,27),(58,33),(56,39),(50,43),(44,42),(39,38),
   (33,36),(41,30),(42,26),(39,23)),
  ((12,35),(20,39),(24,35),(30,37),(34,42),(35,48),(31,53),(25,54),(24,61),
   (19,66),(14,61),(12,57),(8,51),(10,44)),
  ((40,43),(46,46),(52,46),(54,50),(51,56),(53,61),(46,65),(42,69),(33,66),
   (28,63),(29,57),(36,55),(39,50))),
 (((12,18),(20,14),(28,15),(32,20),(39,21),(41,28),(37,33),(32,33),(25,31),
   (20,37),(13,35),(10,30),(11,25),(8,23)),
  ((34,14),(42,12),(48,15),(54,15),(57,22),(55,29),(58,34),(55,39),(47,39),
   (40,37),(45,28),(42,20),(35,18)),
  ((10,38),(18,41),(23,40),(26,35),(34,37),(37,44),(36,50),(30,53),(27,58),
   (28,64),(23,67),(18,64),(15,58),(10,56),(8,50)),
  ((40,40),(47,43),(54,42),(57,47),(55,53),(57,58),(50,62),(47,67),(40,66),
   (32,69),(31,62),(32,56),(39,52),(42,47))),
)


def ragged_path(polygon, size, rng):
    """Displace each authored edge along its normal at three spatial scales."""
    scale = np.array([size[0] / R8_MASK_WIDTH, size[1] / R8_MASK_HEIGHT])
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
    for polygon in R8_MASK_SHAPES[variant]:
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
    # Cut a few deep, tapered tears into each piece. Keep their placement
    # irregular and their axes oblique to the original outline.
    tears = Image.new("L", size)
    cuts = ImageDraw.Draw(tears)
    gy, gx = np.gradient(gaussian_filter(distance, 2))
    for piece in pieces:
        edge_y, edge_x = np.where(piece & (inside < 1.5))
        centers = []
        for index in rng.permutation(len(edge_x)):
            y0, x0 = edge_y[index], edge_x[index]
            center = np.array([x0, y0], dtype=float)
            if any(np.linalg.norm(center - other) < 130 for other in centers):
                continue
            normal = np.array([gx[y0, x0], gy[y0, x0]])
            length = np.linalg.norm(normal)
            if length < .5:
                continue
            normal /= length
            tangent = np.array([-normal[1], normal[0]])
            depth = rng.uniform(29, 66)
            drift = rng.uniform(-24, 24)
            tip = center + normal * depth + tangent * drift
            tx, ty = np.round(tip).astype(int)
            if not (0 <= tx < width and 0 <= ty < height and piece[ty, tx]):
                continue
            left, right = rng.uniform(9, 25, 2)
            vertices = [
                center - 24*normal - left*tangent,
                center + .24*depth*normal - .65*left*tangent,
                center + .53*depth*normal + (.40*drift - 5)*tangent,
                tip,
                center + .60*depth*normal + (.61*drift + 6)*tangent,
                center + .18*depth*normal + .60*right*tangent,
                center - 24*normal + right*tangent,
            ]
            cuts.polygon(list(map(tuple, vertices)), fill=255)
            centers.append(center)
            if len(centers) == 4:
                break
    torn = np.asarray(tears) > 127
    distance = np.minimum(distance, distance_transform_edt(~torn) - distance_transform_edt(torn))
    long_tear = texture(size, rng, 100)
    coarse = texture(size, rng, 43)
    pulp = texture(size, rng, 9)
    fine = texture(size, rng, 3)
    grain = texture(size, rng, 1)
    # A rough physical edge may extend beyond the original cutout. Only
    # exposed paper does so; printed pixels always come from inside R8.
    tear = distance + 29 * long_tear + 28 * coarse + 15 * pulp + 6 * fine + 1.8 * grain
    paper = np.clip((tear + 2.8) / 1.6, 0, 1)
    print_inset = np.clip(10 + 18 * pulp + 19 * coarse + 9 * long_tear + 2.5 * fine, 3, 29)
    printed = np.clip((tear - print_inset) / 1.35, 0, 1) * np.clip((inside - 3) / 1.5, 0, 1)

    y, x = np.ogrid[:height, :width]
    light = ((x - width * .34) / width)**2 + ((y - height * .28) / height)**2
    backing = np.array([247., 245., 239.]) + (
        5 * coarse + 3 * pulp + 3.5 * grain - 7 * light
    )[..., None]
    # Keep one direction of light, but vary the lift of the individual pieces.
    shadow = np.zeros_like(tear)
    for index, piece in enumerate(pieces):
        piece_alpha = paper * (distance_transform_edt(~piece) < 40)
        offset = (7 + 2.3 * index, 3.5 + 1.3 * index)
        shifted = shift(piece_alpha, offset, order=1, prefilter=False)
        shadow_image = Image.fromarray(np.uint8(np.clip(shifted * 255, 0, 255)))
        contact = np.asarray(shadow_image.filter(ImageFilter.GaussianBlur(2.4)), dtype=float) / 255
        cast = np.asarray(shadow_image.filter(ImageFilter.GaussianBlur(11)), dtype=float) / 255
        np.maximum(shadow, .23 * contact + .13 * cast, out=shadow)
    backing = blend(backing, np.array([78., 66., 53.]), shadow)

    # Individual light pulp fibers, biased along the local edge normal.
    threads = Image.new("L", size)
    draw = ImageDraw.Draw(threads)
    gy, gx = np.gradient(distance)
    edge_y, edge_x = np.where((tear > -3.5) & (tear < -1.5))
    for index in rng.choice(len(edge_x), min(len(edge_x), 6300), replace=False):
        py, px = edge_y[index], edge_x[index]
        normal = np.array([gx[py, px], gy[py, px]])
        length = np.linalg.norm(normal)
        if length < .1:
            continue
        normal /= length
        tangent = np.array([-normal[1], normal[0]])
        base = np.array([px, py], dtype=float)
        tip = base - rng.uniform(2.5, 11.0) * normal + rng.uniform(-4.0, 4.0) * tangent
        draw.line([tuple(base + normal * 2), tuple(tip)], fill=int(rng.integers(55, 185)))
    fiber = np.asarray(threads.filter(ImageFilter.GaussianBlur(.35)), dtype=float) / 255
    backing = blend(backing, np.array([255., 253., 245.]), fiber)
    core = np.array([251., 247., 233.]) + (
        7 * long_tear + 10 * coarse + 23 * pulp + 14 * fine + 19 * grain
    )[..., None]
    result = blend(backing, core, paper)
    result = blend(result, pixels, printed)
    return Image.fromarray(np.round(result).astype(np.uint8))


def render_center_tear(photo):
    """Split one print along a shared tear and pull the two halves apart."""
    rng = np.random.default_rng(801)
    w, h = photo.size
    rows = np.arange(h)
    # One fracture shared by both pieces, with a few larger changes of
    # direction and shorter irregular fibers along the same contour.
    turns = [0, -17, 14, -11, -26, 27, 44, 18, -31, -44, 7, 31, 11, -18, 0]
    seam = w * .49 + np.interp(rows, np.linspace(0, h-1, len(turns)), turns)
    for step, amplitude in ((34, 7.0), (9, 3.1), (2, 1.25)):
        knots = np.arange(0, h + step, step)
        seam += np.interp(rows, knots, rng.normal(0, amplitude, len(knots)))
    distance = seam[:, None] - np.arange(w)[None, :]
    fibers = texture(photo.size, rng, 3)
    pulp = texture(photo.size, rng, 10)
    grain = texture(photo.size, rng, 1)
    surface = np.array([247., 242., 226.]) + (22*pulp + 14*fibers + 10*grain)[..., None]
    pixels = np.asarray(photo)
    frame = (w+300, h+238)
    layers = []
    for side, offset, angle in ((1, (-30, -5), .65), (-1, (30, 10), -.9)):
        inside = side * distance
        coverage = np.clip((inside + .55) / 1.1, 0, 1)
        lip = np.clip(7 + 13*pulp + 6*fibers + 2.5*side*np.sin(rows[:, None]/26), 2.5, 16)
        print_alpha = np.clip((inside - lip) / 1.2, 0, 1)
        paper = Image.fromarray(np.uint8(np.round(blend(surface, pixels, print_alpha))))
        alpha = Image.fromarray(np.uint8(np.round(coverage*255)))
        # A few broken fibers protrude from each side of the same tear.
        thread = Image.new("L", photo.size)
        draw = ImageDraw.Draw(thread)
        for y in rng.choice(rows[5:-5], size=h//2, replace=False):
            x = seam[y]
            draw.line([(x+side*2, y),
                       (x-side*rng.uniform(1, 5.6), y+rng.uniform(-3, 3))],
                      fill=int(rng.integers(65, 192)))
        fiber_layer = Image.new("RGBA", photo.size, (249, 244, 228, 0))
        fiber_layer.putalpha(thread)
        paper.putalpha(alpha)
        piece = Image.new("RGBA", frame)
        xy = (150+offset[0], 110+offset[1])
        piece.alpha_composite(fiber_layer, xy)
        piece.alpha_composite(paper, xy)
        layers.append(piece.rotate(angle, resample=Image.Resampling.BICUBIC))
    bg = np.array([239., 235., 224.]) + (
        4 * texture(frame, rng, 49) + 3 * texture(frame, rng, 1)
    )[..., None]
    for piece in layers:
        lifted = Image.new("L", frame)
        lifted.paste(piece.getchannel("A"), (4, 10))
        contact = np.asarray(lifted.filter(ImageFilter.GaussianBlur(2.7)), dtype=float) / 255
        cast = np.asarray(lifted.filter(ImageFilter.GaussianBlur(11)), dtype=float) / 255
        bg = blend(bg, np.array([70., 58., 46.]), .22*contact + .15*cast)
    output = Image.fromarray(np.uint8(np.round(bg))).convert("RGBA")
    for piece in layers:
        output.alpha_composite(piece)
    return output.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--variant", type=int, choices=range(1, len(R8_MASK_SHAPES)+1), default=1)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--from-cutout", action="store_true", help="use an existing R8 JPEG")
    mode.add_argument("--center-tear", action="store_true", help="split a complete photo into two pieces")
    args = parser.parse_args()
    with Image.open(args.photo) as image:
        source = ImageOps.exif_transpose(image).convert("RGB")
        if args.from_cutout:
            source.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            photo = source
        elif args.center_tear:
            photo = ImageOps.fit(source, (1560, 1040))
        else:
            photo = ImageOps.fit(source, (1800, 1200))
    if args.center_tear:
        result = render_center_tear(photo)
    elif args.from_cutout:
        result = render_cutout(photo)
    else:
        result = render(photo, args.variant-1)
    result.save(args.output, quality=96, subsampling=0)


if __name__ == "__main__":
    main()
