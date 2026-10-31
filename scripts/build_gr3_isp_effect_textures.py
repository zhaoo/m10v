#!/usr/bin/env python3
"""Generate raw experimental GR III/IIIx ISP inputs ON THE BUILD COMPUTER.

No camera code, compressed payload, source photograph, calibrated film model,
or claim of proven DMA/scaler/blend compatibility is provided here. NV12 is
two-plane Y then interleaved CbCr. Warm color is premultiplied in RGB against
black BEFORE full-range BT.601 conversion; chroma is centered on 128, not zero.
Its use in hardware blending requires a separately verified arithmetic contract.
NV12_MODULATION fields are DIFFERENT: raw scalar weights with zero-based UV,
not color. Hardware Resize carries/subsamples them; single-plane scalar loaders
must interpret them as weights, never as neutral-centered chroma/color.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zlib

import numpy as np

VERSION = 'gr3-build-textures-v4-legacy-leak'
LEGACY_LEAK_COMMIT = '0818cfeb00d92b09c89a68d1795707560343c0de'
LEGACY_LEAK_SEED = 0x5207250d
LEGACY_SPREADS = {'narrow': 1, 'medium': 4, 'wide': 8}
MAX_PIXELS = 3072 * 2048
RUNTIME_MAX_BYTES = 0xc00000
MODULATION_FORMATS = ('NV12_MODULATION_Y_CB', 'NV12_MODULATION_Y_CR')
MODULATION_MODEL = ('Scalar byte weights, not colors: Y=mask, selected Cb or Cr=rounded 2x2 mask mean, '
                    'other UV byte=0; all padding=0. No 128 chroma center. Optical/math appearance '
                    'is an uncalibrated candidate for camera acceptance.')


def _runtime_names():
    return ['grain_nv12'] + [f'leak_{position}_{spread}_{channel}_field{suffix}_nv12'
        for suffix in ('', '_vertical') for position in ('left', 'right', 'both')
        for spread in ('narrow', 'medium', 'wide') for channel in ('cb', 'cr')]


def _known_formats():
    formats = {'grain_y8': 'Y8', 'grain_nv12': 'NV12'}
    for position in ('left', 'right', 'both'):
        for spread in ('narrow', 'medium', 'wide'):
            name = f'leak_{position}_{spread}'
            for suffix, fmt in (('_mask_y8', 'Y8'), ('_target_rgb8', 'RGB8'),
                                ('_premult_nv12', 'NV12'), ('_cb_field_nv12', MODULATION_FORMATS[0]),
                                ('_cr_field_nv12', MODULATION_FORMATS[1]),
                                ('_cb_field_vertical_nv12', MODULATION_FORMATS[0]),
                                ('_cr_field_vertical_nv12', MODULATION_FORMATS[1])):
                formats[name + suffix] = fmt
    return formats


def _geometry(width, height):
    if (type(width) is not int or type(height) is not int or
            width < 2 or height < 2 or width % 2 or height % 2 or
            width * height > MAX_PIXELS):
        raise ValueError('geometry must be positive even integers, at most 6291456 pixels')


def grain_plane(width=3072, height=2048, seed=0):
    """Single density channel, clustered periodic multiscale noise, std ~18 DN.

    Periodic filtering avoids an artificial boundary in the stochastic field;
    this does not prove absence of visible repetition when a frame is reused.
    """
    _geometry(width, height)
    rng = np.random.Generator(np.random.PCG64(seed))
    noise = rng.standard_normal((height, width), dtype=np.float32)
    smooth = noise
    for _ in range(3):
        smooth = (2 * smooth + np.roll(smooth, 1, 0) + np.roll(smooth, -1, 0)) * .25
        smooth = (2 * smooth + np.roll(smooth, 1, 1) + np.roll(smooth, -1, 1)) * .25
    noise = .25 * noise + .75 * smooth / max(float(smooth.std()), 1e-6)
    noise -= noise.mean(dtype=np.float64)
    noise *= 18 / max(float(noise.std()), 1e-6)
    result = np.rint(np.clip(128 + noise, 1, 255)).astype(np.uint8)
    # Correct quantization residual on host, keeping the integer mean at 128.
    residual = int(result.astype(np.int64).sum()) - 128 * result.size
    flat = result.ravel()
    if residual:
        eligible = np.flatnonzero(flat > 1 if residual > 0 else flat < 255)
        flat[eligible[:abs(residual)]] += np.uint8(255 if residual > 0 else 1)
    return result


def _legacy_random32(x):
    x = np.asarray(x, dtype=np.uint64) & 0xffffffff
    x = ((x ^ (x >> 16)) * 0x7feb352d) & 0xffffffff
    x = ((x ^ (x >> 15)) * 0x846ca68b) & 0xffffffff
    return x ^ (x >> 16)


def leak_mask(width=256, height=128, position='left', spread='medium'):
    """Host port of pinned old leak(), gain=8; exact integer lattice/rounding.

    Gain is applied by immutable ISP curves. Both combines two old edges by
    screen union; right-edge ripple stays in original image coordinates.
    """
    _geometry(width, height)
    if position not in ('left', 'right', 'both') or spread not in LEGACY_SPREADS:
        raise ValueError('unsupported leak position or spread')
    px = (np.arange(width, dtype=np.int64) * ((256 << 16)//width)) >> 16
    py = (np.arange(height, dtype=np.int64) * ((256 << 16)//height)) >> 16
    x, y = px[None, :] >> 1, py[:, None] >> 1
    xx, yy, dx, dy = x >> 3, y >> 3, x & 7, y & 7
    def lattice(x, y):
        v = (LEGACY_LEAK_SEED ^ 0xa1734) ^ ((x.astype(np.uint64)*0x9e3779b9)&0xffffffff) ^ ((y.astype(np.uint64)*0x85ebca6b)&0xffffffff)
        return (_legacy_random32(v) & 255).astype(np.int64)-128
    ripple = (lattice(xx,yy)*(8-dx)*(8-dy)+lattice(xx+1,yy)*dx*(8-dy)+
              lattice(xx,yy+1)*(8-dx)*dy+lattice(xx+1,yy+1)*dx*dy) >> 6
    # C signed /4 truncates toward zero (Python // floors negatives).
    ripple_quarter = np.where(ripple < 0, -((-ripple)//4), ripple//4)
    index = LEGACY_SPREADS[spread];span = 24+index*24
    reciprocal = (699050,349525,233016,174762,139810,116508,99864,87381,77672)[index]
    def edge(distance):
        weight = (np.maximum(0, span-distance)*reciprocal) >> 16
        weight = (weight*weight) >> 8
        return (weight[None,:]*(192+ripple_quarter)//256).astype(np.uint8)
    left, right = edge(px), edge(255-px)
    if position == 'left':return left
    if position == 'right':return right
    return (255-((255-left.astype(np.int64))*(255-right.astype(np.int64))+127)//255).astype(np.uint8)


def _aligned_stride(row_bytes):
    return (row_bytes + 63) // 64 * 64


def _pack_y8(plane):
    height, width = plane.shape
    stride = _aligned_stride(width)
    packed = np.zeros((height, stride), dtype=np.uint8)
    packed[:, :width] = plane
    return packed.tobytes(), stride


def _pack_nv12(y, cb=None, cr=None):
    height, width = y.shape
    y_raw, stride = _pack_y8(y)
    uv = np.full((height // 2, stride), 128, dtype=np.uint8)
    if cb is not None:
        for channel, component in enumerate((cb, cr)):
            # Average 2x2 full-resolution chroma before rounding/subsampling.
            reduced = component.reshape(height//2, 2, width//2, 2).mean(axis=(1, 3))
            uv[:, channel:width:2] = np.rint(np.clip(reduced, 0, 255)).astype(np.uint8)
    return y_raw + uv.tobytes(), stride


def _pack_modulation_nv12(mask, channel):
    height, width = mask.shape
    y, stride = _pack_y8(mask)
    uv = np.zeros((height//2, stride), dtype=np.uint8)
    low = np.rint(mask.astype(np.float64).reshape(height//2, 2, width//2, 2).mean(axis=(1, 3))).astype(np.uint8)
    uv[:, channel:width:2] = low
    return y + uv.tobytes(), stride


def build_resources(prefix, width=3072, height=2048, leak_width=256, leak_height=128, seed=0):
    """Write PREFIX.json and PREFIX.raw; return their Paths.

    Manifest offsets are absolute within the uncompressed raw blob. Padding and
    row alignment are explicit; copying/loading into a DMA domain is NOT proven.
    """
    _geometry(width, height)
    _geometry(leak_width, leak_height)
    prefix = Path(prefix)
    manifest_path, blob_path = prefix.with_suffix('.json'), prefix.with_suffix('.raw')
    blob = bytearray()
    assets = []

    def append(name, raw, fmt, w, h, stride, **metadata):
        blob.extend(b'\0' * ((-len(blob)) % 64))
        metadata.setdefault('planes', [dict(offset=0, length=len(raw), stride=stride)])
        assets.append(dict(name=name, offset=len(blob), length=len(raw), format=fmt,
                           width=w, height=h, stride=stride,
                           sha256=hashlib.sha256(raw).hexdigest(),
                           crc32=f'{zlib.crc32(raw):08x}', **metadata))
        blob.extend(raw)

    grain = grain_plane(width, height, seed)
    raw, stride = _pack_y8(grain)
    append('grain_y8', raw, 'Y8', width, height, stride, planes=[dict(offset=0, length=len(raw), stride=stride)])
    raw, stride = _pack_nv12(grain)
    append('grain_nv12', raw, 'NV12', width, height, stride,
           planes=[dict(offset=0, length=stride*height, stride=stride),
                   dict(offset=stride*height, length=stride*height//2, stride=stride)])
    for position in ('left', 'right', 'both'):
        for spread in ('narrow', 'medium', 'wide'):
            name = f'leak_{position}_{spread}'
            mask = leak_mask(leak_width, leak_height, position, spread)
            raw, stride = _pack_y8(mask)
            append(name + '_mask_y8', raw, 'Y8', leak_width, leak_height, stride)
            rgb = np.empty((leak_height, leak_width, 3), dtype=np.uint8)
            rgb[:] = (255, 112, 32)
            rgb_stride = _aligned_stride(leak_width*3)
            padded = np.zeros((leak_height, rgb_stride), dtype=np.uint8)
            padded[:, :leak_width*3] = rgb.reshape(leak_height, -1)
            append(name + '_target_rgb8', padded.tobytes(), 'RGB8', leak_width, leak_height, rgb_stride)
            premult = rgb.astype(np.float64) * (mask.astype(np.float64)[:, :, None] / 255)
            r, g, b = premult.transpose(2, 0, 1)
            y = np.rint(.299*r + .587*g + .114*b).astype(np.uint8)
            cb = 128 - .168736*r - .331264*g + .5*b
            cr = 128 + .5*r - .418688*g - .081312*b
            raw, stride = _pack_nv12(y, cb, cr)
            append(name + '_premult_nv12', raw, 'NV12', leak_width, leak_height, stride,
                   planes=[dict(offset=0, length=stride*leak_height, stride=stride),
                           dict(offset=stride*leak_height, length=stride*leak_height//2, stride=stride)])
    # A separate compact pack selects the runtime-only resource set.
    for position in ('left', 'right', 'both'):
        for spread in ('narrow', 'medium', 'wide'):
            mask = leak_mask(leak_width, leak_height, position, spread)
            for index, channel in enumerate(('cb', 'cr')):
                raw, stride = _pack_modulation_nv12(mask, index)
                append(f'leak_{position}_{spread}_{channel}_field_nv12', raw, MODULATION_FORMATS[index],
                       leak_width, leak_height, stride,
                       planes=[dict(offset=0, length=stride*leak_height, stride=stride),
                               dict(offset=stride*leak_height, length=stride*leak_height//2, stride=stride)])
    # Portrait saved-orientation fields are generated on the BUILD HOST. Rotate
    # the scalar mask first, then regenerate Cb/Cr pairs: rotating an interleaved
    # NV12 UV byte array would swap channel parity and is expressly incorrect.
    for position in ('left', 'right', 'both'):
        for spread in ('narrow', 'medium', 'wide'):
            mask = np.rot90(leak_mask(leak_width, leak_height, position, spread), k=-1)
            for index, channel in enumerate(('cb', 'cr')):
                raw, stride = _pack_modulation_nv12(mask, index)
                append(f'leak_{position}_{spread}_{channel}_field_vertical_nv12', raw, MODULATION_FORMATS[index],
                       leak_height, leak_width, stride,
                       planes=[dict(offset=0, length=stride*leak_width, stride=stride),
                               dict(offset=stride*leak_width, length=stride*leak_width//2, stride=stride)])
    manifest = dict(schema=1, generator=VERSION, resource_set='experimental_full',
                    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    numpy_version=np.__version__, blob_file=blob_path.name,
                    blob_length=len(blob), blob_sha256=hashlib.sha256(blob).hexdigest(),
                    parameters=dict(width=width, height=height, leak_width=leak_width, leak_height=leak_height, seed=seed),
                    model=dict(legacy_leak_commit=LEGACY_LEAK_COMMIT,legacy_leak_seed=LEGACY_LEAK_SEED,
                               legacy_spreads=LEGACY_SPREADS,grain='PCG64 multiscale correlated single density channel; uncalibrated',
                               warm_rgb=[255, 112, 32], color='BT.601 full range, NV12 CbCr, RGB premultiplied against black',
                               modulation=MODULATION_MODEL,
                               runtime='raw uncompressed host-generated experimental inputs; no hardware compatibility claim'), assets=assets)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(blob)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest_path, blob_path


def pack_runtime_resources(manifest_path, output_prefix):
    """Pack exactly grain NV12 +36 horizontal/vertical selective fields, raw/64-aligned, <=12MiB.

    Source manifest/blob hashes bind provenance. Resource bytes, layouts and
    identities are preserved; only blob offsets change. No DMA claim is made.
    """
    manifest_path, output_prefix = Path(manifest_path), Path(output_prefix)
    source = verify_resources(manifest_path)
    source_manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    source_blob = (manifest_path.parent / source['blob_file']).read_bytes()
    originals = {a['name']: a for a in source['assets']}
    blob, assets = bytearray(), []
    for name in _runtime_names():
        if name not in originals:
            raise ValueError('missing required runtime resource: ' + name)
        asset = dict(originals[name])
        raw = source_blob[asset['offset']:asset['offset']+asset['length']]
        blob.extend(bytes((-len(blob)) % 64))
        asset['offset'] = len(blob)
        assets.append(asset)
        blob.extend(raw)
    if len(blob) > RUNTIME_MAX_BYTES:
        raise ValueError('runtime resource blob exceeds fixed 12MiB budget')
    packed_path, blob_path = output_prefix.with_suffix('.json'), output_prefix.with_suffix('.raw')
    if packed_path.resolve() == manifest_path.resolve() or blob_path.resolve() == (manifest_path.parent/source['blob_file']).resolve():
        raise ValueError('runtime output must not overwrite its source')
    manifest = dict(schema=1, generator=VERSION, resource_set='runtime_modulation',
                    source_manifest_sha256=source_manifest_sha256, source_blob_sha256=source['blob_sha256'],
                    source_sha256=source['source_sha256'], numpy_version=source.get('numpy_version'),
                    packer_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    blob_file=blob_path.name, blob_length=len(blob), blob_sha256=hashlib.sha256(blob).hexdigest(),
                    parameters=source['parameters'], model=source['model'], assets=assets)
    packed_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(blob)
    packed_path.write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    verify_resources(packed_path)
    return packed_path, blob_path


def verify_resources(manifest_path):
    """Reject corrupt bytes, range/geometry mistakes, or per-resource checksums."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    blob_file = manifest['blob_file']
    if Path(blob_file).name != blob_file:
        raise ValueError('blob_file must be a sibling filename')
    blob = (manifest_path.parent / blob_file).read_bytes()
    if len(blob) != manifest['blob_length'] or hashlib.sha256(blob).hexdigest() != manifest['blob_sha256']:
        raise ValueError('blob length/hash mismatch')
    previous_end = 0
    names = set()
    known = _known_formats()
    for asset in manifest['assets']:
        name, fmt = asset['name'], asset['format']
        if name in names or known.get(name) != fmt:
            raise ValueError('invalid asset name/format or duplicate resource')
        names.add(name)
        _geometry(asset['width'], asset['height'])
        offset, length, stride = asset['offset'], asset['length'], asset['stride']
        channels = 3 if asset['format'] == 'RGB8' else 1
        expected = stride * asset['height']
        if fmt == 'NV12' or fmt in MODULATION_FORMATS:
            expected = expected * 3 // 2
        if (fmt not in ('Y8', 'RGB8', 'NV12', *MODULATION_FORMATS) or offset < previous_end or
                offset % 64 or stride % 64 or stride < asset['width']*channels or
                length != expected or offset + length > len(blob)):
            raise ValueError('invalid asset geometry/range/format')
        expected_planes = [dict(offset=0, length=stride*asset['height'], stride=stride)]
        if fmt == 'NV12' or fmt in MODULATION_FORMATS:
            expected_planes.append(dict(offset=stride*asset['height'], length=stride*asset['height']//2, stride=stride))
        if asset.get('planes') != expected_planes:
            raise ValueError('invalid asset plane layout')
        raw = blob[offset:offset+length]
        if hashlib.sha256(raw).hexdigest() != asset['sha256'] or f'{zlib.crc32(raw):08x}' != asset['crc32']:
            raise ValueError('asset hash/checksum mismatch')
        if fmt in MODULATION_FORMATS:
            height, width = asset['height'], asset['width']
            y = np.frombuffer(raw[:stride*height], dtype=np.uint8).reshape(height, stride)
            uv = np.frombuffer(raw[stride*height:], dtype=np.uint8).reshape(height//2, stride)
            channel = MODULATION_FORMATS.index(fmt)
            expected = np.rint(y[:, :width].astype(np.float64).reshape(height//2, 2, width//2, 2).mean(axis=(1, 3))).astype(np.uint8)
            if (y[:, width:].any() or uv[:, width:].any() or uv[:, 1-channel:width:2].any() or
                    not np.array_equal(uv[:, channel:width:2], expected)):
                raise ValueError('invalid selective modulation weights')
        previous_end = offset + length
    resource_set = manifest.get('resource_set')
    if resource_set == 'runtime_modulation' and (names != set(_runtime_names()) or len(blob) > RUNTIME_MAX_BYTES):
        raise ValueError('invalid runtime resource set/budget')
    if resource_set == 'experimental_full' and names != set(known):
        raise ValueError('incomplete experimental resource set')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('builds/gr3-isp-textures/effects'))
    parser.add_argument('--width', type=int, default=3072)
    parser.add_argument('--height', type=int, default=2048)
    parser.add_argument('--leak-width', type=int, default=256)
    parser.add_argument('--leak-height', type=int, default=128)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--pack-runtime', type=Path, help='source manifest to pack runtime-only assets; use --output for destination')
    args = parser.parse_args()
    if args.pack_runtime:
        manifest, blob = pack_runtime_resources(args.pack_runtime, args.output)
        print(f'{manifest}\n{blob}')
    elif args.verify:
        verify_resources(args.verify)
        print(f'Verified {args.verify}')
    else:
        manifest, blob = build_resources(args.output, args.width, args.height, args.leak_width, args.leak_height, args.seed)
        verify_resources(manifest)
        print(f'{manifest}\n{blob}')


if __name__ == '__main__':
    main()
