"""Decode, normalize and entropy-read back a fixed-capacity camera JPEG. JSON stdin/out."""
import base64, io, json, sys, warnings
from PIL import Image
Image.MAX_IMAGE_PIXELS = 40000000
warnings.simplefilter('error', Image.DecompressionBombWarning)
try:
    request = json.load(sys.stdin)
    raw = base64.b64decode(request['jpeg_base64'], validate=True)
    capacity = request['capacity']
    if capacity not in (112509, 16687, 91119, 107902): raise ValueError('unsupported capacity')
    with Image.open(io.BytesIO(raw)) as source:
        if source.format != 'JPEG' or source.size != (720, 480): raise ValueError('JPEG must be 720 x 480')
        source.load()
        image = source.convert('RGB')
    best = None
    for quality in range(95, 0, -1):
        out = io.BytesIO()
        image.save(out, 'JPEG', quality=quality, subsampling=1, progressive=False, optimize=False)
        jpeg = out.getvalue()
        if len(jpeg) <= capacity - 4:
            best = jpeg
            break
    if best is None: raise ValueError('image cannot fit fixed camera slot')
    # JPEG comments are ignored by decoders; unlike trailing padding, keep EOI at the last byte.
    left = capacity - len(best)
    comments = bytearray()
    while left:
        size = min(left, 65537)
        if 0 < left - size < 4: size -= 4
        comments += b'\xff\xfe' + (size - 2).to_bytes(2, 'big') + bytes(size - 4)
        left -= size
    padded = best[:2] + comments + best[2:]
    with Image.open(io.BytesIO(padded)) as check:
        check.load()
        if check.size != (720,480) or check.info.get('progressive'): raise ValueError('entropy readback failed')
    print(json.dumps(dict(jpeg_base64=base64.b64encode(padded).decode(), quality=quality)))
except Exception as error:
    print(str(error), file=sys.stderr)
    sys.exit(1)
